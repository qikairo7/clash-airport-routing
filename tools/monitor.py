import copy
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import time

import psutil
import yaml

from controller import Controller
from policy import byte_amount, counter_segment, new_ledger, update_ledger, utc

ROOT = Path(__file__).resolve().parents[1]


def now():
    return datetime.now(timezone.utc).isoformat()


def read_yaml(path):
    try:
        with Path(path).open(encoding="utf-8-sig") as stream:
            value = yaml.load(stream, Loader=getattr(yaml, "CSafeLoader", yaml.SafeLoader)) or {}
    except yaml.YAMLError:
        raise ValueError("本机 YAML 格式无效；原文不会输出到日志") from None
    if not isinstance(value, dict):
        raise ValueError("YAML 顶层必须为对象")
    return value


def resolve(base, value):
    return (base / value).resolve()


def state_digest(state):
    payload = {key: value for key, value in state.items() if key != "checksum"}
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def save(path, state):
    if state.get("version", 1) >= 2:
        state["checksum"] = state_digest(state)
    pending = path.with_suffix(".pending.json")
    pending.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    if path.exists():
        path.with_suffix(".previous.json").write_bytes(path.read_bytes())
    pending.replace(path)


class Monitor:
    def __init__(self, path):
        self.path = Path(path).resolve()
        if (ROOT / "local").resolve() not in self.path.parents:
            raise ValueError("监测设置必须位于本项目被忽略的 local/ 内")
        self.settings = read_yaml(self.path)
        self.runtime = self.settings["runtime"]
        self.api = Controller(self.runtime.get("controller_url"), self.runtime.get("controller_pipe"),
                              self.runtime.get("secret_env", "MIHOMO_SECRET"))
        self.home = resolve(self.path.parent, self.runtime["home"])
        self.live_config = resolve(self.path.parent, self.runtime["config"])
        if self.home not in self.live_config.parents:
            raise ValueError("运行配置必须位于声明的 Mihomo 工作目录内")
        self.state_path = self.path.with_name("policy-state.json")

    @contextmanager
    def exclusive(self):
        with self.state_path.with_suffix(".lock").open("a+b") as stream:
            stream.seek(0)
            stream.write(b"0")
            stream.flush()
            stream.seek(0)
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            try:
                yield
            finally:
                stream.seek(0)
                if os.name == "nt":
                    msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(stream.fileno(), fcntl.LOCK_UN)

    def load(self):
        state = json.loads(self.state_path.read_text(encoding="utf-8-sig"))
        if state.get("version", 1) >= 2 and state.get("checksum") != state_digest(state):
            raise RuntimeError("台账校验失败；保留现有文件，不能重新初始化清零")
        return state

    def identity(self):
        matches = []
        core_name = Path(self.runtime["core"]).name.lower()
        for process in psutil.process_iter(["name", "pid", "create_time", "cmdline"]):
            try:
                info = process.info
                arguments = info["cmdline"] or []
                if not info["name"] or info["name"].lower() != core_name or "-f" not in arguments:
                    continue
                index = arguments.index("-f") + 1
                if index < len(arguments):
                    argument = Path(arguments[index])
                    if argument.is_absolute() and argument.resolve() == self.live_config:
                        matches.append([info["pid"], info["create_time"]])
            except (psutil.AccessDenied, psutil.NoSuchProcess):
                continue
        if len(matches) != 1:
            raise RuntimeError("无法唯一确认内核身份；需要绝对路径的 -f")
        return matches[0]

    def billing(self, snapshot):
        result = {}
        for source, budget in self.settings.get("budgets", {}).items():
            age = (datetime.now(timezone.utc) - utc(budget["observed_at"])).total_seconds()
            if source not in self.settings["sources"] or not 0 <= age <= 3600:
                raise ValueError("预算来源无效或账单记录超过一小时 / 位于未来")
            ledger = new_ledger(byte_amount(budget["used"], budget["unit"]), byte_amount(budget["total"], budget["unit"]),
                                byte_amount(budget["threshold"], budget["unit"]), snapshot)
            ledger["billing_observed_at"] = utc(budget["observed_at"]).isoformat()
            result[source] = ledger
        if not result:
            raise ValueError("至少配置一个已核验的订阅预算")
        return result

    def initialize(self):
        if self.state_path.exists():
            raise ValueError("已有台账，禁止重新初始化清零")
        snapshot = self.api.request("GET", "/connections")
        state = {"version": 2, "budgets": self.billing(snapshot), "health": {}, "preferences": {},
                 "core_identity": self.identity(), "created_at": now(), "last_reload": None, "error": None}
        self.checkpoint(state, snapshot)
        save(self.state_path, state)

    def checkpoint(self, state, snapshot):
        counter = snapshot["downloadTotal"] + snapshot["uploadTotal"]
        state.setdefault("checkpoints", []).append({"at": now(), "counter": counter, "core_identity": state["core_identity"]})
        cutoff = datetime.now(timezone.utc).timestamp() - 86400
        state["checkpoints"] = [row for row in state["checkpoints"] if utc(row["at"]).timestamp() >= cutoff]

    def account(self, state):
        snapshot = self.api.request("GET", "/connections")
        identity = self.identity()
        if identity != state["core_identity"]:
            for ledger in state["budgets"].values():
                ledger.update(blocked=True, blocked_reason="core_restart_requires_new_billing_baseline")
        for source, ledger in state["budgets"].items():
            multipliers = {node["alias"]: node["multiplier"] for node in self.settings["nodes"] if node["source"] == source}
            ledger["max_multiplier"] = max(ledger.get("max_multiplier", 0), max(multipliers.values()))
            multipliers["__unattributed_maximum__"] = ledger["max_multiplier"]
            state["budgets"][source] = update_ledger(ledger, snapshot, multipliers)
        if identity == state["core_identity"]:
            self.checkpoint(state, snapshot)
        save(self.state_path, state)
        return snapshot

    def migrate(self):
        if self.state_path.exists():
            raise ValueError("已有新台账，禁止重复迁移")
        legacy = resolve(self.path.parent, self.runtime["legacy_state"])
        state = json.loads(legacy.read_text(encoding="utf-8"))
        before = copy.deepcopy(state["budgets"])
        state.update(version=2, migrated_at=now(), error=None, last_reload=state.get("last_applied_at"))
        state["migration_source"] = str(legacy)
        state["migration_baseline"] = {source: {key: ledger[key] for key in ("baseline_bytes", "upper_bound_bytes", "blocked")}
                                       for source, ledger in before.items()}
        if state["budgets"] != before:
            raise RuntimeError("迁移意外改变台账")
        save(self.state_path, state)

    def calibration_bridge(self, state, snapshot, identity, source, observed):
        multipliers = [node["multiplier"] for node in self.settings["nodes"] if node["source"] == source]
        multipliers.append(state["budgets"][source].get("max_multiplier", 0))
        if not multipliers:
            raise ValueError("缺少账单来源的完整倍率")
        counter = snapshot["downloadTotal"] + snapshot["uploadTotal"]
        checkpoints = [row for row in state.get("checkpoints", [])
                       if utc(row["at"]) <= observed and row["core_identity"] == identity]
        if checkpoints:
            difference = counter - checkpoints[-1]["counter"]
            if difference < 0:
                raise ValueError("账单衔接计数减少，不能解除保护")
            return difference * max(multipliers), "counter_checkpoint_before_local_refresh"
        if identity == state["core_identity"] and utc(state.get("initialized_at", state.get("created_at"))) <= observed:
            return state["budgets"][source]["upper_bound_bytes"], "legacy_conservative_overlap"
        if identity != state["core_identity"] and observed.timestamp() >= identity[1]:
            return counter * max(multipliers), "fresh_bill_after_uncontrolled_restart_with_full_new_segment_overlap"
        raise ValueError("没有可信的刷新前计数衔接点，保留保护锁")

    def refresh_billing(self, confirm_cycle=False):
        state = self.load()
        snapshot = self.account(state)
        budgets = self.billing(snapshot)
        if set(budgets) != set(state["budgets"]):
            raise ValueError("刷新账单不能增删既有预算来源")
        for source, ledger in budgets.items():
            previous = state["budgets"][source].get("billing_observed_at")
            if previous and utc(ledger["billing_observed_at"]) <= utc(previous):
                raise ValueError("需要比旧基线更新的账单记录")
            if ledger["baseline_bytes"] < state["budgets"][source]["baseline_bytes"] and not confirm_cycle:
                raise ValueError("账单用量下降，需要明确确认新账期")
            observed = utc(ledger["billing_observed_at"])
            if observed.timestamp() < self.identity()[1]:
                raise ValueError("新账单时间早于当前内核启动")
            bridge, method = self.calibration_bridge(state, snapshot, self.identity(), source, observed)
            ledger.update(carry_bytes=bridge, upper_bound_bytes=bridge, billing_bridge_method=method)
            if ledger["baseline_bytes"] + bridge >= ledger["threshold_bytes"]:
                ledger.update(blocked=True, blocked_reason="conservative_budget_threshold")
        state.setdefault("billing_history", []).append({"at": now(), "budgets": copy.deepcopy(state["budgets"]),
                                                        "core_identity": state["core_identity"]})
        state.update(budgets=budgets, core_identity=self.identity(), error=None, billing_refreshed_at=now())
        save(self.state_path, state)

    def import_local_billing(self, confirm_cycle=False):
        state = self.load()
        snapshot = self.account(state)
        identity = self.identity()
        registry = read_yaml(resolve(self.path.parent, self.runtime["registry"]))
        additions = {}
        for source, uid in self.runtime["billing_profiles"].items():
            entry = next(row for row in registry["items"] if row["uid"] == uid)
            values = entry["extra"]
            observed = datetime.fromtimestamp(entry["updated"], timezone.utc)
            if observed.timestamp() > datetime.now(timezone.utc).timestamp() or observed.timestamp() < identity[1]:
                raise ValueError("本机账单时间无效或早于当前内核启动，不能解除未知流量保护")
            old = state["budgets"][source]
            version = hashlib.sha256(json.dumps({"updated": entry["updated"], **values}, sort_keys=True).encode()).hexdigest()
            if old.get("billing_version") == version:
                continue
            previous = old.get("billing_observed_at")
            if previous and observed <= utc(previous):
                raise ValueError("本机订阅记录不是更新版本")
            used = byte_amount(values["upload"], "B") + byte_amount(values["download"], "B")
            total = byte_amount(values["total"], "B")
            if used < old["baseline_bytes"] and not confirm_cycle:
                raise ValueError("账单用量下降，需要明确确认新账期")
            bridge, method = self.calibration_bridge(state, snapshot, identity, source, observed)
            budget = self.settings["budgets"][source]
            ledger = new_ledger(used, total, byte_amount(budget["threshold"], budget["unit"]), snapshot)
            ledger.update(carry_bytes=bridge, upper_bound_bytes=bridge, billing_observed_at=observed.isoformat(),
                          billing_version=version, billing_bridge_method=method,
                          max_multiplier=old.get("max_multiplier", 0),
                          warning_bytes=byte_amount(budget.get("warning", budget["threshold"]), budget["unit"]))
            if used + bridge >= ledger["threshold_bytes"]:
                ledger.update(blocked=True, blocked_reason="conservative_budget_threshold")
            additions[source] = ledger
        if not additions:
            return {"changed": False, "reason": "本机账单版本已经导入"}
        state.setdefault("billing_history", []).append({"at": now(), "reason": "explicit_local_billing_import",
                                                        "budgets": copy.deepcopy(state["budgets"]),
                                                        "core_identity": state["core_identity"]})
        state["budgets"].update(additions)
        state.update(core_identity=identity, billing_refreshed_at=now(), error=None)
        save(self.state_path, state)
        return {"changed": True, "sources": list(additions)}

    def recover_ledger(self):
        previous = self.state_path.with_suffix(".previous.json")
        state = json.loads(previous.read_text(encoding="utf-8"))
        if state.get("version", 1) < 2 or state.get("checksum") != state_digest(state):
            raise RuntimeError("前一版台账也不可信，拒绝恢复或初始化")
        # 先保存损坏版本和可信副本，再使用真实连续计数保守补算。
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        self.state_path.with_name("damaged-state-" + stamp + ".json").write_bytes(self.state_path.read_bytes())
        self.state_path.with_name("recovery-checkpoint-" + stamp + ".json").write_bytes(previous.read_bytes())
        self.account(state)
        state["recovered_at"] = now()
        save(self.state_path, state)

    def status(self):
        state = self.load()
        fields = {"baseline_bytes", "total_bytes", "threshold_bytes", "upper_bound_bytes", "blocked", "blocked_reason",
                  "billing_observed_at", "warning_bytes", "billing_bridge_method"}
        age = (datetime.now(timezone.utc) - utc(state.get("updated_at", state.get("created_at", state.get("initialized_at"))))).total_seconds()
        return {"updated_at": state.get("updated_at"), "heartbeat_recent": age < 90,
                "mode": self.api.request("GET", "/configs")["mode"],
                "last_reload": state.get("last_reload"), "reload_deferred": state.get("reload_deferred", False),
                "pending_reason": state.get("pending_reason"), "error": state.get("error"),
                "openai_common_exit": state.get("openai_common_exit"), "renewal_error": state.get("renewal_error"),
                "services": state.get("service_status", {}), "alerts": state.get("alerts", []),
                "budgets": {source: {key: value for key, value in ledger.items() if key in fields}
                            for source, ledger in state["budgets"].items()}}

    def finish(self, state):
        state.update(updated_at=now(), error=None)
        state["alerts"] = []
        for source, ledger in state["budgets"].items():
            if ledger["baseline_bytes"] + ledger["upper_bound_bytes"] >= ledger.get("warning_bytes", ledger["threshold_bytes"]):
                state["alerts"].append({"source": source, "reason": "budget_warning_or_lock"})
            if ledger.get("billing_observed_at") and (datetime.now(timezone.utc) - utc(ledger["billing_observed_at"])).days >= 7:
                state["alerts"].append({"source": source, "reason": "manual_billing_calibration_due"})
        save(self.state_path, state)

    def controlled_restart(self):
        state = self.load()
        if state.get("restart_incomplete"):
            raise RuntimeError("上次受控重启未完成，不能重复启动")
        original = copy.deepcopy(state["budgets"])
        state["restart_incomplete"] = True
        save(self.state_path, state)
        for ledger in state["budgets"].values():
            ledger.update(blocked=True, blocked_reason="controlled_restart_gate")
        save(self.state_path, state)
        self.apply_pending(force=True)
        state = self.load()
        self.account(state)
        for source, ledger in state["budgets"].items():
            if ledger.get("blocked_reason") == "controlled_restart_gate":
                ledger["blocked"] = original[source]["blocked"]
                if original[source].get("blocked_reason"):
                    ledger["blocked_reason"] = original[source]["blocked_reason"]
                else:
                    ledger.pop("blocked_reason", None)
        state.setdefault("counter_segments", []).append({"at": now(), "core_identity": state["core_identity"],
                                                          "budgets": copy.deepcopy(state["budgets"]),
                                                          "reason": "controlled_restart"})
        # 重启时保留已移除来源的配置；新内核启动后才恢复正常候选。
        self.api.request("POST", "/restart", {"path": str(self.live_config), "payload": ""})
        deadline = time.monotonic() + 30
        previous = state["core_identity"]
        while time.monotonic() < deadline:
            try:
                identity = self.identity()
                fresh = self.api.request("GET", "/connections")
                if identity != previous:
                    break
            except (OSError, RuntimeError):
                pass
            time.sleep(1)
        else:
            raise RuntimeError("内核重启未完成，保护配置与重启标记保留")
        state["budgets"] = {source: counter_segment(ledger, fresh) for source, ledger in state["budgets"].items()}
        state.update(core_identity=identity, restart_incomplete=False)
        self.checkpoint(state, fresh)
        save(self.state_path, state)
        self.apply_pending(force=True)

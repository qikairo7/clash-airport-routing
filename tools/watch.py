import argparse
import copy
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import subprocess
import time
from urllib.error import HTTPError, URLError
from urllib.parse import quote

import yaml
import psutil

from build import CAPACITY, INTERACTIVE, ROOT, SERVICES, build, read_yaml
from controller import Controller
from policy import byte_amount, new_ledger, observe_health, policy_reload_allowed, update_ledger, utc


def save(path, state):
    pending = path.with_suffix(".pending.json")
    pending.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    pending.replace(path)


def resolve(base, value):
    return (base / value).resolve()


def specifications():
    values = {row["id"]: (row["name"], row.get("health"), row.get("head")) for row in SERVICES if row["auto"]}
    values.update({f"interactive-{i}": (name, *params) for i, (name, params) in enumerate(INTERACTIVE.items())})
    values.update({f"capacity-{i}": (name, *params) for i, (name, params) in enumerate(CAPACITY.items())})
    return values


class Watcher:
    def __init__(self, path):
        self.path = Path(path).resolve()
        if ROOT / "local" not in self.path.parents:
            raise ValueError("监测设置必须放在被忽略的 local/ 内")
        self.settings = read_yaml(self.path)
        if not self.settings.get("policy"):
            raise ValueError("后台监测需要显式启用 policy 和节点测量记录")
        self.runtime = self.settings["runtime"]
        self.api = Controller(self.runtime.get("controller_url"), self.runtime.get("controller_pipe"),
                              self.runtime.get("secret_env", "MIHOMO_SECRET"))
        self.home = resolve(self.path.parent, self.runtime["home"])
        self.live_config = resolve(self.path.parent, self.runtime["config"])
        self.persistent = resolve(self.path.parent, self.runtime.get("persistent_config", self.runtime["config"]))
        if self.home not in self.live_config.parents:
            raise ValueError("运行配置必须位于声明的 Mihomo 工作目录内")
        for path in {self.live_config, self.persistent}:
            existing = read_yaml(path)
            if not existing.get("proxy-groups"):
                raise ValueError("目标必须是完整 Mihomo 配置；不能把 Verge 的增强片段当完整配置覆盖")
        self.state_path = self.path.with_name("policy-state.json")
        self.specs = specifications()
        for source in self.settings.get("budgets", {}):
            original = read_yaml(resolve(self.path.parent, self.settings["sources"][source]))
            mapped = {node["name"] for node in self.settings["nodes"] if node["source"] == source}
            if any(node["name"] not in mapped for node in original["proxies"]):
                raise ValueError("预算需要该来源全部节点的倍率，包括手动与未验收节点")

    def identity(self):
        matches = []
        core_name = Path(self.runtime["core"]).name.lower()
        for process in psutil.process_iter(["name", "pid", "create_time", "cmdline"]):
            try:
                info = process.info
                if not info["name"] or info["name"].lower() != core_name:
                    continue
                arguments = info["cmdline"] or []
                if "-f" not in arguments or arguments.index("-f") + 1 >= len(arguments):
                    continue
                config_argument = Path(arguments[arguments.index("-f") + 1])
                if config_argument.is_absolute() and config_argument.resolve() == self.live_config:
                    matches.append([info["pid"], info["create_time"]])
            except (psutil.AccessDenied, psutil.NoSuchProcess):
                continue
        if len(matches) != 1:
            raise RuntimeError("无法唯一确认内核进程身份；需要用绝对路径的 -f 启动 Mihomo")
        return matches[0]

    def billing(self, snapshot):
        budgets = {}
        for source, budget in self.settings.get("budgets", {}).items():
            if source not in self.settings["sources"]:
                raise ValueError("预算引用了不存在的来源")
            age = (datetime.now(timezone.utc) - utc(budget["observed_at"])).total_seconds()
            if not 0 <= age <= 3600:
                raise ValueError("账单时间位于未来或超过一小时；需要先核对当前用量")
            unit = budget["unit"]
            budgets[source] = new_ledger(byte_amount(budget["used"], unit), byte_amount(budget["total"], unit),
                                          byte_amount(budget["threshold"], unit), snapshot)
            budgets[source]["billing_observed_at"] = utc(budget["observed_at"]).isoformat()
        if not budgets:
            raise ValueError("至少填写一个已经核验的订阅预算")
        return budgets

    def initialize(self):
        if self.state_path.exists():
            raise ValueError("已有台账，不允许重新初始化抹掉流量或保护锁")
        snapshot = self.api.request("GET", "/connections")
        budgets = self.billing(snapshot)
        state = {"version": 1, "budgets": budgets, "health": {}, "preferences": {}, "last_reload": None,
                 "core_identity": self.identity(),
                 "created_at": datetime.now(timezone.utc).isoformat(), "error": None}
        save(self.state_path, state)

    def refresh_billing(self):
        state = json.loads(self.state_path.read_text(encoding="utf-8"))
        snapshot = self.api.request("GET", "/connections")
        budgets = self.billing(snapshot)
        if set(budgets) != set(state["budgets"]):
            raise ValueError("刷新账单必须保留已有预算来源，不能删除保护台账")
        for source, ledger in budgets.items():
            previous_time = state["budgets"][source].get("billing_observed_at")
            if previous_time and utc(ledger["billing_observed_at"]) <= utc(previous_time):
                raise ValueError("刷新账单需要更新的供应商账单记录，不能重复使用旧基线")
        state.setdefault("billing_history", []).append({"at": datetime.now(timezone.utc).isoformat(),
                                                        "budgets": state["budgets"], "core_identity": state["core_identity"]})
        state.update(budgets=budgets, core_identity=self.identity(), error=None,
                     billing_refreshed_at=datetime.now(timezone.utc).isoformat())
        save(self.state_path, state)

    def status(self):
        state = json.loads(self.state_path.read_text(encoding="utf-8"))
        fields = {"baseline_bytes", "total_bytes", "threshold_bytes", "upper_bound_bytes", "blocked", "blocked_reason"}
        return {"updated_at": state.get("updated_at"), "last_reload": state.get("last_reload"),
                "reload_deferred": state.get("reload_deferred", False), "error": state.get("error"),
                "budgets": {source: {key: value for key, value in ledger.items() if key in fields}
                            for source, ledger in state["budgets"].items()}}

    def health(self, state, config):
        providers = self.api.request("GET", "/providers/proxies")["providers"]
        nodes = {node["alias"]: node for node in self.settings["nodes"]}
        checked = 0
        for service, (_, url, status) in self.specs.items():
            observed = state["health"].setdefault(service, {})
            for provider_name, provider in providers.items():
                if not provider_name.startswith(service + "-"):
                    continue
                for node in provider.get("proxies", []):
                    history = node.get("extra", {}).get(url, {}).get("history", [])
                    if not history and config.get("proxy-providers", {}).get(provider_name, {}).get("health-check", {}).get("url") == url:
                        history = node.get("history", [])
                    if history:
                        sample = history[-1]
                        observed[node["name"]] = observe_health(observed.get(node["name"], {}), sample["delay"] > 0, sample["time"])
            # 被移出自动池的节点仍在完整手动目录；恢复检查最多每轮两次。
            for alias, health in list(observed.items()):
                if not health.get("quarantined") or checked >= 2:
                    continue
                if (datetime.now(timezone.utc) - utc(health["last_sample_at"])).total_seconds() < 60:
                    continue
                if state["budgets"].get(nodes[alias]["source"], {}).get("blocked"):
                    continue
                api = "/proxies/" + quote(alias, safe="") + "/delay?url=" + quote(url, safe="") + "&timeout=5000&expected=" + str(status)
                try:
                    result = self.api.request("GET", api)
                    passed = result.get("delay", 0) > 0
                except (HTTPError, RuntimeError):
                    passed = False
                observed[alias] = observe_health(health, passed, datetime.now(timezone.utc).isoformat())
                checked += 1

    def deploy(self, generated):
        # 先检查待部署的 providers，再写完整配置；备份放在 local/。
        backup = self.path.parent / "policy-backup"
        backup.mkdir(exist_ok=True)
        for index, path in enumerate(dict.fromkeys([self.live_config, self.persistent])):
            target = backup / f"before-{index}.yaml"
            if not target.exists():
                shutil.copy2(path, target)
        source_providers = self.path.parent / "policy-output/providers"
        staging = self.home / "policy-staging"
        (staging / "providers").mkdir(parents=True, exist_ok=True)
        for source in source_providers.glob("*.yaml"):
            shutil.copy2(source, staging / "providers" / source.name)
        candidate = staging / "config.yaml"
        candidate.write_text(yaml.safe_dump(generated, allow_unicode=True, sort_keys=False), encoding="utf-8")
        result = subprocess.run([self.runtime["core"], "-t", "-d", str(staging), "-f", str(candidate)], capture_output=True)
        if result.returncode:
            (self.path.parent / "policy-core-validation.log").write_bytes(result.stdout + result.stderr)
            raise RuntimeError("待部署配置未通过 Mihomo 校验")
        destination = self.home / "providers"
        destination.mkdir(parents=True, exist_ok=True)
        previous_providers = {}
        (backup / "providers").mkdir(exist_ok=True)
        for source in source_providers.glob("*.yaml"):
            target = destination / source.name
            previous_providers[target] = target.read_bytes() if target.exists() else None
            saved = backup / "providers" / source.name
            if target.exists() and not saved.exists():
                shutil.copy2(target, saved)
            shutil.copy2(source, target)
        previous = {path: path.read_bytes() for path in {self.live_config, self.persistent}}
        for path in previous:
            pending = path.with_suffix(".policy-pending.yaml")
            pending.write_bytes(candidate.read_bytes())
            pending.replace(path)
        try:
            self.api.request("PUT", "/configs?force=true", {"path": str(self.live_config), "payload": ""})
        except (OSError, RuntimeError, HTTPError, URLError):
            for path, data in previous_providers.items():
                if data is None:
                    path.unlink(missing_ok=True)
                else:
                    path.write_bytes(data)
            for path, data in previous.items():
                path.write_bytes(data)
            self.api.request("PUT", "/configs?force=true", {"path": str(self.live_config), "payload": ""})
            raise
        actual = self.api.request("GET", "/proxies")["proxies"]
        if any(group["name"] not in actual for group in generated["proxy-groups"]):
            raise RuntimeError("内核没有加载全部策略组")

    def step(self):
        state = json.loads(self.state_path.read_text(encoding="utf-8"))
        settings = copy.deepcopy(self.settings)
        snapshot = self.api.request("GET", "/connections")
        if self.identity() != state["core_identity"]:
            for ledger in state["budgets"].values():
                ledger.update(blocked=True, blocked_reason="core_restart_requires_new_billing_baseline")
        for source, ledger in state["budgets"].items():
            multipliers = {node["alias"]: node["multiplier"] for node in settings["nodes"] if node["source"] == source}
            state["budgets"][source] = update_ledger(ledger, snapshot, multipliers)
        save(self.state_path, state)
        current = read_yaml(self.live_config)
        self.health(state, current)
        settings["policy"]["health"] = state["health"]
        settings["policy"]["blocked_sources"] = [source for source, budget in state["budgets"].items() if budget["blocked"]]
        current_groups = self.api.request("GET", "/proxies")["proxies"]
        metadata = {node["alias"]: node for node in settings["nodes"]}
        for service in SERVICES:
            choice = current_groups.get(service["name"], {}).get("now")
            if not choice and service["name"] in current_groups:
                choice = self.api.request("GET", "/proxies/" + quote(service["name"], safe="")).get("now")
            node = metadata.get(choice, {})
            if node.get("exit_country") and not state["health"].get(service["id"], {}).get(choice, {}).get("quarantined"):
                state["preferences"][service["id"]] = {"preferred_country": node["exit_country"], "preferred_exit_id": node.get("exit_id")}
        settings["policy"]["services"] = {**settings["policy"].get("services", {}), **state["preferences"]}
        generated_settings = self.path.with_name("settings.policy-generated.yaml")
        generated_settings.write_text(yaml.safe_dump(settings, allow_unicode=True, sort_keys=False), encoding="utf-8")
        generated = build(generated_settings, self.path.parent / "policy-output")
        budget_changed = bool(settings["policy"]["blocked_sources"])
        state["reload_deferred"] = generated != current and not policy_reload_allowed(snapshot, budget_changed)
        if generated != current and not state["reload_deferred"]:
            self.deploy(generated)
            state["last_reload"] = datetime.now(timezone.utc).isoformat()
        blocked = {node["alias"] for node in settings["nodes"] if node["source"] in settings["policy"]["blocked_sources"]}
        for row in (self.api.request("GET", "/connections").get("connections") or []):
            if blocked.intersection(row.get("chains", [])):
                self.api.request("DELETE", "/connections/" + quote(row["id"], safe=""))
        state["updated_at"] = datetime.now(timezone.utc).isoformat()
        state["error"] = None
        save(self.state_path, state)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="监测已经接入公开生成器的 Mihomo 配置；设置与台账仅保留在 local/")
    parser.add_argument("mode", choices=["initialize", "refresh-billing", "status", "once", "run"])
    parser.add_argument("--settings", default=str(ROOT / "local/settings.yaml"))
    args = parser.parse_args()
    watcher = Watcher(args.settings)
    if args.mode == "initialize":
        watcher.initialize()
    elif args.mode == "refresh-billing":
        watcher.refresh_billing()
    elif args.mode == "status":
        print(json.dumps(watcher.status(), ensure_ascii=False))
    elif args.mode == "once":
        watcher.step()
    else:
        while True:
            try:
                watcher.step()
            except (OSError, RuntimeError, ValueError, HTTPError, URLError) as error:
                state = json.loads(watcher.state_path.read_text(encoding="utf-8"))
                state.update(error=type(error).__name__, error_at=datetime.now(timezone.utc).isoformat())
                save(watcher.state_path, state)
            time.sleep(10)

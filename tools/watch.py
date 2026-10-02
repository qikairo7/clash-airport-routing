import argparse
import copy
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.parse import quote

import yaml

from build import CAPACITY, INTERACTIVE, ROOT, SERVICES, build
from monitor import Monitor, now, read_yaml, resolve, save
from availability import Availability
from policy import observe_health, policy_reload_allowed, utc


def specifications():
    values = {row["id"]: (row["name"], row.get("health"), row.get("head")) for row in SERVICES if row["auto"]}
    values.update({f"interactive-{i}": (name, *params) for i, (name, params) in enumerate(INTERACTIVE.items())})
    values.update({f"capacity-{i}": (name, *params) for i, (name, params) in enumerate(CAPACITY.items())})
    return values


class Watcher(Availability, Monitor):
    def __init__(self, path):
        super().__init__(path)
        if not self.settings.get("policy"):
            raise ValueError("后台监测需要显式启用 policy 和节点测量记录")
        self.persistent = resolve(self.path.parent, self.runtime.get("persistent_config", self.runtime["config"]))
        for target in {self.live_config, self.persistent}:
            if not read_yaml(target).get("proxy-groups"):
                raise ValueError("目标必须是完整 Mihomo 配置，不能覆盖 Verge 增强片段")
        self.specs = specifications()
        for source in self.settings.get("budgets", {}):
            original = read_yaml(resolve(self.path.parent, self.settings["sources"][source]))
            mapped = {node["name"] for node in self.settings["nodes"] if node["source"] == source}
            if any(node["name"] not in mapped for node in original["proxies"]):
                raise ValueError("预算需要该来源全部节点的倍率，包括手动与未验收节点")

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
            for alias, health in list(observed.items()):
                if not health.get("quarantined") or checked >= 2 or alias not in nodes:
                    continue
                if (utc(now()) - utc(health["last_sample_at"])).total_seconds() < 60:
                    continue
                if state["budgets"].get(nodes[alias]["source"], {}).get("blocked"):
                    continue
                api = "/proxies/" + quote(alias, safe="") + "/delay?url=" + quote(url, safe="") + "&timeout=5000&expected=" + str(status)
                try:
                    passed = self.api.request("GET", api).get("delay", 0) > 0
                except (HTTPError, RuntimeError):
                    passed = False
                observed[alias] = observe_health(health, passed, now())
                checked += 1
        self.active_checks = checked

    def deploy(self, generated):
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

    def apply_pending(self, force=False):
        state = self.load()
        snapshot = self.account(state)
        settings = copy.deepcopy(self.settings)
        current = read_yaml(self.live_config)
        self.health(state, current)
        settings["policy"]["health"] = state["health"]
        settings["policy"]["blocked_sources"] = [source for source, ledger in state["budgets"].items() if ledger["blocked"]]
        settings["policy"]["services"] = {**settings["policy"].get("services", {}), **state["preferences"]}
        generated_settings = self.path.with_name("settings.policy-generated.yaml")
        generated_settings.write_text(yaml.safe_dump(settings, allow_unicode=True, sort_keys=False), encoding="utf-8")
        generated = build(generated_settings, self.path.parent / "policy-output")
        definitions = {service["name"]: {"ai": True, "url": service["health"], "status": service["head"]}
                       for service in SERVICES if service["auto"] and service.get("health")}
        state["selection"] = {}
        metadata = {node["alias"]: node for node in settings["nodes"]}
        for group in generated["proxy-groups"]:
            if group["name"].endswith(" 候选"):
                rows = []
                for provider in group.get("use", []):
                    names = read_yaml(self.path.parent / "policy-output" / generated["proxy-providers"][provider]["path"])["proxies"]
                    rows.extend(metadata[node["name"]] for node in names)
                state["selection"][group["name"][:-3]] = rows
        blocked = {node["alias"] for node in settings["nodes"] if node["source"] in settings["policy"]["blocked_sources"]}
        changed = generated != current
        state["reload_deferred"] = changed and not (force or policy_reload_allowed(snapshot, bool(blocked)))
        if changed and not state["reload_deferred"]:
            self.deploy(generated)
            state["last_reload"] = now()
        for row in (self.api.request("GET", "/connections").get("connections") or []):
            if blocked.intersection(row.get("chains", [])):
                self.api.request("DELETE", "/connections/" + quote(row["id"], safe=""))
        if settings["policy"].get("stable_ai"):
            self.pin(state, definitions, self.api.request("GET", "/providers/proxies")["providers"])
        self.finish(state)

    def step(self):
        self.apply_pending()


def create_watcher(path):
    if read_yaml(path).get("runtime", {}).get("adapter") == "verge":
        from verge import VergeWatcher
        return VergeWatcher(path)
    return Watcher(path)


def run_watcher(settings_path):
    startup = settings_path.with_name("watch-startup.json")
    while True:
        try:
            watcher = create_watcher(settings_path)
            watcher.identity()
            watcher.api.request("GET", "/configs")
            break
        except (OSError, RuntimeError, ValueError, HTTPError, URLError) as error:
            save(startup, {"at": now(), "ready": False, "phase": "waiting_for_core_and_files", "error": type(error).__name__})
            time.sleep(10)
    save(startup, {"at": now(), "ready": True})
    with watcher.exclusive():
        while True:
            started = time.monotonic()
            try:
                watcher.step()
            except (OSError, RuntimeError, ValueError, HTTPError, URLError) as error:
                state = watcher.load()
                state.update(error=type(error).__name__, error_at=now())
                save(watcher.state_path, state)
            time.sleep(max(0, 10 - (time.monotonic() - started)))


def main():
    parser = argparse.ArgumentParser(description="本机策略、账单和维护；设置与台账仅保留在 local/")
    parser.add_argument("mode", choices=["initialize", "migrate", "refresh-billing", "import-local-billing", "status",
                                          "once", "run", "apply-pending", "controlled-restart", "recheck", "restore", "recover-ledger"])
    parser.add_argument("--settings", default=str(ROOT / "local/settings.yaml"))
    parser.add_argument("--confirm-cycle", action="store_true")
    args = parser.parse_args()
    settings_path = Path(args.settings).resolve()
    if sys.stderr is None and (ROOT / "local").resolve() in settings_path.parents:
        # pythonw 没有控制台，启动失败也必须留下本机诊断记录。
        sys.stderr = settings_path.with_name("watch-error.log").open("a", encoding="utf-8")
    if args.mode == "run":
        if (ROOT / "local").resolve() not in settings_path.parents:
            raise ValueError("监测设置必须位于本项目被忽略的 local/ 内")
        run_watcher(settings_path)
        return
    watcher = create_watcher(args.settings)
    if args.mode == "status":
        print(json.dumps(watcher.status(), ensure_ascii=False))
        return
    with watcher.exclusive():
        if args.mode == "refresh-billing":
            watcher.refresh_billing(args.confirm_cycle)
        elif args.mode in {"initialize", "migrate", "controlled-restart", "recover-ledger"}:
            getattr(watcher, args.mode.replace("-", "_"))()
        elif args.mode == "import-local-billing":
            print(json.dumps(watcher.import_local_billing(args.confirm_cycle), ensure_ascii=False))
        elif args.mode == "apply-pending":
            watcher.apply_pending(force=True)
        elif args.mode in {"recheck", "restore"}:
            getattr(watcher, args.mode)()
        elif args.mode == "once":
            watcher.step()


if __name__ == "__main__":
    main()

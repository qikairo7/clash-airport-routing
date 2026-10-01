import copy
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess
import time
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import ProxyHandler, build_opener
from zoneinfo import ZoneInfo

import yaml

from monitor import Monitor, ROOT, now, read_yaml, resolve, save
from availability import Availability
from policy import limited_candidates, observe_health, policy_reload_allowed, select_candidates, utc


def fingerprint(proxy, hosts):
    parameters = {key: value for key, value in proxy.items() if key != "name"}
    parameters["server"] = str(hosts.get(proxy["server"], proxy["server"]))
    return hashlib.sha256(json.dumps(parameters, sort_keys=True).encode()).hexdigest()[:16]


def metadata_name(name):
    return bool(re.search(r"(?i)traffic|expire|days left|remaining|流量|到期|剩余", name) or
                re.match(r"^[\d.]+\s*G\s*\|", name))


def initial_transport(node, service, verified_services):
    if not node.get("initial_proof_valid"):
        return False
    if service.startswith("AI "):
        return (node["provider"], node["name"]) in verified_services.get(service, set())
    check = {"OpenAI 自动（1倍优先）": "openai", "Claude 自动（1倍优先）": "claude",
             "Google 自动（1倍优先）": "gemini", "开发": "github_web", "GitHub API": "github_api",
             "GitHub 文件": "github_raw", "容器": "docker", "社交": "x", "Telegram 线路": "telegram"}.get(service)
    return node.get("checks", {}).get(check, {}).get("passed", False) if check else node.get("trace_passed", False)


class VergeWatcher(Availability, Monitor):
    def __init__(self, path):
        super().__init__(path)
        self.merge_path = resolve(self.path.parent, self.runtime["merge"])
        self.script_path = resolve(self.path.parent, self.runtime["script"])
        self.profile = resolve(self.path.parent, self.runtime["profile"])
        self.generated = self.profile / "clash-verge.yaml"
        self.inventory()
        self.runtime_versions(read_yaml(self.live_config))

    def runtime_versions(self, live):
        self.provider_paths = {name: row.get("path") for name, row in live.get("proxy-providers", {}).items()}
        self.root_endpoints = {row["name"]: fingerprint(row, live.get("hosts", {})) for row in live.get("proxies", [])}

    def inventory(self):
        paths = [resolve(self.path.parent, value) for value in self.settings["sources"].values()]
        paths.append(resolve(self.path.parent, self.runtime["measurements"]))
        signature = tuple((str(path), path.stat().st_mtime_ns, path.stat().st_size) for path in paths)
        if signature == getattr(self, "inventory_signature", None):
            return
        measured = json.loads(resolve(self.path.parent, self.runtime["measurements"]).read_text(encoding="utf-8"))
        results = {row["endpoint_id"]: row for row in measured["results"]}
        old = {(row["provider"], row["name"]): row for row in measured["configured_entries"]}
        self.nodes, self.parameters, self.hosts = {}, {}, {}
        for source, value in self.settings["sources"].items():
            profile = read_yaml(resolve(self.path.parent, value))
            hosts = profile.get("hosts", {})
            for name, address in hosts.items():
                if name in self.hosts and self.hosts[name] != address:
                    raise ValueError("来源静态解析冲突")
                self.hosts[name] = address
            provider = self.runtime["source_labels"][source]
            for proxy in profile["proxies"]:
                alias = proxy["name"]
                if metadata_name(alias):
                    continue
                match = re.search(r"(\d+(?:\.\d+)?)x(?:\s|$)", alias)
                multiplier = float(match.group(1)) if match else self.runtime["default_multipliers"][source]
                if multiplier is None:
                    raise ValueError("来源节点倍率缺失")
                endpoint = fingerprint(proxy, hosts)
                previous = old.get((provider, alias), {})
                proof = results.get(endpoint, {}) if previous.get("endpoint_id") == endpoint else {}
                ingress = hashlib.sha256(str(hosts.get(proxy["server"], proxy["server"])).encode()).hexdigest()[:16]
                row = {"name": alias, "alias": alias, "source": source, "provider": provider, "multiplier": multiplier,
                       "endpoint_id": endpoint, "ingress_id": ingress, "exit_id": proof.get("exit_id"),
                       "exit_country": proof.get("quality", {}).get("country", ""),
                       "checked_at": proof.get("measured_at"), "checks": proof.get("checks", {}),
                       "parameter_changed": bool(previous and not proof), "initial_proof_valid": bool(proof),
                       "trace_passed": proof.get("trace_status") == [200, 200, 200]}
                if alias in self.nodes:
                    raise ValueError("不同来源存在重复节点名称，无法可靠核算")
                self.nodes[alias] = row
                self.parameters[alias] = copy.deepcopy(proxy)
        self.settings["nodes"] = list(self.nodes.values())
        labels = {label: source for source, label in self.runtime["source_labels"].items()}
        for row in measured["configured_entries"]:
            if row.get("kind") == "node" and row["provider"] in labels and row["name"] not in self.nodes and row.get("multiplier"):
                self.settings["nodes"].append({"alias": row["name"], "source": labels[row["provider"]], "multiplier": row["multiplier"]})
        self.inventory_signature = signature
        self.expected_endpoints = {alias: row["endpoint_id"] for alias, row in self.nodes.items()}

    def definitions(self, merge, live):
        pools = merge["x-verified-pools"]["pools"]
        definitions = {name: {"candidates": pools[name]["candidates"], "ai": False}
                       for name in ["开发", "GitHub API", "GitHub 文件", "容器", "社交", "Telegram 线路", "媒体大流量", "通用海外"]}
        for name in ["OpenAI", "Claude", "Google"]:
            definitions[name + " 自动（1倍优先）"] = {"candidates": pools[name]["active_candidates"] + pools[name]["milk_backup"], "ai": True}
        for service in merge["x-service-pools"]:
            if not service.get("manual_only"):
                definitions["AI " + service["name"]] = {"candidates": service["candidates"], "ai": True,
                                                         "url": service["url"], "status": service["status"]}
        for name, spec in definitions.items():
            group = next(row for row in live["proxy-groups"] if row["name"] in {name, name + " 候选"} and row.get("url"))
            # 增强脚本可以将首页换成 robots.txt，监测必须使用实际加载的地址。
            spec["url"] = group["url"]
            spec["status"] = group.get("expected-status", spec.get("status", 200))
            spec["manual_groups"] = self.runtime.get("manual_groups", {}).get(name, [])
        return definitions

    def leaf(self, proxies, name):
        seen = set()
        while name in proxies and name not in seen:
            seen.add(name)
            row = proxies[name]
            following = row.get("now")
            if not following and row.get("type") in {"Selector", "Fallback", "URLTest", "LoadBalance"}:
                following = self.api.request("GET", "/proxies/" + quote(name, safe="")).get("now")
            if not following:
                return name
            name = following
        return name

    def health(self, state, definitions):
        providers = self.api.request("GET", "/providers/proxies")["providers"]
        active = 0
        for name, spec in definitions.items():
            observed = state["health"].setdefault(name, {})
            for candidate in spec["candidates"]:
                alias = candidate["name"]
                if alias not in self.nodes:
                    continue
                node = self.nodes[alias]
                record = self.sample(providers, alias, spec["url"])
                identity = state.setdefault("node_versions", {}).setdefault(alias, {"endpoint_id": node["endpoint_id"], "at": now()})
                if identity["endpoint_id"] != node["endpoint_id"]:
                    identity.update(endpoint_id=node["endpoint_id"], at=now())
                if node["parameter_changed"] and record and utc(record["time"]) < utc(identity["at"]):
                    record = None
                previous = observed.get(alias, {})
                if previous.get("endpoint_id") not in {None, node["endpoint_id"]}:
                    previous = {}
                if record:
                    previous = observe_health(previous, record["delay"] > 0, record["time"])
                    previous.update(last_passed=record["delay"] > 0, endpoint_id=node["endpoint_id"])
                    if record["delay"] > 0:
                        state.setdefault("transport", {}).setdefault(name, {})[alias] = {"at": record["time"], "endpoint_id": node["endpoint_id"]}
                if previous.get("quarantined") and active < 2 and not state["budgets"][node["source"]]["blocked"]:
                    if (utc(now()) - utc(previous["last_sample_at"])).total_seconds() >= 60:
                        passed = self.probe(providers, alias, spec)
                        previous = observe_health(previous, passed, now())
                        previous.update(last_passed=passed, endpoint_id=node["endpoint_id"])
                        active += 1
                observed[alias] = previous
        self.active_checks = active
        return providers

    def overlay(self, state, merge, live, definitions):
        for alias, proof in state.get("exits", {}).items():
            node = self.nodes.get(alias)
            if node and node["endpoint_id"] == proof["endpoint_id"]:
                node.update(exit_id=proof["exit_id"], exit_country=proof["country"], checked_at=proof["at"])
        proxies = self.api.request("GET", "/proxies")["proxies"]
        blocked = [source for source, ledger in state["budgets"].items() if ledger["blocked"]]
        bases = {}
        for source, value in self.settings["sources"].items():
            relative = "profiles/" + Path(value).name
            matching = [name for name, provider in live["proxy-providers"].items()
                        if provider.get("path") == relative and not name.startswith("路由策略 ")]
            # 保护后基础来源可能被删掉，从最后的有效配置取定义用于解锁。
            bases[source] = matching[0] if matching else self.runtime["base_providers"][source]
        business_path = self.path.with_name("business-evidence.json")
        business = json.loads(business_path.read_text(encoding="utf-8")) if business_path.exists() else {}
        anchor = self.nodes.get(self.leaf(proxies, "AI ChatGPT Codex"))
        if anchor and anchor.get("exit_id") and anchor["source"] not in blocked:
            coordinated = ["AI ChatGPT Codex", "OpenAI 自动（1倍优先）"]
            common = all(any(self.nodes.get(item["name"], {}).get("exit_id") == anchor["exit_id"] for item in definitions[name]["candidates"])
                         for name in coordinated)
            state["openai_common_exit"] = bool(common)
            if common:
                for name in coordinated:
                    state["preferences"][name] = {"preferred_country": anchor["exit_country"], "preferred_exit_id": anchor["exit_id"]}
        service_proofs = json.loads(resolve(self.path.parent, self.runtime["service_measurements"]).read_text(encoding="utf-8"))
        verified_services = {"AI " + row["name"]: {(item["provider"], item["name"]) for item in row["candidates"]}
                             for row in service_proofs["services"]}
        proof_time = datetime.fromisoformat(service_proofs["checked_at"]).replace(tzinfo=ZoneInfo("Asia/Shanghai")).astimezone(timezone.utc).isoformat()
        groups, report = [], {}
        for name, spec in definitions.items():
            current = self.nodes.get(self.leaf(proxies, name))
            if spec["ai"] and current and current["exit_country"] and current["source"] not in blocked and not (
                    state.get("openai_common_exit") and name in {"AI ChatGPT Codex", "OpenAI 自动（1倍优先）"}):
                if not state["health"].get(name, {}).get(current["name"], {}).get("quarantined"):
                    state["preferences"][name] = {"preferred_country": current["exit_country"], "preferred_exit_id": current["exit_id"]}
            rows = []
            for index, item in enumerate(spec["candidates"]):
                node = self.nodes.get(item["name"])
                if not node or node["provider"] != item["provider"] or node["multiplier"] > 1:
                    continue
                row = copy.deepcopy(node)
                row["priority"] = index
                exit_proof = state.get("exits", {}).get(row["alias"], {})
                if exit_proof.get("endpoint_id") == row["endpoint_id"]:
                    row.update(exit_id=exit_proof["exit_id"], exit_country=exit_proof["country"], checked_at=exit_proof["at"])
                fresh = state.get("transport", {}).get(name, {}).get(row["alias"], {})
                fresh_valid = fresh.get("endpoint_id") == row["endpoint_id"] and bool(fresh.get("at"))
                initial_valid = initial_transport(row, name, verified_services)
                transport_at = fresh["at"] if fresh_valid else ((proof_time if name.startswith("AI ") else node["checked_at"]) if initial_valid else None)
                proof = business.get(name, {}).get(row["alias"], {})
                age_ok = row["checked_at"] and (utc(now()) - utc(row["checked_at"])).total_seconds() < 72 * 3600
                row["evidence"] = {name: {"checked_at": transport_at, "transport": "passed" if age_ok and (fresh_valid or initial_valid) else "pending",
                                           "business": proof.get("status", "pending"), "business_checked_at": proof.get("checked_at")}}
                rows.append(row)
            preference = state["preferences"].get(name, {})
            policy = {"qualification_max_age_hours": 72, "services": state["preferences"], "blocked_sources": blocked,
                      "health": state["health"], "require_business": False}
            capacity = name in {"GitHub 文件", "容器", "媒体大流量"}
            order = ["primary", "bulk"] if spec["ai"] else ["bulk", "primary"]
            if capacity:
                rows = [row for row in rows if row["source"] == "bulk"]
                order = ["bulk"]
            selected, excluded = select_candidates(rows, name, order, policy)
            if spec["ai"]:
                selected = limited_candidates(selected, preference.get("preferred_country", selected[0]["exit_country"] if selected else ""),
                                              preference.get("preferred_exit_id"), 4)
            report[name] = [{key: row.get(key) for key in ("alias", "source", "exit_country", "ingress_id", "exit_id", "checked_at")} for row in selected]
            if capacity:
                distributed_name = "奶昔 " + name + " 多节点"
                distributed = next((row for row in live["proxy-groups"] if row["name"] == distributed_name), None)
                near = [alias for alias in (distributed or {}).get("proxies", []) if alias in {row["alias"] for row in selected}]
                if distributed:
                    groups.append({"name": distributed_name, "direct": near})
                groups.append({"name": name, "direct": ([distributed_name] if near else []) + [row["alias"] for row in selected if row["alias"] not in near]})
                continue
            layers = [{"provider": bases[row["source"]], "names": [row["alias"]],
                       "path": "policy-providers/" + row["endpoint_id"] + "-" + hashlib.sha256(row["alias"].encode()).hexdigest()[:8] + ".yaml"} for row in selected]
            groups.append({"name": name, "layers": layers, "stable": spec["ai"], "manual_groups": spec["manual_groups"]})
        blocked_nodes = [node["alias"] for node in self.settings["nodes"] if node["source"] in blocked]
        blocked_providers = [name for name, provider in live["proxy-providers"].items()
                             if any(provider.get("path") == "profiles/" + Path(self.settings["sources"][source]).name for source in blocked)]
        save(self.path.with_name("selection-report.json"), {"at": now(), "selected": report, "business_scope": "pending unless real authenticated request recorded"})
        state["selection"] = report
        return {"version": 1, "groups": groups, "blocked_nodes": blocked_nodes, "blocked_providers": blocked_providers}

    def prepare(self, state, overlay):
        # 自动来源固定到已验收参数；刷新原文件不能让同名新参数直接接入自动池。
        for group in overlay["groups"]:
            for layer in group.get("layers", []):
                if not layer.get("path"):
                    continue
                payload = {"proxies": [self.parameters[alias] for alias in layer["names"]]}
                # 客户端校验和正式服务工作目录不同，使用各自目录内的相同文件副本。
                for home in {self.home, self.profile}:
                    path = home / layer["path"]
                    path.parent.mkdir(parents=True, exist_ok=True)
                    if path.exists() and read_yaml(path) != payload:
                        raise RuntimeError("已验收节点快照发生不一致，拒绝覆盖")
                    if not path.exists():
                        path.write_text(yaml.safe_dump(payload, allow_unicode=True, sort_keys=False), encoding="utf-8")
        merge = read_yaml(self.merge_path)
        merge["x-routing-policy"] = overlay
        merge["x-budget-state"]["tag_blocked"] = state["budgets"]["primary"]["blocked"]
        base = read_yaml(resolve(self.path.parent, self.runtime["base_profile"]))
        base["hosts"] = {**self.hosts, **merge.get("hosts", {})}
        for key in ("x-verified-pools", "x-service-pools", "x-budget-state", "x-routing-policy"):
            base[key] = merge[key]
        result = subprocess.run([self.runtime.get("node", "node"), str(ROOT / "tools/evaluate_verge.cjs"), str(self.script_path)],
                                input=json.dumps(base), text=True, encoding="utf-8", capture_output=True)
        if result.returncode:
            self.path.with_name("generation.log").write_text(result.stderr, encoding="utf-8")
            raise RuntimeError("持久脚本生成失败；详情仅保留在本机")
        desired = json.loads(result.stdout)
        candidate = read_yaml(self.live_config)
        for key in ("proxy-groups", "rules", "proxy-providers", "proxies", "hosts"):
            candidate[key] = desired[key]
        pending = self.path.with_name("runtime-candidate.yaml")
        pending.write_text(yaml.safe_dump(candidate, allow_unicode=True, sort_keys=False), encoding="utf-8")
        checked = subprocess.run([self.runtime["core"], "-t", "-d", str(self.home), "-f", str(pending)], capture_output=True)
        if checked.returncode:
            self.path.with_name("core-validation.log").write_bytes(checked.stdout + checked.stderr)
            raise RuntimeError("候选配置未通过 Mihomo 校验")
        return merge, candidate

    def deploy(self, state, overlay):
        merge, candidate = self.prepare(state, overlay)
        paths = {self.merge_path: merge, self.live_config: candidate, self.generated: candidate}
        previous = {path: path.read_bytes() for path in paths}
        identity = self.identity()
        backup = self.path.parent / "before-deployment"
        backup.mkdir(exist_ok=True)
        for name, path in [("merge.yaml", self.merge_path), ("runtime.yaml", self.live_config), ("generated.yaml", self.generated)]:
            shutil.copy2(path, backup / name)
        choices = {name: row["now"] for name, row in self.api.request("GET", "/proxies")["proxies"].items()
                   if row.get("type") == "Selector" and row.get("now")}
        try:
            for path, value in paths.items():
                pending = path.with_suffix(".policy-pending.yaml")
                pending.write_text(yaml.safe_dump(value, allow_unicode=True, sort_keys=False), encoding="utf-8")
                pending.replace(path)
            self.api.request("PUT", "/configs?force=true", {"path": str(self.live_config), "payload": ""})
            if self.identity() != identity:
                raise RuntimeError("配置重载改变了内核身份")
            actual = self.api.request("GET", "/proxies")["proxies"]
            for entry in overlay["groups"]:
                if entry["name"] not in actual:
                    raise RuntimeError("缺少部署策略组")
            for name, choice in choices.items():
                if name in actual and choice in actual[name].get("all", []):
                    self.api.request("PUT", "/proxies/" + quote(name, safe=""), {"name": choice})
            blocked = set(overlay["blocked_nodes"])
            for row in (self.api.request("GET", "/connections").get("connections") or []):
                if blocked.intersection(row.get("chains", [])):
                    self.api.request("DELETE", "/connections/" + quote(row["id"], safe=""))
            providers = self.api.request("GET", "/providers/proxies")["providers"]
            if any(blocked.intersection(node["name"] for node in provider.get("proxies", [])) for provider in providers.values()):
                raise RuntimeError("受保护节点仍存在于来源目录")
        except (OSError, RuntimeError, HTTPError, URLError):
            for path, content in previous.items():
                path.write_bytes(content)
            self.api.request("PUT", "/configs?force=true", {"path": str(self.live_config), "payload": ""})
            raise
        state.update(applied_overlay=overlay, last_reload=now(), reload_deferred=False, pending_reason=None)
        self.runtime_versions(candidate)
        state.pop("pending_since", None)
        save(self.state_path, state)

    def renew_exits(self, state, definitions, providers, explicit=False):
        due = explicit or not state.get("renewal_scan_at") or (utc(now()) - utc(state["renewal_scan_at"])).total_seconds() >= 21600
        if not due:
            return
        selected = []
        for name, spec in definitions.items():
            if not spec["ai"]:
                continue
            rows = list(state.get("selection", {}).get(name, []))
            for item in spec["candidates"]:
                node = self.nodes.get(item["name"])
                if node and not node["checked_at"] and node["alias"] not in [row["alias"] for row in rows]:
                    rows.append(node)
            for row in rows:
                alias = row["alias"]
                proof = state.get("exits", {}).get(alias, {})
                checked = proof.get("at") if proof.get("endpoint_id") == self.nodes[alias]["endpoint_id"] else row.get("checked_at")
                if explicit or not checked or (utc(now()) - utc(checked)).total_seconds() >= 48 * 3600:
                    if alias not in [item[1] for item in selected] and not state["budgets"][row["source"]]["blocked"]:
                        selected.append((name, alias, spec))
        if not selected:
            state["renewal_scan_at"] = now()
            return
        selected = selected[:max(0, 2 - getattr(self, "active_checks", 0))]
        if not selected:
            return
        work = self.path.parent / "exit-recheck"
        work.mkdir(exist_ok=True)
        def free_port():
            with socket.socket() as listener:
                listener.bind(("127.0.0.1", 0))
                return listener.getsockname()[1]
        port, controller = free_port(), free_port()
        config = {"mixed-port": port, "external-controller": "127.0.0.1:" + str(controller),
                  "allow-lan": False, "bind-address": "127.0.0.1", "mode": "rule", "log-level": "silent",
                  "tun": {"enable": False}, "dns": {"enable": False}, "ipv6": False,
                  "interface-name": self.runtime["test_interface"], "hosts": self.hosts,
                  "profile": {"store-selected": False}, "proxies": [self.parameters[alias] for _, alias, _ in selected],
                  "proxy-groups": [{"name": "ExitCheck", "type": "select", "proxies": [alias for _, alias, _ in selected]}],
                  "rules": ["MATCH,ExitCheck"]}
        path = work / "config.yaml"
        path.write_text(yaml.safe_dump(config, allow_unicode=True, sort_keys=False), encoding="utf-8")
        from controller import Controller
        api = Controller("http://127.0.0.1:" + str(controller), secret_env="UNUSED_EXIT_TEST_SECRET")
        opener = build_opener(ProxyHandler({"https": "http://127.0.0.1:" + str(port)}))
        process = subprocess.Popen([self.runtime["core"], "-d", str(work), "-f", str(path)],
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=0x08000000 if os.name == "nt" else 0)
        try:
            for _ in range(10):
                try:
                    api.request("GET", "/version")
                    break
                except (OSError, HTTPError, URLError):
                    time.sleep(.5)
            for name, alias, spec in selected:
                self.active_checks = getattr(self, "active_checks", 0) + 1
                if not self.probe(providers, alias, spec):
                    state.setdefault("renewal_errors", {})[alias] = "service_transport_failed"
                    continue
                api.request("PUT", "/proxies/ExitCheck", {"name": alias})
                traces = []
                for _ in range(3):
                    with opener.open("https://www.cloudflare.com/cdn-cgi/trace", timeout=8) as response:
                        # Cloudflare 的诊断响应是简单的逐行键值，没有账号凭据。
                        traces.append(dict(line.split("=", 1) for line in response.read().decode().splitlines() if "=" in line))
                if len({row.get("ip") for row in traces}) != 1 or not traces[0].get("ip") or not traces[0].get("loc"):
                    state.setdefault("renewal_errors", {})[alias] = "unstable_exit"
                    continue
                proof = {"at": now(), "endpoint_id": self.nodes[alias]["endpoint_id"],
                         "exit_id": hashlib.sha256(traces[0]["ip"].encode()).hexdigest()[:16], "country": traces[0]["loc"].lower()}
                state.setdefault("exits", {})[alias] = proof
                state.setdefault("transport", {}).setdefault(name, {})[alias] = {"at": now(), "endpoint_id": self.nodes[alias]["endpoint_id"]}
                state.setdefault("renewal_errors", {}).pop(alias, None)
        finally:
            process.terminate()
            process.wait(timeout=10)
        # 待检查候选超过两条时，后续轮继续；结束后才进入下一次六小时扫描。
        if len(selected) < 2:
            state["renewal_scan_at"] = now()

    def sync_sources(self):
        for value in self.settings["sources"].values():
            origin = resolve(self.path.parent, value)
            target = self.home / "profiles" / origin.name
            if not target.exists() or target.read_bytes() != origin.read_bytes():
                target.parent.mkdir(exist_ok=True)
                shutil.copy2(origin, target)
                live = read_yaml(self.live_config)
                for name, provider in live["proxy-providers"].items():
                    if provider.get("path") == "profiles/" + origin.name:
                        self.api.request("PUT", "/providers/proxies/" + quote(name, safe=""))

    def apply_pending(self, force=False):
        self.inventory()
        state = self.load()
        snapshot = self.account(state)
        self.sync_sources()
        merge, live = read_yaml(self.merge_path), read_yaml(self.live_config)
        self.runtime_versions(live)
        definitions = self.definitions(merge, live)
        providers = self.health(state, definitions)
        if not any(ledger["blocked"] for ledger in state["budgets"].values()):
            try:
                self.renew_exits(state, definitions, providers)
            except (OSError, HTTPError, URLError, RuntimeError) as error:
                state["renewal_error"] = {"at": now(), "type": type(error).__name__}
        overlay = self.overlay(state, merge, live, definitions)
        previous = state.get("applied_overlay", {})
        budget_changed = set(overlay["blocked_nodes"]) != set(previous.get("blocked_nodes", []))
        empty = [entry["name"] for entry in overlay["groups"] if entry.get("stable") and not entry["layers"]]
        previously_usable = {entry["name"] for entry in previous.get("groups", []) if entry.get("layers") or entry.get("direct")}
        unexpected_empty = [name for name in empty if name in previously_usable] if not any(ledger["blocked"] for ledger in state["budgets"].values()) else []
        changed = overlay != previous
        state["reload_deferred"] = bool(changed and (unexpected_empty or not (force or policy_reload_allowed(snapshot, budget_changed))))
        if changed and not state["reload_deferred"]:
            self.deploy(state, overlay)
            providers = self.api.request("GET", "/providers/proxies")["providers"]
        elif state["reload_deferred"]:
            state.setdefault("pending_since", now())
            elapsed = (utc(now()) - utc(state["pending_since"])).total_seconds()
            state["pending_reason"] = "核心资格缺失，停止部署：" + "、".join(empty) if unexpected_empty else (
                "持续连接已延后超过30分钟；可以执行维护应用" if elapsed >= 1800 else "活动连接尚未结束")
        self.pin(state, definitions, providers)
        self.finish(state)

    def step(self):
        self.apply_pending()

    def recheck(self):
        state = self.load()
        live = read_yaml(self.live_config)
        definitions = self.definitions(read_yaml(self.merge_path), live)
        providers = self.api.request("GET", "/providers/proxies")["providers"]
        self.active_checks = 0
        self.renew_exits(state, definitions, providers, explicit=True)
        save(self.state_path, state)
        return {"checked": self.active_checks, "business": "pending"}

    def restore(self):
        backup = self.path.parent / "before-deployment"
        # 恢复配置不恢复额度；先用当前台账生成保护覆盖层再部署。
        merge = read_yaml(backup / "merge.yaml")
        live = read_yaml(backup / "runtime.yaml")
        state = self.load()
        self.account(state)
        definitions = self.definitions(merge, live)
        overlay = self.overlay(state, merge, live, definitions)
        current = self.merge_path.read_bytes()
        self.merge_path.write_text(yaml.safe_dump(merge, allow_unicode=True, sort_keys=False), encoding="utf-8")
        try:
            self.deploy(state, overlay)
        except (OSError, RuntimeError, HTTPError, URLError):
            self.merge_path.write_bytes(current)
            raise

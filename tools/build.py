import argparse
import copy
import json
import math
import re
from datetime import date
from pathlib import Path

import yaml

from policy import limited_candidates, select_candidates

ROOT = Path(__file__).resolve().parents[1]
SERVICES = json.loads((ROOT / "catalog/services.json").read_text(encoding="utf-8"))
ROUTES = json.loads((ROOT / "catalog/routes.json").read_text(encoding="utf-8"))
INTERACTIVE = {
    "开发": ("https://github.com/", 200),
    "GitHub API": ("https://api.github.com/repos/git/git", 200),
    "社交": ("https://x.com/", 200),
    "Telegram": ("https://web.telegram.org/", 200),
    "通用海外": ("https://www.gstatic.com/generate_204", 204),
}
CAPACITY = {
    "GitHub 文件": ("https://raw.githubusercontent.com/git/git/master/README.md", 200),
    "容器与依赖": ("https://registry-1.docker.io/v2/", 401),
    "媒体与下载": ("https://www.gstatic.com/generate_204", 204),
}


def read_yaml(path):
    # 不把解析异常中的订阅原文输出到控制台。
    try:
        data = yaml.safe_load(Path(path).read_text(encoding="utf-8-sig"))
    except (OSError, yaml.YAMLError) as error:
        raise ValueError("无法读取 YAML 文件，请在本机检查格式和文件路径") from None
    if not isinstance(data, dict):
        raise ValueError("YAML 顶层必须是对象")
    return data


def generate(settings, sources, base=None, demo=False, block_primary=False):
    if settings.get("demo") and not demo:
        raise ValueError("演示配置仅允许 --demo，不可作为真实网络配置")
    if "primary" not in sources or "bulk" not in sources:
        raise ValueError("必须配置 primary 和 bulk 两个来源")
    if any(key not in {"primary", "bulk", "temporary"} for key in sources):
        raise ValueError("来源名称仅支持 primary、bulk、temporary")
    pools = {key: {} for key in sources}
    for key, source in sources.items():
        if not isinstance(source.get("proxies"), list):
            raise ValueError("来源必须包含 proxies 数组")
        for proxy in source["proxies"]:
            if not isinstance(proxy, dict) or not proxy.get("name") or not proxy.get("type"):
                raise ValueError("来源包含无效节点或流量提示，请先移除提示记录")
            if proxy["name"] in pools[key]:
                raise ValueError("同一来源包含重复节点名称")
            if not demo and (str(proxy.get("server", "")).endswith(".invalid") or proxy.get("password") == "DEMO_ONLY"):
                raise ValueError("真实配置中仍有演示节点")
            if proxy.get("skip-cert-verify") and not settings.get("allow_insecure"):
                raise ValueError("来源关闭证书校验；请先检查证书或显式设置 allow_insecure")
            pools[key][proxy["name"]] = copy.deepcopy(proxy)

    nodes = settings.get("nodes", [])
    if not isinstance(nodes, list):
        raise ValueError("nodes 必须为数组")
    aliases, references = set(), set()
    service_ids = {service["id"] for service in SERVICES}
    for node in nodes:
        alias = node.get("alias", "")
        if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]*", alias) or alias in aliases or alias in {"DIRECT", "REJECT", "GLOBAL", "PASS"}:
            raise ValueError("节点 alias 必须唯一，且仅含英文字母、数字、横线和下划线")
        key, name = node.get("source"), node.get("name")
        if key not in pools or name not in pools[key] or (key, name) in references:
            raise ValueError("节点映射缺失或重复引用同一个来源节点")
        multiplier = node.get("multiplier")
        if isinstance(multiplier, bool) or not isinstance(multiplier, (int, float)) or not math.isfinite(multiplier) or multiplier <= 0:
            raise ValueError("每个映射节点必须填写正数 multiplier")
        roles, services = node.get("roles", []), node.get("services", [])
        if not isinstance(roles, list) or not set(roles) <= {"interactive", "bulk"}:
            raise ValueError("roles 仅支持 interactive、bulk")
        if not isinstance(services, list) or not set(services) <= service_ids | ({"*"} if demo else set()):
            raise ValueError("services 需要填写有效服务 ID，正式配置禁止通配符")
        if node.get("qualified") is True:
            try:
                qualified_on = date.fromisoformat(str(node["qualified_on"]))
            except (KeyError, ValueError):
                raise ValueError("已验收节点必须填写 qualified_on 日期") from None
            if qualified_on > date.today():
                raise ValueError("验收日期不能位于未来")
        aliases.add(alias)
        references.add((key, name))
        pools[key][name]["name"] = alias

    blocked_sources = set(settings.get("policy", {}).get("blocked_sources", []))
    if block_primary:
        blocked_sources.add("primary")
    if not blocked_sources <= set(sources):
        raise ValueError("blocked_sources 引用了不存在的订阅")
    # 未参加自动池的节点保留完整手动目录，使用独立名称空间防止跨订阅重名。
    all_nodes = []
    for key, pool in pools.items():
        for original, proxy in pool.items():
            if (key, original) not in references:
                proxy["name"] = f"{key}::{original}"
            if key not in blocked_sources:
                all_nodes.append(proxy)

    config = copy.deepcopy(base or {})
    source_hosts = {}
    for source in sources.values():
        for hostname, address in source.get("hosts", {}).items():
            if hostname in source_hosts and source_hosts[hostname] != address:
                raise ValueError("不同订阅包含冲突的 hosts 映射，请先在本机核对")
            source_hosts[hostname] = address
    if source_hosts:
        config["hosts"] = {**source_hosts, **config.get("hosts", {})}
    for key in ["proxies", "proxy-groups", "proxy-providers", "rule-providers", "rules"]:
        config.pop(key, None)
    config.update({"mixed-port": config.get("mixed-port", 7897), "allow-lan": False,
                   "bind-address": "127.0.0.1", "mode": "rule", "log-level": "warning",
                   "proxies": all_nodes, "proxy-groups": [], "proxy-providers": {}, "rules": []})
    payloads = {}

    def candidates(key, role=None, service=None):
        if key in blocked_sources:
            return []
        return [pools[key][node["name"]] for node in nodes
                if node["source"] == key and node.get("qualified") is True and node["multiplier"] <= 1
                and (role is None or role in node.get("roles", []))
                and (service is None or service in node.get("services", []) or (demo and "*" in node.get("services", [])))]

    def make_group(identifier, name, keys, url=None, status=None, interval=180, role=None, service=None, automatic=True):
        providers, manual = [], []
        # 没有 policy 的旧设置保持原行为；启用后按实测地区跨来源排序。
        if settings.get("policy") and automatic:
            metadata = [node for node in nodes if node["source"] in keys and node.get("qualified") is True
                        and node["multiplier"] <= 1 and node["source"] not in blocked_sources
                        and (role is None or role in node.get("roles", []))
                        and (service is None or service in node.get("services", []) or (demo and "*" in node.get("services", [])))]
            ordered, _ = select_candidates(metadata, service or identifier, keys, settings["policy"])
            stable = bool(service and settings["policy"].get("stable_ai", False))
            if stable:
                preference = settings["policy"].get("services", {}).get(service, {})
                ordered = limited_candidates(ordered, preference.get("preferred_country", ordered[0].get("exit_country", "") if ordered else ""),
                                             preference.get("preferred_exit_id"), 4)
                interval = 60
            for index, node in enumerate(ordered):
                provider = f"{identifier}-{node['source']}-{index}"
                providers.append(provider)
                payloads[f"providers/{provider}.yaml"] = {"proxies": [pools[node["source"]][node["name"]]]}
                config["proxy-providers"][provider] = {
                    "type": "file", "path": f"providers/{provider}.yaml",
                    "health-check": {"enable": True, "url": url, "interval": interval,
                                     "timeout": 5000, "lazy": interval != 60, "expected-status": status},
                }
            automatic_name = name + " 候选" if stable else name
            config["proxy-groups"].append({"name": automatic_name, "type": "fallback", "use": providers,
                "url": url, "interval": interval, "timeout": 5000,
                "lazy": interval != 60, "expected-status": status} if providers else
                {"name": automatic_name, "type": "select", "proxies": ["REJECT"]})
            if stable:
                config["proxy-groups"].append({"name": name, "type": "select", "proxies": [automatic_name,
                    *[f"全部节点 {key}" for key in keys], "REJECT"]})
            return
        for key in keys:
            selected = candidates(key, role, service)
            if not selected:
                continue
            if automatic:
                provider = f"{identifier}-{key}"
                providers.append(provider)
                payloads[f"providers/{provider}.yaml"] = {"proxies": selected}
                config["proxy-providers"][provider] = {
                    "type": "file", "path": f"providers/{provider}.yaml",
                    "health-check": {"enable": True, "url": url, "interval": interval,
                                     "timeout": 5000, "lazy": interval != 60, "expected-status": status},
                }
            else:
                manual.extend(proxy["name"] for proxy in selected)
        if not providers and not manual:
            config["proxy-groups"].append({"name": name, "type": "select", "proxies": ["REJECT"]})
        elif automatic:
            config["proxy-groups"].append({"name": name, "type": "fallback", "use": providers,
                "url": url, "interval": interval, "timeout": 5000,
                "lazy": interval != 60, "expected-status": status})
        else:
            config["proxy-groups"].append({"name": name, "type": "select", "proxies": manual})

    for service in SERVICES:
        make_group(service["id"], service["name"], ["primary", "bulk"],
                   service.get("health"), service.get("head"), service.get("interval", 180),
                   service=service["id"], automatic=service["auto"])
    for index, (name, (url, status)) in enumerate(INTERACTIVE.items()):
        make_group(f"interactive-{index}", name, ["bulk", "primary"], url, status, role="interactive")
    for index, (name, (url, status)) in enumerate(CAPACITY.items()):
        make_group(f"capacity-{index}", name, ["bulk"], url, status, role="bulk")
    for key, pool in pools.items():
        manual = [proxy["name"] for proxy in pool.values()] if key not in blocked_sources else []
        config["proxy-groups"].append({"name": f"全部节点 {key}", "type": "select", "proxies": manual or ["REJECT"]})

    rules = config["rules"]
    for network in ["127.0.0.0/8", "10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "169.254.0.0/16"]:
        rules.append(f"IP-CIDR,{network},DIRECT,no-resolve")
    for network in ["::1/128", "fc00::/7", "fe80::/10"]:
        rules.append(f"IP-CIDR6,{network},DIRECT,no-resolve")
    # 精确下载主机先于 AI 父域；AI 专用主机先于 GitHub 等普通父域。
    for target, hosts in ROUTES["exact"].items():
        rules.extend(f"DOMAIN,{host},{target}" for host in hosts)
    for service in SERVICES:
        rules.extend(f"DOMAIN,{host},{service['name']}" for host in service.get("domains", []))
        rules.extend(f"DOMAIN-SUFFIX,{host},{service['name']}" for host in service.get("suffixes", []))
    for target, hosts in ROUTES["suffix"].items():
        target = "DIRECT" if target == "国内直连" else target
        rules.extend(f"DOMAIN-SUFFIX,{host},{target}" for host in sorted(hosts, key=lambda value: -len(value)))
    rules.append("MATCH,通用海外")
    return config, payloads


def build(settings_path, output, demo=False, block_primary=False):
    path = Path(settings_path).resolve()
    settings = read_yaml(path)
    sources = {key: read_yaml(path.parent / value) for key, value in settings.get("sources", {}).items()}
    base = read_yaml(path.parent / settings["base"]) if settings.get("base") else None
    config, payloads = generate(settings, sources, base, demo, block_primary)
    output = Path(output).resolve()
    # 仅写入被忽略目录；后台任务使用自己的 local/ 子目录，避免覆盖演示产物。
    if output != (ROOT / "output").resolve() and (ROOT / "local").resolve() not in output.parents:
        raise ValueError("输出目录必须为本项目 output/ 或被忽略的 local/ 内的独立目录")
    output.mkdir(parents=True, exist_ok=True)
    for relative, data in {**payloads, "config.yaml": config}.items():
        target = output / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")
    print(f"已生成：{len(config['proxy-groups'])} 个组，{len(payloads)} 个独立来源，{len(config['rules'])} 条规则")
    return config


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="从本机节点导出和逐服务验收记录生成 Mihomo 分流配置")
    parser.add_argument("--settings", default=str(ROOT / "local/settings.yaml"))
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--block-primary", action="store_true", help="移除主订阅自动候选并关闭其手动目录")
    arguments = parser.parse_args()
    try:
        build(arguments.settings, ROOT / "output", arguments.demo, arguments.block_primary)
    except ValueError as error:
        parser.exit(1, f"生成失败：{error}\n")

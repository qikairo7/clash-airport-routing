import argparse
import csv
import json
import unicodedata
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from xml.etree import ElementTree as ET

from build import CAPACITY, INTERACTIVE, ROOT, SERVICES, generate, read_yaml

SVG = "http://www.w3.org/2000/svg"
ET.register_namespace("", SVG)
DESTINATION = ROOT / "docs/diagrams"
COLORS = ["#2563eb", "#0f766e", "#7c3aed", "#b45309"]
CHAPTERS = [
    ("02-ai-core", "AI 对话与开发入口", ["chatgpt", "openai", "claude", "gemini", "aistudio", "antigravity"], None),
    ("03-ai-coding", "AI 编程工具", ["copilot", "cursor", "opencode"], None),
    ("04-ai-search", "AI 搜索与聚合", ["perplexity", "grok", "mscopilot", "you", "kagi", "character"], None),
    ("05-ai-models", "AI 模型与抓取 API", ["mistral", "openrouter", "replicate", "firecrawl"], None),
    ("06-ai-media", "AI 图像与视频", ["runway", "stability", "recraft", "muse"], None),
    ("07-ai-manual", "AI 手动服务", [service["id"] for service in SERVICES if not service["auto"]], None),
    ("08-development", "开发与 GitHub API", ["开发", "GitHub API"], None),
    ("09-social", "社交与 Telegram", ["社交", "Telegram"], None),
    ("10-github-files", "GitHub 文件", ["GitHub 文件"], None),
    ("11-packages-exact", "容器与依赖 · 精确主机", ["容器与依赖"], "DOMAIN"),
    ("12-packages-suffix", "容器与依赖 · 后缀", ["容器与依赖"], "DOMAIN-SUFFIX"),
    ("13-media", "媒体与下载", ["媒体与下载"], None),
    ("14-domestic", "国内域名直连", ["DIRECT"], "DOMAIN-SUFFIX"),
    ("15-local-default", "局域网与最终兜底", ["DIRECT", "通用海外"], "network"),
]


@dataclass
class Node:
    lines: list
    children: list = field(default_factory=list)
    rule: dict | None = None


def wrap(text, width):
    # 按显示宽度换行，完整域名只换行不截断。
    lines, current, size = [], "", 0
    for character in text:
        step = 2 if unicodedata.east_asian_width(character) in {"W", "F"} else 1
        if current and size + step > width:
            lines.append(current)
            current, size = "", 0
        current += character
        size += step
    if current:
        lines.append(current)
    return lines


def line_groups(node, depth):
    widths = [17, 26, 18, 83]
    return [line for text in node.lines for line in wrap(text, widths[depth])]


def height(node, depth=0):
    own = len(line_groups(node, depth)) * 22 + 18
    children = sum(height(child, depth + 1) for child in node.children)
    return max(own, children)


def element(parent, tag, **attributes):
    return ET.SubElement(parent, f"{{{SVG}}}{tag}", {key.replace("_", "-"): str(value) for key, value in attributes.items()})


def text(parent, x, y, content, color="#172033", size=16, weight="400"):
    element(parent, "text", x=x, y=y, fill=color, font_size=size, font_weight=weight).text = content


def brace(parent, x, top, bottom, color):
    middle = (top + bottom) / 2
    radius = min(12, (bottom - top) / 5)
    path = (
        f"M {x + 18} {top} Q {x + 7} {top} {x + 7} {top + radius} "
        f"L {x + 7} {middle - radius} Q {x + 7} {middle} {x} {middle} "
        f"Q {x + 7} {middle} {x + 7} {middle + radius} "
        f"L {x + 7} {bottom - radius} Q {x + 7} {bottom} {x + 18} {bottom}"
    )
    element(parent, "path", d=path, fill="none", stroke=color, stroke_width="1.8", data_brace="true")


def draw_node(parent, node, top, depth=0, color=COLORS[0]):
    coordinates = [28, 208, 458, 644]
    braces = [180, 426, 612]
    total = height(node, depth)
    lines = line_groups(node, depth)
    center = top + total / 2
    group = element(parent, "g", data_depth=depth)
    if node.rule:
        group.set("data-rule-index", str(node.rule["index"]))
        group.set("data-rule", node.rule["raw"])
        element(group, "title").text = node.rule["raw"]
    for index, line in enumerate(lines):
        is_first = index == 0
        text(group, coordinates[depth], center - (len(lines) - 1) * 11 + index * 22,
             line, color if depth < 3 and is_first else "#475569" if not is_first else "#172033",
             17 if depth < 3 and is_first else 15, "600" if is_first else "400")
    if node.children:
        stack = sum(height(child, depth + 1) for child in node.children)
        cursor = top + (total - stack) / 2
        brace(group, braces[depth], cursor + 5, cursor + stack - 5, color)
        for child in node.children:
            draw_node(group, child, cursor, depth + 1, color)
            cursor += height(child, depth + 1)


def render_svg(tree, title, subtitle):
    body_height = height(tree)
    canvas = ET.Element(f"{{{SVG}}}svg", {
        "width": "1280", "height": str(body_height + 132), "viewBox": f"0 0 1280 {body_height + 132}",
        "role": "img", "aria-labelledby": "title description",
        "font-family": "Arial, Microsoft YaHei, sans-serif",
    })
    element(canvas, "title", id="title").text = title
    element(canvas, "desc", id="description").text = subtitle + "。从左向右的大括号表示整体与局部的包含关系。"
    element(canvas, "rect", x=0, y=0, width=1280, height=body_height + 132, fill="#ffffff")
    text(canvas, 28, 32, title, size=23, weight="600")
    text(canvas, 28, 58, subtitle, color="#475569", size=14)
    for x, label in zip([28, 208, 458, 644], ["整体", "分类 / 服务组", "结构拆解", "完整规则 / 设计理由"]):
        text(canvas, x, 91, label, color="#64748b", size=13)
    draw_node(canvas, tree, 109)
    return ET.tostring(canvas, encoding="unicode") + "\n"


def collect_rules():
    settings = read_yaml(ROOT / "examples/settings.example.yaml")
    sources = {key: read_yaml(ROOT / "examples" / value) for key, value in settings["sources"].items()}
    config, _ = generate(settings, sources, demo=True)
    result = []
    for index, fields in enumerate(csv.reader(config["rules"]), 1):
        kind = fields[0]
        if kind not in {"DOMAIN", "DOMAIN-SUFFIX", "IP-CIDR", "IP-CIDR6", "MATCH"}:
            raise ValueError(f"导图尚未支持规则类型：{kind}")
        result.append({"index": index, "kind": kind, "value": fields[1] if kind != "MATCH" else "所有未命中请求",
                       "target": fields[2] if kind != "MATCH" else fields[1], "raw": config["rules"][index - 1]})
    return result


def policy(name):
    if name.startswith("AI "):
        return "primary 优先；bulk 合格备用"
    if name in INTERACTIVE:
        return "bulk 优先；primary 低倍率备用"
    if name in CAPACITY:
        return "仅 bulk 容量候选"
    return "DIRECT：不经过机场候选"


def group_node(name, rules, notes):
    kinds = {"DOMAIN": "精确域名", "DOMAIN-SUFFIX": "域名后缀", "IP-CIDR": "IPv4 网段", "IP-CIDR6": "IPv6 网段", "MATCH": "最终兜底"}
    explanations = {"DOMAIN": "仅匹配此主机，位于普通父域之前。", "DOMAIN-SUFFIX": "匹配本域与子域；精确例外先匹配。",
                    "IP-CIDR": "回环或局域网直连；no-resolve 不主动解析。", "IP-CIDR6": "IPv6 回环或局域网直连；no-resolve。",
                    "MATCH": "前面所有规则均未命中时采用通用海外。"}
    branches = [Node(["设计理由"], [Node([notes["groups"][name]])])]
    for kind in kinds:
        selected = [rule for rule in rules if rule["kind"] == kind]
        if selected:
            leaves = [Node([f"#{rule['index']:03d} {rule['value']}", "理由：" + notes["rules"].get(rule["value"], explanations[kind])], rule=rule) for rule in selected]
            branches.append(Node([f"{kinds[kind]} · {len(selected)} 条", kind], leaves))
    service = next((item for item in SERVICES if item["name"] == name), None)
    if service:
        description = [name, *policy(name).split("；"), "已验收；倍率 ≤ 1", "自动 fallback" if service["auto"] else "手动 select"]
        checks = ([f"HEAD 预期 {service['head']}；每 {service.get('interval', 180)} 秒", service["health"], "匿名检查与已登录业务分别验收。"]
                  if service["auto"] else ["未定义自动检查；选择对应服务的合格候选。"])
        branches.append(Node(["检查与资格"], [Node(checks)]))
    else:
        description = [name, policy(name)]
        if name in INTERACTIVE:
            description += ["已验收；倍率 ≤ 1", "roles: interactive"]
        elif name in CAPACITY:
            description += ["已验收；倍率 ≤ 1", "roles: bulk"]
    return Node(description, branches)


def overview():
    return Node(["多订阅分流"], [
        Node(["AI · 30 个服务组"], [Node(["23 个自动", "7 个手动"], [Node(["按服务取得资格；倍率不超过 1。", "primary 优先，bulk 逐服务合格候选备用。"])]),
                                   Node(["专属资源与认证"], [Node(["精确主机和服务父域分别列出。", "共享身份主机按实际业务复测。"])])]),
        Node(["互动 · 5 个组"], [Node(["开发 / GitHub API", "社交 / Telegram", "通用海外"], [Node(["bulk 优先；primary 低倍率备用。", "重视互动响应与业务连通；API 状态另判。"])])]),
        Node(["容量 · 3 个组"], [Node(["GitHub 文件", "容器与依赖", "媒体与下载"], [Node(["仅 bulk 自动候选，控制主订阅消耗。", "精确下载主机先于 AI 和普通父域。"])])]),
        Node(["DIRECT"], [Node(["国内域名", "回环与局域网"], [Node(["明确匹配才直连；保留本机网络访问。", "公开模板没有完整国内 IP 规则库。"])])]),
        Node(["全部节点目录"], [Node(["primary / bulk", "temporary"], [Node(["保留高倍率、未验收和临时节点的手动入口。", "选择目录不自动改变既有业务组选路。"])])]),
        Node(["规则首匹配"], [Node(["局域网先匹配", "精确普通主机", "AI 主机与父域", "普通与国内后缀", "最终 MATCH"], [Node(["规则按生成序号从小到大匹配。", "某一条命中后停止；图按分类展示。"])])]),
    ])


def candidate_tree():
    return Node(["订阅全部节点"], [
        Node(["来源"], [Node(["primary"], [Node(["AI 优先；普通互动备用；不承担容量自动池。"])]),
                       Node(["bulk"], [Node(["AI 备用、普通互动主力、下载容量。"])]),
                       Node(["temporary"], [Node(["仅手动目录；临近到期不加入自动池。"])])]),
        Node(["服务资格"], [Node(["qualified 与日期"], [Node(["真实测量后填写；未验收节点留手动目录。"])]),
                          Node(["multiplier ≤ 1"], [Node(["自动池的成本门槛；不能将真实 5 倍率填成 1。"])]),
                          Node(["services"], [Node(["按服务 ID 列出资格，正式配置禁止 *。", "一个节点通过多项后可进入多个服务池。"])]),
                          Node(["roles"], [Node(["interactive 决定互动资格，bulk 决定容量资格。", "用途资格与 AI 服务资格分别填写。"])])]),
        Node(["选择机制"], [Node(["自动服务"], [Node(["每个服务与来源独立 provider 检查。", "同来源沿 nodes 顺序排列；fallback 按顺序选可用候选。"])]),
                           Node(["手动 AI"], [Node(["select 选择逐服务合格、低倍率候选。"])]),
                           Node(["没有合格候选"], [Node(["select 仅包含 REJECT；用户所需业务不能据此宣布可用。"])])]),
        Node(["故障与额度"], [Node(["备用切换"], [Node(["只影响新连接；既有连接需单独处理。"])]),
                           Node(["block-primary"], [Node(["移除主来源自动候选和手动目录；需重建、部署。", "公开生成器没有自动账单监控。"])])]),
    ])


def artifacts():
    notes = json.loads((ROOT / "catalog/diagram-notes.json").read_text(encoding="utf-8"))
    rules = collect_rules()
    required_groups = {service["name"] for service in SERVICES} | set(INTERACTIVE) | set(CAPACITY) | {"DIRECT"}
    if set(notes["groups"]) != required_groups:
        raise ValueError("导图设计说明与当前服务组不一致")
    if not set(notes["rules"]) <= {rule["value"] for rule in rules}:
        raise ValueError("精确例外的设计说明没有对应实际规则")
    by_id = {service["id"]: service["name"] for service in SERVICES}
    data = {"01-overview.svg": render_svg(overview(), "多订阅分流 · 单向括号总览", f"公开模板 {len(rules)} 条规则；从整体拆解到分类、部分与设计理由")}
    manifest, used, whole = [], [], []
    for slug, title, keys, kind in CHAPTERS:
        targets = [by_id.get(key, key) for key in keys]
        selected = [rule for rule in rules if rule["target"] in targets
                    and (kind is None or rule["kind"] == kind or kind == "network" and rule["kind"] in {"IP-CIDR", "IP-CIDR6", "MATCH"})]
        if not selected:
            raise ValueError(f"导图章节没有对应规则：{slug}")
        groups = [group_node(name, [rule for rule in selected if rule["target"] == name], notes) for name in targets if any(rule["target"] == name for rule in selected)]
        tree = Node([title], groups)
        filename = f"{slug}.svg"
        data[filename] = render_svg(tree, title + " · 完整规则", f"{len(selected)} 条规则；编号对应实际首匹配顺序；大括号只表示结构包含")
        manifest.append({"file": filename, "title": title, "rule_indices": [rule["index"] for rule in selected]})
        used.extend(rule["index"] for rule in selected)
        whole.extend(groups)
    if Counter(used) != Counter(rule["index"] for rule in rules):
        raise ValueError("规则图存在遗漏、重复或未分类规则")
    data["16-node-policy.svg"] = render_svg(candidate_tree(), "节点选择与额度 · 单向括号图", "来源、服务资格、用途资格、选择机制、故障与额度分别拆解")
    data["17-all-rules.svg"] = render_svg(Node(["全部公开规则", f"{len(rules)} 条"], whole), "全部公开规则 · 单向括号图", "每条规则完整展开；可按原尺寸阅读，也可按章节查看")
    report = {"rule_count": len(rules), "rule_types": dict(Counter(rule["kind"] for rule in rules)),
              "service_groups": len(SERVICES), "business_groups": len(INTERACTIVE) + len(CAPACITY),
              "rules": rules, "chapters": manifest, "coverage": "each rule appears exactly once across chapters"}
    data["manifest.json"] = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    return data


def main():
    parser = argparse.ArgumentParser(description="从公开生成器导出完整规则的单向括号图；不读取私人订阅")
    parser.add_argument("--check", action="store_true", help="核对已提交图表与当前规则是否一致，不写文件")
    args = parser.parse_args()
    files = artifacts()
    if args.check:
        for name, content in files.items():
            path = DESTINATION / name
            if not path.exists() or path.read_text(encoding="utf-8") != content:
                raise SystemExit(f"导图未同步，请运行 tools/render_rule_diagrams.py：{name}")
        print(f"单向括号图检查通过：{len(files) - 1} 张 SVG，全部规则逐条覆盖")
    else:
        DESTINATION.mkdir(parents=True, exist_ok=True)
        for name, content in files.items():
            (DESTINATION / name).write_text(content, encoding="utf-8", newline="\n")
        print(f"已生成 {len(files) - 1} 张单向括号图；规则清单见 docs/diagrams/manifest.json")


if __name__ == "__main__":
    main()

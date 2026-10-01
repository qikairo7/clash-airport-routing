# 完整单向括号导图

从左向右拆解：**整体 → 分类 / 服务组 → 结构拆解 → 全部具体规则与设计理由**。大括号表示包含关系，关键词按列对齐。规则编号表示执行优先级，图上的分类位置不是规则执行顺序。

当前公开生成器产生 **185 条规则**，下方 14 个规则章节中每条出现一次：`DOMAIN` 49 条、`DOMAIN-SUFFIX` 127 条、IPv4 / IPv6 本地网段 8 条、`MATCH` 1 条。30 个 AI 组、8 个普通业务组及 DIRECT 全部覆盖。

规则来自 `tools/build.py` 对公开示例的实际生成结果，设计说明来自 `catalog/diagram-notes.json`。图中逐条保留序号、完整域名或网段、目标服务组、匹配类型与理由；服务组同时写明出口顺序、自动 / 手动方式、资格与 AI 检查条件。

## 阅读入口

- [单张完整图：全部 185 条规则](diagrams/17-all-rules.svg)。打开原图可放大阅读，文字是矢量格式。
- [本机浏览页](rule-diagrams.html)。克隆后打开，选择一个章节或全部规则；页面与图片都在仓库内，离线可用。
- [节点选择与额度结构](diagrams/16-node-policy.svg)。高倍率、未验收和临时节点的用途也在图中。
- [机器可核对的规则清单](diagrams/manifest.json)。包含原始规则、生成序号与章节覆盖关系。

私人环境可能有更多规则；Agent 需要读取实际运行态并在本机生成对应导图，不能用公开模板的覆盖数量代替本机验收。

## 整体结构

[![多订阅分流的单向括号总览](diagrams/01-overview.svg)](diagrams/01-overview.svg)

## AI 服务的全部规则

这些组按服务分别取得资格。自动组为 primary 优先、bulk 合格备用；手动组由使用者明确选择逐服务合格候选。自动池倍率不超过 1，匿名状态与实际账号业务分别验收。

<details>
<summary>02 · AI 对话与开发入口：ChatGPT / Codex、OpenAI API、Claude、Gemini、AI Studio、Antigravity</summary>

[![AI 对话与开发入口的全部规则和理由](diagrams/02-ai-core.svg)](diagrams/02-ai-core.svg)

</details>

<details>
<summary>03 · AI 编程工具：GitHub Copilot、Cursor、OpenCode</summary>

[![AI 编程工具的全部规则和理由](diagrams/03-ai-coding.svg)](diagrams/03-ai-coding.svg)

</details>

<details>
<summary>04 · AI 搜索与聚合：Perplexity、Grok、Microsoft Copilot、You、Kagi、Character</summary>

[![AI 搜索与聚合的全部规则和理由](diagrams/04-ai-search.svg)](diagrams/04-ai-search.svg)

</details>

<details>
<summary>05 · AI 模型与抓取 API：Mistral、OpenRouter、Replicate、Firecrawl</summary>

[![AI 模型与抓取 API 的全部规则和理由](diagrams/05-ai-models.svg)](diagrams/05-ai-models.svg)

</details>

<details>
<summary>06 · AI 图像与视频：Runway、Stability、Recraft、Muse</summary>

[![AI 图像与视频的全部规则和理由](diagrams/06-ai-media.svg)](diagrams/06-ai-media.svg)

</details>

<details>
<summary>07 · AI 手动服务：Cerebras、Groq、Poe、Midjourney、ElevenLabs、Phind、JetBrains</summary>

[![AI 手动服务的全部规则和理由](diagrams/07-ai-manual.svg)](diagrams/07-ai-manual.svg)

</details>

## 普通业务的全部规则

开发、API 与社交等互动组为 bulk 优先、primary 低倍率备用；文件、镜像、软件包和媒体的自动池仅使用 bulk。每条精确例外和父域后缀都在图中展开。

<details>
<summary>08 · 开发与 GitHub API</summary>

[![开发与 GitHub API 的全部规则和理由](diagrams/08-development.svg)](diagrams/08-development.svg)

</details>

<details>
<summary>09 · 社交与 Telegram</summary>

[![社交与 Telegram 的全部规则和理由](diagrams/09-social.svg)](diagrams/09-social.svg)

</details>

<details>
<summary>10 · GitHub 文件：Raw、源码、Releases、对象与资源</summary>

[![GitHub 文件的全部规则和理由](diagrams/10-github-files.svg)](diagrams/10-github-files.svg)

</details>

<details>
<summary>11 · 容器与依赖：所有精确主机</summary>

[![容器与依赖精确主机的全部规则和理由](diagrams/11-packages-exact.svg)](diagrams/11-packages-exact.svg)

</details>

<details>
<summary>12 · 容器与依赖：所有域名后缀</summary>

[![容器与依赖后缀的全部规则和理由](diagrams/12-packages-suffix.svg)](diagrams/12-packages-suffix.svg)

</details>

<details>
<summary>13 · 媒体与下载：视频、直播与云盘</summary>

[![媒体与下载的全部规则和理由](diagrams/13-media.svg)](diagrams/13-media.svg)

</details>

## 直连与最终兜底的全部规则

<details>
<summary>14 · 国内域名：全部明确直连后缀</summary>

[![国内域名直连的全部规则和理由](diagrams/14-domestic.svg)](diagrams/14-domestic.svg)

</details>

<details>
<summary>15 · 回环、局域网、IPv6 与最后一条 MATCH</summary>

[![本地网段与最终兜底的全部规则和理由](diagrams/15-local-default.svg)](diagrams/15-local-default.svg)

</details>

## 节点资格、选择与额度

[![节点选择与额度的单向括号拆解](diagrams/16-node-policy.svg)](diagrams/16-node-policy.svg)

同一节点可以进入多个已取得资格的服务池；没有合格候选的组生成 `REJECT`。完整手动目录保留全部来源节点，但选择该目录不会自动改变既有业务组选路。`--block-primary` 需要重建、部署并处理旧连接，详见[额度保护](quota-and-failover.md)。

## 首匹配与规则边界

读取叶节点上的 `#001` 等序号判断首匹配顺序：局域网 → 普通精确主机 → AI 主机及后缀 → 普通与国内后缀 → MATCH。例如 Cursor 更新包、GitLab Registry、JetBrains 安装包、X 视频在父域之前归入容量用途；Copilot 专属代理和 Antigravity daily API 保留 AI 用途。

同一个 HTTPS 主机内的聊天、附件和下载不能靠域名规则拆分。共享云、身份和 CDN 主机的采用范围写在对应规则理由里；更多限制见[规则说明](rules.md)。

## 更新与完整性检查

修改 `catalog/services.json`、`catalog/routes.json`、生成规则逻辑或设计说明后执行：

```powershell
.\.venv\Scripts\python.exe tools/render_rule_diagrams.py
.\.venv\Scripts\python.exe tools/render_rule_diagrams.py --check
```

脚本只读取公开示例和目录，使用标准库生成 SVG；不读取用户订阅，也不访问网络。`--check` 不写文件，逐字核对已提交图与当前生成结果；遗漏、重复或未分类规则会直接报错。公开 CI 同样执行检查，防止图与配置不同步。

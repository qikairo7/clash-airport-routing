# Clash 多订阅分流实践

为一台电脑组合多份 Clash / Mihomo 订阅，按服务选择出口：AI 使用逐服务验收的低倍率候选，开发与社交优先容量订阅，文件与镜像下载使用容量线路。

**把这个仓库交给能访问本机文件和终端的 Agent，让它读取已有订阅、测量节点、生成配置、部署到客户端并验证实际分流。** 下方提示词是使用入口；生成器、分类目录和文档是 Agent 完成任务的依据。

[Agent 部署指南](docs/agent-deployment.md) · [完整单向括号导图](docs/routing-mindmap.md) · [使用文档](docs/README.md) · [分流规则](docs/rules.md) · [贡献指南](CONTRIBUTING.md) · [MIT 许可证](LICENSE)

## 复制给 Agent：在我的电脑上部署

将下面整段发给 Codex、Claude Code、DSH 或其他具备本机文件与终端能力的 Agent。已有 Clash / Mihomo 客户端和订阅时，Agent 从本机读取；尚无订阅时，只需补充套餐用途、额度和预算等非敏感信息。需要至少两份主力来源的本机 YAML，才能使用当前生成器。

```text
请按照 https://github.com/qikairo7/clash-airport-routing 在我的电脑上完成多订阅分流部署。

先读取仓库 README.md、docs/agent-deployment.md、docs/routing-mindmap.md，
再读取部署、测量、额度说明、catalog/、examples/settings.example.yaml 和 tools/build.py。
检查本机与仓库适用的 AGENTS.md；已有目录就复用并核对版本，保留我的改动。

我授权你读取本机已有 Clash / Mihomo 客户端、订阅配置和运行状态，
在本机备份后生成配置、导入或更新持久配置、重载并验证业务请求。
完成已授权的步骤，不要只给我命令让我操作，也不要停在演示生成。

从本机识别全部订阅和节点，只输出脱敏别名、倍率、额度、用途和验证结果。
不要让我在聊天中提供订阅链接、服务器、出口 IP、端口、密码、令牌或完整配置。
缺少会影响配置的非敏感信息时一次性询问；已提供的信息直接复用。

按服务与流量成本选择 primary / bulk / temporary，不照搬机场品牌和节点国家名。
为全部节点建立本机清单；隔离测试全部独立候选，至少三轮轻量检查并记录失败和重复入口，
对准备进入自动池的候选至少测三轮取中位数，大文件带宽只测筛选后的低倍率候选。
结合 Net.Coffee https://ip.net.coffee/ 与 https://ip.net.coffee/link/，
分别核验 AI 地区、出口稳定性、匿名接口和已有登录会话里的真实业务。
同一服务保留多个合格候选与备用来源；不把通用测速或信誉分数当作业务成功。
晚高峰单独测一轮；当前不在时段内就明确记录待验收，不伪造结果。

将真实订阅、节点映射、备份与测量结果保留在被忽略的本机目录。
根据证据填写 local/settings.yaml，正式配置禁止 services: ['*']。
运行离线测试、生成器和 Mihomo -t，部署 config.yaml 及全部被引用的 providers/。
Clash Verge Rev 要修改持久配置并核对实际内核工作目录，不能仅覆盖生成文件。
需要后台保护时再读取 docs/policy-monitoring.md，按实测出口、证据时效和账单基线启用 policy。
保持规则模式，核对国内 AI 的 DIRECT 匹配；后台普通候选调整等现有连接结束后部署，
不要在正在生成或下载时反复完整重载。额度锁定仍立即执行并关闭受保护来源的旧连接。
核对运行态组、provider 数量、规则顺序与实际业务的匹配链，验证故障备用和恢复。

交付从左向右的本机单向括号导图，逐条展示实际规则、服务与候选节点的包含关系，
保留规则顺序、匹配类型、完整域名或网段、目标策略和设计理由，不用放射式布局。
同时交付服务到出口表、节点资格与未通过原因，
并记录实际加载证据、复测结果、倍率成本、更新步骤和恢复办法。
匿名检测、已登录生成、长连接、附件和晚高峰分别注明验证范围。
不购买套餐、不公开本机资料；新增付费操作或扩大系统网络设置范围先说明。
遇到权限或客户端能力限制，明确报告具体阻塞，不宣称部署完成。
```

Agent 的逐步执行、文件契约与完成条件见[部署指南](docs/agent-deployment.md)。只有云端仓库权限、无法访问你的电脑的 Agent，可以准备脱敏方案与示例；本机导入与运行验收需要本机执行能力。

## 单向括号导图：整体如何拆成规则

从左向右阅读：**整体 → 分类与服务组 → 精确域名 / 后缀 / 网段 → 每条完整规则及设计理由**。大括号表示整体包含哪些部分；规则编号对应生成器的首匹配顺序。

[![多订阅分流单向括号总览](docs/diagrams/01-overview.svg)](docs/diagrams/01-overview.svg)

当前公开模板 **185 条规则全部进入导图**：49 条精确域名、127 条域名后缀、8 条本地网段和 1 条最终兜底。覆盖 **30 个 AI 组、8 个普通业务组、DIRECT**；每条规则保留完整值、序号、目标组和设计理由。

- [全部规则的单张完整括号图](docs/diagrams/17-all-rules.svg)：185 条规则从整体到局部完整展开，可打开原图放大阅读。
- [按业务阅读的完整导图](docs/routing-mindmap.md)：将同一套完整规则拆成 14 个章节，逐图展开，便于查看。
- [节点选择与额度括号图](docs/diagrams/16-node-policy.svg)：来源、服务资格、用途资格、备用与额度分别拆解。
- [本机导图浏览页](docs/rule-diagrams.html)：克隆仓库后由 Agent 打开，选择章节或完整图，查看原始尺寸；GitHub 上直接阅读上面的图文页面。

公开图由生成器的实际规则自动生成，原图使用 SVG，放大不损失文字。真实机场节点使用本机别名，Agent 根据用户实际运行规则和全部节点清单生成本机括号图；公开 185 条规则不代表某台电脑的完整私人运行配置。

配置按两个维度决定：**请求先匹配服务组，服务组再从符合资格的订阅节点中选择出口**。候选数量与顺序由本机测量决定，多个订阅不会叠加单个连接的带宽。

## 项目能做什么

| 能力 | 公开版实现 |
|---|---|
| 多订阅整合 | 读取两份主力订阅的本机 YAML，可增加一份临时订阅；按唯一别名整理节点 |
| AI 专属分流 | 30 个服务组，其中 23 个自动、7 个手动；每个自动服务与订阅组合独立检查 |
| 开发、社交与下载分流 | 8 个普通业务组；GitHub 页面、API、文件及容器依赖分别归类 |
| 节点使用资格 | 根据本机填写的倍率、验收日期和服务资格选择自动候选；全部来源节点有手动目录 |
| 实测出口排序 | 可选 `policy` 按同出口、同国家、来源与优先级排序，过滤过期证据并合并已确认的重复线路 |
| 后台额度与节点保护 | `tools/watch.py` 持续核算已配置来源的保守用量，隔离连续失败候选；额度锁定移除来源并关闭旧连接 |
| 网络测量 | 用 curl 核对连接复用，记录三轮请求延迟与单连接带宽；失败样本保留 |

**当前公开版的边界：**初始节点资格由使用者测量后填写，生成器不会自动判断“家宽”或出口信誉；没有全量节点扫描器和供应商自动账单采集。后台需要当前账单基线、全部节点倍率与已接入的配置，契约见[后台保护指南](docs/policy-monitoring.md)。已经提供 [Clash Verge 本机适配与中文维护入口](docs/verge-runtime.md)，适配器要求增强脚本满足明确的数据契约；账号生成、附件与晚高峰需要独立验收。

## 快速开始：运行演示

需要 **Python 3.11+**。以下命令使用 Windows PowerShell；项目 Python 依赖由 `requirements.txt` 安装。

```powershell
git clone https://github.com/qikairo7/clash-airport-routing.git
cd clash-airport-routing
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe tools/build.py --settings examples/settings.example.yaml --demo
```

生成结果为 `output/config.yaml` 和 `output/providers/`。**演示节点使用 `.invalid` 域名和演示凭据，不能连接真实网络。** 这一步用于了解文件结构和验证生成流程。

运行离线检查：

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe tools/check_public.py
```

Linux / macOS 可使用 `python3 -m venv .venv` 创建环境，并将后续 Python 命令替换为 `.venv/bin/python`。配置格式已在 Mihomo **v1.19.31** 上核验。

## 接入自己的订阅

按[部署指南](docs/deployment.md)完成本机文件准备、生成、内核加载和实际请求验收：

1. 把订阅的本机导出 YAML 放进 `local/`，创建 `local/settings.yaml`，参考[设置示例](examples/settings.example.yaml)。
2. 将 `demo` 设为 `false`，设置 `sources.primary` 和 `sources.bulk`；`temporary` 可选。文件路径相对于设置文件。
3. 为准备进入自动池的节点填写唯一别名、真实倍率、验收日期及已通过的[服务 ID](catalog/services.json)。正式配置禁止使用 `*` 代替逐服务资格。
4. 生成配置，再用 Mihomo 执行语法检查。整个 `providers/` 目录必须与配置一起部署。
5. 在客户端核对实际运行的组、来源和规则，再复测业务请求。

```powershell
.\.venv\Scripts\python.exe tools/build.py --settings local/settings.yaml
# 将 mihomo 替换为自己的内核程序路径；-d 指定文件来源的工作目录。
mihomo -t -d output -f output/config.yaml
```

`primary` 是优先服务于 AI 的订阅，`bulk` 是承载日常与下载流量的订阅，不绑定任何机场品牌。可选的 `base` 保留 DNS、TUN、hosts 等网络字段；来源中的 hosts 会合并，来源之间冲突时报错，`base.hosts` 可明确覆盖。节点、策略组、来源和规则会重新生成。生成器默认写入 `output/`，客户端加载步骤由[部署指南](docs/deployment.md)说明。

已有设置不含 `policy` 时保持原有候选顺序。启用实测排序和后台保护时，参考[策略示例](examples/settings.policy.example.yaml)与[后台保护指南](docs/policy-monitoring.md)；示例日期不会自动更新，不能代替实际验收。

`policy.stable_ai: true` 使用最多四个候选的 fallback 子组和保留手动入口的 select 业务组。日常选择通过本机接口进行；后台、账单导入、受控重启与恢复使用同一台账。Verge 的自动来源保存已验收参数快照，同名节点参数改变后不继承旧资格；未被业务组使用的 provider 停止后台健康检查。

## 默认如何分流

| 用途 | 自动出口顺序 |
|---|---|
| ChatGPT / Codex、Claude、Gemini、Antigravity 等自动 AI 服务 | 主订阅逐服务合格候选 → 容量订阅逐服务合格候选 |
| 开发文档、GitHub 页面 / Git、GitHub API、X、Telegram | 容量订阅 → 主订阅低倍率备用 |
| GitHub Raw / Releases、容器镜像、软件包、模型文件、媒体 | 容量订阅自动候选 |
| 国内常用站点、局域网 | DIRECT，具体覆盖范围见[规则说明](docs/rules.md) |
| 高倍率、未验收或临时节点 | 各订阅的完整手动目录 |

规则按顺序首匹配：精确下载主机优先于 AI 父域，AI 专用 API 优先于普通平台父域。例如 Cursor 更新包和 Cursor API 分组处理，GitHub Copilot 与 GitHub 文件分组处理。共享云、认证、支付与 CDN 的父域需按具体服务核对。

自动故障切换作用于新连接，已经建立的下载或生成连接无法迁移；检查成功与账号业务可用性分别验收。详细参数见[服务目录](catalog/services.json)、[普通路由目录](catalog/routes.json)和[故障切换说明](docs/quota-and-failover.md)。

## 测量与复验

测量需要 **curl 7.70+** 和运行中的本机代理。默认代理地址为 `http://127.0.0.1:7897`，可通过 `--proxy` 修改。

```powershell
# 三轮测量，核对连接复用并计算中位数。
.\.venv\Scripts\python.exe tools/measure.py --rounds 3
# 晚高峰单独记录一轮。
.\.venv\Scripts\python.exe tools/measure.py --rounds 1 --period evening
```

三轮带宽测量约下载 **30 MB 实际流量**，计费按节点倍率计算。结果写入 `reports/`。工具测量的是当前规则选择的出口；全量节点与 AI 账号验收流程见[测量指南](docs/measurement.md)。

公开 CI 验证生成器、规则边界和样本校验。历史节点测量、匿名接口响应与已登录生成结果分别记录在[案例文档](docs/case-study.md)；每份结果都有其时段和范围。后续规则补充见[2026-10-01 验收记录](docs/upstream-review-2026-10-01.md)。

## 仓库导航

| 位置 | 内容 |
|---|---|
| [`catalog/`](catalog/) | AI 服务与普通业务的分流目录 |
| [`tools/`](tools/) | 配置生成、测量和公开文件检查工具 |
| [`examples/`](examples/) | 使用保留域名的演示订阅与设置 |
| [`tests/`](tests/) | 配置行为、规则边界和测量回归测试 |
| [`docs/`](docs/README.md) | 部署、测量、额度、规则、方案及历史案例 |
| `local/`、`output/`、`reports/` | 本机输入与产物，被 Git 忽略 |

## 贡献、反馈与许可

- 规则补充、缺陷修复和文档改进按[贡献指南](CONTRIBUTING.md)提交；新规则需要来源、正反例及适用的验收结果。
- 普通问题使用[反馈表单](https://github.com/qikairo7/clash-airport-routing/issues/new/choose)；软件安全缺陷使用[私密漏洞报告](https://github.com/qikairo7/clash-airport-routing/security/advisories/new)，处理范围见[安全说明](SECURITY.md)。
- 公开贡献使用最小脱敏示例。真实订阅、账号令牌、节点服务器和运行配置留在本机。
- 本项目原创代码、文档与示例采用 [MIT](LICENSE)，版权署名为 `Copyright (c) 2026 qikairo7`。第三方规则、客户端和服务的来源与许可见 [NOTICE](NOTICE.md)。
- 功能和文档变化记录在[更新记录](CHANGELOG.md)。

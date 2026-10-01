# Clash 多订阅分流实践

为一台电脑组合多份 Clash / Mihomo 订阅，按服务选择出口：AI 使用逐服务验收的低倍率候选，开发与社交优先容量订阅，文件与镜像下载使用容量线路。

项目包含**本地配置生成器、分流目录、测量工具与可复验的实践文档**。适合已经有订阅、希望整理线路用途和流量成本的使用者。订阅在自己的电脑上导出、测量和处理。

[使用文档](docs/README.md) · [分流规则](docs/rules.md) · [实测案例](docs/case-study.md) · [贡献指南](CONTRIBUTING.md) · [问题反馈](https://github.com/qikairo7/clash-airport-routing/issues/new/choose) · [MIT 许可证](LICENSE)

## 项目能做什么

| 能力 | 公开版实现 |
|---|---|
| 多订阅整合 | 读取两份主力订阅的本机 YAML，可增加一份临时订阅；按唯一别名整理节点 |
| AI 专属分流 | 30 个服务组，其中 23 个自动、7 个手动；每个自动服务与订阅组合独立检查 |
| 开发、社交与下载分流 | 8 个普通业务组；GitHub 页面、API、文件及容器依赖分别归类 |
| 节点使用资格 | 根据本机填写的倍率、验收日期和服务资格选择自动候选；全部来源节点有手动目录 |
| 主订阅额度保护 | `--block-primary` 生成移除主订阅的配置；部署和旧连接处理见[额度保护说明](docs/quota-and-failover.md) |
| 网络测量 | 用 curl 核对连接复用，记录三轮请求延迟与单连接带宽；失败样本保留 |

**当前公开版的边界：**节点资格由使用者测量后填写，生成器不会自动判断“家宽”或出口信誉。公开版尚未包含全量节点扫描器、自动账单采集和后台额度保护程序；本机案例的这些能力与公开工具分别记录。

## 快速开始：运行演示

需要 **Python 3.11+**。以下命令使用 Windows PowerShell；项目唯一 Python 依赖由 `requirements.txt` 安装。

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

`primary` 是优先服务于 AI 的订阅，`bulk` 是承载日常与下载流量的订阅，不绑定任何机场品牌。可选的 `base` 保留 DNS、TUN、hosts 等网络字段；节点、策略组、来源和规则会重新生成。生成器写入 `output/`，客户端加载步骤由[部署指南](docs/deployment.md)说明。

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

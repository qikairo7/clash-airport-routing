# 2026-10-01 规则补充与运行验收

## 本轮阅读与版本

重新获取 GitHub 当前默认分支提交和完整文件目录，下载选定的规则、模板、说明及转换脚本，核对 Git 对象与 SHA-256。共核验 322 份文本、15,209,869 字节；三个指定项目的规则和配置文本全部纳入，新增项目按电脑上的相关服务选择。这个数量表示来源文件核验范围，不表示逐条人工审查或逐个服务登录成功。

| 来源 | 核验提交 | 提交时间 UTC | 阅读范围 |
|---|---|---|---|
| [szkane/ClashRuleSet](https://github.com/szkane/ClashRuleSet/tree/2dd1d60558df4276a5c5b7654cbfdae0458f7418) | `2dd1d605` | 2026-09-30 06:45 | 168 份选定文本：分类规则、转换器配置、模板和说明 |
| [Semporia/Clash](https://github.com/Semporia/Clash/tree/0c5a4173628ab5e099f62aab7276c2e1dcf4bd45) | `0c5a4173` | 2026-09-10 03:14 | 59 份：服务 YAML、平台模板和加载关系 |
| [GMOogway/shadowrocket-rules](https://github.com/GMOogway/shadowrocket-rules/tree/aae44de5cc04c41e4d3b4c71e38ddb9a44551c37) | `aae44de5` | 2026-10-01 01:26 | 15 份：模块、factory 输入、脚本及说明 |
| [blackmatrix7/ios_rule_script](https://github.com/blackmatrix7/ios_rule_script/tree/c9b2158695596a1ba866adcf74def8d5ab348e25) | `c9b21586` | 2026-09-29 21:50 | 70 份：OpenAI、开发、Docker、GitHub、模型下载、社交等相关分类 |
| [MetaCubeX/meta-rules-dat](https://github.com/MetaCubeX/meta-rules-dat) | source `4178770b` / meta `c3e7b224` | source 2026-06-05；meta 2026-10-01 01:26 | 7 份源说明及构建文件，另核验生成分支提交 |
| [Loyalsoldier/clash-rules](https://github.com/Loyalsoldier/clash-rules) | source `ab21f1c7` / release `6921063d` | source 2026-07-28；release 2026-09-30 22:40 | 3 份源说明及构建文件，另核验生成分支提交 |

前三个提交与上轮固定版本相同。上轮的格式解析、分类交集和模板加载路径结论仍有版本依据；这轮进一步检查当前首匹配归属及公开模板的遗漏。仓库最新提交不代表每个规则文件近期更新，例如此次读取的 blackmatrix OpenAI / Docker 文件头仍标注 2025-06-06。

## 从三个项目继续吸收的内容

| 来源 | 内容与本机现状 | 本次落实 |
|---|---|---|
| szkane Developer | GCR、Quay、GitLab Registry、Microsoft Registry、JitPack、模型下载已经在本机容量组；公开模板缺少其中一些专门分类 | 同步公开目录，将镜像仓库与源码页面区分；下载例外优先于服务父域 |
| Semporia AI / GitHub / Microsoft | AI 清单中含 GitHub、Hugging Face 和 ModelScope；本机已分别使用文件组、容量组及国内直连 | 增加边界回归测试，确保模型文件不会因为 AI 分类而消耗高信誉出口 |
| GMOogway 三类模块及 factory | 国内、代理、拒绝清单有交集；Shadowrocket 的模块优先级不能直接套用 Mihomo | 保留自定义业务例外的首匹配顺序，继续使用已核验的国内分类；不把混合语法 factory 输入直接拼入配置 |

GMOogway 2026-10-01 README 显示 DIRECT 111,364、PROXY 27,342、REJECT 186,111 条。生成前后内容、重复域名与类别交集不能相加作为有效覆盖数量。Semporia 模板中的文件需要实际被 `rule-providers` / `RULE-SET` 引用才能生效。以上结构经验继续用于本项目的生成与验收。

## 本机实际调整的六项归类

| 主机或后缀 | 调整前 | 调整后 | 依据及作用 |
|---|---|---|---|
| `pkg.dev` | 兜底 | 容器容量组 | [Google Artifact Registry 命名](https://docs.cloud.google.com/artifact-registry/docs/docker/names)：覆盖地区化镜像及语言包主机 |
| `dhi.io` | 兜底 | 容器容量组 | [Docker 当前网络清单](https://docs.docker.com/desktop/enterprise/allow-list/)：Docker Hardened Images |
| Docker 已知 R2 租户的精确主机 | 兜底 | 容器容量组 | [Docker 官方仓库历史问题与维护者修正](https://github.com/docker/docs/issues/21960)；只匹配该租户，不使用整个 R2 父域 |
| `download.todesktop.com` | 兜底 | 容器容量组 | 本项目已有的软件更新分流用途；补齐本机与公开目录差异 |
| `daily-cloudcode-pa.googleapis.com` | 普通海外 | Antigravity 专属组 | [Antigravity 代理项目的实际端点记录](https://github.com/yuaotian/antigravity-proxy/blob/main/README_EN.md)；与现有 sandbox API 使用同一服务策略。来源为第三方项目的自身实现记录 |
| `chatgpt.livekit.cloud` | 两条旧 AI 归类 | ChatGPT Codex 专属组 | [blackmatrix OpenAI 分类](https://github.com/blackmatrix7/ios_rule_script/blob/c9b2158695596a1ba866adcf74def8d5ab348e25/rule/Clash/OpenAI/OpenAI.yaml)；归入已有专属候选和健康检查 |

六条规则替换两条旧归类，8013 条变为 **8017 条**，100 个策略组、50 个显式节点来源保持一致。下载策略继续只使用容量订阅；AI 服务继续使用已筛选的主力与备用候选。配置重载返回 204，内核 PID 不变，累计流量计数连续；DNS、TUN、节点来源和其他字段经结构比较保持一致。

公开模板同时补齐已有本机分类：`gcr.io`、`quay.io`、`registry.gitlab.com`、`mcr.microsoft.com`、`jitpack.io`、JetBrains 下载、GitLab Pages、GitHub Blog、Sourcegraph 等。普通平台页面与镜像下载使用不同策略；共享云租户、普通 `googleapis.com`、无关 `livekit.cloud` 和名称含 registry 的其他网站有反例测试。

## 验收记录

- 公开生成器 14 项测试通过，新增 21 个域名边界样例。
- 正式 Mihomo 语法检查通过；实际规则归属与容量组的候选树分别核验。
- 对 20 个端点各执行三轮 HTTP 请求。16 个具有预期匿名状态的端点全部符合：GitHub 网页 / Raw / API、六项注册表与主要 AI / 社交入口。
- 401 表示注册表或 API 的匿名认证要求；405 表示匿名方法响应，均不等于完整已登录业务成功。
- 另四个根路径单独记录：ToDesktop 400、Docker R2 400、Antigravity daily 404、LiveKit 200；只说明 TLS / HTTP 可达。
- Docker 匿名授权和 alpine 清单返回 200，镜像层的 CloudFront 范围请求返回 206，读取前 64 KiB。本轮实际 CDN 为 `production.cloudfront.docker.com`，没有把 R2 根路径响应写成镜像下载成功。
- TAG 额度保护任务仍运行；本次没有重新筛选订阅节点或执行全部节点测速。

本轮验证针对规则补充与回归。它没有新增已登录模型调用、语音 UDP、晚高峰或单连接带宽验收。HTTP Session 的复用没有用 `num_connects` 计量，因此不作为延迟基准。WebSocket、语音和长连接的要求参考 [OpenAI 网络说明](https://help.openai.com/en/articles/9247338-network-recommendations-for-chatgpt-errors-on-web-and-apps)，网页状态不会替代这些场景。

## 来源更新的处理

MetaCubeX 的 MRS 和 Loyalsoldier 的生成分支提供持续维护的通用规则来源；本轮核验了构建路径与生成版本，本机继续使用已验收的业务规则。来源之间存在复用关系，多个仓库包含同一域名不会被算作多份独立验证。更新应固定提交、比较分类与父子域覆盖、生成候选、验证语法、重载，再验证真实运行首匹配。

节点候选来自用户的三家本地订阅。GitHub 上的公开规则能补充域名分类，无法证明机场节点的倍率、入口独立性、AI 账号可用性或长期质量。候选资格以本机订阅与实际业务测量为依据。

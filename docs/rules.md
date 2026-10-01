# 详细规则与上游审查

## 首匹配顺序

模板按以下顺序生成：局域网 → 精确 API / 文件 / 下载主机 → AI 专用主机及父域 → 国内常用站点和普通服务 → 通用海外。

例如 `downloads.cursor.com` 先走下载；`api.cursor.com` 走 Cursor AI。`copilot-proxy.githubusercontent.com` 先走 Copilot，`raw.githubusercontent.com` 走 GitHub 文件。`video.twimg.com` 先走媒体，其他 X 图片走社交。`api.github.com` 的匿名额度和 GitHub 页面连通分开检查。

`services.json` 定义 30 个 AI 组，其中 23 个自动、7 个手动。Gemini 的特定 Google 登录与 OAuth 主机保留同一 AI 路径，但普通 Google 和全部 `googleapis.com` 没有整体归为 AI。这样的身份域规则可能影响其他 Google 登录，需要按实际使用情况复测。

## 共享域边界

不把整个 `auth0.com`、`sentry.io`、`stripe.com`、`gstatic.com`、`amazonaws.com`、`azure.com` 或 `storage.googleapis.com` 转到 AI。这些域同时服务很多产品。新增依赖要从具体主机和实际请求确认，避免宽泛关键字规则。

域名规则无法区分同一 HTTPS 主机内的聊天、附件和下载路径。本项目不执行 HTTPS 解密，因此同域大文件仍可能使用 AI 出口，需要额度缓冲或手动切换。

本模板没有整进程的浏览器代理规则，没有导入全量广告阻断名单。Telegram 目前公开模板提供域名；实际客户端 IP、IPv6、语音和通话需按 [Telegram 官方网段](https://core.telegram.org/resources/cidr.txt) 更新并验证，再将 IP 规则放在通用兜底之前。公开版不把案例私有网段清单当作长期固定事实。

## 三个仓库如何补充

案例研究固定了以下版本，共读取 240 份文本、14,777,904 字节，解析 393,245 条原始规则记录。原始记录包含重复和生成前后输入，不代表独立生效规则数。

| 上游 | 固定提交 | 获得的补充 |
|---|---|---|
| [szkane/ClashRuleSet](https://github.com/szkane/ClashRuleSet/tree/2dd1d60558df4276a5c5b7654cbfdae0458f7418) | `2dd1d60558df4276a5c5b7654cbfdae0458f7418` | 开发依赖、软件分发、AI 服务分类；转换器 ini 与 Mihomo YAML 的区别 |
| [Semporia/Clash](https://github.com/Semporia/Clash/tree/0c5a4173628ab5e099f62aab7276c2e1dcf4bd45) | `0c5a4173628ab5e099f62aab7276c2e1dcf4bd45` | 规则来源与类别结构、GitHub / Microsoft / AI 的细分 |
| [GMOogway/shadowrocket-rules](https://github.com/GMOogway/shadowrocket-rules/tree/aae44de5cc04c41e4d3b4c71e38ddb9a44551c37) | `aae44de5cc04c41e4d3b4c71e38ddb9a44551c37` | 国内、代理、拒绝三类交集与规则冲突检查 |

szkane 的 `kclash.ini` 是订阅转换器配置，不能直接替换 YAML。其宽泛云域、进程和不适用 URL 规则需要逐项处理。

Semporia 的文件存在不代表其默认配置已经引用：当时的 Clash-Verge 模板没有加载 `AI.yaml`。采用规则前要沿 `rule-providers` 和 `RULE-SET` 确认实际调用路径。

GMOogway 的 factory 输入混合裸域名、`full:`、`ip-cidr:` 等格式，不能直接拼接成 Mihomo rules。当时成品中 DIRECT / PROXY / REJECT 的精确匹配交集分别为 162 / 312 / 128 项；父子域覆盖冲突还需要另查。没有复制整份 18.6 万条拒绝清单。

研究遍历和格式解析了全部文本；对重点分类核对了相关域名、顺序与排除原因，没有逐个登录全部服务或宣称人工逐条审阅 39 万条记录。公开项目不附私人 CSV，也不再分发上游完整规则库，其使用与许可见 [NOTICE](../NOTICE.md)。

## 更新规则的检查顺序

1. 固定上游提交，阅读变化与实际加载路径。
2. 按服务用途分类，排除共享父域、宽泛关键字与客户端不支持语法。
3. 给精确下载 / API 例外安排优先级。
4. 增加真实规则边界测试，运行生成器与 Mihomo `-t`。
5. 对照正式运行的规则顺序并发起实际业务请求。

模板未自动追随上游 main。修改目录后重新构建、部署与验收。

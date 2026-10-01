# 来源、致谢与许可

项目由本机配置实践重新整理，公开的 Python 工具、示例结构、测试与说明采用 MIT 许可。上游仓库、客户端、网站及其规则的许可由各自作者决定；本项目的 MIT 不覆盖它们。

没有打包三个上游的完整规则文件、原始下载、第三方脚本或图片。目录中的域名、公开端点与状态是本项目按用途整理的配置事实；参考上游获得分类线索，实际采用与排除的方法见 [规则说明](docs/rules.md)。若希望复制完整上游清单，请先核验其当前许可与原始来源。

| 来源 | 用途 |
|---|---|
| [foru17/homelab cross-border-network](https://github.com/foru17/homelab/tree/main/skills/cross-border-network) | 分层拓扑、复用连接与单连接测量、按段诊断、人民币 / 美元成本与安全检查的工作流程 |
| [szkane/ClashRuleSet](https://github.com/szkane/ClashRuleSet) | 开发、AI、软件下载类别与规则格式审查 |
| [Semporia/Clash](https://github.com/Semporia/Clash) | 规则来源、平台模板和服务清单审查 |
| [GMOogway/shadowrocket-rules](https://github.com/GMOogway/shadowrocket-rules) | DIRECT / PROXY / REJECT 冲突审查与跨客户端格式差异 |
| [blackmatrix7/ios_rule_script](https://github.com/blackmatrix7/ios_rule_script) | 服务专属主机与下载分类线索；逐文件更新时间核验 |
| [MetaCubeX/meta-rules-dat](https://github.com/MetaCubeX/meta-rules-dat) / [Loyalsoldier/clash-rules](https://github.com/Loyalsoldier/clash-rules) | 构建流程、生成分支和规则版本追溯 |
| [Mihomo](https://github.com/MetaCubeX/mihomo) / [官方文档](https://wiki.metacubex.one/) | 运行内核、file provider、fallback 与语法验证 |
| [Clash Verge Rev](https://github.com/clash-verge-rev/clash-verge-rev) | 案例客户端与持久配置环境 |
| [Net.Coffee](https://ip.net.coffee/) | 当时的出口评分、网页连通、DNS / WebRTC 与远程 Ping 观测 |
| [curl 文档](https://curl.se/docs/manpage.html) | 同进程顺序请求、HTTP/1.1、连接数量和计量字段 |

状态与语义参考：[Mihomo v1.19.31 HEAD 请求](https://github.com/MetaCubeX/mihomo/blob/v1.19.31/adapter/adapter.go)、[fallback 实现](https://github.com/MetaCubeX/mihomo/blob/v1.19.31/adapter/outboundgroup/fallback.go)。AI 网络域参考：[OpenAI 官方说明](https://help.openai.com/en/articles/9247338-network-recommendations-for-chatgpt-errors-on-web-and-apps)、[GitHub Copilot 官方清单](https://docs.github.com/en/copilot/reference/copilot-allowlist-reference)、[VS Code 网络说明](https://code.visualstudio.com/docs/setup/network)。

本项目不售卖订阅，也没有提供订阅购买或推广链接。

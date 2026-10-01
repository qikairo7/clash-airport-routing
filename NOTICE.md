# 来源与许可声明

## 本项目的许可

本项目原创的 Python 工具、配置生成逻辑、测试、说明文档及演示结构采用根目录的 [MIT 许可证](LICENSE)。版权署名为 `Copyright (c) 2026 qikairo7`。复制或再分发这些内容时，应保留许可证要求的版权及许可声明；完整条款以 `LICENSE` 为准。

上游规则库、依赖、客户端和外部服务分别适用自己的许可或使用条款。项目 MIT 许可不替代它们，也不授予第三方服务的账号、订阅或品牌使用权限。

## 采用内容的范围

公开仓库提供自行整理的工具、目录和方法，没有打包上游的完整规则库、原始下载、第三方脚本或图片。`catalog/` 中的公开域名、端点与观测状态按用途归类，采用理由、规则边界与验证范围见[规则说明](docs/rules.md)及[本轮来源审查](docs/upstream-review-2026-10-01.md)。

来源列入下表表示参考关系，不表示本项目可以按 MIT 再许可其全部内容。若引入第三方代码、文本或规则文件，需要核验对应版本的许可与原始来源，保留要求的声明，并记录采用范围。没有明确许可的内容需要另行确认授权。

## 参考来源

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

## 依赖与复用贡献

Python 依赖列于 [requirements.txt](requirements.txt)，按依赖自身的许可安装；本项目没有将其源码打包到仓库。Mihomo、Clash Verge Rev 与 curl 同样由各自项目提供和授权。

贡献者提交原创内容时按本项目 MIT 许可提供；第三方贡献需在 PR 中注明来源、版本、原许可证与需要保留的声明，流程见[贡献指南](CONTRIBUTING.md)。

# 使用文档

从[项目首页](../README.md)复制提示词交给具备本机执行能力的 Agent，按[Agent 部署指南](agent-deployment.md)完成部署。分类、全部具体规则与设计理由见[完整单向括号导图](routing-mindmap.md)。也可以按下表自行阅读与操作。

## 配置与使用

| 想完成的事情 | 阅读内容 |
|---|---|
| 让 Agent 读取订阅、测量、部署并验收 | [Agent 本机部署指南](agent-deployment.md) |
| 逐条查看全部规则、每个服务组与候选的设计原因 | [完整单向括号导图](routing-mindmap.md) |
| 准备两份主力订阅，导出并加载配置 | [部署与更新](deployment.md) |
| 理解 AI、开发、下载的规则顺序 | [详细规则与来源审查](rules.md) |
| 测量节点，填写自动候选资格 | [节点验收与逐段诊断](measurement.md) |
| 控制高倍率流量，理解锁定和备用 | [额度保护与故障切换](quota-and-failover.md) |
| 按实测出口排序、运行后台保护与刷新账单 | [后台策略与额度监测](policy-monitoring.md) |
| 使用现有 Verge 增强配置、中文维护与本机账单 | [Clash Verge 本机适配与维护](verge-runtime.md) |
| 比较已有套餐下的三档配置方式 | [三档配置方案](plans.md) |

### 建议使用顺序

1. 交给 Agent 时从[部署指南](agent-deployment.md)开始；自行操作时运行[首页演示](../README.md)，认识 `config.yaml` 与 `providers/` 的关系。
2. 按[测量指南](measurement.md)确认节点倍率、独立入口和逐服务资格。
3. 按[部署指南](deployment.md)填写本机设置，生成、检查并加载配置。
4. 检查实际规则归属与业务请求，记录上午和晚高峰结果。
5. 按[额度说明](quota-and-failover.md)维护账单基线，接近额度时生成并部署锁定配置。

## 历史案例与后续补充

| 文档 | 记录范围 |
|---|---|
| [2026-10-01 上午复测](case-study.md) | 全量节点测量、网站连通、复用请求、带宽、成本与未通过场景 |
| [Antigravity API 地区错误实修](antigravity-troubleshooting.md) | API 规则遗漏、文件来源目录和一次实际模型生成恢复 |
| [2026-10-01 规则补充](upstream-review-2026-10-01.md) | 六个规则来源复核、六项本机调整、公开目录补齐及端点回归 |
| [2026-10-01 后台策略验收](policy-acceptance-2026-10-01.md) | 真实隔离内核、候选文件保护、测试额度锁定与备用、账单历史 |
| [2026-10-01 稳定出口与本机维护验收](optimization-acceptance-2026-10-01.md) | 统一台账、真实故障与恢复、正式端点、持续连接及未验收范围 |

历史结果的时间、客户端和业务范围以各篇记录为准。私人环境的全部运行配置、后台任务、互动图和原始日志保留在本机；公开项目提供可复用的工具、目录和方法。

## 配置参考与项目维护

- [设置示例](../examples/settings.example.yaml)：订阅文件路径、节点别名、倍率、角色和服务资格。
- [AI 服务目录](../catalog/services.json)：服务 ID、域名和检查参数。
- [普通分流目录](../catalog/routes.json)：开发、文件、依赖、社交及国内站点。
- [更新记录](../CHANGELOG.md)：项目功能、规则及文档变化。
- [贡献指南](../CONTRIBUTING.md)：规则证据、复现步骤、开发检查和 PR 流程。
- [安全说明](../SECURITY.md)：本机敏感资料与私密漏洞报告。
- [MIT 许可证](../LICENSE)和[来源声明](../NOTICE.md)：项目与第三方内容的许可范围。

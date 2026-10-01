# Antigravity API 地区错误：补齐真实端点与运行来源

2026-10-01，案例在 DSH 的 Antigravity 供应器中出现 HTTP 400：`User location is not supported for the API use.`。页面和匿名健康检查正常，实际 Gemini 生成失败。

## 已确认的两处缺口

| 项目 | 修正前 | 修正后 |
|---|---|---|
| `cloudcode-pa.googleapis.com` | AI Antigravity 主订阅美国出口 | 同一 AI 服务组 |
| `daily-cloudcode-pa.sandbox.googleapis.com` | 命中普通 `googleapis.com`，走香港容量出口 | 精确主机规则进入 AI Antigravity，与主 API 使用同组 |
| 容量订阅 AI 文件来源 | 运行工作目录缺文件，刷新返回 503，实际导入 0 个节点 | 在实际内核目录同步来源并刷新，6 个候选实际导入且检查可用 |

Google 的 [Antigravity FAQ](https://antigravity.google/docs/faq) 当时支持地区清单列出美国、台湾等地区，没有列出香港。错误分流与地区拒绝相符；单看错误消息仍不能证明所有类似报错都由 IP 造成，账号关联地区与后端判断也需要独立核验。

公开模板已新增精确的备用 API 主机规则，并增加其正例与 `unrelated.sandbox.googleapis.com` 反例。没有把整个 `sandbox.googleapis.com` 或 `googleapis.com` 转入 AI。

## 本机验证结果

持久增强源码与运行规则一致；运行连接记录确认两个 API 主机均使用 AI Antigravity 的主订阅美国 1 倍出口。核心没有重启、累计流量没有清零，规则增加一条。

在已安装的 DSH Antigravity 供应器上执行一次极小真实生成：用户消息为 `Reply with exactly OK.`，最大输出 64 token，Gemini 3.8 Flash 解析到 `gemini-3.8-flash-tiered`，备用 API 返回 HTTP **200**，完整文本为 **OK**，正常结束。测试使用供应器正常认证，没有将账号令牌复制或输出到日志。

这证明该次 DSH 供应器的实际生成恢复，不代表全部模型、长会话、工具调用、图片与官方 IDE 的所有功能都已验收。匿名请求另得到预期 401，匿名响应不替代上述真实生成结果。

## 排查顺序

1. 从真实错误和客户端实现确认所有 API 端点；官网 200 不足以证明 API 完整覆盖。
2. 查运行态首匹配规则和连接链；注意重试端点是否落入普通出口。
3. 对照供应商当前支持地区与实际出口，不仅看节点名称。
4. 查 provider **运行时导入数量**；配置中存在来源与候选记录，不等于运行中成功导入。
5. provider 刷新报缺文件时核对内核实际 HomeDir，文件路径必须位于该目录或允许的 SAFE_PATHS 内。只在客户端目录执行 `-t` 可能漏掉服务工作目录缺文件的问题。
6. 同步订阅导出后刷新对应 provider，再核对候选与实际备用。订阅文件变化或工作目录重建时也要同步。
7. 最后执行极小真实生成，检查 HTTP 状态、文本与正常结束；保留失败样本，禁止用网页判活宣布恢复。

本案例的同步修复运行在私人后台保护任务中。公开模板输出目录已经包含全部 provider 文件；按照 [部署说明](deployment.md) 部署整个目录即可，公开仓库没有包含私人任务、订阅或账号数据。

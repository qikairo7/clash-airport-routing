# 更新记录

记录会影响使用方式、规则归属或项目维护的变化。日期按北京时间；提交标识用于回查具体改动，正式版本标签以仓库实际发布为准。

## 2026-10-01：仓库文档与贡献入口整理

- 重整 README：项目用途、公开能力、演示、真实订阅接入、分流方法和文档导航。
- 扩充贡献指南，说明规则来源、正反例、兼容影响、暂存后公开检查和 PR 流程。
- 增加文档索引、问题反馈与规则补充表单、PR 模板。
- 明确 MIT 与第三方来源边界，完善安全说明及私密漏洞报告入口。
- 公开文件检查允许新增的维护文档与模板。

## 2026-10-01：镜像仓库与 AI 端点补充

提交：[427a0f6](https://github.com/qikairo7/clash-airport-routing/commit/427a0f61c8d78e3da111936332f787ef87332a48)。

- 补齐 Artifact Registry、Docker Hardened Images 和 Docker 已知 R2 租户的分流。
- 补齐 GCR、Quay、GitLab / Microsoft 镜像仓库、JitPack 和开发站点目录。
- 为 ChatGPT LiveKit 和 Antigravity daily API 补充服务专属归属。
- 新增 21 个域名边界样例，记录规则来源和本机回归范围。

详细结果见[规则补充与运行验收](docs/upstream-review-2026-10-01.md)。

## 2026-10-01：Antigravity API 实修

提交：[eb54095](https://github.com/qikairo7/clash-airport-routing/commit/eb54095ccd44a88abc5282639525b09e175ebb67)。

- 补上 `daily-cloudcode-pa.sandbox.googleapis.com` 的专属分流。
- 记录客户端与服务内核工作目录差异、文件来源检查和实际生成恢复。

详细结果见[Antigravity 排障记录](docs/antigravity-troubleshooting.md)。

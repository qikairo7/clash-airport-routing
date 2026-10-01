# Clash Verge 本机适配与维护

本机后台由 `tools/watch.py` 选择适配器。默认接管公开生成器的完整 Mihomo 配置；`runtime.adapter: verge` 接管现有 Verge 持久脚本和 merge。两种入口共用 `monitor.py` 的账单、检查点、历史、单实例与计数分段，以及 `availability.py` 的健康出口固定选择。不会请求供应商订阅或用量接口。

## 接入条件

Verge 适配器面向本项目现有增强配置，持久脚本必须定义 `main(config)`，调用 `applyRoutingPolicy(config)`，并支持 `x-verified-pools`、`x-service-pools`、`x-budget-state`。它不自动改写任意第三方脚本。先备份客户端配置和台账，再按 [字段示例](../examples/verge.runtime.example.yaml) 填写被忽略的本机设置。所有真实节点、指纹测量、账单、路径、用户标识与凭据均留在 `local/` 或客户端目录。

`sources` 为本机已经刷新过的 YAML 文件。`registry` 为客户端 profiles 注册表，`billing_profiles` 映射来源到本机 profile UID。后台仅同步已有文件到当前内核的文件型 provider；相同文件不刷新。`source_labels`、`default_multipliers`、`base_providers` 映射当前增强脚本的来源。缺少倍率、重复节点名称、冲突的静态解析都拒绝接入。

`measurements` 指向本机的完整测量记录：顶层 `configured_entries` 记录 `provider/name/endpoint_id/kind`，`results` 记录相同端点的 `measured_at/exit_id/quality.country/checks`。端点指纹由除了名称之外的全部代理参数计算，先用订阅 hosts 规范化 server，再使用排序 JSON 的 SHA256 前 16 位；名称相同、参数不同不能继承资格。`service_measurements` 保存逐服务检查清单及收到检查结果的时间；旧记录的本地时间在导入时明确转换为上海时区。匿名检查只能作为连通证据。

核心 AI 业务入口为 select，含自动候选、配置中声明的手动目录和 REJECT。自动候选是最多四条合格线路的 fallback，60 秒健康检查；合格数量随实际检查变化，不承诺始终有四条。内核固定选择通过本机控制接口改变新连接；正常连接不因这个选择请求被删除。后台保留健康的当前选择，故障后固定已确认健康的备用；全部候选确认失败时，在自动模式下阻断该服务。用户手动选择不会被日常策略覆盖；自动池没有合格线路时明确显示原因，已配置的手动入口保留。新鲜连通样本可能恢复候选资格，仍不代表账号业务验收通过。

自动来源指向已验收节点的参数快照。原订阅出现同名参数变化时，手动目录可读取新文件，自动候选继续引用已验收版本，并等待新参数的资格核验和成员更新；不存在静默沿用名称资格的路径。历史来源别名与倍率仍纳入保护核算，以便识别订阅删除之后尚未结束的旧连接。未被任何组引用的 provider 关闭健康检查。

无后台时内核仍能自动备用，恢复节点可能重新被内核优先使用；后台离线期间不承诺实时额度阻断或保持出口。后台重新上线后，只在计数连续时补算离线区间；内核计数出现未知缺口则继续保护。健康失败隔离、恢复间隔和业务资格仍遵循[监测说明](policy-monitoring.md)。

## 台账与校准

台账版本 2 使用校验摘要、原子写入及前一版副本。每 10 秒左右保存一轮，检查与网络超时会增加轮次用时；保留 24 小时计数检查点。异常退出可以由现有计划任务重试。台账锁约束所有修改命令，后台运行时不能直接并行导入。

本机订阅刷新后，执行 `import-local-billing`。同一记录版本不会重复建基线；更旧版本拒绝。导入保存旧基线和累计，再以刷新前最近检查点衔接刷新之后的流量。首次旧台账迁移没有刷新前检查点时，内核身份和计数连续才允许保守重叠：把旧估算整体带入新基线，可能高估而不会把它清掉。客户端收到记录的时间不代表供应商精确计费截至时间。

TAG 的提醒、保护值为 200 / 220 GiB，奶昔为 400 / 450 GiB；本机设置可填写已经确认的其他阈值。时间到期不自动归零。用量下降必须显式确认新账期。内核意外重启时保护锁保留，新账单必须晚于新内核启动，并保守覆盖新计数段。受控重启会先阻止保护来源的新连接、关闭旧连接、保存最终计数，随后建立新段并带入全部旧估算；已有额度锁继续生效。

## 操作入口

从仓库根目录运行 PowerShell。默认设置路径为 `local/optimization/settings.yaml`，其他电脑通过 `-设置` 指定实际设置。`runtime.task` 填已有计划任务名称，维护入口会停止任务、等待退出、取得台账锁，结束后恢复原先运行的任务。

```powershell
powershell -NoProfile -File tools/manage.ps1 -操作 状态
powershell -NoProfile -File tools/manage.ps1 -操作 导入账单
powershell -NoProfile -File tools/manage.ps1 -操作 复验
powershell -NoProfile -File tools/manage.ps1 -操作 应用配置
powershell -NoProfile -File tools/manage.ps1 -操作 受控重启
powershell -NoProfile -File tools/manage.ps1 -操作 恢复配置
# 当前台账损坏时，仅从校验通过的前一版恢复并补算连续计数：
powershell -NoProfile -File tools/manage.ps1 -操作 恢复台账
# 确认供应商进入新账期、用量下降后，才使用：
powershell -NoProfile -File tools/manage.ps1 -操作 导入账单 -确认新账期
```

首次接手已有后台使用 `watch.py migrate`，必须先停止旧进程，核对新台账 `migration_baseline` 金额与保护锁一致。旧后台入口应只转发到新后台，不继续运行另一套算法。计划任务使用 Python、watch.py、设置的绝对路径，禁止重复实例；建议设置异常重试和无限执行时长。`initialize` 拒绝覆盖已有台账。

普通成员变化遇到活动连接会延后；超过 30 分钟显示维护原因。`应用配置` 是明确的维护操作，允许在持续连接存在时完整重载。Mihomo 校验在正式写入之前执行，失败不覆盖正式配置；控制器失败恢复此次前配置。恢复配置按当前台账重新应用额度限制，不恢复旧台账。

`复验` 每次最多处理两个核心候选，使用隔离内核验证对应服务端点及三次出口观察，仅保存出口摘要和国家。六小时扫描在证据剩余不足 24 小时时开始安排复验；新健康样本只能续对应服务的连通资格。复验不更新账号生成成功记录，也不进行大文件测速。

生产验收还需分别记录账号生成、附件、长期连接、晚高峰、DNS 最终上游及泄露复测。来源关闭证书校验的节点继续标明实际情况，不能只改变开关就宣称安全验收通过。

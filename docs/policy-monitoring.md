# 实测出口策略与后台额度监测

`policy` 是可选设置。未启用时，现有设置、候选顺序和命令保持原有行为。启用后，生成器根据实测出口和带时间的证据排序；`tools/watch.py` 另外负责运行监测、额度锁定与部署。节点扫描、出口测量和供应商账单采集仍由本机执行者完成。

## 1. 准备节点证据

参考 [策略示例](../examples/settings.policy.example.yaml)，把字段加入真实的 `local/settings.yaml`。示例是不能联网的演示，日期固定，过期后候选退出属于预期行为；正式设置不能使用 `services: ['*']`。

每个准备自动使用的节点仍需 `qualified`、`qualified_on`、`roles`、逐服务 `services` 和已确认的倍率。另填写：

| 字段 | 含义 |
|---|---|
| `exit_country` | 实际出口国家；使用一致的小写代码，不从节点名称猜测 |
| `ingress_id`、`exit_id` | 本机测量后生成的入口、出口标识；原地址留在本机，相同组合只保留一个候选 |
| `priority` | 同出口、国家和来源内的顺序，较小数值优先，默认 0 |
| `evidence.<服务 ID>` | 此服务的连通与业务证据；没有此项时使用 `evidence.transport` |

证据示例中的时间必须替换为实际检查时间，保留时区：

```yaml
evidence:
  chatgpt:
    checked_at: '2026-10-01T08:00:00+08:00'
    transport: passed
    business: pending
    # 完成账号业务验收后才填写 passed 和独立的业务时间。
    # business_checked_at: '2026-10-01T08:05:00+08:00'
```

`business` 只接受 `passed`、`failed`、`pending`。业务失败的候选退出此服务自动池；业务成功缺少独立时间或已经过期时按待验收处理。HTTP 401 可以证明接口响应，不能证明账号生成成功。通用 `transport` 证据只用于连通层面的选择，不能把不同服务的账号业务结果混为一项。

`policy.qualification_max_age_hours` 默认 72；未来时间和过期证据不接受。`require_business: true` 时，只有有效的账号业务成功证据可以入池。`policy.services.<服务 ID>.preferred_country` 和 `preferred_exit_id` 设置偏好；排序依次为同出口、同国家、来源顺序、`priority`。因此同国家的容量备用可以排在其他国家的主来源之前。缺少入口或出口标识时保留候选，但不能宣称已确认线路独立。

## 2. 确认后台接管范围

公开后台接管已经由本项目生成并加载的**独立 Mihomo 完整配置**，生成时会替换节点、策略组、providers 与规则。基础 DNS、TUN 等字段通过 `base` 保留。先按[部署指南](deployment.md)完成加载和实际业务验证，再启用后台。

Clash Verge Rev 的增强片段、生成文件和持久脚本有不同职责。独立后台不能覆盖客户端增强片段；使用已实现的 [Verge 适配器](verge-runtime.md)。`tools/verge_policy.js` 导出 `applyRoutingPolicy(config)`，输入 `x-routing-policy.version: 1`，`groups` 中提供自动组 `name` 与有序 `layers: [{provider, names}]`，可选 `direct` 叶节点列表；`stable: true` 和 `manual_groups` 创建 select 业务入口与 fallback 候选子组。顶层 `blocked_nodes`、`blocked_providers` 指定锁定范围。

将 [运行与账单字段示例](../examples/runtime.policy.example.yaml) 合并到真实设置中。`home`、`config`、`persistent_config` 相对于设置文件；`core` 使用内核可执行文件的绝对路径。完整运行配置必须位于 `home` 中，`persistent_config` 省略时与 `config` 相同。内核用绝对路径的 `-f` 启动，以便确认唯一进程身份。

`controller_url` 与 `controller_pipe` 只填一个：HTTP 只允许本机回环地址，控制密钥来自 `secret_env` 指定的环境变量；Windows 管道使用从当前内核发现的名称。不要把密钥写进设置、提交或日志。后台不会开启新的控制接口。

每份需要保护的来源都填写 `budgets.<来源>`：`used`、`total`、`threshold` 和明确的 `unit: B / GB / GiB`。GB 为十进制，GiB 为二进制。`observed_at` 是供应商当前账单的核验时间，必须带时区、不能位于未来且不超过一小时。所有被保护来源的节点都要映射倍率，包括高倍率、手动和未验收节点；否则拒绝接入。

## 3. 启动与检查

从仓库根目录执行，实际 Python 路径沿用本机环境：

```powershell
.\.venv\Scripts\python.exe tools/watch.py initialize --settings local/settings.yaml
.\.venv\Scripts\python.exe tools/watch.py once --settings local/settings.yaml
.\.venv\Scripts\python.exe tools/watch.py status --settings local/settings.yaml
.\.venv\Scripts\python.exe tools/watch.py run --settings local/settings.yaml
```

`initialize` 只执行一次；已有 `policy-state.json` 时拒绝重新初始化。`run` 每 10 秒记录状态；只启动一个实例。后台启动后保留已有账单基线，不因日期变化解锁。操作系统计划任务应使用绝对 Python、脚本和设置路径，工作目录指向仓库，禁止重复实例；此工具不会自行安装计划任务。

启动内核后，先等待实际 provider 节点与业务组加载，再开始请求与健康观测。管理接口可达不代表节点已准备好。状态中的 `updated_at` 应持续更新，`error` 应为空；错误只记录类型，校验详细输出留在本机 `policy-core-validation.log`。

后台记录当前自动 AI 叶节点的实际国家与出口偏好。健康观测仅使用对应检查地址：三次相隔至少 60 秒的失败会隔离候选；恢复需要三次相隔至少 60 秒的成功，且隔离冷却不少于 180 秒。每轮最多检查两个隔离候选，避免恢复检查集中消耗流量。

普通候选更新只在没有现有连接时完整部署。有持续下载或 WebSocket 时，`reload_deferred: true` 可能持续存在；更新后的台账与候选文件仍会保存，现有 fallback 继续为新连接选择存活候选。额度保护不能等待长连接：锁定来源后立即部署并关闭其连接。空候选组为 REJECT。

## 4. 额度、刷新与恢复

台账把当前供应商用量作为基线。本机捕获的节点流量按倍率核算，无法归属的短连接与计数差额按该来源最高倍率作保守估算。`upper_bound_bytes` 是基线之后的估算量，保护判断为基线加估算量达到阈值。它不能精确反映其他设备或供应商开销，应留出缓冲。达到阈值、计数减少或内核身份变化后保持锁定。

核验新的供应商账单后，停止后台实例，更新设置中的用量、总量、阈值和更晚的观测时间，再执行：

```powershell
.\.venv\Scripts\python.exe tools/watch.py refresh-billing --settings local/settings.yaml
.\.venv\Scripts\python.exe tools/watch.py once --settings local/settings.yaml
.\.venv\Scripts\python.exe tools/watch.py status --settings local/settings.yaml
# 核对来源、实际请求与台账后，重新启动 run 或既有计划任务。
```

刷新保留相同预算来源，把旧台账与内核身份加入 `billing_history`，并通过刷新前计数检查点保守衔接新基线。不能复用旧时间、删除预算来源或删除台账来绕过保护。意外重启内核需要启动之后的新账单；受控重启保存旧累计并建立新计数段。新基线加衔接估算低于阈值才会解除预算锁定；恢复配置仍遵守现有连接的部署限制。`policy.stable_ai: true` 启用最多四个候选的稳定 AI 入口，使用共用的选择管理流程；未启用时保持原配置结构。

部署产物在设置旁的 `policy-output/`，候选校验在内核工作目录的 `policy-staging/`。首次正式配置和被覆盖的 provider 文件备份到 `policy-backup/`。Mihomo 校验失败不改正式文件；控制器重载失败恢复本次修改前文件并再次重载。恢复原配置时先停后台，把备份的完整配置与 providers 手动恢复到对应位置，用 `Mihomo -t` 校验并按现有启动机制重载，最后读取运行态与实际链路。保留台账，避免恢复文件被下一轮后台立即覆盖。

## 5. 实际验收范围

保持规则模式。GLOBAL 会绕过国内分流，`open.bigmodel.cn` 等国内 AI 应核对实际 DIRECT 链路。不要仅根据 curl `--noproxy` 宣称直连：生产 TUN 仍可能捕获流量。隔离测试需确认物理网卡和内核路径。

上线验收分别记录：实际配置与 provider 数量、规则链路、匿名接口、账号业务、现有长连接、备用与恢复、晚高峰。额度锁定在隔离内核使用明确的测试预算触发，不能改写正式账单制造通过。公开 CI 只验证离线行为；本机真实内核和节点结果另行记录，保持时间与范围明确。

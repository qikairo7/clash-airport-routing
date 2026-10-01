# 贡献指南

欢迎提交规则补充、配置生成器修复、测量改进和使用文档。贡献围绕可复现的分流行为展开，节点测量与个人输入保留在自己的电脑上。

## 选择贡献入口

| 内容 | 入口 | 应提供的材料 |
|---|---|---|
| 生成失败、规则误匹配、文档错误 | [问题反馈](https://github.com/qikairo7/clash-airport-routing/issues/new/choose) | 版本、最小复现、预期与实际结果 |
| 新服务、下载主机或分类调整 | [规则补充表单](https://github.com/qikairo7/clash-airport-routing/issues/new?template=rule_request.yml) | 公开来源、主机、用途和规则边界 |
| 已完成的代码或文档改进 | Pull Request | 变更原因、影响范围及适用的检查结果 |
| 软件漏洞、可能暴露凭据的行为 | [私密漏洞报告](https://github.com/qikairo7/clash-airport-routing/security/advisories/new) | 按 [SECURITY](SECURITY.md) 提供不含真实密钥的复现 |

小型修正可以直接提交 PR。涉及组名、设置格式、候选逻辑或部署行为的变化，先说明兼容影响和迁移办法。

## 在本机准备开发环境

Fork 仓库后，克隆自己的副本并创建分支。下列命令从仓库根目录执行：

```powershell
git switch -c docs/improve-guide
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe tools/build.py --settings examples/settings.example.yaml --demo
```

Linux / macOS 使用 `python3 -m venv .venv` 和 `.venv/bin/python`。演示输入采用 `.invalid` 地址和 `DEMO_ONLY` 凭据，适合离线开发；真实订阅放在 `local/`。

## 文件分别负责什么

| 文件或目录 | 适合修改的内容 |
|---|---|
| `catalog/services.json` | AI 服务 ID、组名、精确域名、后缀及健康检查参数 |
| `catalog/routes.json` | 国内、开发、下载、社交等普通业务域名 |
| `catalog/diagram-notes.json` | 服务组与精确例外的设计理由 |
| `tools/build.py` | 本机输入校验、候选选择、组与规则生成 |
| `tools/policy.py` | 证据时效、出口排序、重复线路、故障隔离与保守额度核算 |
| `tools/controller.py`、`tools/watch.py` | 本机控制接口、台账与备份、候选校验和部署时机 |
| `tools/verge_policy.js` | Clash Verge Rev 持久增强脚本的策略转换函数 |
| `tools/measure.py` | curl 连接复用和单连接测量、失败样本判定 |
| `tools/check_public.py` | 公开文件范围与基础敏感内容检查 |
| `tools/render_rule_diagrams.py` | 从实际生成规则导出单向括号图及覆盖清单 |
| `tests/` | 真实行为和规则边界的回归测试 |
| `docs/`、`README.md` | 使用指南、验收方法和范围明确的案例记录 |

## 补充规则所需的证据

每次补充应说明：

1. **用途：**具体服务、API、认证、软件更新还是大文件下载，以及目标策略组。
2. **来源：**优先提供服务官方说明或源项目的文件链接；记录查阅日期，引用仓库时固定提交。
3. **范围：**优先使用精确主机；后缀规则要说明覆盖哪些子域。共享云、认证、CDN 根域要检查其他租户。
4. **首匹配影响：**检查下载子域、API、普通网页和现有父域的顺序，说明哪些连接会改走其他组。
5. **验证：**补充应匹配的正例和应保持原归属的反例。健康检查变化要记录 HEAD / GET 方法、状态和响应语义。

例如补充 `registry.gitlab.com` 时，同时验证它进入容量组、`gitlab.com` 页面保持开发组。补充某个共享云租户时，同时验证同一父域的其他租户保持原归属。

节点资格不能仅依赖名称、国家标签或第三方信誉分数。匿名 401、方法 405、网页连通、已登录生成和长连接分别报告；声明实测结果时注明时段、样本数和未验证场景。

## 变更检查

代码、目录和公开文件检查命令：

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe tools/build.py --settings examples/settings.example.yaml --demo
.\.venv\Scripts\python.exe tools/render_rule_diagrams.py --check
git diff --check
```

修改生成结构或新增语法时，另用自己的 Mihomo 核验演示输出：

```powershell
mihomo -t -d output -f output/config.yaml
```

仅改文字时检查相对链接、命令、文件名与当前实现是否一致，并说明检查范围。无需为措辞修正制造网络测试结果。

准备好要提交的公开文件后，逐文件暂存，再检查：

```powershell
# 将文件名替换为本次实际改动；不要暂存 local/、output/ 或 reports/。
git add README.md CONTRIBUTING.md
.\.venv\Scripts\python.exe tools/check_public.py
git diff --cached --check
git diff --cached
```

`check_public.py` 读取 Git 跟踪文件，**新文件需要先暂存才会被扫描**。它检查允许的文件路径、常见敏感格式和演示凭据；提交前仍需查看实际差异。

## 提交 Pull Request

1. 一次 PR 处理一个相关问题，保留已有使用方式；必要的兼容变化需写清。
2. 使用具体的提交说明，例如 `Fix registry download routing` 或 `Clarify provider deployment paths`。
3. 在 PR 模板中填写改动原因、规则来源、验证方法和结果；不适用的检查说明原因。
4. 涉及功能、规则或使用方式变化时，更新对应文档和 `CHANGELOG.md`。
   新增或调整服务组时，同步更新 `catalog/diagram-notes.json` 的设计理由和 `docs/routing-mindmap.md` 的章节说明，再运行 `tools/render_rule_diagrams.py` 更新完整括号图；改变部署方式时同步检查首页提示词与 `docs/agent-deployment.md`。
5. 根据 CI 结果与审查意见完成修正，再由维护者处理合并。

公开 CI 执行离线测试、演示生成和公开文件检查，不持有订阅与 AI 账号。业务成功的结论需另外提供范围明确、已经脱敏的证据。

后台行为调整需验证真实内核的初始化、控制接口、无效候选文件保护、测试额度锁定和备用请求。使用隔离端口与测试账单，不修改正式账单基线；测试产物留在 `local/`，公开说明要区分接口连通与实际模型生成。

## 隐私与许可

`local/`、`output/`、`reports/`、`.scratch/` 和 `*.local.*` 是本机资料，不能强制加入提交。Issue、PR、截图及日志同样需要检查。使用保留域名的最小示例替代真实服务器，移除订阅链接、令牌、出口 IP、控制器密钥和原始账单。

提交原创代码、文档与示例时，请确认有权按项目 [MIT 许可证](LICENSE)提供这些内容。引入第三方内容时注明来源、原许可证及采用范围；无法确认许可时，先提交来源线索供讨论。需要保留的上游声明记录在 [NOTICE](NOTICE.md)，项目的 MIT 不替代上游许可。

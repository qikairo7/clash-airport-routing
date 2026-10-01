# 贡献约定

规则补充请提交服务名称、公开官方说明、精确域名、希望进入的用途组，以及 HEAD / GET 的实际观测。不要提交账号、订阅链接、真实服务器、出口 IP、账单截图或完整运行配置。

修改规则或候选逻辑需要运行：

```powershell
python -m unittest discover -s tests -v
python tools/build.py --settings examples/settings.example.yaml --demo
python tools/check_public.py
```

规则边界改变时增加正例和反例；共享域、下载子域、API 与普通网页都要核对。CI 仅进行离线检查与示例构建，真实业务的地区、方法、响应语义及故障切换需单独说明。

`output/`、`local/`、`reports/` 和任何 `*.local.*` 不参与提交。公开扫描只是基础检查；提交前仍应逐文件查看差异，避免日志、复制的配置与第三方规则库进入历史。

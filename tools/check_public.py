import re
import subprocess
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
ALLOWED_ROOT = {"README.md", "LICENSE", "NOTICE.md", "SECURITY.md", "CONTRIBUTING.md", "CHANGELOG.md", ".gitignore", ".gitattributes", "requirements.txt", ".github/PULL_REQUEST_TEMPLATE.md"}
PREFIXES = ("docs/", "catalog/", "examples/", "tools/", "tests/", ".github/workflows/", ".github/ISSUE_TEMPLATE/")
PATTERNS = [
    re.compile(r"gh[pousr]_[A-Za-z0-9]{20,}"),
    re.compile(r"github_pat_[A-Za-z0-9_]{30,}"),
    re.compile(r"-----BEGIN (?:RSA |OPENSSH |EC )?PRIVATE KEY-----"),
    re.compile(r"https?://[^\s<>\"']+[?&](?:token|access_token|key|auth)=[^\s<>\"']+", re.I),
    re.compile(r"[A-Z]:[\\/]+Users[\\/]+[^\s/\\]+[\\/]+AppData", re.I),
    re.compile(r"[a-f0-9]{64}[\\/]+runtime[\\/]+config\.yaml", re.I),
]


def check():
    result = subprocess.run(["git", "ls-files", "-z"], cwd=ROOT, capture_output=True, check=True)
    paths = [path for path in result.stdout.decode("utf-8").split("\0") if path]
    if not paths:
        raise ValueError("没有跟踪文件；请先暂存准备公开的文件")
    failures = []
    for relative in paths:
        if relative not in ALLOWED_ROOT and not relative.startswith(PREFIXES):
            failures.append(f"禁止公开的文件路径：{relative}")
            continue
        path = ROOT / relative
        try:
            content = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            failures.append(f"文件不是可检查的 UTF-8 文本：{relative}")
            continue
        if any(pattern.search(content) for pattern in PATTERNS):
            failures.append(f"发现可能的敏感内容：{relative}")
        if relative.startswith("examples/") and path.suffix in {".yaml", ".yml"}:
            data = yaml.safe_load(content)
            for proxy in data.get("proxies", []):
                if not str(proxy.get("server", "")).endswith(".invalid"):
                    failures.append(f"示例中出现非保留域名服务器：{relative}")
                for field in ["username", "password", "uuid"]:
                    if field in proxy and proxy[field] != "DEMO_ONLY":
                        failures.append(f"示例中出现非演示凭据：{relative}")
    if failures:
        raise ValueError("\n".join(failures))
    print(f"公开检查通过：{len(paths)} 个跟踪文本文件，示例仅含保留域名与演示凭据")


if __name__ == "__main__":
    try:
        check()
    except ValueError as error:
        raise SystemExit(str(error)) from None

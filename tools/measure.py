import argparse
import json
import os
import shutil
import statistics
import subprocess
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
TARGETS = {
    "ChatGPT": "https://chatgpt.com/cdn-cgi/trace",
    "GitHub": "https://github.com/favicon.ico",
    "X": "https://x.com/favicon.ico",
}


def curl_samples(url, proxy, count, timeout=20):
    executable = shutil.which("curl.exe") or shutil.which("curl")
    if not executable:
        raise ValueError("需要 curl 7.70 或更新版本")
    command = [executable, "--silent", "--show-error", "--http1.1", "--proxy", proxy,
               "--noproxy", "", "--max-time", str(timeout)]
    for _ in range(count):
        command.extend(["--output", os.devnull, "--write-out", "%{json}\n", url])
    result = subprocess.run(command, capture_output=True, text=True, timeout=count * timeout + 10)
    rows = []
    for line in result.stdout.splitlines():
        try:
            raw = json.loads(line)
            # curl 原始 JSON 含 IP、请求 URL 等信息；仅保留这些计量字段。
            row = {key: raw[key] for key in ["http_code", "num_connects", "time_total", "size_download"]}
        except (json.JSONDecodeError, KeyError):
            raise ValueError("curl 返回格式不完整，请检查 curl 版本") from None
        rows.append(row)
    return rows, result.returncode


def validate_latency(rows, code):
    return (code == 0 and len(rows) == 11 and all(row["http_code"] == 200 for row in rows)
            and rows[0]["num_connects"] == 1
            and all(row["num_connects"] == 0 for row in rows[1:]))


def validate_bandwidth(rows, code, size):
    return (code == 0 and len(rows) == 1 and rows[0]["http_code"] == 200
            and rows[0]["num_connects"] == 1 and rows[0]["size_download"] == size
            and rows[0]["time_total"] > 0)


def measure(proxy, rounds, kind, period):
    parsed = urlsplit(proxy)
    if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost", "::1"} or parsed.username:
        raise ValueError("proxy 仅接受本机无认证 HTTP 代理地址")
    report = {"measured_at": datetime.now().astimezone().isoformat(), "period": period,
              "rounds": rounds, "latency": {}, "bandwidth": {}, "complete": False}
    destination = ROOT / "reports"
    destination.mkdir(exist_ok=True)
    path = destination / (datetime.now().strftime("%Y%m%d-%H%M%S-%f") + ".json")

    def save():
        path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    try:
        if kind in {"latency", "all"}:
            for name, url in TARGETS.items():
                item = {"samples": []}
                report["latency"][name] = item
                for index in range(rounds):
                    rows, code = curl_samples(url, proxy, 11)
                    valid = validate_latency(rows, code)
                    sample = {"round": index + 1, "valid": valid, "curl_exit": code, "requests": rows}
                    item["samples"].append(sample)
                    save()
                    if not valid:
                        raise ValueError(f"{name} 第 {index + 1} 轮不满足状态或连接复用条件；失败记录已保留")
                    sample["median_ms"] = round(statistics.median(row["time_total"] * 1000 for row in rows[1:]), 2)
                item["median_ms"] = statistics.median(sample["median_ms"] for sample in item["samples"])
                print(f"{name}：复用请求中位数 {item['median_ms']} ms")
        if kind in {"bandwidth", "all"}:
            size = 10_000_000
            item = {"bytes_per_round": size, "samples": []}
            report["bandwidth"] = item
            for index in range(rounds):
                rows, code = curl_samples(f"https://speed.cloudflare.com/__down?bytes={size}", proxy, 1, 60)
                valid = validate_bandwidth(rows, code, size)
                sample = {"round": index + 1, "valid": valid, "curl_exit": code, "requests": rows}
                item["samples"].append(sample)
                save()
                if not valid:
                    raise ValueError(f"带宽第 {index + 1} 轮长度、状态或连接数量不符合条件；失败记录已保留")
                sample["mbps"] = round(size * 8 / rows[0]["time_total"] / 1_000_000, 2)
            item["median_mbps"] = statistics.median(sample["mbps"] for sample in item["samples"])
            print(f"单连接带宽中位数 {item['median_mbps']} Mbps")
        report["complete"] = True
    finally:
        save()
        print(f"记录已保存：reports/{path.name}")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="复用 HTTP/1.1 测延迟，顺序单连接测带宽；不输出 IP 和响应正文")
    parser.add_argument("--proxy", default="http://127.0.0.1:7897")
    parser.add_argument("--rounds", type=int, choices=[1, 3], default=3)
    parser.add_argument("--kind", choices=["latency", "bandwidth", "all"], default="all")
    parser.add_argument("--period", choices=["daytime", "evening"], default="daytime")
    options = parser.parse_args()
    try:
        measure(options.proxy, options.rounds, options.kind, options.period)
    except (ValueError, subprocess.TimeoutExpired) as error:
        message = str(error) if isinstance(error, ValueError) else "curl 进程超时；失败记录已保留"
        parser.exit(1, f"测量失败：{message}\n")

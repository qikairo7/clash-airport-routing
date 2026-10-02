import ctypes
import http.client
import io
import json
import os
from urllib.parse import urlsplit
from urllib.request import Request, build_opener, ProxyHandler


class PipeSocket:
    def __init__(self, stream):
        self.stream = stream

    def makefile(self, mode):
        # 命名管道单次读取可能短于 HTTP 声明长度，标准缓冲器负责补足读取。
        return io.BufferedReader(self.stream)


class Controller:
    def __init__(self, url=None, pipe=None, secret_env="MIHOMO_SECRET"):
        if bool(url) == bool(pipe):
            raise ValueError("只设置一个本机 controller_url 或 controller_pipe")
        if url:
            parsed = urlsplit(url)
            if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "::1"} or parsed.username or parsed.password or parsed.query:
                raise ValueError("控制器必须是没有内嵌凭据的本机回环 HTTP 地址")
        elif os.name != "nt" or not pipe.startswith("\\\\.\\pipe\\"):
            raise ValueError("controller_pipe 仅支持 Windows 本机命名管道")
        self.url, self.pipe = url.rstrip("/") if url else None, pipe
        self.secret = os.environ.get(secret_env, "")
        self.opener = build_opener(ProxyHandler({}))

    def request(self, method, path, data=None):
        payload = json.dumps(data).encode() if data is not None else b""
        if not self.pipe:
            headers = {"Content-Type": "application/json"}
            if self.secret:
                headers["Authorization"] = "Bearer " + self.secret
            request = Request(self.url + path, data=payload if method != "GET" else None,
                              headers=headers, method=method)
            with self.opener.open(request, timeout=15) as response:
                body = response.read()
            return json.loads(body) if body else {}
        wait = ctypes.WinDLL("kernel32", use_last_error=True).WaitNamedPipeW
        wait.argtypes = [ctypes.c_wchar_p, ctypes.c_uint32]
        wait.restype = ctypes.c_int
        if not wait(self.pipe, 10000):
            raise RuntimeError("本机 Mihomo 管理管道不可用")
        # 标准库负责解析 HTTP 响应；控制器凭据不会写入文件或日志。
        headers = [f"{method} {path} HTTP/1.1", "Host: localhost", "Connection: close",
                   "Content-Type: application/json", f"Content-Length: {len(payload)}"]
        if self.secret:
            headers.append("Authorization: Bearer " + self.secret)
        headers.extend(["", ""])
        with open(self.pipe, "r+b", buffering=0) as stream:
            stream.write("\r\n".join(headers).encode("ascii") + payload)
            try:
                response = http.client.HTTPResponse(PipeSocket(stream))
                response.begin()
                body = response.read()
                if response.status >= 400:
                    raise RuntimeError(f"Mihomo 管理请求失败，HTTP {response.status}")
            except http.client.HTTPException:
                raise RuntimeError("Mihomo 管理响应未完整收到，等待内核就绪后重试") from None
        return json.loads(body) if body else {}

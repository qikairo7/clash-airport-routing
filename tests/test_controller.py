import http.client
import os
from pathlib import Path
import sys
import threading
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from controller import PipeSocket


class ControllerTests(unittest.TestCase):
    def test_real_pipe_reads_complete_fragmented_response(self):
        # 真实系统管道分多次写入，验证标准缓冲读取能补足较大的 HTTP 响应。
        read_fd, write_fd = os.pipe()
        payload = b"x" * 100_000
        headers = b"HTTP/1.1 200 OK\r\nConnection: close\r\nContent-Length: 100000\r\n\r\n"

        def send():
            with os.fdopen(write_fd, "wb", buffering=0) as stream:
                stream.write(headers)
                for offset in range(0, len(payload), 997):
                    stream.write(payload[offset:offset + 997])

        thread = threading.Thread(target=send, daemon=True)
        thread.start()
        with os.fdopen(read_fd, "rb", buffering=0) as stream:
            response = http.client.HTTPResponse(PipeSocket(stream))
            response.begin()
            self.assertEqual(response.read(), payload)
        thread.join(timeout=5)
        self.assertFalse(thread.is_alive())


if __name__ == "__main__":
    unittest.main()

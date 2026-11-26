"""文件基本信息：backend/http_api.py

目的：使用 Python 标准库提供 API HTTP 服务，避免开发阶段引入未确认的 Web 框架。
输入：HTTP JSON 请求、路径和任务下载请求。
输出：OpenAPI 兼容 JSON、ZIP 或统一 ErrorResponse。
维护：路由变化必须同步 openapi.yaml、api.md、契约测试和目录索引。
"""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import urlparse

from .application import Application
from .errors import AppError


class RequestHandler(BaseHTTPRequestHandler):
    """将八个 API 端点映射到 Application。"""

    app: Application

    def do_GET(self) -> None:  # noqa: N802
        """处理 GET 路由；无显式返回值，响应写入 socket。"""

        try:
            path = urlparse(self.path).path.rstrip("/")
            parts = path.strip("/").split("/") if path else []
            if path == "/health":
                self._json({"status": "ok"}, 200)
            elif path == "/api/v1/projects":
                self._json(self.app.list_projects(), 200)
            elif len(parts) == 4 and parts[:3] == ["api", "v1", "projects"]:
                self._json(self.app.get_project(parts[3]), 200)
            elif len(parts) == 4 and parts[:3] == ["api", "v1", "tasks"]:
                self._json(self.app.get_task(parts[3]), 200)
            elif len(parts) == 5 and parts[:3] == ["api", "v1", "tasks"] and parts[4] == "results":
                self._json(self.app.get_results(parts[3]), 200)
            elif len(parts) == 5 and parts[:3] == ["api", "v1", "tasks"] and parts[4] == "download":
                content, filename = self.app.download_results(parts[3])
                self._bytes(content, 200, "application/zip", filename)
            else:
                raise AppError("TASK_FAILED", "接口不存在", 404)
        except AppError as exc:
            self.app.logger.error("HTTP GET failed path=%s code=%s message=%s", self.path, exc.code, exc.message)
            self._json(exc.to_dict(), exc.status)
        except Exception as exc:  # pragma: no cover
            self.app.logger.exception("unexpected HTTP GET failure path=%s", self.path)
            self._json({"error": {"code": "INTERNAL_ERROR", "message": str(exc)}}, 500)

    def do_POST(self) -> None:  # noqa: N802
        """处理 POST 路由；读取 JSON 后写入响应。"""

        try:
            payload = self._read_json()
            path = urlparse(self.path).path.rstrip("/")
            parts = path.strip("/").split("/") if path else []
            if path == "/api/v1/projects":
                body, status = self.app.create_project(payload)
            elif len(parts) == 5 and parts[:3] == ["api", "v1", "projects"] and parts[4] == "training-tasks":
                body, status = self.app.start_training(parts[3])
            elif len(parts) == 5 and parts[:3] == ["api", "v1", "projects"] and parts[4] == "evaluation-tasks":
                body, status = self.app.create_evaluation(parts[3], payload)
            else:
                raise AppError("TASK_FAILED", "接口不存在", 404)
            self._json(body, status)
        except AppError as exc:
            self.app.logger.error("HTTP POST failed path=%s code=%s message=%s", self.path, exc.code, exc.message)
            self._json(exc.to_dict(), exc.status)
        except json.JSONDecodeError:
            self._json({"error": {"code": "INPUT_INVALID", "message": "请求体必须是 JSON"}}, 400)
        except Exception as exc:  # pragma: no cover
            self.app.logger.exception("unexpected HTTP POST failure path=%s", self.path)
            self._json({"error": {"code": "INTERNAL_ERROR", "message": str(exc)}}, 500)

    def _read_json(self) -> dict[str, Any]:
        """读取并解析 JSON 请求体；返回字典，空或非对象时抛出 AppError。"""

        length = int(self.headers.get("Content-Length", "0"))
        if length > 10 * 1024 * 1024:
            raise AppError("INPUT_INVALID", "请求体过大", 400)
        body = self.rfile.read(length)
        data = json.loads(body.decode("utf-8"))
        if not isinstance(data, dict):
            raise AppError("INPUT_INVALID", "请求体必须是 JSON 对象", 400)
        return data

    def _json(self, payload: dict[str, Any], status: int) -> None:
        """写 JSON 响应；参数为响应字典和状态码。"""

        raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        try:
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            return

    def _bytes(self, content: bytes, status: int, content_type: str, filename: str | None = None) -> None:
        """写二进制响应；参数为内容、状态、MIME 类型和可选文件名。"""

        try:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(content)))
            if filename:
                self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
            self.end_headers()
            self.wfile.write(content)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            return

    def log_message(self, format: str, *args: Any) -> None:
        """保留标准日志接口但不输出额外噪声；参数由 BaseHTTPRequestHandler 提供。"""

        return None


def create_server(app: Application, host: str, port: int) -> ThreadingHTTPServer:
    """创建线程化 HTTP 服务。

    参数：app 为 Application；host 和 port 为监听地址。
    返回：已绑定但尚未 serve_forever 的 ThreadingHTTPServer。
    """

    class BoundHandler(RequestHandler):
        pass

    BoundHandler.app = app
    return ThreadingHTTPServer((host, port), BoundHandler)

"""文件基本信息：backend/server.py

目的：提供后端服务命令行入口。
输入：环境变量 ARRAYLAB_HOST/PORT 等配置。
输出：持续运行的 HTTP 服务。
维护：启动方式变化时同步 backend/目录说明.md 和根目录索引。
"""

from __future__ import annotations

from .application import Application
from .config import Settings
from .http_api import create_server


def main() -> None:
    """创建 Application 并启动 HTTP 服务；无参数，无返回值。"""

    settings = Settings.from_env()
    app = Application(settings)
    server = create_server(app, settings.host, settings.port)
    print(f"ArrayLab backend listening on http://{settings.host}:{settings.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        app.close()


if __name__ == "__main__":
    main()

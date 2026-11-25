"""文件基本信息：tests/contract/test_http_api.py

目的：通过真实标准库 HTTP server 验证项目列表、项目绑定和错误响应。
输入：临时 .aedt 文件、临时 SQLite 和数据目录。
输出：pytest HTTP 契约测试结果。
维护：路由或错误结构变化同步 openapi.yaml、api.md 和契约目录索引。
"""

import json
import threading
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from backend.application import Application
from backend.config import Settings
from backend.http_api import create_server


@pytest.mark.contract
def test_http_project_binding_and_invalid_input(tmp_path: Path):
    """验证 HTTP 项目绑定成功、列表查询和错误响应。"""

    aedt = tmp_path / "api-demo.aedt"
    aedt.write_text("stub", encoding="utf-8")
    app = Application(Settings("127.0.0.1", 0, tmp_path / "state.sqlite3", tmp_path / "data", "stub", 4, "stub"))
    server = create_server(app, "127.0.0.1", 0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        request = Request(base + "/api/v1/projects", data=json.dumps({"hfss_project_path": str(aedt)}).encode(), headers={"Content-Type": "application/json"}, method="POST")
        with urlopen(request) as response:
            created = json.load(response)
            assert response.status == 201
        with urlopen(base + "/api/v1/projects") as response:
            assert len(json.load(response)["items"]) == 1
        bad = Request(base + "/api/v1/projects", data=json.dumps({}).encode(), headers={"Content-Type": "application/json"}, method="POST")
        with pytest.raises(HTTPError) as exc:
            urlopen(bad)
        assert exc.value.code == 400
        assert json.load(exc.value)["error"]["code"] == "PROJECT_PATH_INVALID"
        assert created["status"] == "ready_to_train"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
        app.close()

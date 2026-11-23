"""文件基本信息：tests/contract/test_openapi_contract.py

目的：验证 OpenAPI 路径、核心 schema 和错误枚举仍与文档一致。
输入：根目录 openapi.yaml。
输出：pytest 契约测试结果。
维护：接口文档变化必须同步 api.md、后端路由和本测试。
"""

from pathlib import Path

import pytest
import yaml


@pytest.mark.contract
def test_openapi_declares_eight_required_operations():
    """验证项目规定的八个 HTTP 操作均存在。"""

    document = yaml.safe_load(Path("openapi.yaml").read_text(encoding="utf-8-sig"))
    paths = document["paths"]
    expected = {
        ("/api/v1/projects", "get"), ("/api/v1/projects", "post"),
        ("/api/v1/projects/{project_id}", "get"),
        ("/api/v1/projects/{project_id}/training-tasks", "post"),
        ("/api/v1/projects/{project_id}/evaluation-tasks", "post"),
        ("/api/v1/tasks/{task_id}", "get"),
        ("/api/v1/tasks/{task_id}/results", "get"),
        ("/api/v1/tasks/{task_id}/download", "get"),
    }
    assert {(path, method) for path, spec in paths.items() for method in spec if method in {"get", "post"}} == expected


@pytest.mark.contract
def test_openapi_array_input_and_error_response_are_present():
    """验证 ArrayInput 和 ErrorResponse 的关键 schema。"""

    document = yaml.safe_load(Path("openapi.yaml").read_text(encoding="utf-8-sig"))
    schemas = document["components"]["schemas"]
    assert set(schemas["ArrayInput"]["required"]) == {"unit_count", "units"}
    assert set(schemas["ErrorResponse"]["required"]) == {"error"}
    assert "DUPLICATE_POSITION" in schemas["ErrorInfo"]["properties"]["code"]["enum"]

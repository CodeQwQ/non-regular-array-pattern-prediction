"""文件基本信息：tests/hfss_server/test_hfss_environment.py

目的：在服务器验收作业中检查 HFSS 工程、COM 依赖和实验适配入口。
输入：ARRAYLAB_HFSS_PROJECT_PATH、可选 ARRAYLAB_HFSS_MODULE_PATH。
输出：服务器环境验收结果；开发机默认不收集该 marker。
维护：环境要求变化同步 requirements、验证规范、HFSSAdapter 契约和验收记录模板。
"""

import importlib.util
import os
from pathlib import Path

import pytest


@pytest.mark.hfss_server
def test_server_has_hfss_project_com_and_adapter_entry():
    """验证服务器具备可访问 .aedt、win32com 和 HFSS 类入口。"""

    project_path = os.getenv("ARRAYLAB_HFSS_PROJECT_PATH")
    if not project_path:
        pytest.fail("ARRAYLAB_HFSS_PROJECT_PATH is required for server HFSS acceptance")
    project = Path(project_path)
    assert project.is_absolute() and project.suffix.lower() == ".aedt" and project.is_file()
    try:
        import win32com.client  # noqa: F401
    except ImportError as exc:
        pytest.fail(f"win32com is required on the HFSS server: {exc}")
    module_path = Path(os.getenv("ARRAYLAB_HFSS_MODULE_PATH", "非规则阵列方向图预测项目文件/hfss.py"))
    assert module_path.is_file(), f"HFSS module not found: {module_path}"
    spec = importlib.util.spec_from_file_location("arraylab_server_hfss", module_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert hasattr(module, "HFSS")

"""文件基本信息：tests/unit/test_hfss_real_adapter.py

目的：验证真实 HFSS 适配器的延迟模块加载、绑定映射和 runner 缺失错误。
输入：临时 fake hfss.py 和 .aedt 工程，不连接真实 COM。
输出：pytest 适配器契约测试结果。
维护：真实 COM/runner 契约变化同步 TASK-HFSS-001 和服务器测试。
"""

import pytest

from backend.errors import AppError
from backend.hfss_real_adapter import RealHFSSAdapter


@pytest.mark.unit
def test_real_adapter_loads_hfss_class_lazily_and_requires_runner(tmp_path):
    """验证 bind 使用注入模块，训练 runner 未配置时明确失败。"""

    module = tmp_path / "fake_hfss.py"
    module.write_text("class HFSS:\n    def __init__(self, path, design):\n        self.path = path\n        self.design = design\n", encoding="utf-8")
    project = tmp_path / "server.aedt"
    project.write_text("stub", encoding="utf-8")
    adapter = RealHFSSAdapter(module, "number1")
    result = adapter.bind(str(project), "project_1")
    assert result["mode"] == "real"
    with pytest.raises(AppError, match="runner"):
        adapter.run_training("project_1", "task_1")

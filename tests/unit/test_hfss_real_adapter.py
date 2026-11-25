"""文件基本信息：tests/unit/test_hfss_real_adapter.py

目的：验证真实 HFSS 适配器的延迟模块加载、绑定映射和 runner 缺失错误。
输入：临时 fake hfss.py 和 .aedt 工程，不连接真实 COM。
输出：pytest 适配器契约测试结果。
维护：真实 COM/runner 契约变化同步验证规范、验收场景清单和服务器测试。
"""

import pytest

from backend.errors import AppError
from backend.hfss_real_adapter import RealHFSSAdapter, load_runners


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


@pytest.mark.unit
def test_configured_runner_module_must_expose_both_operations(tmp_path):
    """验证真实模式不会把缺失的训练或验证函数静默替换成 stub。"""

    module = tmp_path / "runner.py"
    module.write_text("def run_training(instance, project_id, task_id, context): return {'status': 'succeeded'}\n", encoding="utf-8")
    with pytest.raises(AppError, match="run_training 和 run_validation"):
        load_runners(module)


@pytest.mark.unit
def test_configured_runner_module_is_loaded(tmp_path):
    """验证显式 runner 模块的两个函数均被注入。"""

    module = tmp_path / "runner.py"
    module.write_text(
        "def run_training(instance, project_id, task_id, context): return {'status': 'succeeded'}\n"
        "def run_validation(instance, project_id, task_id, array_input): return {'status': 'succeeded', 'result': {}}\n",
        encoding="utf-8",
    )
    training, validation = load_runners(module)
    assert callable(training)
    assert callable(validation)

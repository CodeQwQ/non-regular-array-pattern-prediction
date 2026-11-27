"""文件基本信息：tests/unit/test_hfss_runner.py

目的：验证真实 HFSS runner 的纯算法边界、默认加载和导出网格校验。
输入：固定方向图夹具、虚拟阵列参数和临时 runner 模块。
输出：pytest runner 契约与算法等价性证据。
维护：runner 输入输出、采样网格或算法公式变化时同步验证规范、验收清单和目录索引。
"""

from pathlib import Path

import pytest

from backend.hfss_real_adapter import load_runners
from backend.hfss_runner import _read_component, _run_validation_process, _training_iterations_with_processes, _work_dir


@pytest.mark.unit
def test_default_runner_loads_without_connecting_hfss():
    """正式默认 runner 可加载，导入过程不应连接 COM。"""

    training, validation = load_runners(None)
    assert training.__name__ == "run_training"
    assert validation.__name__ == "run_validation"


@pytest.mark.unit
def test_component_reader_rejects_incomplete_direction_grid(tmp_path: Path):
    """导出文件缺少标准采样点时必须失败。"""

    path = tmp_path / "bad.csv"
    path.write_text("Phi[deg],Theta[deg],dB(DirTheta)\n0,0,-1\n", encoding="utf-8")
    with pytest.raises(ValueError, match="采样点数量"):
        _read_component(path, "dB(DirTheta)")


@pytest.mark.unit
def test_spawn_training_workers_preserve_iteration_order(tmp_path: Path):
    """真实 runner 的 spawn worker 按迭代序返回 30 份、每份 9 行特征。"""

    module = tmp_path / "fake_hfss.py"
    module.write_text(
        "class HFSS:\n"
        "    def __init__(self, path, design, output_root=None): self.output_root = output_root\n"
        "    def move(self, **kwargs): pass\n"
        "    def move_xyz(self, **kwargs): pass\n"
        "    def set_board_size(self, *args, **kwargs): pass\n"
        "    def Box60(self, *args, **kwargs): pass\n"
        "    def Box60_Box61(self, *args, **kwargs): pass\n"
        "    def kuidian(self, *args, **kwargs): pass\n"
        "    def run(self): pass\n"
        "    def source_context(self, *args, **kwargs): pass\n"
        "    def phase_theta_cycle(self, *args, **kwargs): pass\n"
        "    def phase_phi_cycle(self, *args, **kwargs): pass\n"
        "    def amp_theta_cycle(self, *args, **kwargs): pass\n"
        "    def amp_phi_cycle(self, *args, **kwargs): pass\n"
        "    def delete(self, *args, **kwargs): pass\n",
        encoding="utf-8",
    )
    project = tmp_path / "template.aedt"
    project.write_text("fake", encoding="utf-8")
    context = {
        "data_root": str(tmp_path / "data"),
        "hfss_project_path": str(project),
        "hfss_module_path": str(module),
        "hfss_design_name": "number1",
        "max_hfss_workers": 2,
    }
    work = _work_dir(context, "project_1", "task_1", "training")
    rows = _training_iterations_with_processes(None, context, work)
    assert len(rows) == 30 * 9
    assert (work / "train_data" / "train_features_iter_1.csv").is_file()
    assert (work / "train_data" / "train_features_iter_30.csv").is_file()


@pytest.mark.unit
def test_spawn_validation_worker_releases_isolated_project(tmp_path: Path):
    """验证 worker 能在独立进程执行 COM 边界并清理复制的工程文件。"""

    module = tmp_path / "fake_hfss.py"
    module.write_text(
        "class HFSS:\n"
        "    def __init__(self, path, design, output_root=None): self.output_root = output_root\n"
        "    def move(self, **kwargs): pass\n"
        "    def move_xyz(self, **kwargs): pass\n"
        "    def set_board_size(self, *args, **kwargs): pass\n"
        "    def Box60(self, *args, **kwargs): pass\n"
        "    def Box60_Box61(self, *args, **kwargs): pass\n"
        "    def kuidian(self, *args, **kwargs): pass\n"
        "    def run(self): pass\n"
        "    def source_context(self, *args, **kwargs): pass\n"
        "    def phase_theta_cycle(self, *args, **kwargs): pass\n"
        "    def phase_phi_cycle(self, *args, **kwargs): pass\n"
        "    def amp_theta_cycle(self, *args, **kwargs): pass\n"
        "    def amp_phi_cycle(self, *args, **kwargs): pass\n"
        "    def delete(self, *args, **kwargs): pass\n",
        encoding="utf-8",
    )
    project = tmp_path / "template.aedt"
    project.write_text("fake", encoding="utf-8")
    output = tmp_path / "validation"
    _run_validation_process({
        "output_root": str(output),
        "project_path": str(project),
        "module_path": str(module),
        "design_name": "number1",
        "slot_root": str(tmp_path / "slots"),
        "iteration": "validation_task",
        "units": [{"unit_id": 1, "i": 1, "j": 1, "x": 0, "y": 0}],
    })
    assert not list((output / "hfss_instances").glob("*.aedt"))

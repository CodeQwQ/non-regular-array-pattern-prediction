"""文件基本信息：tests/unit/test_hfss_runner.py

目的：验证真实 HFSS runner 的纯算法边界、默认加载和导出网格校验。
输入：固定方向图夹具、虚拟阵列参数和临时 runner 模块。
输出：pytest runner 契约与算法等价性证据。
维护：runner 输入输出、采样网格或算法公式变化时同步验证规范、验收清单和目录索引。
"""

from pathlib import Path

import pytest

from backend.hfss_real_adapter import load_runners
from backend.hfss_runner import _read_component


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

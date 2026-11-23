"""文件基本信息：tests/unit/test_golden_fixtures.py

目的：执行 ALG-EQ-001 的确定性纯函数黄金夹具。
输入：tests/fixtures/golden_input 和 golden_output JSON。
输出：黄金值回归测试结果。
维护：黄金夹具变化必须更新 manifest、追踪矩阵和算法审查记录。
"""

import json
from pathlib import Path

import pytest

from backend.algorithm_reference import build_zn, calculate_unit_features


FIXTURES = Path(__file__).parents[1] / "fixtures"


@pytest.mark.unit
def test_feature_center_golden_fixture():
    """验证规则 3×3 中心单元的八方位特征。"""

    source = json.loads((FIXTURES / "golden_input/feature_center_3x3.json").read_text(encoding="utf-8"))
    expected = json.loads((FIXTURES / "golden_output/feature_center_3x3.json").read_text(encoding="utf-8"))
    assert calculate_unit_features(source["layout"], source["unit_index"]) == expected["features"]


@pytest.mark.unit
def test_z_small_golden_fixture():
    """验证小型 Z 矩阵的相位和增益。"""

    source = json.loads((FIXTURES / "golden_input/z_small.json").read_text(encoding="utf-8"))
    expected = json.loads((FIXTURES / "golden_output/z_small.json").read_text(encoding="utf-8"))
    matrix = build_zn([complex(*value) for value in source["g_ave"]], source["u_list"], source["v_list"], source["m_flat"], source["n_flat"], source["beta"], source["dx"], source["dy"], source["center_comp"])
    for row, expected_row in zip(matrix, expected["values"]):
        for value, expected_value in zip(row, expected_row):
            assert value.real == pytest.approx(expected_value[0], abs=expected["tolerance"])
            assert value.imag == pytest.approx(expected_value[1], abs=expected["tolerance"])

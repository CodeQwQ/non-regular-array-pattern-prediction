"""文件基本信息：tests/unit/test_algorithm_reference.py

目的：验证 3×3/5×5 阵列约定、八方位特征、Z 矩阵相位和方向图点数。
输入：小型固定算法夹具。
输出：pytest 算法纯函数测试结果。
维护：算法变更必须同步 ALG-EQ-001 黄金基线和实验参考实现。
"""

import cmath

import pytest

from backend.algorithm_reference import PATTERN_POINT_COUNT, build_zn, calculate_unit_features, generate_grid_array, get_grid_direction


@pytest.mark.unit
def test_grid_size_and_first_point_match_experiment_convention():
    """验证训练规模 3×3、测试规模 5×5 和首单元原点。"""

    train = generate_grid_array(3, 3, seed=42)
    test = generate_grid_array(5, 5, seed=42)
    assert len(train) == 9 and train[0][:2] == (0.0, 0.0)
    assert len(test) == 25 and test[0][:2] == (0.0, 0.0)


@pytest.mark.unit
def test_eight_direction_and_feature_order():
    """验证方位编号和最近邻特征顺序。"""

    assert get_grid_direction((1, 1), (1, 2)) == 1
    assert get_grid_direction((1, 1), (0, 2)) == 2
    array = [(0.0, 0.0, 0, 0), (10.0, 0.0, 0, 1), (0.0, 10.0, 1, 0)]
    features = calculate_unit_features(array, 0)
    assert features[0] == 1.2
    assert features[6] == 1.2


@pytest.mark.unit
def test_build_zn_matches_complex_phase_formula():
    """验证不显式构造 G 对角矩阵时的 Z 单元值。"""

    result = build_zn([2 + 0j], [1.0], [0.0], [0], [0], 2.0, 0.5, 0.5, -0.5)
    expected = 2 * cmath.exp(1j * (2.0 * 0.25))
    assert result[0][0].real == pytest.approx(expected.real)
    assert result[0][0].imag == pytest.approx(expected.imag)


@pytest.mark.unit
def test_pattern_point_count_is_16471():
    """验证方向图 91×181 网格点数。"""

    assert PATTERN_POINT_COUNT == 16471

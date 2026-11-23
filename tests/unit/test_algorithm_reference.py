"""文件基本信息：tests/unit/test_algorithm_reference.py

目的：验证 3×3/5×5 阵列约定、八方位特征、Z 矩阵相位和方向图点数。
输入：小型固定算法夹具。
输出：pytest 算法纯函数测试结果。
维护：算法变更必须同步 ALG-EQ-001 黄金基线和实验参考实现。
"""

import cmath

import pytest

from backend.algorithm_reference import (
    PATTERN_POINT_COUNT,
    build_virtual_grid,
    build_zn,
    calculate_unit_features,
    expand_cn_samples,
    generate_grid_array,
    get_grid_direction,
    polarized_ecp,
    solve_cn,
    synthesize_total_field,
)


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


@pytest.mark.unit
def test_polarization_and_virtual_grid_order():
    """验证 45° 极化恒等夹具和 meshgrid flatten 顺序。"""

    assert polarized_ecp(0, 0, 0, 0, 45) == pytest.approx(1 + 0j)
    grid = build_virtual_grid()
    assert grid["m_flat"][:6] == [1, 2, 3, 4, 5, 1]
    assert grid["n_flat"][:6] == [1, 1, 1, 1, 1, 2]
    assert (grid["m_flat"][-1], grid["n_flat"][-1]) == (5, 5)


@pytest.mark.unit
def test_canonical_normal_equation_round_trip():
    """验证正规方程路径可以恢复小型确定性 cn。"""

    z = [[1 + 0j, 0.2 + 0.1j], [0.3 - 0.2j, 1.2 + 0j], [0.8 + 0.1j, -0.4 + 0.3j]]
    expected = [0.7 - 0.2j, -0.1 + 0.4j]
    target = [sum(row[i] * expected[i] for i in range(2)) for row in z]
    actual = solve_cn(z, target)
    assert actual[0].real == pytest.approx(expected[0].real, abs=1e-10)
    assert actual[0].imag == pytest.approx(expected[0].imag, abs=1e-10)
    assert actual[1].real == pytest.approx(expected[1].real, abs=1e-10)
    assert actual[1].imag == pytest.approx(expected[1].imag, abs=1e-10)


@pytest.mark.unit
def test_cn_dataset_expansion_shape_and_column_order():
    """验证 8 特征 + element_id + cn 实虚部的展开顺序。"""

    columns, rows = expand_cn_samples([[1] * 8, [2] * 8], [[complex(i, -i) for i in range(25)], [complex(i + 1, -i - 1) for i in range(25)]])
    assert columns == ["right", "right_up", "up", "left_up", "left", "left_down", "down", "right_down", "element_id", "cn_real", "cn_imag"]
    assert len(rows) == 50
    assert rows[0][8:] == [1.0, 0.0, 0.0]
    assert rows[24][8] == 25.0


@pytest.mark.unit
def test_total_field_identity_and_amplitude_phase_views():
    """验证单元零位置恒等和两单元幅值/复场视图分离。"""

    pattern = [{"Phi[deg]": 0.0, "Theta[deg]": 0.0, "ECP_dB": 0.0, "ECP_Phase_deg": 0.0}]
    one = synthesize_total_field([pattern], [(0.0, 0.0)], steer_theta_deg=0, steer_phi_deg=0)
    two = synthesize_total_field([pattern, pattern], [(0.0, 0.0), (0.0, 0.0)], steer_theta_deg=0, steer_phi_deg=0)
    assert one["amplitude_linear"] == pytest.approx([1.0])
    assert one["complex_field"] == pytest.approx([1.0 + 0j])
    assert two["amplitude_linear"] == pytest.approx([2.0])
    assert two["complex_field"] == pytest.approx([2.0 + 0j])


@pytest.mark.unit
def test_total_field_rejects_grid_mismatch():
    """验证单元方向图网格错位会 fail-loud。"""

    first = [{"Phi[deg]": 0.0, "Theta[deg]": 0.0, "ECP_dB": 0.0, "ECP_Phase_deg": 0.0}]
    second = [{"Phi[deg]": 2.0, "Theta[deg]": 0.0, "ECP_dB": 0.0, "ECP_Phase_deg": 0.0}]
    with pytest.raises(ValueError, match="网格"):
        synthesize_total_field([first, second], [(0.0, 0.0), (0.0, 0.0)])

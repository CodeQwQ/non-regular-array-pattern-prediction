"""文件基本信息：backend/algorithm_reference.py

目的：提取实验代码中的关键纯算法规则，供黄金夹具和后端适配层复用。
输入：阵列坐标、网格索引、方向余弦、平均 ECP 和虚拟阵列参数。
输出：8 维邻域特征、虚拟阵列 Z 矩阵和方向图网格校验结果。
维护：任何数学变更必须同步 ALG-EQ-001 黄金夹具和实验参考实现。
"""

from __future__ import annotations

import cmath
import math
import random
from collections.abc import Sequence
from typing import Any

TRAIN_GRID_ROWS = 3
TRAIN_GRID_COLS = 3
TEST_GRID_ROWS = 5
TEST_GRID_COLS = 5
FEATURE_SCALAR = 12.0
THETA_VALUES = tuple(range(0, 181, 2))
PHI_VALUES = tuple(range(0, 361, 2))
PATTERN_POINT_COUNT = len(THETA_VALUES) * len(PHI_VALUES)
VIRTUAL_GRID_ROWS = 5
VIRTUAL_GRID_COLS = 5
VIRTUAL_DX_M = 0.005
VIRTUAL_DY_M = 0.005
VIRTUAL_CENTER_COMP = -2.0
DEFAULT_FREQUENCY_HZ = 27.5e9
SPEED_OF_LIGHT_M_S = 3e8


def calc_distance(p1: Sequence[float], p2: Sequence[float]) -> float:
    """计算两个二维坐标点的欧氏距离；参数为两个坐标，返回浮点距离。"""

    return math.hypot(float(p1[0]) - float(p2[0]), float(p1[1]) - float(p2[1]))


def get_grid_direction(center_grid: Sequence[int], neighbor_grid: Sequence[int]) -> int | None:
    """将相邻格子映射为实验约定的八方位编号；非相邻返回 None。"""

    i0, j0 = center_grid
    i1, j1 = neighbor_grid
    return {(0, 1): 1, (-1, 1): 2, (-1, 0): 3, (-1, -1): 4, (0, -1): 5, (1, -1): 6, (1, 0): 7, (1, 1): 8}.get((i1 - i0, j1 - j0))


def generate_grid_array(rows: int, cols: int, cell_side: float = 80.0, cell_step: float = 400.0, seed: int | None = None) -> list[tuple[float, float, int, int]]:
    """生成与实验脚本相同的随机阵列；返回按行优先排列的 `(x,y,i,j)` 列表。"""

    rng = random.Random(seed)
    points: list[tuple[float, float, int, int]] = []
    for i in range(rows):
        for j in range(cols):
            if not points:
                x, y = 0.0, 0.0
            else:
                x = rng.uniform(i * cell_step, i * cell_step + cell_side)
                y = rng.uniform(j * cell_step, j * cell_step + cell_side)
            points.append((x, y, i, j))
    return points


def calculate_unit_features(antenna_array: Sequence[Sequence[float]], unit_idx: int, feature_scalar: float = FEATURE_SCALAR) -> list[float]:
    """计算单元八个方位最近邻距离倒数特征；返回固定顺序的 8 维列表。"""

    center = antenna_array[unit_idx]
    nearest = [math.inf] * 9
    for idx, neighbor in enumerate(antenna_array):
        if idx == unit_idx:
            continue
        direction = get_grid_direction((int(center[2]), int(center[3])), (int(neighbor[2]), int(neighbor[3])))
        if direction is not None:
            distance = calc_distance(center, neighbor)
            if distance < nearest[direction]:
                nearest[direction] = distance
    return [round(feature_scalar / nearest[d], 6) if math.isfinite(nearest[d]) else 0.0 for d in range(1, 9)]


def build_zn(g_ave: Sequence[complex], u_list: Sequence[float], v_list: Sequence[float], m_flat: Sequence[int], n_flat: Sequence[int], beta: float, dx: float, dy: float, center_comp: float) -> list[list[complex]]:
    """构造等价于实验 `G @ E` 的 Z 矩阵，不显式创建巨大对角矩阵。

    参数：g_ave 为平均复 ECP；u/v 为方向余弦；m/n 为虚拟阵元索引；beta 为波数；dx/dy 为间距；center_comp 为中心补偿。
    返回：方向采样点 × 虚拟阵元数量的复数矩阵列表。
    """

    if not (len(g_ave) == len(u_list) == len(v_list)):
        raise ValueError("g_ave、u_list、v_list 长度必须一致")
    if len(m_flat) != len(n_flat):
        raise ValueError("m_flat、n_flat 长度必须一致")
    return [[complex(gain) * cmath.exp(1j * beta * ((center_comp + n - 1) * dx * u + (center_comp + m - 1) * dy * v)) for m, n in zip(m_flat, n_flat)] for gain, u, v in zip(g_ave, u_list, v_list)]


def validate_pattern_records(records: Sequence[dict[str, Any]]) -> None:
    """校验方向图记录的网格、字段和点数；不合格时抛出 ValueError。"""

    if len(records) != PATTERN_POINT_COUNT:
        raise ValueError(f"方向图采样点数量必须为 {PATTERN_POINT_COUNT}")
    required = {"Phi[deg]", "Theta[deg]", "ECP_dB", "ECP_Phase_deg"}
    for record in records:
        if set(record) != required:
            raise ValueError("方向图字段必须为 Phi[deg]、Theta[deg]、ECP_dB、ECP_Phase_deg")
        if record["Theta[deg]"] not in THETA_VALUES or record["Phi[deg]"] not in PHI_VALUES:
            raise ValueError("方向图角度不符合 2 度网格")


def restore_complex(amplitude_db: float, phase_deg: float) -> complex:
    """按实验口径将 dB 幅度和角度相位恢复为复数。

    参数：amplitude_db 为 dB 幅度；phase_deg 为角度制相位。
    返回：`10**(dB/20) * exp(j*phase)` 复数值。
    """

    return (10.0 ** (float(amplitude_db) / 20.0)) * cmath.exp(1j * math.radians(float(phase_deg)))


def complex_to_pattern(value: complex) -> tuple[float, float]:
    """将复数 ECP 转换为 dB 幅度和角度相位；参数为复数，返回 `(dB, degree)`。"""

    amplitude = abs(value)
    return 20.0 * math.log10(max(amplitude, 1e-10)), math.degrees(cmath.phase(value))


def polarized_ecp(r_e_theta_db: float, r_e_phi_db: float, r_e_theta_phase_deg: float, r_e_phi_phase_deg: float, phi_deg: float, polarization_deg: float = 45.0) -> complex:
    """按实验 45° 极化公式合成一个方向采样点的 ECP 复数值。

    参数：两个极化分量的 dB/相位、当前 Phi 角和极化角。
    返回：`Etheta*cos(phi-pol) - Ephi*sin(phi-pol)` 复数 ECP。
    """

    theta = restore_complex(r_e_theta_db, r_e_theta_phase_deg)
    phi = restore_complex(r_e_phi_db, r_e_phi_phase_deg)
    angle = math.radians(float(phi_deg) - float(polarization_deg))
    return theta * math.cos(angle) - phi * math.sin(angle)


def direction_cosines(theta_deg: float, phi_deg: float) -> tuple[float, float]:
    """计算方向余弦 u/v；参数为角度制 Theta/Phi，返回 `(u,v)`。"""

    theta = math.radians(float(theta_deg))
    phi = math.radians(float(phi_deg))
    return math.sin(theta) * math.cos(phi), math.sin(theta) * math.sin(phi)


def build_virtual_grid(rows: int = VIRTUAL_GRID_ROWS, cols: int = VIRTUAL_GRID_COLS, dx: float = VIRTUAL_DX_M, dy: float = VIRTUAL_DY_M, center_comp: float = VIRTUAL_CENTER_COMP) -> dict[str, Any]:
    """复刻实验 `meshgrid(arange(1,6), arange(1,6)).flatten()` 的虚拟阵元顺序。

    参数：rows/cols 为虚拟阵列规模；dx/dy 为米制间距；center_comp 为中心补偿。
    返回：包含 m_flat、n_flat、位置和参数的字典；默认顺序首项 `(m=1,n=1)`。
    """

    m_flat: list[int] = []
    n_flat: list[int] = []
    positions: list[tuple[float, float]] = []
    for n in range(1, cols + 1):
        for m in range(1, rows + 1):
            m_flat.append(m)
            n_flat.append(n)
            positions.append(((m - 1 + center_comp) * dx, (n - 1 + center_comp) * dy))
    return {"m_flat": m_flat, "n_flat": n_flat, "positions_m": positions, "rows": rows, "cols": cols, "dx": dx, "dy": dy, "center_comp": center_comp}


def solve_cn(z_matrix: Sequence[Sequence[complex]], target: Sequence[complex]) -> list[complex]:
    """按实验规定的正规方程 `(ZᴴZ)^(-1) Zᴴg` 求解虚拟阵元 cn。

    参数：z_matrix 为 N×M 复数 Z；target 为长度 N 的复数方向图。
    返回：长度 M 的复数 cn；矩阵奇异时抛出 ValueError。
    """

    rows = [list(map(complex, row)) for row in z_matrix]
    if not rows or len(rows) != len(target):
        raise ValueError("Z 行数必须与 target 长度一致且不为空")
    width = len(rows[0])
    if width == 0 or any(len(row) != width for row in rows):
        raise ValueError("Z 必须是规则非空矩阵")
    gram = [[0j for _ in range(width)] for _ in range(width)]
    rhs = [0j for _ in range(width)]
    for i in range(width):
        for j in range(width):
            gram[i][j] = sum(rows[k][i].conjugate() * rows[k][j] for k in range(len(rows)))
        rhs[i] = sum(rows[k][i].conjugate() * complex(target[k]) for k in range(len(rows)))
    return _solve_linear_system(gram, rhs)


def _solve_linear_system(matrix: list[list[complex]], vector: list[complex]) -> list[complex]:
    """用带部分主元的高斯消元解复数线性系统；内部函数参数为方阵和右端，返回解向量。"""

    n = len(vector)
    augmented = [list(matrix[i]) + [vector[i]] for i in range(n)]
    for col in range(n):
        pivot = max(range(col, n), key=lambda row: abs(augmented[row][col]))
        if abs(augmented[pivot][col]) < 1e-14:
            raise ValueError("正规方程矩阵奇异或病态")
        augmented[col], augmented[pivot] = augmented[pivot], augmented[col]
        pivot_value = augmented[col][col]
        augmented[col] = [value / pivot_value for value in augmented[col]]
        for row in range(n):
            if row == col:
                continue
            factor = augmented[row][col]
            if factor:
                augmented[row] = [augmented[row][j] - factor * augmented[col][j] for j in range(n + 1)]
    return [augmented[i][-1] for i in range(n)]


def expand_cn_samples(features: Sequence[Sequence[float]], cn_samples: Sequence[Sequence[complex]]) -> tuple[list[str], list[list[float]]]:
    """将 270×8 特征和 270×25 cn 展开为 6750×11 训练行。

    参数：features 每行 8 个特征；cn_samples 每行 25 个复数 cn。
    返回：固定列名和行列表 `[8特征, element_id, cn_real, cn_imag]`。
    """

    if len(features) != len(cn_samples):
        raise ValueError("features 与 cn_samples 样本数必须一致")
    columns = ["right", "right_up", "up", "left_up", "left", "left_down", "down", "right_down", "element_id", "cn_real", "cn_imag"]
    rows: list[list[float]] = []
    for feature_row, cn_row in zip(features, cn_samples):
        if len(feature_row) != 8 or len(cn_row) != 25:
            raise ValueError("每个样本必须是 8 个特征和 25 个 cn")
        for element_id, value in enumerate(cn_row, start=1):
            rows.append([float(x) for x in feature_row] + [float(element_id), float(complex(value).real), float(complex(value).imag)])
    return columns, rows


def synthesize_total_field(element_patterns: Sequence[Sequence[dict[str, float]]], positions_m: Sequence[Sequence[float]], frequency_hz: float = DEFAULT_FREQUENCY_HZ, steer_theta_deg: float = 20.0, steer_phi_deg: float = 0.0) -> dict[str, Any]:
    """按实验计划 011 的幅值/复场分离口径合成总阵方向图。

    参数：element_patterns 为每个单元的标准方向图记录；positions_m 为米制位置；frequency_hz 为频率；steer_theta/phi 为导向角。
    返回：包含标准总阵 records、线性幅值数组和复场数组的字典；网格错位或数量不一致时抛出 ValueError。
    """

    if not element_patterns or len(element_patterns) != len(positions_m):
        raise ValueError("单元方向图数量必须与位置数量一致且不为空")
    first_keys = [(row["Theta[deg]"], row["Phi[deg]"]) for row in element_patterns[0]]
    if len(set(first_keys)) != len(first_keys):
        raise ValueError("单元方向图存在重复 Theta/Phi 键")
    maps = []
    for pattern in element_patterns:
        current = {(row["Theta[deg]"], row["Phi[deg]"]): row for row in pattern}
        if list(current) != first_keys:
            raise ValueError("单元方向图 Theta/Phi 网格不一致")
        maps.append(current)
    beta = 2.0 * math.pi * frequency_hz / SPEED_OF_LIGHT_M_S
    steer_u, steer_v = direction_cosines(steer_theta_deg, steer_phi_deg)
    records: list[dict[str, float]] = []
    amplitude_linear: list[float] = []
    complex_field: list[complex] = []
    for theta, phi in first_keys:
        u, v = direction_cosines(theta, phi)
        amplitude_sum = 0.0
        total = 0j
        for pattern, position in zip(maps, positions_m):
            if len(position) != 2:
                raise ValueError("位置必须是 x/y 二元米制坐标")
            x_m, y_m = float(position[0]), float(position[1])
            value = restore_complex(pattern[(theta, phi)]["ECP_dB"], pattern[(theta, phi)]["ECP_Phase_deg"])
            amplitude_sum += abs(value)
            phase = beta * (x_m * (u - steer_u) + y_m * (v - steer_v))
            total += value * cmath.exp(1j * phase)
        amplitude_linear.append(amplitude_sum)
        complex_field.append(total)
        amp_db = 20.0 * math.log10(max(amplitude_sum, 1e-10))
        records.append({"Phi[deg]": float(phi), "Theta[deg]": float(theta), "ECP_dB": amp_db, "ECP_Phase_deg": math.degrees(cmath.phase(total))})
    return {"records": records, "amplitude_linear": amplitude_linear, "complex_field": complex_field}

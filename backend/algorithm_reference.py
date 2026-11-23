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
    return [[complex(gain) * cmath.exp(1j * beta * ((m - center_comp) * dx * u + (n - center_comp) * dy * v)) for m, n in zip(m_flat, n_flat)] for gain, u, v in zip(g_ave, u_list, v_list)]


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

"""文件基本信息：backend/data_io.py

目的：提供实验 CSV/文本数据的 fail-loud 读取和结构校验边界。
输入：方向图 CSV、阵元位置 CSV、特征 CSV 和 cn 展开 CSV。
输出：规范化记录、位置列表、特征行和 cn 数据行。
维护：列名、单位、网格和行数规则变化必须同步 requirements、黄金基线和测试。
"""

from __future__ import annotations

import csv
import math
from pathlib import Path
from typing import Any

from .algorithm_reference import PATTERN_POINT_COUNT, PHI_VALUES, THETA_VALUES, validate_pattern_records

PATTERN_FIELDS = ("Phi[deg]", "Theta[deg]", "ECP_dB", "ECP_Phase_deg")
FEATURE_FIELDS = ("right", "right_up", "up", "left_up", "left", "left_down", "down", "right_down")
CN_FIELDS = FEATURE_FIELDS + ("element_id", "cn_real", "cn_imag")


def load_pattern_csv(path: str | Path, expected_point_count: int = PATTERN_POINT_COUNT, verify_grid: bool = True) -> list[dict[str, float]]:
    """读取方向图 CSV 并校验字段、采样点、角度唯一性和数值有限性。

    参数：path 为 CSV 路径；expected_point_count 为期望点数；verify_grid 控制是否检查标准 2° 网格。
    返回：标准四字段浮点记录列表；文件缺失或不合法时抛出 ValueError/FileNotFoundError。
    """

    file_path = Path(path)
    if not file_path.is_file():
        raise FileNotFoundError(file_path)
    with file_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if tuple(reader.fieldnames or ()) != PATTERN_FIELDS:
            raise ValueError(f"{file_path} 字段必须严格为 {PATTERN_FIELDS}")
        records = []
        for row in reader:
            try:
                record = {field: float(row[field]) for field in PATTERN_FIELDS}
            except (TypeError, ValueError):
                raise ValueError(f"{file_path} 存在非数字方向图字段") from None
            if not all(math.isfinite(value) for value in record.values()):
                raise ValueError(f"{file_path} 存在 NaN/Inf")
            records.append(record)
    if len(records) != expected_point_count:
        raise ValueError(f"{file_path} 采样点数量为 {len(records)}，期望 {expected_point_count}")
    keys = [(row["Theta[deg]"], row["Phi[deg]"]) for row in records]
    if len(set(keys)) != len(keys):
        raise ValueError(f"{file_path} 存在重复 Theta/Phi 网格键")
    if verify_grid:
        validate_pattern_records(records)
    return records


def load_position_table(path: str | Path, n_units: int) -> list[tuple[float, float]]:
    """读取 mil 单位位置表并转换为米。

    参数：path 为包含 unit_id/abs_x/abs_y 的 CSV；n_units 为期望单元数量。
    返回：按 unit_id 排列的 `(x_m, y_m)` 列表。
    """

    file_path = Path(path)
    if not file_path.is_file():
        raise FileNotFoundError(file_path)
    with file_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        required = {"unit_id", "abs_x", "abs_y"}
        if not required.issubset(set(reader.fieldnames or ())):
            raise ValueError(f"{file_path} 缺少位置字段 {sorted(required)}")
        rows = list(reader)
    if len(rows) != n_units:
        raise ValueError(f"位置表行数为 {len(rows)}，期望 {n_units}")
    positions: list[tuple[float, float] | None] = [None] * n_units
    for row in rows:
        try:
            unit_id = int(row["unit_id"])
            x = float(row["abs_x"])
            y = float(row["abs_y"])
        except (TypeError, ValueError):
            raise ValueError("位置表包含非法 unit_id 或坐标") from None
        if not 1 <= unit_id <= n_units or positions[unit_id - 1] is not None:
            raise ValueError("unit_id 必须从 1 到 n 连续且不重复")
        if not math.isfinite(x) or not math.isfinite(y):
            raise ValueError("位置表坐标必须是有限数字")
        positions[unit_id - 1] = (x * 0.0254, y * 0.0254)
    if any(position is None for position in positions):
        raise ValueError("位置表 unit_id 不连续")
    return [position for position in positions if position is not None]


def load_feature_csv(path: str | Path, expected_rows: int | None = None) -> list[list[float]]:
    """读取 8 维布局特征 CSV。

    参数：path 为特征 CSV；expected_rows 可选期望行数。
    返回：按文件顺序排列的 8 维浮点行。
    """

    file_path = Path(path)
    with file_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if tuple(reader.fieldnames or ()) != FEATURE_FIELDS:
            raise ValueError(f"特征字段必须严格为 {FEATURE_FIELDS}")
        rows = []
        for row in reader:
            try:
                values = [float(row[field]) for field in FEATURE_FIELDS]
            except (TypeError, ValueError):
                raise ValueError("特征文件包含非数字字段") from None
            if not all(math.isfinite(value) for value in values):
                raise ValueError("特征文件包含 NaN/Inf")
            rows.append(values)
    if expected_rows is not None and len(rows) != expected_rows:
        raise ValueError(f"特征行数为 {len(rows)}，期望 {expected_rows}")
    return rows


def load_cn_dataset(path: str | Path, expected_samples: int | None = None) -> tuple[list[str], list[dict[str, float]]]:
    """读取 11 列 cn 展开数据并阻止首样本被 skiprows 丢弃。

    参数：path 为包含 8 特征、element_id、cn_real、cn_imag 的 CSV；expected_samples 可选样本组数。
    返回：固定列名和字典行列表；每连续 25 行必须是 element_id 1～25。
    """

    file_path = Path(path)
    with file_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if tuple(reader.fieldnames or ()) != CN_FIELDS:
            raise ValueError(f"cn 数据字段必须严格为 {CN_FIELDS}")
        rows: list[dict[str, float]] = []
        for row in reader:
            try:
                converted = {field: float(row[field]) for field in CN_FIELDS}
            except (TypeError, ValueError):
                raise ValueError("cn 数据包含非数字字段") from None
            if int(converted["element_id"]) != converted["element_id"]:
                raise ValueError("element_id 必须是整数")
            rows.append(converted)
    if len(rows) % 25 != 0:
        raise ValueError("cn 数据行数必须是 25 的整数倍")
    for start in range(0, len(rows), 25):
        ids = [int(row["element_id"]) for row in rows[start:start + 25]]
        if ids != list(range(1, 26)):
            raise ValueError("每个样本的 element_id 必须按 1～25 连续排列")
    if expected_samples is not None and len(rows) != expected_samples * 25:
        raise ValueError(f"cn 数据行数为 {len(rows)}，期望 {expected_samples * 25}")
    return list(CN_FIELDS), rows

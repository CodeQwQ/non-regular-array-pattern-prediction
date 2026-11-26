"""文件基本信息：backend/hfss_runner.py

目的：把实验代码的训练、ECP 后处理、XGBoost 训练和验证流程封装为后端 runner。
输入：已绑定的 HFSS COM 实例、项目/任务标识和后端 runner 上下文。
输出：训练模型与平均 ECP 产物，或标准化 HFSS 验证方向图结果。
维护：算法公式、HFSS 导出字段、采样网格和模型参数变化必须同步项目总览、
架构、验证规范、黄金夹具、目录索引和服务器验收记录。
"""

from __future__ import annotations

import csv
import math
from pathlib import Path
from typing import Any, Iterable

from .algorithm_reference import (
    DEFAULT_FREQUENCY_HZ,
    FEATURE_SCALAR,
    PHI_VALUES,
    PATTERN_POINT_COUNT,
    SPEED_OF_LIGHT_M_S,
    TEST_GRID_ROWS,
    THETA_VALUES,
    TRAIN_GRID_ROWS,
    build_virtual_grid,
    calculate_unit_features,
    complex_to_pattern,
    generate_grid_array,
    polarized_ecp,
    synthesize_total_field,
)


FEATURE_FIELDS = ("right", "right_up", "up", "left_up", "left", "left_down", "down", "right_down")
PATTERN_FIELDS = ("Phi[deg]", "Theta[deg]", "ECP_dB", "ECP_Phase_deg")


def _numpy():
    """延迟加载 numpy；返回模块，缺少依赖时由训练任务报告明确错误。"""

    try:
        import numpy as np  # type: ignore
    except ImportError as exc:
        raise RuntimeError("真实 HFSS runner 需要 numpy") from exc
    return np


def _work_dir(context: dict[str, Any] | None, project_id: str, task_id: str, name: str) -> Path:
    """计算任务隔离目录；参数为 runner 上下文、项目、任务和阶段名，返回可写目录。"""

    context = context or {}
    root = Path(context.get("data_root") or Path(__file__).resolve().parents[1] / "data")
    project_name = str(context.get("project_name") or project_id)
    path = root / project_name / "temp" / task_id / name
    path.mkdir(parents=True, exist_ok=True)
    return path


def _write_features(path: Path, rows: Iterable[Iterable[float]]) -> None:
    """写入实验约定的八维特征 CSV。"""

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(FEATURE_FIELDS)
        writer.writerows(rows)


def _read_component(path: Path, component: str) -> tuple[list[float], list[float], list[float]]:
    """读取 HFSS 导出的幅度或相位列，返回 phi、theta 和数值数组。"""

    with path.open("r", newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        fields = set(reader.fieldnames or ())
        required = {"Phi[deg]", "Theta[deg]", component}
        if not required.issubset(fields):
            raise ValueError(f"{path} 缺少方向图字段 {sorted(required)}")
        phi: list[float] = []
        theta: list[float] = []
        values: list[float] = []
        for row in reader:
            phi.append(float(row["Phi[deg]"]))
            theta.append(float(row["Theta[deg]"]))
            values.append(float(row[component]))
    if len(values) != PATTERN_POINT_COUNT:
        raise ValueError(f"{path} 采样点数量为 {len(values)}，期望 {PATTERN_POINT_COUNT}")
    expected = [(float(phi_value), float(theta_value)) for theta_value in THETA_VALUES for phi_value in PHI_VALUES]
    if list(zip(phi, theta)) != expected:
        raise ValueError(f"{path} 方向图网格必须是 Theta 外层、Phi 内层的 2 度网格")
    return phi, theta, values


def _ecp_from_exports(base: Path, iteration: str | int, group: int):
    """从四类 HFSS 导出文件计算一个单元的 45 度极化 ECP。"""

    np = _numpy()
    prefix = f"train{iteration}"
    phi, theta, phi_db = _read_component(base / f"{prefix}_3D_dir_phi_{group}.csv", "dB(DirPhi)")
    _, _, theta_db = _read_component(base / f"{prefix}_3D_dir_theta_{group}.csv", "dB(DirTheta)")
    _, _, phi_phase = _read_component(base / f"{prefix}_3D_phase_phi_{group}.csv", "ang_deg(rEPhi)[deg]")
    _, _, theta_phase = _read_component(base / f"{prefix}_3D_phase_theta_{group}.csv", "ang_deg(rETheta)[deg]")
    ecp = np.array(
        [polarized_ecp(db_t, db_p, phase_t, phase_p, phi_value) for db_t, db_p, phase_t, phase_p, phi_value in zip(theta_db, phi_db, theta_phase, phi_phase, phi)],
        dtype=complex,
    )
    return phi, theta, ecp


def _write_pattern(path: Path, phi: Iterable[float], theta: Iterable[float], values: Iterable[complex]) -> None:
    """写入四字段 ECP 方向图 CSV。"""

    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(PATTERN_FIELDS)
        for phi_value, theta_value, value in zip(phi, theta, values):
            db, phase = complex_to_pattern(complex(value))
            writer.writerow([f"{float(phi_value):.6f}", f"{float(theta_value):.6f}", f"{db:.9f}", f"{phase:.9f}"])


def _write_dataset(path: Path, features: list[list[float]], cn_samples: list[list[complex]]) -> None:
    """按实验顺序写入 8 特征、element_id、cn 实虚部训练集。"""

    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow((*FEATURE_FIELDS, "element_id", "cn_real", "cn_imag"))
        for feature_row, cn_row in zip(features, cn_samples):
            for element_id, value in enumerate(cn_row, start=1):
                writer.writerow([*feature_row, element_id, float(complex(value).real), float(complex(value).imag)])


def _build_z(g_ave, theta, phi):
    """构造与实验 `G @ E` 等价的 numpy Z 矩阵。"""

    np = _numpy()
    grid = build_virtual_grid()
    u = np.sin(np.deg2rad(theta)) * np.cos(np.deg2rad(phi))
    v = np.sin(np.deg2rad(theta)) * np.sin(np.deg2rad(phi))
    beta = 2.0 * math.pi * DEFAULT_FREQUENCY_HZ / SPEED_OF_LIGHT_M_S
    phase = beta * (
        (grid["center_comp"] + np.asarray(grid["n_flat"]) - 1.0)[None, :] * grid["dx"] * u[:, None]
        + (grid["center_comp"] + np.asarray(grid["m_flat"]) - 1.0)[None, :] * grid["dy"] * v[:, None]
    )
    return np.asarray(g_ave, dtype=complex)[:, None] * np.exp(1j * phase)


def _simulate_training_iteration(hfss: Any, iteration: int, output_root: Path, seed: int) -> list[list[float]]:
    """生成一个 3×3 训练布局并执行一次与实验脚本相同的 HFSS 流程。"""

    points = generate_grid_array(TRAIN_GRID_ROWS, TRAIN_GRID_COLS, seed=seed)
    features = [calculate_unit_features(points, index, FEATURE_SCALAR) for index in range(len(points))]
    _write_features(output_root / "train_data" / f"train_features_iter_{iteration}.csv", features)
    hfss.output_root = str(output_root) + ("\\" if "\\" in str(output_root) else "/")
    relative_cs_count = 70
    for x, y, i, j in points:
        if x == 0 and y == 0:
            hfss.move_xyz(col_pos=x, row_pos=y, relative_cs_count=relative_cs_count + 1)
            relative_cs_count += 2
        else:
            hfss.move(col_distance=x, row_distance=y)
            hfss.move_xyz(col_pos=x, row_pos=y, relative_cs_count=relative_cs_count)
            relative_cs_count += 1
    hfss.set_board_size("-2.5*xcell", "-2.5*ycell", "xcell1+780mil", "ycell1+780mil")
    hfss.Box60("-2.5*xcell", "-2.5*ycell", "xcell1+780mil", "ycell1+780mil")
    hfss.Box60_Box61(TRAIN_GRID_ROWS)
    hfss.kuidian(n=TRAIN_GRID_ROWS * TRAIN_GRID_COLS)
    hfss.run()
    hfss.source_context(n=TRAIN_GRID_ROWS * TRAIN_GRID_COLS)
    hfss.phase_theta_cycle(iteration=iteration, n=TRAIN_GRID_ROWS * TRAIN_GRID_COLS)
    hfss.phase_phi_cycle(iteration=iteration, n=TRAIN_GRID_ROWS * TRAIN_GRID_COLS)
    hfss.amp_theta_cycle(iteration=iteration, n=TRAIN_GRID_ROWS * TRAIN_GRID_COLS)
    hfss.amp_phi_cycle(iteration=iteration, n=TRAIN_GRID_ROWS * TRAIN_GRID_COLS)
    hfss.delete(5)
    return features


def run_training(instance: Any, project_id: str, task_id: str, context: dict[str, Any] | None = None) -> dict[str, Any]:
    """执行完整训练流水线并返回模型和平均 ECP 产物路径。"""

    np = _numpy()
    work = _work_dir(context, project_id, task_id, "training")
    all_features: list[list[float]] = []
    for iteration in range(1, 31):
        all_features.extend(_simulate_training_iteration(instance, iteration, work, seed=1000 + iteration))

    ecp_dir = work / "ecp_single"
    ecp_dir.mkdir(parents=True, exist_ok=True)
    average: Any = None
    ecp_samples: list[Any] = []
    theta_values: Any = None
    phi_values: Any = None
    sample_number = 0
    for iteration in range(1, 31):
        for group in range(1, 10):
            phi, theta, ecp = _ecp_from_exports(work, iteration, group)
            if average is None:
                average = np.zeros_like(ecp, dtype=complex)
                phi_values = np.asarray(phi, dtype=float)
                theta_values = np.asarray(theta, dtype=float)
            average += ecp
            sample_number += 1
            ecp_samples.append(ecp)
            _write_pattern(ecp_dir / f"ECP_single_{sample_number}.csv", phi, theta, ecp)

    if average is None or sample_number != 270:
        raise RuntimeError("HFSS 训练未生成完整的 270 组方向图")
    average_pattern = average / sample_number
    average_path = work / "Average_ECP_270.csv"
    _write_pattern(average_path, phi_values, theta_values, average_pattern)

    z = _build_z(np.asarray(average_pattern, dtype=complex), theta_values, phi_values)
    cn_samples = [
        [complex(value) for value in np.linalg.solve(z.conj().T @ z, z.conj().T @ ecp)]
        for ecp in ecp_samples
    ]

    dataset_path = work / "dataset_single_element_6750.csv"
    _write_dataset(dataset_path, all_features, cn_samples)
    from .model_adapter import XGBoostCnModel

    model_path = work / "cn_model.json"
    model = XGBoostCnModel()
    model.fit(
        [feature + [float(element_id)] for feature, sample in zip(all_features, cn_samples) for element_id in range(1, 26)],
        [[float(value.real), float(value.imag)] for sample in cn_samples for value in sample],
    )
    model.save(model_path)
    return {
        "status": "succeeded",
        "project_id": project_id,
        "task_id": task_id,
        "implementation": "hfss_com_training",
        "model_path": str(model_path),
        "average_pattern_path": str(average_path),
        "dataset_path": str(dataset_path),
    }


def _simulate_validation(instance: Any, iteration: str, output_root: Path, units: list[dict[str, Any]]) -> None:
    """执行一次与测试脚本同口径的验证仿真。"""

    instance.output_root = str(output_root) + ("\\" if "\\" in str(output_root) else "/")
    relative_cs_count = 71
    for unit in units:
        x, y = float(unit["x"]), float(unit["y"])
        if x != 0 or y != 0:
            instance.move(col_distance=x, row_distance=y)
        instance.move_xyz(col_pos=x, row_pos=y, relative_cs_count=relative_cs_count)
        relative_cs_count += 1
    size = max(TEST_GRID_ROWS, math.ceil(math.sqrt(len(units))))
    instance.set_board_size("-2.5*xcell", "-2.5*ycell", f"xcell1+{size * 400 - 420}mil", f"ycell1+{size * 400 - 420}mil")
    instance.Box60("-2.5*xcell", "-2.5*ycell", f"xcell1+{size * 400 - 420}mil", f"ycell1+{size * 400 - 420}mil")
    instance.Box60_Box61(size)
    instance.kuidian(n=len(units))
    instance.run()
    instance.source_context(n=len(units))
    instance.phase_theta_cycle(iteration=iteration, n=len(units), report_prefix="validation_rE Plot")
    instance.phase_phi_cycle(iteration=iteration, n=len(units), report_prefix="validation_rE Plot")
    instance.amp_theta_cycle(iteration=iteration, n=len(units), report_prefix="validation_amp Plot")
    instance.amp_phi_cycle(iteration=iteration, n=len(units), report_prefix="validation_amp Plot")
    instance.delete(size)


def run_validation(instance: Any, project_id: str, task_id: str, context: dict[str, Any] | None = None) -> dict[str, Any]:
    """执行绑定工程的验证仿真并返回标准单元/总阵方向图结果。"""

    context = context or {}
    raw_input = context.get("array_input")
    units = raw_input.get("units") if isinstance(raw_input, dict) else None
    if not isinstance(units, list) or not units:
        raise ValueError("验证 runner 缺少规范化 units")
    work = _work_dir(context, project_id, task_id, "validation")
    iteration = f"validation_{task_id}"
    _simulate_validation(instance, iteration, work, units)
    patterns: list[list[dict[str, float]]] = []
    for group in range(1, len(units) + 1):
        phi, theta, ecp = _ecp_from_exports(work, iteration, group)
        records = []
        for phi_value, theta_value, value in zip(phi, theta, ecp):
            db, phase = complex_to_pattern(complex(value))
            records.append({"Phi[deg]": float(phi_value), "Theta[deg]": float(theta_value), "ECP_dB": db, "ECP_Phase_deg": phase})
        patterns.append(records)
    positions_m = [(float(unit["x"]) * 0.0254, float(unit["y"]) * 0.0254) for unit in units]
    total = synthesize_total_field(patterns, positions_m)
    return {
        "status": "succeeded",
        "project_id": project_id,
        "task_id": task_id,
        "implementation": "hfss_com_validation",
        "result": {
            "implementation": "hfss_com",
            "units": {str(index + 1): pattern for index, pattern in enumerate(patterns)},
            "total_array": total,
        },
    }

"""文件基本信息：backend/reference_engine.py

目的：封装真实预测链路的算法编排，不连接 HFSS、不读取绝对路径。
输入：规范化阵列输入、已训练的 cn 模型、平均 ECP 方向图和虚拟阵列参数。
输出：每个物理单元 ECP、总阵合成结果和算法实现标识。
维护：切换到生产任务前必须通过 ALG-EQ-001 黄金夹具和真实数据等价性审查。
"""

from __future__ import annotations

import math
from typing import Any, Protocol, Sequence

from .algorithm_reference import (
    build_virtual_grid,
    build_zn,
    calculate_unit_features,
    complex_to_pattern,
    direction_cosines,
    synthesize_total_field,
)
from .models import ArrayInput


class CnModel(Protocol):
    """XGBoost cn 模型所需的最小 predict 接口。"""

    def predict(self, features: Sequence[Sequence[float]]) -> list[list[float]]: ...


class ReferencePredictionEngine:
    """基于实验规则的无 HFSS 预测引擎；模型和方向图通过构造函数注入。"""

    implementation = "xgboost_reference"

    def __init__(self, model: CnModel, average_pattern: Sequence[dict[str, float]], virtual_grid: dict[str, Any] | None = None) -> None:
        self.model = model
        self.average_pattern = list(average_pattern)
        self.virtual_grid = virtual_grid or build_virtual_grid()
        self._z_matrix = self._build_z_matrix()

    def _build_z_matrix(self) -> list[list[complex]]:
        """从平均 ECP 记录构造 Z 矩阵；无参数，返回方向点×虚拟阵元复矩阵。"""

        g_ave = []
        u_list = []
        v_list = []
        for record in self.average_pattern:
            amplitude = 10.0 ** (float(record["ECP_dB"]) / 20.0)
            phase = math.radians(float(record["ECP_Phase_deg"]))
            g_ave.append(amplitude * complex(math.cos(phase), math.sin(phase)))
            u, v = direction_cosines(record["Theta[deg]"], record["Phi[deg]"])
            u_list.append(u)
            v_list.append(v)
        return build_zn(g_ave, u_list, v_list, self.virtual_grid["m_flat"], self.virtual_grid["n_flat"], 2.0 * math.pi * 27.5e9 / 3e8, self.virtual_grid["dx"], self.virtual_grid["dy"], self.virtual_grid["center_comp"])

    def predict(self, array_input: ArrayInput, branch: str = "prediction") -> dict[str, Any]:
        """预测每个物理单元 ECP 并合成总阵。

        参数：array_input 为规范化阵列输入；branch 只能是 prediction。
        返回：包含每个单元 ECP、总阵结果和实现标识的字典。
        """

        if branch != "prediction":
            raise ValueError("ReferencePredictionEngine 只负责 prediction 分支")
        layout = [(unit.x, unit.y, unit.i - 1, unit.j - 1) for unit in array_input.units]
        unit_patterns: list[list[dict[str, float]]] = []
        for unit_index in range(array_input.unit_count):
            features = calculate_unit_features(layout, unit_index)
            model_input = [features + [float(element_id)] for element_id in range(1, len(self.virtual_grid["m_flat"]) + 1)]
            predictions = self.model.predict(model_input)
            if len(predictions) != len(self.virtual_grid["m_flat"]) or any(len(row) != 2 for row in predictions):
                raise ValueError("cn 模型输出必须是每个虚拟阵元一行、实虚部两列")
            cn = [complex(float(row[0]), float(row[1])) for row in predictions]
            records: list[dict[str, float]] = []
            for direction_index, record in enumerate(self.average_pattern):
                ecp = sum(self._z_matrix[direction_index][element_index] * cn[element_index] for element_index in range(len(cn)))
                amplitude_db, phase_deg = complex_to_pattern(ecp)
                records.append({"Phi[deg]": float(record["Phi[deg]"]), "Theta[deg]": float(record["Theta[deg]"]), "ECP_dB": amplitude_db, "ECP_Phase_deg": phase_deg})
            unit_patterns.append(records)
        positions_m = [(unit.x * 0.0254, unit.y * 0.0254) for unit in array_input.units]
        total = synthesize_total_field(unit_patterns, positions_m)
        return {"implementation": self.implementation, "units": {str(index + 1): records for index, records in enumerate(unit_patterns)}, "total_array": total}

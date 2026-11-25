"""文件基本信息：backend/algorithm.py

目的：定义预测算法接口和开发阶段确定性替身，供任务编排与测试注入。
输入：规范化阵列输入和分支名称。
输出：标准方向图记录、单元结果和算法实现标识。
维护：替身不代表最终算法；真实算法接入必须通过 ALG-EQ-001 黄金夹具审查。
"""

from __future__ import annotations

from typing import Any, Protocol

from .errors import AppError
from .models import ArrayInput


class PredictionEngine(Protocol):
    """预测算法的最小接口。"""

    def predict(self, array_input: ArrayInput, branch: str = "prediction") -> dict[str, Any]: ...


class StubPredictionEngine:
    """确定性开发替身，生成完整 91×181 方向图以验证数据契约。"""

    implementation = "stub"

    def predict(self, array_input: ArrayInput, branch: str = "prediction") -> dict[str, Any]:
        """生成开发阶段的总阵和单元方向图。

        参数：array_input 为后端已校验的阵列输入；branch 为 prediction 或 validation。
        返回：包含总阵记录、单元记录和实现标识的结果字典。
        """

        branch_offset = 0.0 if branch == "prediction" else 0.5
        unit_offset = min(array_input.unit_count, 100) * 0.01
        total: list[dict[str, float]] = []
        for theta in range(0, 181, 2):
            for phi in range(0, 361, 2):
                total.append({
                    "Phi[deg]": float(phi),
                    "Theta[deg]": float(theta),
                    "ECP_dB": -20.0 + unit_offset + branch_offset + 0.01 * theta + 0.001 * phi,
                    "ECP_Phase_deg": float((theta + phi + array_input.unit_count) % 360),
                })
        units = {str(unit.unit_id): list(total) for unit in array_input.units}
        return {"implementation": self.implementation, "total_array": {"records": total}, "units": units}


class NotReadyPredictionEngine:
    """生产服务在首次训练完成前使用的占位引擎。

    服务可以在没有预置模型时启动，绑定工程后由训练任务安装真实引擎。
    该对象拒绝预测，避免把启动占位状态误报成算法结果。
    """

    implementation = "reference_not_ready"

    def __init__(self, reason: str = "模型尚未训练完成") -> None:
        self.reason = reason

    def predict(self, array_input: ArrayInput, branch: str = "prediction") -> dict[str, Any]:
        """拒绝尚未完成模型加载的预测请求。

        参数：array_input 为规范化阵列输入；branch 为请求分支。
        返回：不会返回结果；始终抛出 MODEL_NOT_READY。
        """

        del array_input, branch
        raise AppError("MODEL_NOT_READY", self.reason, 409)

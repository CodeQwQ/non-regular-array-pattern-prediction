"""文件基本信息：backend/hfss_adapter.py

目的：定义可注入的 HFSSAdapter 协议和开发阶段替身。
输入：项目路径、设计信息和任务参数。
输出：绑定、训练、验证状态及可追踪错误。
维护：真实 COM 适配器和替身必须保持输入、输出、单位和异常契约一致。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from .errors import AppError


class HFSSAdapter(Protocol):
    """真实 HFSS 与测试替身共同遵守的最小接口。"""

    def bind(self, project_path: str, project_id: str) -> dict[str, Any]: ...

    def run_training(self, project_id: str, task_id: str) -> dict[str, Any]: ...

    def run_validation(self, project_id: str, task_id: str, array_input: dict[str, Any]) -> dict[str, Any]: ...


@dataclass
class StubHFSSAdapter:
    """不连接真实 HFSS 的开发替身；只验证流程和契约。"""

    mode: str = "stub"

    def bind(self, project_path: str, project_id: str) -> dict[str, Any]:
        """校验工程路径并返回替身绑定结果。

        参数：project_path 为绝对工程路径；project_id 为项目标识。
        返回：绑定信息字典；路径不合格时抛出 PROJECT_PATH_INVALID。
        """

        path = Path(project_path)
        if not path.is_absolute() or path.suffix.lower() != ".aedt":
            raise AppError("PROJECT_PATH_INVALID", "HFSS 工程路径必须是绝对 .aedt 文件", 400)
        if not path.exists():
            raise AppError("PROJECT_PATH_INVALID", "HFSS 工程文件不可访问", 400)
        return {"project_id": project_id, "mode": self.mode, "path": str(path)}

    def run_training(self, project_id: str, task_id: str) -> dict[str, Any]:
        """模拟训练阶段的 HFSS 结果；参数为项目和任务标识。"""

        return {"project_id": project_id, "task_id": task_id, "mode": self.mode, "status": "succeeded"}

    def run_validation(self, project_id: str, task_id: str, array_input: dict[str, Any]) -> dict[str, Any]:
        """模拟验证分支并返回输入快照；参数为项目、任务和规范化输入。"""

        return {"project_id": project_id, "task_id": task_id, "mode": self.mode, "status": "succeeded", "input": array_input}


class UnavailableHFSSAdapter:
    """用于明确阻断真实 HFSS 操作的适配器。"""

    def bind(self, project_path: str, project_id: str) -> dict[str, Any]:
        """报告真实 HFSS 当前不可用；参数为工程路径和项目标识。"""

        raise AppError("PROJECT_BIND_FAILED", "真实 HFSS 适配器尚未在当前环境启用", 500)

    def run_training(self, project_id: str, task_id: str) -> dict[str, Any]:
        """报告真实 HFSS 当前不可用；参数为项目和任务标识。"""

        raise AppError("TASK_FAILED", "真实 HFSS 适配器尚未在当前环境启用", 500)

    def run_validation(self, project_id: str, task_id: str, array_input: dict[str, Any]) -> dict[str, Any]:
        """报告真实 HFSS 当前不可用；参数为项目、任务和输入快照。"""

        raise AppError("TASK_FAILED", "真实 HFSS 适配器尚未在当前环境启用", 500)

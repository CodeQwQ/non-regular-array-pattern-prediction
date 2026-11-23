"""文件基本信息：backend/models.py

目的：定义后端内部的输入、项目、任务和结果数据模型。
输入：HTTP JSON 或 SQLite 行数据。
输出：类型明确的 dataclass 和序列化字典。
维护：字段变化必须同步 api.md、openapi.yaml、验证规范和测试。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


def utc_now() -> str:
    """生成 UTC ISO 时间戳；无参数，返回带时区的字符串。"""

    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class ArrayUnit:
    """一个阵列单元的规范化位置和编号。"""

    unit_id: int
    i: int
    j: int
    x: float
    y: float

    def to_dict(self) -> dict[str, Any]:
        """序列化单元；无参数，返回 API 单元字典。"""

        return {"unit_id": self.unit_id, "i": self.i, "j": self.j, "x": self.x, "y": self.y}


@dataclass(frozen=True)
class ArrayInput:
    """规范化的阵列输入。"""

    unit_count: int
    units: tuple[ArrayUnit, ...]

    def to_dict(self) -> dict[str, Any]:
        """序列化阵列输入；无参数，返回包含 unit_count 和 units 的字典。"""

        return {"unit_count": self.unit_count, "units": [unit.to_dict() for unit in self.units]}


@dataclass
class Project:
    """项目和模型状态；binding_status 与 model_status 分离避免 API 状态冲突。"""

    project_id: str
    project_name: str
    hfss_project_path: str
    hfss_project_name: str
    binding_status: str
    model_status: str
    created_at: str
    updated_at: str
    model_version: str | None = None
    last_error: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        """序列化公开项目状态；内部 binding_status 不直接暴露为 model_status。"""

        return {
            "project_id": self.project_id,
            "project_name": self.project_name,
            "hfss_project_name": self.hfss_project_name,
            "model_status": self.model_status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@dataclass
class Task:
    """训练或评价任务状态。"""

    task_id: str
    project_id: str
    task_type: str
    status: str
    current_stage: str
    result_available: bool
    prediction_status: str | None = None
    validation_status: str | None = None
    message: str | None = None
    error: dict[str, Any] | None = None
    created_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)

    def to_dict(self) -> dict[str, Any]:
        """序列化任务状态；无参数，返回 OpenAPI Task 字典。"""

        return {
            "task_id": self.task_id,
            "project_id": self.project_id,
            "task_type": self.task_type,
            "status": self.status,
            "current_stage": self.current_stage,
            "prediction_status": self.prediction_status,
            "validation_status": self.validation_status,
            "message": self.message,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "result_available": self.result_available,
            "error": self.error,
        }

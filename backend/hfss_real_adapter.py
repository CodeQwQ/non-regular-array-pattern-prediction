"""文件基本信息：backend/hfss_real_adapter.py

目的：延迟加载现有实验 HFSS 类，提供服务器真实 COM 适配边界。
输入：.aedt 工程路径、设计名、实验 hfss.py 路径和可注入训练/验证 runner。
输出：绑定的 HFSS 实例、任务 runner 结果或明确 AppError。
维护：真实 COM 调用必须在服务器验收中验证；不得让模块 import 触发 HFSS 连接。
"""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path
from typing import Any, Callable

from .errors import AppError


Runner = Callable[[Any, str, str, dict[str, Any] | None], dict[str, Any]]


class RealHFSSAdapter:
    """服务器端 HFSS 适配器；连接只在 bind 时发生。"""

    mode = "real"

    def __init__(self, module_path: str | Path | None = None, design_name: str = "number1", training_runner: Runner | None = None, validation_runner: Runner | None = None) -> None:
        self.module_path = Path(module_path or os.getenv("ARRAYLAB_HFSS_MODULE_PATH", "非规则阵列方向图预测项目文件/hfss.py"))
        self.design_name = design_name
        self.training_runner = training_runner
        self.validation_runner = validation_runner
        self._instances: dict[str, Any] = {}

    def _load_class(self):
        """延迟加载实验 HFSS 类；返回 class，失败时抛出 PROJECT_BIND_FAILED。"""

        if not self.module_path.is_file():
            raise AppError("PROJECT_BIND_FAILED", f"HFSS 适配模块不存在：{self.module_path}", 500)
        try:
            spec = importlib.util.spec_from_file_location("arraylab_real_hfss", self.module_path)
            if spec is None or spec.loader is None:
                raise ImportError("module spec unavailable")
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            return module.HFSS
        except Exception as exc:
            raise AppError("PROJECT_BIND_FAILED", f"HFSS COM 适配模块加载失败：{exc}", 500) from exc

    def bind(self, project_path: str, project_id: str) -> dict[str, Any]:
        """真实加载工程并建立 project_id 到 HFSS 实例的映射。

        参数：project_path 为绝对 `.aedt` 路径；project_id 为项目标识。
        返回：绑定模式和工程信息；COM/工程失败时抛出 AppError。
        """

        path = Path(project_path)
        if not path.is_absolute() or path.suffix.lower() != ".aedt" or not path.is_file():
            raise AppError("PROJECT_PATH_INVALID", "HFSS 工程路径必须是可访问的绝对 .aedt 文件", 400)
        hfss_class = self._load_class()
        try:
            self._instances[project_id] = hfss_class(str(path), self.design_name)
        except Exception as exc:
            raise AppError("PROJECT_BIND_FAILED", f"HFSS 工程加载失败：{exc}", 500) from exc
        return {"project_id": project_id, "mode": self.mode, "path": str(path), "design_name": self.design_name}

    def _instance(self, project_id: str) -> Any:
        """读取已绑定 HFSS 实例；参数为项目 ID，返回 COM 封装实例。"""

        try:
            return self._instances[project_id]
        except KeyError:
            raise AppError("PROJECT_BIND_FAILED", "项目尚未绑定 HFSS 工程", 409) from None

    def run_training(self, project_id: str, task_id: str) -> dict[str, Any]:
        """执行注入的真实训练 runner；未注入时明确失败。"""

        if self.training_runner is None:
            raise AppError("TASK_FAILED", "真实 HFSS 训练 runner 尚未配置", 500)
        return self.training_runner(self._instance(project_id), project_id, task_id, None)

    def run_validation(self, project_id: str, task_id: str, array_input: dict[str, Any]) -> dict[str, Any]:
        """执行注入的真实验证 runner；未注入时明确失败。"""

        if self.validation_runner is None:
            raise AppError("TASK_FAILED", "真实 HFSS 验证 runner 尚未配置", 500)
        return self.validation_runner(self._instance(project_id), project_id, task_id, array_input)

"""文件基本信息：backend/hfss_real_adapter.py

目的：延迟加载现有实验 HFSS 类，提供服务器真实 COM 适配边界。
输入：.aedt 工程路径、设计名、实验 hfss.py 路径和可配置训练/验证 runner 模块。
输出：绑定的 HFSS 实例、任务 runner 结果或明确 AppError。
维护：真实 COM 调用必须在服务器验收中验证；不得让模块 import 触发 HFSS 连接。
"""

from __future__ import annotations

import importlib
import importlib.util
import os
from pathlib import Path
from typing import Any, Callable

from .errors import AppError


Runner = Callable[[Any, str, str, dict[str, Any] | None], dict[str, Any]]


def load_runners(module_path: str | Path | None) -> tuple[Runner | None, Runner | None]:
    """按显式配置加载服务器端训练/验证 runner。

    参数：module_path 为包含 ``run_training`` 和 ``run_validation`` 的 Python
    文件路径。未配置时加载仓库内的 ``backend/hfss_runner.py``。
    返回：训练 runner 和验证 runner。模块不存在、导入失败或函数缺失时抛出
    ``AppError``，不允许静默回退到替身。
    """

    path = Path(module_path) if module_path is not None else Path(__file__).with_name("hfss_runner.py")
    if not path.is_file():
        raise AppError("CONFIG_INVALID", f"HFSS runner 模块不存在：{path}", 500)
    try:
        if path.resolve() == Path(__file__).with_name("hfss_runner.py").resolve():
            module = importlib.import_module("backend.hfss_runner")
        else:
            spec = importlib.util.spec_from_file_location("arraylab_configured_hfss_runner", path)
            if spec is None or spec.loader is None:
                raise ImportError("module spec unavailable")
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
    except AppError:
        raise
    except Exception as exc:
        raise AppError("CONFIG_INVALID", f"HFSS runner 模块加载失败：{exc}", 500) from exc
    training_runner = getattr(module, "run_training", None)
    validation_runner = getattr(module, "run_validation", None)
    if not callable(training_runner) or not callable(validation_runner):
        raise AppError("CONFIG_INVALID", "HFSS runner 必须同时提供 run_training 和 run_validation", 500)
    return training_runner, validation_runner


class RealHFSSAdapter:
    """服务器端 HFSS 适配器；连接只在 bind 时发生。"""

    mode = "real"

    def __init__(self, module_path: str | Path | None = None, design_name: str = "number1", training_runner: Runner | None = None, validation_runner: Runner | None = None, runner_context: dict[str, Any] | None = None) -> None:
        configured_path = module_path or os.getenv("ARRAYLAB_HFSS_MODULE_PATH")
        self.module_path = Path(configured_path) if configured_path else Path(__file__).resolve().parents[1] / "非规则阵列方向图预测项目文件" / "hfss.py"
        self.design_name = design_name
        self.training_runner = training_runner
        self.validation_runner = validation_runner
        self.runner_context = dict(runner_context or {})
        self._instances: dict[str, Any] = {}
        self._project_names: dict[str, str] = {}

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
            self._project_names[project_id] = path.stem
        except Exception as exc:
            raise AppError("PROJECT_BIND_FAILED", f"HFSS 工程加载失败：{exc}", 500) from exc
        return {"project_id": project_id, "mode": self.mode, "path": str(path), "design_name": self.design_name}

    def set_project_name(self, project_id: str, project_name: str) -> None:
        """登记用户项目名；参数为项目 ID 和显示名，供 runner 保持数据目录一致。"""

        self._project_names[project_id] = project_name

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
        context = dict(self.runner_context)
        context["project_name"] = self._project_names.get(project_id, project_id)
        return self.training_runner(self._instance(project_id), project_id, task_id, context)

    def run_validation(self, project_id: str, task_id: str, array_input: dict[str, Any]) -> dict[str, Any]:
        """执行注入的真实验证 runner；未注入时明确失败。"""

        if self.validation_runner is None:
            raise AppError("TASK_FAILED", "真实 HFSS 验证 runner 尚未配置", 500)
        context = dict(self.runner_context)
        context["array_input"] = array_input
        context["project_name"] = self._project_names.get(project_id, project_id)
        return self.validation_runner(self._instance(project_id), project_id, task_id, context)

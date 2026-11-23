"""文件基本信息：backend/application.py

目的：组装后端依赖并提供八个 API 操作对应的业务服务。
输入：HTTP 层传入的 JSON、项目 ID 和任务 ID。
输出：公开 API 字典、ZIP 字节或 AppError。
维护：路由行为变化必须同步 api.md、openapi.yaml、验收清单和契约测试。
"""

from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path
from typing import Any

from .algorithm import StubPredictionEngine
from .config import Settings
from .errors import AppError
from .hfss_adapter import StubHFSSAdapter, UnavailableHFSSAdapter
from .storage import SQLiteStore
from .task_manager import TaskManager
from .validation import normalise_array_input


class Application:
    """模块化单体的组合根和 API 业务门面。"""

    def __init__(self, settings: Settings | None = None, store: SQLiteStore | None = None) -> None:
        self.settings = settings or Settings.from_env()
        self.settings.ensure_directories()
        self.store = store or SQLiteStore(self.settings.db_path)
        adapter = StubHFSSAdapter() if self.settings.hfss_mode == "stub" else UnavailableHFSSAdapter()
        self.tasks = TaskManager(self.settings, self.store, adapter, StubPredictionEngine())

    def close(self) -> None:
        """关闭后台资源；无参数，返回 None。"""

        self.tasks.close()

    def create_project(self, payload: dict[str, Any]) -> tuple[dict[str, Any], int]:
        """绑定 HFSS 工程并创建项目。

        参数：payload 需要包含本机绝对 `.aedt` 路径。
        返回：`(ProjectCreateResponse, 201)`。
        """

        path = payload.get("hfss_project_path") if isinstance(payload, dict) else None
        if not isinstance(path, str) or not path:
            raise AppError("PROJECT_PATH_INVALID", "hfss_project_path 必填", 400)
        # bind 会执行绝对路径、扩展名和可访问性检查；真实适配器替换时仍保持该契约。
        project_id = "pending"
        if self.settings.hfss_mode != "stub":
            raise AppError("PROJECT_BIND_FAILED", "真实 HFSS 适配器尚未在当前开发环境启用", 500)
        project = self.store.create_project(path, payload.get("project_name"))
        try:
            StubHFSSAdapter().bind(path, project.project_id)
        except AppError:
            self.store.update_project(project.project_id, binding_status="invalid", model_status="invalid")
            raise
        return {"project_id": project.project_id, "status": "ready_to_train"}, 201

    def list_projects(self) -> dict[str, Any]:
        """获取项目列表；无参数，返回 `{"items": [...]}`。"""

        return {"items": [project.to_dict() for project in self.store.list_projects()]}

    def get_project(self, project_id: str) -> dict[str, Any]:
        """获取项目和模型状态；不存在时抛出 404 AppError。"""

        project = self.store.get_project(project_id)
        if project is None:
            raise AppError("PROJECT_PATH_INVALID", "项目不存在", 404)
        return project.to_dict()

    def start_training(self, project_id: str) -> tuple[dict[str, Any], int]:
        """显式创建训练任务；参数为项目 ID，返回 202 和任务摘要。"""

        task = self.tasks.start_training(project_id)
        return {"task_id": task.task_id, "project_id": task.project_id, "status": "queued"}, 202

    def create_evaluation(self, project_id: str, payload: dict[str, Any]) -> tuple[dict[str, Any], int]:
        """创建预测/验证任务；参数为项目 ID 和 EvaluationTaskCreateRequest。"""

        if not isinstance(payload, dict) or "input" not in payload or "modes" not in payload:
            raise AppError("INPUT_INVALID", "input 和 modes 必填", 400)
        array_input = normalise_array_input(payload["input"])
        modes = payload["modes"]
        if not isinstance(modes, list):
            raise AppError("INPUT_INVALID", "modes 必须是数组", 400)
        task = self.tasks.create_evaluation(project_id, array_input, modes)
        return {"task_id": task.task_id, "project_id": task.project_id, "status": "queued"}, 202

    def get_task(self, task_id: str) -> dict[str, Any]:
        """查询任务状态；参数为 task_id，返回 OpenAPI Task 字典。"""

        task = self.store.get_task(task_id)
        if task is None:
            raise AppError("TASK_FAILED", "任务不存在", 404)
        return task.to_dict()

    def get_results(self, task_id: str) -> dict[str, Any]:
        """查询结果；未准备好时返回 RESULT_NOT_READY。"""

        task = self.store.get_task(task_id)
        if task is None:
            raise AppError("RESULT_NOT_READY", "任务不存在", 404)
        result = self.store.get_result(task_id)
        if result is None or not task.result_available:
            raise AppError("RESULT_NOT_READY", "结果尚未准备好", 409)
        return result["payload"]

    def download_results(self, task_id: str) -> tuple[bytes, str]:
        """打包任务结果。

        参数：task_id 为任务标识。
        返回：`(ZIP 字节, 文件名)`；结果不存在或未完成时抛出 AppError。
        """

        task = self.store.get_task(task_id)
        result = self.store.get_result(task_id)
        context = self.store.get_task_context(task_id)
        if task is None or result is None or context is None or not task.result_available:
            raise AppError("RESULT_NOT_READY", "结果尚未准备好", 409)
        result_dir = Path(context["result_dir"] or "")
        if not result_dir.exists():
            raise AppError("DOWNLOAD_FAILED", "结果目录不存在", 500)
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
            for file in result_dir.rglob("*"):
                if file.is_file():
                    archive.write(file, file.relative_to(result_dir).as_posix())
            archive.writestr("task_result.json", json.dumps(result["payload"], ensure_ascii=False, indent=2))
        return buffer.getvalue(), f"{task_id}_result.zip"

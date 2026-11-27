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

from .algorithm import NotReadyPredictionEngine, PredictionEngine, StubPredictionEngine
from .data_io import load_pattern_csv
from .config import Settings
from .cleanup import start_cleanup_process
from .errors import AppError
from .hfss_adapter import StubHFSSAdapter, UnavailableHFSSAdapter
from .hfss_real_adapter import RealHFSSAdapter, load_runners
from .logging_utils import configure_logging
from .storage import SQLiteStore
from .task_manager import TaskManager
from .validation import normalise_array_input
from .model_adapter import XGBoostCnModel
from .reference_engine import ReferencePredictionEngine


class Application:
    """模块化单体的组合根和 API 业务门面。"""

    def __init__(self, settings: Settings | None = None, store: SQLiteStore | None = None) -> None:
        self.settings = settings or Settings.from_env()
        self.settings.ensure_directories()
        self.logger = configure_logging(self.settings.data_root)
        self.store = store or SQLiteStore(self.settings.db_path)
        self.cleanup_process = start_cleanup_process(self.settings.data_root, self.settings.retention_days) if self.settings.cleanup_enabled else None
        if self.settings.hfss_mode == "stub":
            adapter = StubHFSSAdapter()
        elif self.settings.hfss_mode == "real":
            training_runner, validation_runner = load_runners(self.settings.hfss_runner_module_path)
            adapter = RealHFSSAdapter(
                self.settings.hfss_module_path,
                self.settings.hfss_design_name,
                training_runner=training_runner,
                validation_runner=validation_runner,
                runner_context={
                    "data_root": str(self.settings.data_root),
                    "max_hfss_workers": self.settings.max_hfss_workers,
                    "hfss_design_name": self.settings.hfss_design_name,
                },
            )
        else:
            adapter = UnavailableHFSSAdapter()
        predictor = self._build_predictor()
        predictor_loader = self._load_predictor_after_training if self.settings.predictor_mode == "reference" else None
        self.tasks = TaskManager(self.settings, self.store, adapter, predictor, predictor_loader=predictor_loader)

    def _build_predictor(self):
        """根据配置构造 stub 或真实参考预测引擎；参数无，返回 PredictionEngine。"""

        if self.settings.predictor_mode == "stub":
            return StubPredictionEngine()
        if self.settings.predictor_mode != "reference":
            raise AppError("INTERNAL_ERROR", f"未知预测模式：{self.settings.predictor_mode}", 500)
        if self.settings.average_pattern_path is None or self.settings.model_path is None:
            return NotReadyPredictionEngine("模型尚未训练完成，请先绑定 HFSS 工程并启动训练")
        if not self.settings.average_pattern_path.is_file() or not self.settings.model_path.is_file():
            return NotReadyPredictionEngine("模型训练产物尚未生成，请先绑定 HFSS 工程并启动训练")
        return self._load_reference_predictor(self.settings.model_path, self.settings.average_pattern_path)

    @staticmethod
    def _load_reference_predictor(model_path: Path, average_pattern_path: Path) -> PredictionEngine:
        """从训练 runner 产物构造参考算法引擎。"""

        pattern = load_pattern_csv(average_pattern_path)
        model = XGBoostCnModel()
        model.load(model_path)
        return ReferencePredictionEngine(model, pattern)

    def _load_predictor_after_training(self, response: dict[str, Any]) -> PredictionEngine:
        """校验训练产物并返回可用于后续预测的真实引擎。

        参数：response 为 HFSS 训练 runner 的成功响应，至少包含 model_path。
        返回：ReferencePredictionEngine；缺少平均 ECP 或模型产物时抛出
        MODEL_NOT_READY，训练任务不得进入 ready 状态。
        """

        model_value = response.get("model_path") if isinstance(response, dict) else None
        pattern_value = response.get("average_pattern_path") if isinstance(response, dict) else None
        model_path = Path(model_value) if isinstance(model_value, (str, Path)) else None
        pattern_path = Path(pattern_value) if isinstance(pattern_value, (str, Path)) else self.settings.average_pattern_path
        if model_path is None or not model_path.is_file():
            raise AppError("MODEL_NOT_READY", "训练 runner 未返回可访问的模型文件", 500)
        if pattern_path is None or not pattern_path.is_file():
            raise AppError("MODEL_NOT_READY", "训练 runner 未返回可访问的平均 ECP 文件", 500)
        return self._load_reference_predictor(model_path, pattern_path)

    def close(self) -> None:
        """关闭后台资源；无参数，返回 None。"""

        self.tasks.close()
        if self.cleanup_process is not None and self.cleanup_process.is_alive():
            self.cleanup_process.join(timeout=2)

    def create_project(self, payload: dict[str, Any]) -> tuple[dict[str, Any], int]:
        """绑定 HFSS 工程并创建项目。

        参数：payload 需要包含本机绝对 `.aedt` 路径。
        返回：`(ProjectCreateResponse, 201)`。
        """

        path = payload.get("hfss_project_path") if isinstance(payload, dict) else None
        if not isinstance(path, str) or not path:
            raise AppError("PROJECT_PATH_INVALID", "hfss_project_path 必填", 400)
        project = self.store.create_project(path, payload.get("project_name"))
        try:
            self.tasks.hfss.bind(path, project.project_id)
            set_project_name = getattr(self.tasks.hfss, "set_project_name", None)
            if callable(set_project_name):
                set_project_name(project.project_id, project.project_name)
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

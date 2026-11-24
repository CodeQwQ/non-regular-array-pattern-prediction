"""文件基本信息：backend/task_manager.py

目的：编排训练、预测、验证和双模式后台任务，维护主任务与分支状态。
输入：SQLiteStore、HFSSAdapter、PredictionEngine、项目和规范化输入。
输出：立即返回的 queued Task，后台更新状态、结果文件和错误证据。
维护：状态转换变化必须同步 api.md、openapi.yaml、验证规范和测试。
"""

from __future__ import annotations

import json
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from typing import Any

from .algorithm import PredictionEngine
from .config import Settings
from .errors import AppError
from .hfss_adapter import HFSSAdapter
from .models import ArrayInput, Project, Task
from .storage import SQLiteStore


class TaskManager:
    """后台任务编排器；线程池容量由 Settings 限制为最多 4。"""

    def __init__(self, settings: Settings, store: SQLiteStore, hfss: HFSSAdapter, predictor: PredictionEngine) -> None:
        self.settings = settings
        self.store = store
        self.hfss = hfss
        self.predictor = predictor
        self.executor = ThreadPoolExecutor(max_workers=settings.max_hfss_workers, thread_name_prefix="arraylab-task")
        self._lock = threading.Lock()

    def close(self) -> None:
        """关闭后台线程池；无参数，返回 None。"""

        self.executor.shutdown(wait=False, cancel_futures=False)

    def start_training(self, project_id: str) -> Task:
        """创建并异步启动训练任务。

        参数：project_id 为已绑定项目。
        返回：queued Task；前置条件不满足时抛出 AppError。
        """

        project = self.store.get_project(project_id)
        if project is None:
            raise AppError("PROJECT_PATH_INVALID", "项目不存在", 404)
        if project.binding_status != "ready_to_train":
            raise AppError("PROJECT_BIND_FAILED", "项目尚未完成 HFSS 工程绑定", 409)
        if project.model_status == "training":
            raise AppError("TASK_FAILED", "项目已有训练任务运行中", 409)
        task = self.store.create_task(project_id, "training")
        self.store.update_project(project_id, model_status="training", last_error=None)
        self.executor.submit(self._run_training, task.task_id, project)
        return task

    def create_evaluation(self, project_id: str, array_input: ArrayInput, modes: list[str]) -> Task:
        """创建并异步启动预测/验证评价任务。

        参数：project_id 为项目标识；array_input 为规范化输入；modes 为 prediction/validation 子集。
        返回：queued Task；模型或绑定前置不满足时抛出 AppError。
        """

        project = self.store.get_project(project_id)
        if project is None:
            raise AppError("PROJECT_PATH_INVALID", "项目不存在", 404)
        if not modes:
            raise AppError("MODE_REQUIRED", "至少选择 prediction 或 validation 一种模式", 400)
        if len(set(modes)) != len(modes) or any(mode not in {"prediction", "validation"} for mode in modes):
            raise AppError("INPUT_INVALID", "modes 只能包含唯一的 prediction 或 validation", 400)
        if "prediction" in modes and project.model_status != "ready":
            raise AppError("MODEL_NOT_READY", "模型尚未训练完成，不能执行预测", 409)
        if "validation" in modes and project.binding_status != "ready_to_train":
            raise AppError("PROJECT_BIND_FAILED", "HFSS 工程尚未绑定，不能执行验证", 409)
        task = self.store.create_task(project_id, "evaluation", array_input.to_dict(), modes, project.model_version)
        self.executor.submit(self._run_evaluation, task.task_id, project, array_input, modes)
        return task

    def _run_training(self, task_id: str, project: Project) -> None:
        """后台执行训练阶段；参数为任务和项目；失败时写入统一错误。"""

        try:
            self.store.update_task(task_id, status="running", current_stage="data_generation", message="正在生成训练数据")
            self.store.update_task(task_id, current_stage="hfss_simulation", message="正在执行 HFSS 仿真与数据提取")
            self.hfss.run_training(project.project_id, task_id)
            self.store.update_task(task_id, current_stage="model_training", message="正在训练预测模型")
            version = f"model_{task_id}"
            self.store.update_project(project.project_id, model_status="ready", model_version=version, last_error=None)
            self.store.update_task(task_id, status="succeeded", current_stage="model_training", message="模型训练完成，可执行评价")
        except AppError as exc:
            self.store.update_project(project.project_id, model_status="failed", last_error=exc.to_dict())
            self.store.update_task(task_id, status="failed", current_stage="model_training", message=exc.message, error=exc.to_dict())
        except Exception as exc:  # pragma: no cover - 防止后台线程吞掉未知错误
            error = {"code": "INTERNAL_ERROR", "message": str(exc)}
            self.store.update_project(project.project_id, model_status="failed", last_error=error)
            self.store.update_task(task_id, status="failed", current_stage="model_training", message=str(exc), error=error)

    def _run_evaluation(self, task_id: str, project: Project, array_input: ArrayInput, modes: list[str]) -> None:
        """后台执行评价分支并生成单/双模式结果。"""

        branch_results: dict[str, dict[str, Any]] = {}
        artifacts: list[dict[str, Any]] = []
        result_dir = self._result_dir(project, task_id)
        result_dir.mkdir(parents=True, exist_ok=True)
        (result_dir / "input.json").write_text(json.dumps(array_input.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
        try:
            self.store.update_task(task_id, status="running", current_stage="prediction" if "prediction" in modes else "validation", message="评价任务执行中")
            for mode in modes:
                self.store.update_task(task_id, **{f"{mode}_status": "running"}, current_stage=mode, message=f"正在执行 {mode} 分支")
                try:
                    if mode == "validation":
                        branch_results[mode] = self._run_validation(project.project_id, task_id, array_input)
                    else:
                        branch_results[mode] = self.predictor.predict(array_input, mode)
                    branch_artifacts = self._write_branch(result_dir, mode, branch_results[mode])
                    artifacts.extend(branch_artifacts)
                    self.store.update_task(task_id, **{f"{mode}_status": "succeeded"}, message=f"{mode} 分支完成")
                except AppError as exc:
                    self.store.update_task(task_id, **{f"{mode}_status": "failed"}, message=exc.message, error=exc.to_dict())
                except Exception as exc:  # pragma: no cover
                    self.store.update_task(task_id, **{f"{mode}_status": "failed"}, message=str(exc), error={"code": "TASK_FAILED", "message": str(exc)})

            succeeded = [mode for mode in modes if mode in branch_results]
            if len(succeeded) == len(modes):
                status = "succeeded"
            elif succeeded:
                status = "partial_success"
            else:
                status = "failed"
            mode_name = "comparison" if set(succeeded) == {"prediction", "validation"} else (succeeded[0] if succeeded else modes[0])
            payload = {"task_id": task_id, "status": status, "mode": mode_name, "total_array_result": {mode: branch_results[mode].get("total_array") for mode in succeeded}, "files": artifacts}
            implementations = {
                mode: branch_results[mode].get("implementation", getattr(self.predictor, "implementation", type(self.predictor).__name__))
                for mode in succeeded
            }
            (result_dir / "metadata.json").write_text(
                json.dumps(
                    {
                        "task_id": task_id,
                        "implementations": implementations,
                        "hfss_mode": getattr(self.hfss, "mode", "unknown"),
                        "status": status,
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            artifacts.insert(0, {"name": "metadata.json", "type": "metadata", "source": "common", "downloadable": True})
            self.store.save_result(task_id, mode_name, payload, artifacts, str(result_dir))
            self.store.update_task(task_id, status=status, current_stage="result_persist", result_available=bool(succeeded), message="结果已生成" if succeeded else "评价任务失败")
        except Exception as exc:  # pragma: no cover
            error = {"code": "INTERNAL_ERROR", "message": str(exc)}
            self.store.update_task(task_id, status="failed", current_stage="result_persist", message=str(exc), error=error)

    def _run_validation(self, project_id: str, task_id: str, array_input: ArrayInput) -> dict[str, Any]:
        """执行 HFSS 验证并取得方向图结果。

        参数：project_id 为项目标识；task_id 为任务标识；array_input 为规范化阵列输入。
        返回：包含 `units` 和 `total_array` 的标准结果字典。开发 stub 未返回结果时使用
        预测替身保持本地流程可测；真实适配器缺少方向图结果时明确失败，禁止伪造验证通过。
        """

        adapter_response = self.hfss.run_validation(project_id, task_id, array_input.to_dict())
        if isinstance(adapter_response, dict):
            result = adapter_response.get("result")
            if isinstance(result, dict) and "units" in result and "total_array" in result:
                return result
        if getattr(self.hfss, "mode", "unknown") == "stub":
            return self.predictor.predict(array_input, "validation")
        raise AppError("TASK_FAILED", "HFSS 验证未返回标准方向图结果", 500)

    def _result_dir(self, project: Project, task_id: str) -> Path:
        """计算项目任务结果目录；参数为项目和任务 ID，返回目录路径。"""

        number = self.store.next_project_task_number(project.project_id)
        date = datetime.now().strftime("%Y-%m-%d")
        return self.settings.data_root / project.project_name / "output" / f"{date}_{number}"

    @staticmethod
    def _write_branch(result_dir: Path, mode: str, result: dict[str, Any]) -> list[dict[str, Any]]:
        """写入一个分支的标准结果和单元结果文件，返回 artifact 元数据。"""

        branch_dir = result_dir / mode
        branch_dir.mkdir(parents=True, exist_ok=True)
        (branch_dir / "total_array.json").write_text(json.dumps(result["total_array"], ensure_ascii=False), encoding="utf-8")
        (branch_dir / "unit_results.json").write_text(json.dumps(result["units"], ensure_ascii=False), encoding="utf-8")
        return [
            {"name": f"{mode}/total_array.json", "type": "total_array_data", "source": mode, "downloadable": True},
            {"name": f"{mode}/unit_results.json", "type": "unit_data", "source": mode, "downloadable": True},
        ]

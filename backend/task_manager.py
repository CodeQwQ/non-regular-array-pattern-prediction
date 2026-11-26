"""文件基本信息：backend/task_manager.py

目的：编排训练、预测、验证和双模式后台任务，校验训练产物并安装可用模型，维护主任务与分支状态。
输入：SQLiteStore、HFSSAdapter、PredictionEngine、项目和规范化输入。
输出：立即返回的 queued Task，后台更新状态、结果文件和错误证据。
维护：状态转换变化必须同步 api.md、openapi.yaml、验证规范和测试。
"""

from __future__ import annotations

import json
import logging
import math
import shutil
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from html import escape
from pathlib import Path
from typing import Any, Callable

from .algorithm import PredictionEngine
from .config import Settings
from .errors import AppError
from .hfss_adapter import HFSSAdapter
from .models import ArrayInput, Project, Task
from .storage import SQLiteStore


class TaskManager:
    """后台任务编排器；线程池容量由 Settings 限制为最多 4。"""

    def __init__(
        self,
        settings: Settings,
        store: SQLiteStore,
        hfss: HFSSAdapter,
        predictor: PredictionEngine,
        predictor_loader: Callable[[dict[str, Any]], PredictionEngine] | None = None,
    ) -> None:
        self.settings = settings
        self.store = store
        self.hfss = hfss
        self.predictor = predictor
        self.predictor_loader = predictor_loader
        self.executor = ThreadPoolExecutor(max_workers=settings.max_hfss_workers, thread_name_prefix="arraylab-task")
        self._lock = threading.Lock()
        self.logger = logging.getLogger("arraylab")

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
            training_response = self.hfss.run_training(project.project_id, task_id)
            self._require_adapter_success(training_response, "HFSS 训练")
            self._require_training_artifact(training_response)
            self.store.update_task(task_id, current_stage="model_training", message="正在训练预测模型")
            if self.predictor_loader is not None:
                # 真实训练必须在模型文件和平均方向图均可访问后才能宣布 ready。
                # loader 失败会进入统一失败路径，禁止把数据库状态写成 ready。
                self.predictor = self.predictor_loader(training_response)
            version = f"model_{task_id}"
            self.store.update_project(project.project_id, model_status="ready", model_version=version, last_error=None)
            self.store.update_task(task_id, status="succeeded", current_stage="model_training", message="模型训练完成，可执行评价")
        except AppError as exc:
            self.logger.error("training failed project_id=%s task_id=%s code=%s message=%s", project.project_id, task_id, exc.code, exc.message)
            self.store.update_project(project.project_id, model_status="failed", last_error=exc.to_dict())
            self.store.update_task(task_id, status="failed", current_stage="model_training", message=exc.message, error=exc.to_dict())
        except Exception as exc:  # pragma: no cover - 防止后台线程吞掉未知错误
            self.logger.exception("unexpected training failure project_id=%s task_id=%s", project.project_id, task_id)
            error = {"code": "INTERNAL_ERROR", "message": str(exc)}
            self.store.update_project(project.project_id, model_status="failed", last_error=error)
            self.store.update_task(task_id, status="failed", current_stage="model_training", message=str(exc), error=error)

    def _run_evaluation(self, task_id: str, project: Project, array_input: ArrayInput, modes: list[str]) -> None:
        """后台执行评价分支并生成单/双模式结果。"""

        branch_results: dict[str, dict[str, Any]] = {}
        branch_errors: dict[str, dict[str, Any]] = {}
        artifacts: list[dict[str, Any]] = []
        result_dir: Path | None = None
        staging_dir: Path | None = None
        result_persisted = False
        try:
            with self._lock:
                result_dir = self._result_dir(project, task_id)
                staging_dir = result_dir.with_name(f".{result_dir.name}.{task_id}.staging")
                staging_dir.mkdir(parents=True, exist_ok=False)
            (staging_dir / "input.json").write_text(json.dumps(array_input.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
            self.store.update_task(task_id, status="running", current_stage="prediction" if "prediction" in modes else "validation", message="评价任务执行中")
            for mode in modes:
                self.store.update_task(task_id, **{f"{mode}_status": "running"}, current_stage=mode, message=f"正在执行 {mode} 分支")
                try:
                    if mode == "validation":
                        raw_result = self._run_validation(project.project_id, task_id, array_input)
                    else:
                        raw_result = self.predictor.predict(array_input, mode)
                    branch_result = self._normalise_result(raw_result)
                    branch_artifacts = self._write_branch(staging_dir, mode, branch_result)
                    branch_results[mode] = branch_result
                    artifacts.extend(branch_artifacts)
                    self.store.update_task(task_id, **{f"{mode}_status": "succeeded"}, message=f"{mode} 分支完成")
                except AppError as exc:
                    self.logger.error("evaluation branch failed project_id=%s task_id=%s mode=%s code=%s message=%s", project.project_id, task_id, mode, exc.code, exc.message)
                    branch_errors[mode] = exc.to_dict()
                    self.store.update_task(task_id, **{f"{mode}_status": "failed"}, message=exc.message, error=exc.to_dict())
                except Exception as exc:  # pragma: no cover
                    self.logger.exception("unexpected evaluation branch failure project_id=%s task_id=%s mode=%s", project.project_id, task_id, mode)
                    branch_errors[mode] = {"error": {"code": "TASK_FAILED", "message": str(exc)}}
                    self.store.update_task(task_id, **{f"{mode}_status": "failed"}, message=str(exc), error=branch_errors[mode])

            succeeded = [mode for mode in modes if mode in branch_results]
            if len(succeeded) == len(modes):
                status = "succeeded"
            elif succeeded:
                status = "partial_success"
            else:
                status = "failed"
            mode_name = "comparison" if set(succeeded) == {"prediction", "validation"} else (succeeded[0] if succeeded else modes[0])
            comparison = None
            if set(succeeded) == {"prediction", "validation"}:
                comparison, comparison_artifacts = self._write_comparison(
                    staging_dir,
                    branch_results["prediction"]["total_array"],
                    branch_results["validation"]["total_array"],
                )
                artifacts.extend(comparison_artifacts)
            payload = {"task_id": task_id, "status": status, "mode": mode_name, "total_array_result": {mode: branch_results[mode].get("total_array") for mode in succeeded}, "files": artifacts}
            if comparison is not None:
                payload["comparison"] = comparison
            implementations = {
                mode: branch_results[mode].get(
                    "implementation",
                    "hfss_com" if mode == "validation" else getattr(self.predictor, "implementation", type(self.predictor).__name__),
                )
                for mode in succeeded
            }
            provenance = {
                mode: (
                    "predictor_stub_fallback"
                    if mode == "validation" and branch_results[mode].get("implementation") == "stub_prediction_fallback"
                    else "hfss_result"
                    if mode == "validation"
                    else "prediction_engine"
                )
                for mode in succeeded
            }
            metadata = {
                "task_id": task_id,
                "project_id": project.project_id,
                "project_name": project.project_name,
                "modes": modes,
                "model_version": project.model_version,
                "input_snapshot": "input.json",
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "branch_status": {mode: "succeeded" if mode in succeeded else "failed" for mode in modes},
                "branch_errors": branch_errors,
                "implementations": implementations,
                "provenance": provenance,
                "hfss_mode": getattr(self.hfss, "mode", "unknown"),
                "status": status,
            }
            (staging_dir / "metadata.json").write_text(
                json.dumps(metadata, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            artifacts.insert(0, {"name": "metadata.json", "type": "metadata", "source": "common", "downloadable": True})
            if succeeded:
                assert result_dir is not None and staging_dir is not None
                staging_dir.replace(result_dir)
                self.store.save_result(
                    task_id,
                    mode_name,
                    payload,
                    artifacts,
                    str(result_dir),
                    status=status,
                    current_stage="result_persist",
                    message="结果已生成",
                )
                result_persisted = True
            else:
                self.store.update_task(task_id, status="failed", current_stage="result_persist", result_available=False, message="评价任务失败")
                self._remove_result_path(staging_dir)
        except Exception as exc:  # pragma: no cover
            self.logger.exception("unexpected evaluation failure project_id=%s task_id=%s", project.project_id, task_id)
            if not result_persisted:
                self._remove_result_path(staging_dir)
                self._remove_result_path(result_dir)
            error = {"code": "INTERNAL_ERROR", "message": str(exc)}
            self.store.update_task(task_id, status="failed", current_stage="result_persist", message=str(exc), error=error)

    def _run_validation(self, project_id: str, task_id: str, array_input: ArrayInput) -> dict[str, Any]:
        """执行 HFSS 验证并取得方向图结果。

        参数：project_id 为项目标识；task_id 为任务标识；array_input 为规范化阵列输入。
        返回：包含 `units` 和 `total_array` 的标准结果字典。开发 stub 未返回结果时使用
        预测替身保持本地流程可测；真实适配器缺少方向图结果时明确失败，禁止伪造验证通过。
        """

        adapter_response = self.hfss.run_validation(project_id, task_id, array_input.to_dict())
        self._require_adapter_success(adapter_response, "HFSS 验证")
        if isinstance(adapter_response, dict):
            result = adapter_response.get("result")
            if isinstance(result, dict) and "units" in result and "total_array" in result:
                result = dict(result)
                result.setdefault("implementation", "hfss_com")
                return result
        if getattr(self.hfss, "mode", "unknown") == "stub":
            result = dict(self.predictor.predict(array_input, "validation"))
            result["implementation"] = "stub_prediction_fallback"
            return result
        raise AppError("TASK_FAILED", "HFSS 验证未返回标准方向图结果", 500)

    @staticmethod
    def _require_adapter_success(response: Any, stage: str) -> None:
        """要求 HFSS 适配器明确返回 succeeded；参数为响应和阶段名称，无返回值。"""

        if not isinstance(response, dict) or response.get("status") != "succeeded":
            status = response.get("status") if isinstance(response, dict) else "invalid_response"
            message = response.get("message") if isinstance(response, dict) else None
            raise AppError(
                "TASK_FAILED",
                message or f"{stage}未成功完成：{status}",
                500,
                details=[{"field": "adapter_status", "reason": str(status)}],
            )

    def _require_training_artifact(self, response: Any) -> None:
        """要求真实训练返回可访问模型产物；stub 模式允许使用开发替身。"""

        if getattr(self.hfss, "mode", "unknown") == "stub":
            return
        model_path = response.get("model_path") if isinstance(response, dict) else None
        if not isinstance(model_path, (str, Path)) or not Path(model_path).is_file():
            raise AppError("TASK_FAILED", "真实训练未返回可访问的模型产物", 500)

    @staticmethod
    def _normalise_result(result: dict[str, Any]) -> dict[str, Any]:
        """裁剪为可持久化的标准结果；移除 reference 计算用的复数中间数组。"""

        if not isinstance(result, dict) or not isinstance(result.get("total_array"), dict) or not isinstance(result.get("units"), dict):
            raise AppError("TASK_FAILED", "算法结果缺少 units 或 total_array", 500)
        total_array = result["total_array"]
        if not isinstance(total_array.get("records"), list):
            raise AppError("TASK_FAILED", "算法总阵结果缺少 records", 500)
        normalised = dict(result)
        normalised["total_array"] = {"records": total_array["records"]}
        try:
            json.dumps(normalised, ensure_ascii=False)
        except TypeError as exc:
            raise AppError("TASK_FAILED", f"算法结果不可序列化：{exc}", 500) from exc
        return normalised

    def _result_dir(self, project: Project, task_id: str) -> Path:
        """计算项目任务结果目录；参数为项目和任务 ID，返回目录路径。"""

        number = self.store.next_project_task_number(project.project_id)
        date = datetime.now().strftime("%Y-%m-%d")
        base = self.settings.data_root / project.project_name / "output"
        candidate = base / f"{date}_{number}"
        while candidate.exists():
            number += 1
            candidate = base / f"{date}_{number}"
        return candidate

    @staticmethod
    def _remove_result_path(path: Path | None) -> None:
        """删除未提交结果目录；参数为临时或已发布目录，返回 None。"""

        if path is None or not path.exists():
            return
        if path.is_dir():
            shutil.rmtree(path, ignore_errors=True)
        else:
            path.unlink(missing_ok=True)

    @staticmethod
    def _write_branch(result_dir: Path, mode: str, result: dict[str, Any]) -> list[dict[str, Any]]:
        """写入一个分支的标准结果、单元结果和总阵 SVG 图，返回 artifact 元数据。"""

        branch_dir = result_dir / mode
        branch_dir.mkdir(parents=True, exist_ok=True)
        (branch_dir / "total_array.json").write_text(json.dumps(result["total_array"], ensure_ascii=False), encoding="utf-8")
        (branch_dir / "unit_results.json").write_text(json.dumps(result["units"], ensure_ascii=False), encoding="utf-8")
        (branch_dir / "total_array.svg").write_text(TaskManager._pattern_svg(result["total_array"].get("records", []), f"{mode} total array"), encoding="utf-8")
        return [
            {"name": f"{mode}/total_array.json", "type": "total_array_data", "source": mode, "downloadable": True},
            {"name": f"{mode}/unit_results.json", "type": "unit_data", "source": mode, "downloadable": True},
            {"name": f"{mode}/total_array.svg", "type": "result_plot", "source": mode, "downloadable": True},
        ]

    @staticmethod
    def _pattern_svg(records: list[dict[str, Any]], title: str, series: list[tuple[str, str, list[dict[str, Any]]]] | None = None) -> str:
        """将 Theta=0° 切面转换为可下载 SVG；参数为记录、标题和可选多序列。"""

        if series is None:
            series = [(title, "#245bd6", records)]
        points_by_series: list[tuple[str, str, str]] = []
        for name, color, source in series:
            cut = sorted((row for row in source if float(row.get("Theta[deg]", 0)) == 0), key=lambda row: float(row.get("Phi[deg]", 0)))
            values = [float(row.get("ECP_dB", 0)) for row in cut]
            if not values:
                continue
            low, high = min(values), max(values)
            span = high - low or 1.0
            points = " ".join(
                f"{20 + index * 560 / max(len(values) - 1, 1):.2f},{180 - (value - low) * 150 / span:.2f}"
                for index, value in enumerate(values)
            )
            points_by_series.append((name, color, points))
        polylines = "".join(f'<polyline points="{points}" fill="none" stroke="{color}" stroke-width="2" />' for _, color, points in points_by_series)
        legend = "".join(f'<text x="20" y="{18 + index * 16}" fill="{color}" font-size="11">{escape(name)}</text>' for index, (name, color, _) in enumerate(points_by_series))
        return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 600 210"><title>{escape(title)}</title><rect width="600" height="210" fill="#fbfcfe"/><line x1="20" y1="180" x2="580" y2="180" stroke="#cbd5e1"/>{polylines}{legend}</svg>'

    @staticmethod
    def _write_comparison(result_dir: Path, prediction: dict[str, Any], validation: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        """写入双模式对比图和误差指标，返回公开 comparison 数据及 artifact 元数据。"""

        comparison_dir = result_dir / "comparison"
        comparison_dir.mkdir(parents=True, exist_ok=True)
        prediction_records = prediction.get("records", [])
        validation_records = validation.get("records", [])
        validation_map = {(row.get("Theta[deg]"), row.get("Phi[deg]")): row for row in validation_records}
        pairs = [
            (row, validation_map[(row.get("Theta[deg]"), row.get("Phi[deg]"))])
            for row in prediction_records
            if (row.get("Theta[deg]"), row.get("Phi[deg]")) in validation_map
        ]
        amp_diffs = [float(pred.get("ECP_dB", 0)) - float(real.get("ECP_dB", 0)) for pred, real in pairs]
        phase_diffs = [((float(pred.get("ECP_Phase_deg", 0)) - float(real.get("ECP_Phase_deg", 0)) + 180.0) % 360.0) - 180.0 for pred, real in pairs]
        metrics = {
            "sample_count": len(pairs),
            "amp_rmse_dB": math.sqrt(sum(value * value for value in amp_diffs) / len(amp_diffs)) if amp_diffs else None,
            "amp_mae_dB": sum(abs(value) for value in amp_diffs) / len(amp_diffs) if amp_diffs else None,
            "phase_rmse_deg": math.sqrt(sum(value * value for value in phase_diffs) / len(phase_diffs)) if phase_diffs else None,
            "phase_mae_deg": sum(abs(value) for value in phase_diffs) / len(phase_diffs) if phase_diffs else None,
        }
        (comparison_dir / "comparison_metrics.json").write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")
        (comparison_dir / "total_array_comparison.svg").write_text(
            TaskManager._pattern_svg(
                prediction_records,
                "prediction and validation comparison",
                [("prediction", "#245bd6", prediction_records), ("validation", "#d65b45", validation_records)],
            ),
            encoding="utf-8",
        )
        return {"metrics": metrics}, [
            {"name": "comparison/comparison_metrics.json", "type": "comparison_metrics", "source": "comparison", "downloadable": True},
            {"name": "comparison/total_array_comparison.svg", "type": "comparison_plot", "source": "comparison", "downloadable": True},
        ]

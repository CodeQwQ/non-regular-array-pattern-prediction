"""文件基本信息：tests/integration/test_backend_flow.py

目的：验证 SQLite、后台任务、开发 HFSSAdapter、结果持久化和 ZIP 下载。
输入：临时 .aedt 文件和临时数据库/数据目录。
输出：pytest 集成测试证据。
维护：行为变化同步验收场景、追踪矩阵和集成目录索引。
"""

import time
from pathlib import Path

import pytest

from backend.application import Application
from backend.config import Settings
from backend.errors import AppError
from backend.models import ArrayInput, ArrayUnit


class ResultHFSSAdapter:
    """返回标准验证结果的真实适配器最小替身。"""

    mode = "real"

    def run_validation(self, project_id, task_id, array_input):
        """返回包含标准 result 的验证响应。"""

        record = {"Phi[deg]": 0.0, "Theta[deg]": 0.0, "ECP_dB": -1.0, "ECP_Phase_deg": 2.0}
        return {"status": "succeeded", "result": {"implementation": "hfss_com", "units": {"1": [record]}, "total_array": {"records": [record]}}}


class EmptyRealHFSSAdapter(ResultHFSSAdapter):
    """不返回方向图的真实适配器替身。"""

    def run_validation(self, project_id, task_id, array_input):
        """返回缺少 result 的响应，验证必须失败。"""

        return {"status": "succeeded"}


class FailedHFSSAdapter(ResultHFSSAdapter):
    """返回失败状态的 HFSS 适配器替身。"""

    def run_training(self, project_id, task_id):
        """返回失败训练状态。"""

        return {"status": "failed", "message": "HFSS 训练失败"}

    def run_validation(self, project_id, task_id, array_input):
        """返回失败验证状态，即使携带结果也不得成功。"""

        return {"status": "failed", "result": {"units": {}, "total_array": {"records": []}}}


def wait_terminal(app: Application, task_id: str) -> dict:
    """轮询任务至终态；参数为应用和任务 ID，返回终态字典。"""

    for _ in range(100):
        state = app.get_task(task_id)
        if state["status"] in {"succeeded", "partial_success", "failed"}:
            return state
        time.sleep(0.01)
    raise AssertionError(f"task did not finish: {task_id}")


@pytest.mark.integration
def test_training_prediction_result_and_download(tmp_path: Path):
    """覆盖绑定、训练、预测、结果网格和下载 ZIP。"""

    aedt = tmp_path / "demo.aedt"
    aedt.write_text("stub", encoding="utf-8")
    app = Application(Settings("127.0.0.1", 0, tmp_path / "state.sqlite3", tmp_path / "data", "stub", 4))
    try:
        project_response, project_status = app.create_project({"hfss_project_path": str(aedt)})
        assert project_status == 201
        training, status = app.start_training(project_response["project_id"])
        assert status == 202
        assert wait_terminal(app, training["task_id"])["status"] == "succeeded"

        evaluation, status = app.create_evaluation(project_response["project_id"], {
            "input": {"unit_count": 1, "units": [{"unit_id": 1, "i": 1, "j": 1, "x": 0, "y": 0}]},
            "modes": ["prediction"],
        })
        assert status == 202
        assert wait_terminal(app, evaluation["task_id"])["status"] == "succeeded"
        result = app.get_results(evaluation["task_id"])
        assert result["mode"] == "prediction"
        assert len(result["total_array_result"]["prediction"]["records"]) == 16471
        metadata = next(path for path in (tmp_path / "data").rglob("metadata.json"))
        assert metadata.read_text(encoding="utf-8").find('"implementations": {') >= 0
        assert '"stub"' in metadata.read_text(encoding="utf-8")
        archive, filename = app.download_results(evaluation["task_id"])
        assert archive[:2] == b"PK"
        assert filename.endswith(".zip")
    finally:
        app.close()


@pytest.mark.integration
def test_real_hfss_validation_uses_adapter_result_and_fails_without_it(tmp_path: Path):
    """验证真实 HFSS 返回结果被采用，缺少结果时不伪造验证通过。"""

    app = Application(Settings("127.0.0.1", 0, tmp_path / "state.sqlite3", tmp_path / "data", "stub", 4))
    array_input = ArrayInput(1, (ArrayUnit(1, 1, 1, 0.0, 0.0),))
    try:
        app.tasks.hfss = ResultHFSSAdapter()
        result = app.tasks._run_validation("project_1", "task_1", array_input)
        assert result["implementation"] == "hfss_com"
        app.tasks.hfss = EmptyRealHFSSAdapter()
        with pytest.raises(AppError, match="未返回标准方向图结果"):
            app.tasks._run_validation("project_1", "task_2", array_input)
        app.tasks.hfss = FailedHFSSAdapter()
        with pytest.raises(AppError, match="未成功完成"):
            app.tasks._run_validation("project_1", "task_3", array_input)
        normalised = app.tasks._normalise_result({"implementation": "xgboost_reference", "units": {}, "total_array": {"records": [], "complex_field": [1 + 0j]}})
        assert normalised["total_array"] == {"records": []}
    finally:
        app.close()


@pytest.mark.integration
def test_failed_hfss_training_does_not_mark_model_ready(tmp_path: Path):
    """验证 HFSS 训练返回 failed 时模型保持不可用。"""

    aedt = tmp_path / "failed-training.aedt"
    aedt.write_text("stub", encoding="utf-8")
    app = Application(Settings("127.0.0.1", 0, tmp_path / "state.sqlite3", tmp_path / "data", "stub", 4))
    try:
        project, _ = app.create_project({"hfss_project_path": str(aedt)})
        app.tasks.hfss = FailedHFSSAdapter()
        training, _ = app.start_training(project["project_id"])
        state = wait_terminal(app, training["task_id"])
        assert state["status"] == "failed"
        assert app.get_project(project["project_id"])["model_status"] == "failed"
    finally:
        app.close()


@pytest.mark.integration
def test_evaluation_setup_failure_reaches_failed_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """验证结果目录初始化失败不会让任务永久停留在 queued/running。"""

    aedt = tmp_path / "failed-evaluation-setup.aedt"
    aedt.write_text("stub", encoding="utf-8")
    app = Application(Settings("127.0.0.1", 0, tmp_path / "state.sqlite3", tmp_path / "data", "stub", 4))
    try:
        project, _ = app.create_project({"hfss_project_path": str(aedt)})
        training, _ = app.start_training(project["project_id"])
        assert wait_terminal(app, training["task_id"])["status"] == "succeeded"
        monkeypatch.setattr(app.tasks, "_result_dir", lambda *_args: (_ for _ in ()).throw(OSError("disk unavailable")))
        evaluation, _ = app.create_evaluation(
            project["project_id"],
            {
                "input": {"unit_count": 1, "units": [{"unit_id": 1, "i": 1, "j": 1, "x": 0, "y": 0}]},
                "modes": ["prediction"],
            },
        )
        state = wait_terminal(app, evaluation["task_id"])
        assert state["status"] == "failed"
        assert state["result_available"] is False
    finally:
        app.close()

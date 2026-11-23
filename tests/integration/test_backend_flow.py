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
        archive, filename = app.download_results(evaluation["task_id"])
        assert archive[:2] == b"PK"
        assert filename.endswith(".zip")
    finally:
        app.close()

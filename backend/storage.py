"""文件基本信息：backend/storage.py

目的：以 SQLite 保存项目、模型、任务、分支和结果索引，并以文件保存大结果。
输入：Settings、项目/任务/结果字段。
输出：Project、Task 和结果字典。
维护：schema 变更必须同步 API、架构、追踪矩阵和迁移说明。
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from .models import Project, Task, utc_now


class SQLiteStore:
    """线程安全的轻量 SQLite repository；每次操作使用独立连接。"""

    def __init__(self, db_path: Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.init_schema()

    def _connect(self) -> sqlite3.Connection:
        """创建 SQLite 连接；无参数，返回 Row 工厂连接。"""

        conn = sqlite3.connect(self.db_path, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    @contextmanager
    def _session(self):
        """提供会提交并关闭的 SQLite 会话；无参数，返回上下文管理器。"""

        conn = self._connect()
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def init_schema(self) -> None:
        """创建项目、任务和结果索引表；无参数，返回 None。"""

        with self._session() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS projects (
                    project_id TEXT PRIMARY KEY, project_name TEXT NOT NULL,
                    hfss_project_path TEXT NOT NULL, hfss_project_name TEXT NOT NULL,
                    binding_status TEXT NOT NULL, model_status TEXT NOT NULL,
                    model_version TEXT, last_error_json TEXT,
                    created_at TEXT NOT NULL, updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS tasks (
                    task_id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(project_id),
                    task_type TEXT NOT NULL, status TEXT NOT NULL, current_stage TEXT NOT NULL,
                    prediction_status TEXT, validation_status TEXT, message TEXT, error_json TEXT,
                    input_json TEXT, modes_json TEXT, model_version TEXT,
                    result_available INTEGER NOT NULL DEFAULT 0, result_dir TEXT,
                    created_at TEXT NOT NULL, updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS task_results (
                    task_id TEXT PRIMARY KEY REFERENCES tasks(task_id), mode TEXT NOT NULL,
                    payload_json TEXT NOT NULL, artifacts_json TEXT NOT NULL, created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_tasks_project ON tasks(project_id);
                """
            )

    def create_project(self, hfss_project_path: str, project_name: str | None = None) -> Project:
        """创建已绑定、待训练项目。

        参数：hfss_project_path 为已校验工程路径；project_name 为可选显示名。
        返回：binding_status=ready_to_train、model_status=unbound 的 Project。
        """

        now = utc_now()
        path = Path(hfss_project_path)
        project = Project(f"project_{uuid.uuid4().hex[:12]}", project_name or path.stem, str(path), path.name, "ready_to_train", "unbound", now, now)
        with self._session() as conn:
            conn.execute("INSERT INTO projects VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", (project.project_id, project.project_name, project.hfss_project_path, project.hfss_project_name, project.binding_status, project.model_status, None, None, now, now))
        return project

    def list_projects(self) -> list[Project]:
        """返回全部项目；无参数，按更新时间倒序返回 Project 列表。"""

        with self._session() as conn:
            rows = conn.execute("SELECT * FROM projects ORDER BY updated_at DESC").fetchall()
        return [self._project(row) for row in rows]

    def get_project(self, project_id: str) -> Project | None:
        """查询项目；参数为 project_id，返回 Project 或 None。"""

        with self._session() as conn:
            row = conn.execute("SELECT * FROM projects WHERE project_id = ?", (project_id,)).fetchone()
        return self._project(row) if row else None

    def update_project(self, project_id: str, **fields: Any) -> Project:
        """更新项目白名单字段并返回项目。

        参数：project_id 为项目标识；fields 可包含 binding_status、model_status、model_version、last_error。
        返回：更新后的 Project；不存在时抛出 KeyError。
        """

        allowed = {"binding_status", "model_status", "model_version", "last_error"}
        if set(fields) - allowed:
            raise ValueError(f"unsupported project fields: {sorted(set(fields) - allowed)}")
        if not fields:
            project = self.get_project(project_id)
            if project is None:
                raise KeyError(project_id)
            return project
        assignments, values = [], []
        for key, value in fields.items():
            column = "last_error_json" if key == "last_error" else key
            assignments.append(f"{column} = ?")
            values.append(json.dumps(value, ensure_ascii=False) if key == "last_error" and value is not None else value)
        assignments.append("updated_at = ?")
        values.extend([utc_now(), project_id])
        with self._session() as conn:
            if conn.execute(f"UPDATE projects SET {', '.join(assignments)} WHERE project_id = ?", values).rowcount != 1:
                raise KeyError(project_id)
        project = self.get_project(project_id)
        assert project is not None
        return project

    def create_task(self, project_id: str, task_type: str, input_payload: dict[str, Any] | None = None, modes: list[str] | None = None, model_version: str | None = None) -> Task:
        """创建 queued 任务并保存输入快照。

        参数：项目、任务类型、规范化输入、模式列表和模型版本。
        返回：新建 Task。
        """

        now = utc_now()
        task = Task(f"task_{task_type}_{uuid.uuid4().hex[:12]}", project_id, task_type, "queued", "queued", False, "not_selected" if modes and "prediction" not in modes else None, "not_selected" if modes and "validation" not in modes else None, "任务已创建", None, now, now)
        with self._session() as conn:
            conn.execute("""INSERT INTO tasks(task_id,project_id,task_type,status,current_stage,prediction_status,validation_status,message,error_json,input_json,modes_json,model_version,result_available,result_dir,created_at,updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, NULL, ?, ?)""", (task.task_id, project_id, task_type, task.status, task.current_stage, task.prediction_status, task.validation_status, task.message, None, json.dumps(input_payload, ensure_ascii=False) if input_payload is not None else None, json.dumps(modes) if modes is not None else None, model_version, now, now))
        return task

    def update_task(self, task_id: str, **fields: Any) -> Task:
        """更新任务状态字段并返回最新 Task。"""

        allowed = {"status", "current_stage", "prediction_status", "validation_status", "message", "error", "result_available", "result_dir"}
        if set(fields) - allowed:
            raise ValueError(f"unsupported task fields: {sorted(set(fields) - allowed)}")
        if not fields:
            task = self.get_task(task_id)
            if task is None:
                raise KeyError(task_id)
            return task
        assignments, values = [], []
        for key, value in fields.items():
            column = "error_json" if key == "error" else key
            assignments.append(f"{column} = ?")
            values.append(json.dumps(value, ensure_ascii=False) if key == "error" and value is not None else (1 if key == "result_available" and value else 0 if key == "result_available" else value))
        assignments.append("updated_at = ?")
        values.extend([utc_now(), task_id])
        with self._session() as conn:
            if conn.execute(f"UPDATE tasks SET {', '.join(assignments)} WHERE task_id = ?", values).rowcount != 1:
                raise KeyError(task_id)
        task = self.get_task(task_id)
        assert task is not None
        return task

    def get_task(self, task_id: str) -> Task | None:
        """查询任务；参数为 task_id，返回 Task 或 None。"""

        with self._session() as conn:
            row = conn.execute("SELECT * FROM tasks WHERE task_id = ?", (task_id,)).fetchone()
        return self._task(row) if row else None

    def get_task_context(self, task_id: str) -> dict[str, Any] | None:
        """返回任务及其输入、模式、模型版本和结果目录等内部字段。"""

        with self._session() as conn:
            row = conn.execute("SELECT * FROM tasks WHERE task_id = ?", (task_id,)).fetchone()
        if row is None:
            return None
        data = dict(row)
        data["input"] = json.loads(data["input_json"]) if data["input_json"] else None
        data["modes"] = json.loads(data["modes_json"]) if data["modes_json"] else []
        data["error"] = json.loads(data["error_json"]) if data["error_json"] else None
        return data

    def next_project_task_number(self, project_id: str) -> int:
        """返回项目下下一个结果目录序号；参数为 project_id，返回从 1 开始的整数。"""

        with self._session() as conn:
            row = conn.execute("SELECT COUNT(*) AS count FROM tasks WHERE project_id = ?", (project_id,)).fetchone()
        return int(row["count"]) + 1

    def save_result(self, task_id: str, mode: str, payload: dict[str, Any], artifacts: list[dict[str, Any]], result_dir: str) -> None:
        """保存结果索引并标记任务可用；参数为任务、模式、结果、文件元数据和目录。"""

        now = utc_now()
        with self._session() as conn:
            conn.execute("INSERT OR REPLACE INTO task_results(task_id,mode,payload_json,artifacts_json,created_at) VALUES (?,?,?,?,?)", (task_id, mode, json.dumps(payload, ensure_ascii=False), json.dumps(artifacts, ensure_ascii=False), now))
            conn.execute("UPDATE tasks SET result_available=1,result_dir=?,updated_at=? WHERE task_id=?", (result_dir, now, task_id))

    def get_result(self, task_id: str) -> dict[str, Any] | None:
        """查询结果；参数为 task_id，返回结果字典或 None。"""

        with self._session() as conn:
            row = conn.execute("SELECT * FROM task_results WHERE task_id = ?", (task_id,)).fetchone()
        if row is None:
            return None
        return {"task_id": task_id, "mode": row["mode"], "payload": json.loads(row["payload_json"]), "artifacts": json.loads(row["artifacts_json"]), "created_at": row["created_at"]}

    @staticmethod
    def _project(row: sqlite3.Row) -> Project:
        """将 SQLite 行转换为 Project。"""

        return Project(row["project_id"], row["project_name"], row["hfss_project_path"], row["hfss_project_name"], row["binding_status"], row["model_status"], row["created_at"], row["updated_at"], row["model_version"], json.loads(row["last_error_json"]) if row["last_error_json"] else None)

    @staticmethod
    def _task(row: sqlite3.Row) -> Task:
        """将 SQLite 行转换为 Task。"""

        return Task(row["task_id"], row["project_id"], row["task_type"], row["status"], row["current_stage"], bool(row["result_available"]), row["prediction_status"], row["validation_status"], row["message"], json.loads(row["error_json"]) if row["error_json"] else None, row["created_at"], row["updated_at"])

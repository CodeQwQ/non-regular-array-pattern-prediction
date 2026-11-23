"""文件基本信息：backend/cleanup.py

目的：实现项目 temp/output 数据三个月保留和独立清理进程。
输入：数据根目录、当前时间和保留天数。
输出：清理统计；失败记录不阻断主服务。
维护：清理规则变化必须同步 requirements.md、验证规范、任务追踪和测试。
"""

from __future__ import annotations

import multiprocessing
import shutil
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path


@dataclass
class CleanupReport:
    """清理执行报告。"""

    removed: list[str] = field(default_factory=list)
    failures: list[dict[str, str]] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        """序列化报告；无参数，返回 removed/failures 字典。"""

        return {"removed": self.removed, "failures": self.failures}


def cleanup_expired(data_root: str | Path, now: datetime | None = None, retention_days: int = 90) -> CleanupReport:
    """清理 temp/output 下超过保留期的文件和目录。

    参数：data_root 为项目数据根目录；now 为可注入当前时间；retention_days 为保留天数。
    返回：CleanupReport；单个路径失败会记录 failures，不向上阻断主服务。
    """

    root = Path(data_root)
    report = CleanupReport()
    if not root.exists():
        return report
    current = now or datetime.now(timezone.utc)
    cutoff = current - timedelta(days=retention_days)
    cutoff_timestamp = cutoff.timestamp()
    for project in root.iterdir():
        if not project.is_dir():
            continue
        for bucket_name in ("temp", "output"):
            bucket = project / bucket_name
            if not bucket.exists():
                continue
            for child in list(bucket.iterdir()):
                try:
                    if child.stat().st_mtime >= cutoff_timestamp:
                        continue
                    if child.is_dir():
                        shutil.rmtree(child)
                    else:
                        child.unlink()
                    report.removed.append(str(child))
                except OSError as exc:
                    report.failures.append({"path": str(child), "reason": str(exc)})
    return report


def _cleanup_worker(data_root: str, retention_days: int) -> None:
    """独立进程入口；参数为数据根目录和保留天数，结果写入日志由调用方负责。"""

    cleanup_expired(data_root, retention_days=retention_days)


def start_cleanup_process(data_root: str | Path, retention_days: int = 90) -> multiprocessing.Process:
    """启动独立清理进程。

    参数：data_root 为数据根目录；retention_days 为保留天数。
    返回：已 start 的 multiprocessing.Process；主进程不等待清理完成。
    """

    process = multiprocessing.Process(target=_cleanup_worker, args=(str(data_root), retention_days), name="arraylab-cleanup")
    process.daemon = True
    process.start()
    return process

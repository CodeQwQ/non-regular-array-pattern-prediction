"""文件基本信息：tests/unit/test_cleanup.py

目的：验证三个月清理边界、temp/output 范围和失败隔离。
输入：临时项目数据目录和可注入当前时间。
输出：pytest 清理测试结果。
维护：保留期或目录规则变化同步 requirements、验证规范和本测试。
"""

import os
from datetime import datetime, timedelta, timezone

import pytest

from backend.cleanup import cleanup_expired


@pytest.mark.unit
def test_cleanup_removes_expired_temp_and_output_but_keeps_recent(tmp_path):
    """验证旧 temp/output 项会删除，新文件会保留。"""

    project = tmp_path / "demo"
    old_temp = project / "temp" / "old.log"
    old_output = project / "output" / "old_result"
    recent = project / "output" / "recent.json"
    old_temp.parent.mkdir(parents=True)
    old_output.mkdir(parents=True)
    old_temp.write_text("old", encoding="utf-8")
    (old_output / "result.json").write_text("old", encoding="utf-8")
    recent.write_text("recent", encoding="utf-8")
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    old_timestamp = (now - timedelta(days=91)).timestamp()
    for path in (old_temp, old_output):
        os.utime(path, (old_timestamp, old_timestamp))
    report = cleanup_expired(tmp_path, now=now)
    assert not old_temp.exists()
    assert not old_output.exists()
    assert recent.exists()
    assert len(report.removed) == 2


@pytest.mark.unit
def test_cleanup_missing_root_is_non_blocking(tmp_path):
    """验证不存在的数据根目录不会阻断启动。"""

    report = cleanup_expired(tmp_path / "missing")
    assert report.to_dict() == {"removed": [], "failures": []}

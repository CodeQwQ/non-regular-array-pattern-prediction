"""文件基本信息：tests/unit/test_server_manifest.py

目的：验证服务器验收 manifest 的必填工程、RUN-ID 和 SHA-256 记录。
输入：临时 .aedt 文件和环境变量 monkeypatch。
输出：pytest manifest 测试结果。
维护：服务器证据字段变化同步验证规范、验收场景清单和服务器验收记录。
"""

import hashlib

import pytest

from scripts.collect_server_manifest import build_manifest


@pytest.mark.unit
def test_server_manifest_records_project_hash(tmp_path, monkeypatch):
    """验证 manifest 记录工程路径和 SHA-256。"""

    project = tmp_path / "server.aedt"
    project.write_text("hfss", encoding="utf-8")
    monkeypatch.setenv("ARRAYLAB_HFSS_PROJECT_PATH", str(project))
    monkeypatch.setenv("ARRAYLAB_RUN_ID", "RUN-TEST-HFSS")
    manifest = build_manifest()
    expected = hashlib.sha256(project.read_bytes()).hexdigest()
    assert manifest["run_id"] == "RUN-TEST-HFSS"
    assert manifest["project"]["project"]["sha256"] == expected


@pytest.mark.unit
def test_server_manifest_requires_project(monkeypatch):
    """验证缺少服务器工程时 fail-loud。"""

    monkeypatch.delenv("ARRAYLAB_HFSS_PROJECT_PATH", raising=False)
    with pytest.raises(RuntimeError, match="ARRAYLAB_HFSS_PROJECT_PATH"):
        build_manifest()

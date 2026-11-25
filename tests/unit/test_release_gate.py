"""文件基本信息：tests/unit/test_release_gate.py

目的：验证发布门禁拒绝 stub/缺失 manifest，并接受完整 passed 证据。
输入：临时 reference/HFSS manifest 和环境变量。
输出：pytest 发布门禁结果。
维护：发布条件变化同步验证规范、验收场景清单和追踪矩阵。
"""

import json

import pytest

from scripts.check_release_gate import check_release_gate


@pytest.mark.unit
def test_release_gate_rejects_stub(monkeypatch):
    """验证 stub 模式不能发布。"""

    monkeypatch.setenv("ARRAYLAB_PREDICTOR_MODE", "stub")
    with pytest.raises(RuntimeError, match="reference"):
        check_release_gate()


@pytest.mark.unit
def test_release_gate_accepts_reference_and_hfss_manifests(tmp_path, monkeypatch):
    """验证完整 reference/HFSS passed manifest 可以通过。"""

    reference = tmp_path / "reference.json"
    hfss = tmp_path / "hfss.json"
    reference.write_text(json.dumps({"real_hfss_data": True}), encoding="utf-8")
    hfss.write_text(json.dumps({"acceptance_status": "passed"}), encoding="utf-8")
    monkeypatch.setenv("ARRAYLAB_PREDICTOR_MODE", "reference")
    monkeypatch.setenv("ARRAYLAB_REFERENCE_MANIFEST", str(reference))
    monkeypatch.setenv("ARRAYLAB_HFSS_RUN_MANIFEST", str(hfss))
    monkeypatch.setenv("ARRAYLAB_HFSS_ACCEPTANCE_STATUS", "passed")
    assert check_release_gate()["status"] == "passed"

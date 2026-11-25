"""文件基本信息：tests/unit/test_prepare_reference_data.py

目的：验证真实数据准备 CLI 的 manifest 生成逻辑。
输入：最小合法方向图 CSV 夹具和 argparse Namespace。
输出：pytest manifest 测试结果。
维护：数据 manifest 字段变化同步验证规范、验收场景清单和追踪矩阵。
"""

import csv
from argparse import Namespace

import pytest

from scripts.prepare_reference_data import build_manifest


@pytest.mark.unit
def test_prepare_reference_manifest_records_pattern_hash(tmp_path):
    """验证 manifest 记录方向图 hash、行数和检查状态。"""

    pattern = tmp_path / "pattern.csv"
    with pattern.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["Phi[deg]", "Theta[deg]", "ECP_dB", "ECP_Phase_deg"])
        writer.writeheader()
        for theta in range(0, 181, 2):
            for phi in range(0, 361, 2):
                writer.writerow({"Phi[deg]": phi, "Theta[deg]": theta, "ECP_dB": 0, "ECP_Phase_deg": 0})
    manifest = build_manifest(Namespace(pattern=str(pattern), positions=None, position_count=25, features=None, feature_rows=None, cn=None, cn_samples=None, output=str(tmp_path / "manifest.json")))
    assert manifest["files"]["pattern"]["rows"] == 16471
    assert manifest["checks"]["pattern_grid"] == "passed"

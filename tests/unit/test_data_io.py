"""文件基本信息：tests/unit/test_data_io.py

目的：验证方向图、位置表、特征和 cn CSV 的 fail-loud 读取规则。
输入：临时 CSV 夹具。
输出：pytest 数据适配测试结果。
维护：列名、单位、行数或网格规则变化必须同步 requirements、黄金基线和本测试。
"""

import csv

import pytest

from backend.data_io import CN_FIELDS, FEATURE_FIELDS, PATTERN_FIELDS, load_cn_dataset, load_feature_csv, load_pattern_csv, load_position_table


@pytest.mark.unit
def test_pattern_csv_validates_exact_grid_keys(tmp_path):
    """验证方向图字段、点数和重复键。"""

    path = tmp_path / "pattern.csv"
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=PATTERN_FIELDS)
        writer.writeheader()
        writer.writerows([
            {"Phi[deg]": 0, "Theta[deg]": 0, "ECP_dB": -1, "ECP_Phase_deg": 2},
            {"Phi[deg]": 2, "Theta[deg]": 0, "ECP_dB": -2, "ECP_Phase_deg": 3},
        ])
    records = load_pattern_csv(path, expected_point_count=2, verify_grid=False)
    assert records[1]["Phi[deg]"] == 2.0

    duplicate = tmp_path / "duplicate.csv"
    duplicate.write_text(
        "Phi[deg],Theta[deg],ECP_dB,ECP_Phase_deg\n0,0,-1,2\n0,0,-2,3\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="重复"):
        load_pattern_csv(duplicate, expected_point_count=2, verify_grid=False)


@pytest.mark.unit
def test_position_table_converts_mil_to_meter_and_checks_ids(tmp_path):
    """验证位置表 unit_id 连续性和 mil→m 转换。"""

    path = tmp_path / "positions.csv"
    path.write_text("unit_id,abs_x,abs_y\n1,100,0\n2,0,100\n", encoding="utf-8")
    assert load_position_table(path, 2) == [(2.54, 0.0), (0.0, 2.54)]
    path.write_text("unit_id,abs_x,abs_y\n1,100,0\n1,0,100\n", encoding="utf-8")
    with pytest.raises(ValueError, match="连续"):
        load_position_table(path, 2)


@pytest.mark.unit
def test_feature_and_cn_dataset_headers_are_strict(tmp_path):
    """验证特征列、cn 列和 25 元素分组。"""

    feature_path = tmp_path / "features.csv"
    feature_path.write_text(",".join(FEATURE_FIELDS) + "\n" + ",".join(["1"] * 8) + "\n", encoding="utf-8")
    assert load_feature_csv(feature_path, 1) == [[1.0] * 8]

    cn_path = tmp_path / "cn.csv"
    with cn_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=CN_FIELDS)
        writer.writeheader()
        for element_id in range(1, 26):
            row = {field: 0 for field in CN_FIELDS}
            row["element_id"] = element_id
            writer.writerow(row)
    columns, rows = load_cn_dataset(cn_path, 1)
    assert columns == list(CN_FIELDS)
    assert len(rows) == 25

    with cn_path.open("a", encoding="utf-8") as handle:
        handle.write("0,0,0,0,0,0,0,0,1,0,0\n")
    with pytest.raises(ValueError, match="25 的整数倍"):
        load_cn_dataset(cn_path)

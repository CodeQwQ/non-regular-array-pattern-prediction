"""文件基本信息：tests/unit/test_reference_engine.py

目的：验证真实预测链路的注入式编排，不需要 xgboost 或 HFSS。
输入：单方向图、1×1 虚拟阵列和假 cn 模型。
输出：单元 ECP、总阵结果和实现标识测试结果。
维护：真实算法接入前后同步 ALG-EQ-001 黄金夹具和任务卡。
"""

import pytest

from backend.models import ArrayInput, ArrayUnit
from backend.reference_engine import ReferencePredictionEngine


class FakeCnModel:
    """返回固定 cn 的最小模型替身。"""

    def predict(self, features):
        """参数为模型输入行，返回每行 cn 实/虚部。"""

        assert len(features) == 1
        assert len(features[0]) == 9
        return [[1.0, 0.0]]


class FullFakeCnModel:
    """返回 25 个虚拟阵元的固定 cn。"""

    def predict(self, features):
        """参数为 25 行 9 列特征，返回 25 行 cn。"""

        assert len(features) == 25
        assert all(len(row) == 9 for row in features)
        return [[1.0 if index == 0 else 0.0, 0.0] for index in range(25)]


@pytest.mark.unit
def test_reference_engine_wires_model_z_ecp_and_total_field():
    """验证模型→Z@cn→ECP→总阵的最小链路。"""

    pattern = [{"Phi[deg]": 0.0, "Theta[deg]": 0.0, "ECP_dB": 0.0, "ECP_Phase_deg": 0.0}]
    grid = {"m_flat": [1], "n_flat": [1], "dx": 0.005, "dy": 0.005, "center_comp": 0.0}
    engine = ReferencePredictionEngine(FakeCnModel(), pattern, grid)
    output = engine.predict(ArrayInput(1, (ArrayUnit(1, 1, 1, 0.0, 0.0),)))
    assert output["implementation"] == "xgboost_reference"
    assert output["units"]["1"][0]["ECP_dB"] == pytest.approx(0.0)
    assert output["total_array"]["records"][0]["ECP_dB"] == pytest.approx(0.0)


@pytest.mark.unit
def test_reference_engine_supports_full_virtual_array_shape():
    """验证完整 25 虚拟阵元输出形状，不依赖 xgboost/HFSS。"""

    pattern = [
        {"Phi[deg]": 0.0, "Theta[deg]": 0.0, "ECP_dB": 0.0, "ECP_Phase_deg": 0.0},
        {"Phi[deg]": 2.0, "Theta[deg]": 0.0, "ECP_dB": 0.0, "ECP_Phase_deg": 0.0},
    ]
    engine = ReferencePredictionEngine(FullFakeCnModel(), pattern)
    output = engine.predict(ArrayInput(1, (ArrayUnit(1, 1, 1, 0.0, 0.0),)))
    assert len(output["units"]["1"]) == 2
    assert len(output["total_array"]["records"]) == 2

"""文件基本信息：tests/unit/test_model_adapter.py

目的：验证 XGBoost 模型适配器的输入矩阵、状态和依赖错误。
输入：小型 9 列特征和 2 列标签。
输出：pytest 模型适配单元测试结果。
维护：模型参数或列语义变化同步项目总览、黄金基线和本测试。
"""

import pytest

from backend.errors import AppError
from backend.model_adapter import XGBoostCnModel, validate_model_matrices
from backend.application import Application
from backend.config import Settings


@pytest.mark.unit
def test_model_matrix_requires_nine_inputs_and_two_targets():
    """验证模型输入/输出列宽。"""

    validate_model_matrices([[0.0] * 9], [[0.0, 0.0]])
    with pytest.raises(ValueError, match="9 列"):
        validate_model_matrices([[0.0] * 8])
    with pytest.raises(ValueError, match="2 列"):
        validate_model_matrices([[0.0] * 9], [[0.0]])


@pytest.mark.unit
def test_untrained_model_has_stable_error():
    """验证未训练模型不能预测。"""

    with pytest.raises(AppError) as exc:
        XGBoostCnModel().predict([[0.0] * 9])
    assert exc.value.code == "MODEL_NOT_READY"


@pytest.mark.unit
def test_reference_predictor_requires_explicit_artifacts(tmp_path):
    """验证 reference 模式不会在缺少模型/平均 ECP 时回退到 stub。"""

    with pytest.raises(AppError) as exc:
        Application(Settings("127.0.0.1", 0, tmp_path / "state.sqlite3", tmp_path / "data", "stub", 4, "reference", None, None))
    assert exc.value.code == "MODEL_NOT_READY"

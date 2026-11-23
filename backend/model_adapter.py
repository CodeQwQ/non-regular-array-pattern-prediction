"""文件基本信息：backend/model_adapter.py

目的：隔离 XGBoost cn 模型依赖、训练参数、模型产物和输入矩阵校验。
输入：9 列输入特征、2 列 cn 实/虚部标签和模型路径。
输出：XGBoost 模型、预测矩阵或明确的依赖/形状错误。
维护：模型参数、随机种子和输入列顺序变化必须同步项目总览、黄金基线和测试。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

from .errors import AppError


MODEL_INPUT_WIDTH = 9
MODEL_TARGET_WIDTH = 2


def validate_model_matrices(features: Sequence[Sequence[float]], targets: Sequence[Sequence[float]] | None = None) -> None:
    """校验 XGBoost 输入/标签的列数和行数。

    参数：features 为 9 列输入；targets 可选，为 2 列 cn 实虚部标签。
    返回：无；不合格时抛出 ValueError。
    """

    if not features or any(len(row) != MODEL_INPUT_WIDTH for row in features):
        raise ValueError("模型输入必须是非空的 9 列矩阵")
    if targets is not None:
        if len(features) != len(targets) or any(len(row) != MODEL_TARGET_WIDTH for row in targets):
            raise ValueError("模型标签必须与输入行数一致且为 2 列")


@dataclass(frozen=True)
class XGBoostParams:
    """实验脚本规定的 XGBoost 参数。"""

    n_estimators: int = 500
    learning_rate: float = 0.1
    max_depth: int = 8
    random_state: int = 42


class XGBoostCnModel:
    """可选依赖的 XGBoost cn 模型适配器。"""

    def __init__(self, params: XGBoostParams | None = None) -> None:
        self.params = params or XGBoostParams()
        self._model: Any = None

    @staticmethod
    def _load_xgb() -> Any:
        """加载 xgboost；返回模块，缺少依赖时抛出可追踪 AppError。"""

        try:
            import xgboost  # type: ignore
        except ImportError as exc:
            raise AppError("INTERNAL_ERROR", "当前环境未安装 xgboost，无法执行真实模型训练", 500) from exc
        return xgboost

    def fit(self, features: Sequence[Sequence[float]], targets: Sequence[Sequence[float]]) -> None:
        """使用实验参数训练 cn 模型。

        参数：features 为 9 列矩阵；targets 为 2 列 cn 实/虚部矩阵。
        返回：无；模型状态写入实例，依赖或形状错误时抛出异常。
        """

        validate_model_matrices(features, targets)
        xgb = self._load_xgb()
        model = xgb.XGBRegressor(
            n_estimators=self.params.n_estimators,
            learning_rate=self.params.learning_rate,
            max_depth=self.params.max_depth,
            random_state=self.params.random_state,
        )
        try:
            model.fit(features, targets)
        except Exception as exc:
            raise AppError("TASK_FAILED", f"XGBoost cn 模型训练失败：{exc}", 500) from exc
        self._model = model

    def load(self, path: str | Path) -> None:
        """加载已有 XGBoost 模型产物。

        参数：path 为模型文件路径。
        返回：无；文件或依赖无效时抛出 AppError。
        """

        model_path = Path(path)
        if not model_path.is_file():
            raise AppError("MODEL_NOT_READY", f"模型文件不存在：{model_path}", 409)
        xgb = self._load_xgb()
        model = xgb.XGBRegressor(
            n_estimators=self.params.n_estimators,
            learning_rate=self.params.learning_rate,
            max_depth=self.params.max_depth,
            random_state=self.params.random_state,
        )
        try:
            model.load_model(model_path)
        except Exception as exc:
            raise AppError("MODEL_NOT_READY", f"模型文件加载失败：{exc}", 409) from exc
        self._model = model

    def predict(self, features: Sequence[Sequence[float]]) -> list[list[float]]:
        """预测 cn 实部/虚部。

        参数：features 为 9 列输入矩阵。
        返回：每行 2 列预测值；未训练时抛出 MODEL_NOT_READY。
        """

        validate_model_matrices(features)
        if self._model is None:
            raise AppError("MODEL_NOT_READY", "XGBoost 模型尚未训练", 409)
        try:
            prediction = self._model.predict(features)
        except Exception as exc:
            raise AppError("TASK_FAILED", f"XGBoost cn 预测失败：{exc}", 500) from exc
        rows = prediction.tolist() if hasattr(prediction, "tolist") else list(prediction)
        if any(len(row) != MODEL_TARGET_WIDTH for row in rows):
            raise AppError("TASK_FAILED", "XGBoost 输出必须是 2 列 cn 实/虚部", 500)
        return [[float(value) for value in row] for row in rows]

    def save(self, path: str | Path) -> None:
        """保存模型产物；参数为目标路径，未训练或依赖不支持时抛出错误。"""

        if self._model is None:
            raise AppError("MODEL_NOT_READY", "XGBoost 模型尚未训练", 409)
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        self._model.save_model(target)


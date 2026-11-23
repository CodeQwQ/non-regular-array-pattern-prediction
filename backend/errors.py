"""文件基本信息：backend/errors.py

目的：定义统一业务异常和 HTTP 错误响应结构。
输入：错误码、消息、状态码和字段详情。
输出：AppError 或 ErrorResponse 字典。
维护：新增错误码时同步 api.md、openapi.yaml、测试和目录索引。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class AppError(Exception):
    """可安全返回给 API 调用方的业务错误。"""

    code: str
    message: str
    status: int = 400
    details: list[dict[str, Any]] = field(default_factory=list)

    def __post_init__(self) -> None:
        super().__init__(self.message)

    def to_dict(self) -> dict[str, Any]:
        """转换为 API 错误响应。

        参数：无。
        返回：包含 error.code、message 和 details 的字典。
        """

        error: dict[str, Any] = {"code": self.code, "message": self.message}
        if self.details:
            error["details"] = self.details
        return {"error": error}


def error_response(error: AppError) -> tuple[dict[str, Any], int]:
    """返回错误体和 HTTP 状态码。

    参数：error 为 AppError。
    返回：`(响应字典, 状态码)`。
    """

    return error.to_dict(), error.status

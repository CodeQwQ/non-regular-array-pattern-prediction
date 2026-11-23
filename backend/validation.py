"""文件基本信息：backend/validation.py

目的：执行阵列输入的规范化、JSON 优先选择和服务端最终业务校验。
输入：JSON 字典或网页表单字典。
输出：ArrayInput；非法输入抛出 AppError。
维护：规则变化必须同步 requirements.md、api.md、openapi.yaml 和 AC 测试。
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any

from .errors import AppError
from .models import ArrayInput, ArrayUnit


def choose_authoritative_input(json_input: Mapping[str, Any] | None, web_input: Mapping[str, Any] | None) -> Mapping[str, Any]:
    """选择权威输入；JSON 存在时始终优先。

    参数：json_input 为文件解析结果；web_input 为网页表单结果。
    返回：被选中的输入映射；两者都为空时抛出 INPUT_INVALID。
    """

    if json_input is not None:
        return json_input
    if web_input is not None:
        return web_input
    raise AppError("INPUT_INVALID", "缺少阵列输入", 400)


def normalise_array_input(payload: Mapping[str, Any]) -> ArrayInput:
    """执行后端权威阵列输入校验和规范化。

    参数：payload 必须包含 unit_count 和 units。
    返回：字段类型、顺序、编号和位置均已校验的 ArrayInput。
    """

    if not isinstance(payload, Mapping):
        raise AppError("INPUT_INVALID", "阵列输入必须是 JSON 对象", 400)
    count = payload.get("unit_count")
    units = payload.get("units")
    if isinstance(count, bool) or not isinstance(count, int) or count < 1:
        raise AppError("INPUT_INVALID", "unit_count 必须是大于 0 的整数", 400, [{"field": "unit_count", "reason": "invalid"}])
    if not isinstance(units, list) or len(units) != count:
        raise AppError("INPUT_INVALID", "unit_count 必须等于 units 数组长度", 400, [{"field": "units", "reason": "length_mismatch"}])

    normalised: list[ArrayUnit] = []
    positions: set[tuple[float, float]] = set()
    for index, raw in enumerate(units, start=1):
        if not isinstance(raw, Mapping):
            raise AppError("INPUT_INVALID", f"第 {index} 个单元必须是对象", 400)
        expected_id = index
        if raw.get("unit_id") != expected_id:
            raise AppError("INPUT_INVALID", "unit_id 必须从 1 到 n 连续", 400, [{"field": "unit_id", "reason": "not_contiguous"}])
        i = raw.get("i")
        j = raw.get("j")
        if isinstance(i, bool) or not isinstance(i, int) or i < 1 or isinstance(j, bool) or not isinstance(j, int) or j < 1:
            raise AppError("INPUT_INVALID", "i 和 j 必须是从 1 开始的整数", 400, [{"field": "i/j", "reason": "invalid"}])
        try:
            x = float(raw["x"])
            y = float(raw["y"])
        except (KeyError, TypeError, ValueError):
            raise AppError("INPUT_INVALID", f"第 {index} 个单元的 x/y 必须是数字", 400) from None
        if not math.isfinite(x) or not math.isfinite(y):
            raise AppError("INPUT_INVALID", f"第 {index} 个单元的 x/y 必须是有限数字", 400)
        position = (x, y)
        if position in positions:
            raise AppError("DUPLICATE_POSITION", "阵列中存在重复位置", 400, [{"field": "units", "reason": "duplicate_position"}])
        positions.add(position)
        normalised.append(ArrayUnit(expected_id, i, j, x, y))
    return ArrayInput(count, tuple(normalised))

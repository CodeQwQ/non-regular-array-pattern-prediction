"""文件基本信息：tests/unit/test_validation.py

目的：验证后端阵列输入规范化、JSON 优先和重复位置规则。
输入：固定合法/非法 ArrayInput 字典。
输出：pytest 断言结果。
维护：规则变化同步 requirements.md、验证规范和 tests/unit/目录索引.md。
"""

import pytest

from backend.errors import AppError
from backend.validation import choose_authoritative_input, normalise_array_input


def valid_payload():
    """生成最小合法输入；无参数，返回一个单元阵列字典。"""

    return {"unit_count": 1, "units": [{"unit_id": 1, "i": 1, "j": 1, "x": 0, "y": 0}]}


@pytest.mark.unit
def test_normalise_array_input_preserves_contract():
    """验证 unit_count、编号、坐标和字段序列化。"""

    value = normalise_array_input(valid_payload())
    assert value.unit_count == 1
    assert value.to_dict()["units"][0] == {"unit_id": 1, "i": 1, "j": 1, "x": 0.0, "y": 0.0}


@pytest.mark.unit
def test_json_input_has_priority():
    """验证 JSON 存在时网页输入不会覆盖它。"""

    json_input = valid_payload()
    web_input = {"unit_count": 1, "units": [{"unit_id": 1, "i": 1, "j": 1, "x": 9, "y": 9}]}
    assert choose_authoritative_input(json_input, web_input) is json_input


@pytest.mark.unit
@pytest.mark.parametrize("mutator,code", [
    (lambda p: p.update(unit_count=2), "INPUT_INVALID"),
    (lambda p: p["units"][0].update(unit_id=2), "INPUT_INVALID"),
    (lambda p: p["units"][0].update(x=float("nan")), "INPUT_INVALID"),
])
def test_invalid_input_is_rejected(mutator, code):
    """验证数量、编号和有限数校验返回稳定错误码。"""

    payload = valid_payload()
    mutator(payload)
    with pytest.raises(AppError) as exc:
        normalise_array_input(payload)
    assert exc.value.code == code


@pytest.mark.unit
def test_duplicate_positions_are_rejected():
    """验证重复坐标返回 DUPLICATE_POSITION。"""

    payload = {"unit_count": 2, "units": [
        {"unit_id": 1, "i": 1, "j": 1, "x": 0, "y": 0},
        {"unit_id": 2, "i": 1, "j": 2, "x": 0, "y": 0},
    ]}
    with pytest.raises(AppError) as exc:
        normalise_array_input(payload)
    assert exc.value.code == "DUPLICATE_POSITION"

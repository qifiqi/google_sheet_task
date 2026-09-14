"""数值缩写展示工具测试。"""

import pytest

from app.utils.number_format import abbreviate_number


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (488981004288, "4889.81亿"),
        (48898100, "4889.81万"),
        (85000, "8.50万"),
        (9999, "9,999"),
        (0, "0"),
        (-150000000, "-1.50亿"),
    ],
)
def test_abbreviate_number_units(value, expected):
    assert abbreviate_number(value) == expected


@pytest.mark.parametrize("value", [None, float("nan"), float("inf"), "abc"])
def test_abbreviate_number_invalid_returns_none(value):
    assert abbreviate_number(value) is None

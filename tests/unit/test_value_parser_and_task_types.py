"""任务类型归一化与通用数值解析工具测试。"""

from datetime import date

import pandas as pd
import pytest

from app.utils.task_types import KNOWN_TASK_TYPES, normalize_task_type
from app.utils.value_parser import (
    _convert_pandas_to_native,
    parse_date,
    parse_float,
    parse_int,
    parse_percent_like,
    parse_ratio,
)


@pytest.mark.parametrize("raw,expected", [
    ("google_sheet", "google_sheet"),
    ("google_sheet_c3", "google_sheet"),
    ("google_sheet_C31", "google_sheet"),
    ("google_sheet_c4", "google_sheet_c4"),
    ("google_sheet_c5", "google_sheet_c5"),
    ("google_sheet_c7", "google_sheet_c7"),
    ("backtest_training", "backtest_training"),
    ("backtest", "backtest_training"),
    ("backtest_multi_product", "backtest_multi_product"),
    ("backtest_multi", "backtest_multi_product"),
    ("multi_product_backtest", "backtest_multi_product"),
    ("model_summary_rebuild", "model_summary_rebuild"),
])
def test_normalize_task_type_maps_known_aliases(raw, expected):
    assert normalize_task_type(raw) == expected


def test_normalize_task_type_keeps_unknown_and_is_case_insensitive():
    assert normalize_task_type("custom_type") == "custom_type"
    assert normalize_task_type(None) == ""
    assert normalize_task_type("  GOOGLE_SHEET  ") == "google_sheet"
    assert set(KNOWN_TASK_TYPES) >= {"google_sheet", "backtest_training"}


def test_parse_int_handles_defaults():
    assert parse_int("1200") == 1200
    assert parse_int(7) == 7
    assert parse_int("1,200") is None, "千分位不属于整数解析职责"
    assert parse_int("abc", default=5) == 5
    assert parse_int(None, default=-1) == -1
    assert parse_int(True) is None


def test_parse_float_strips_thousands_and_rejects_non_finite():
    assert parse_float("1,234.5") == 1234.5
    assert parse_float("NaN", default=0.0) == 0.0
    assert parse_float("inf", default=1.5) == 1.5
    assert parse_float("", default=2.0) == 2.0


def test_parse_percent_like_and_ratio():
    assert parse_percent_like("5%") == 0.05
    assert parse_percent_like("0.07") == 0.07
    assert parse_percent_like("abc", default=0.0) == 0.0
    assert parse_ratio("50%") == 0.5
    assert parse_ratio("50") == 50.0
    assert parse_ratio("abc", default=1.0) == 1.0


def test_parse_date_supports_iso_shapes():
    assert parse_date("2026-08-29") == date(2026, 8, 29)
    assert parse_date("2026-08-29T10:00:00") == date(2026, 8, 29)
    assert parse_date("2026/08/29") is None
    assert parse_date("not-a-date") is None
    assert parse_date("", default=date(1970, 1, 1)) == date(1970, 1, 1)


def test_convert_pandas_to_native_converts_timestamp_and_nat_recursively():
    """Pandas 日期值可安全转换为 JSON 可序列化的原生值。"""
    result = _convert_pandas_to_native({
        "timestamp": pd.Timestamp("2026-09-01 15:27:11"),
        "missing": pd.NaT,
        "nested": [pd.NaT],
    })

    assert result == {
        "timestamp": "2026-09-01T15:27:11",
        "missing": None,
        "nested": [None],
    }


def test_convert_pandas_to_native_converts_series_to_a_json_safe_list():
    result = _convert_pandas_to_native(pd.Series([pd.Timestamp("2026-09-01"), pd.NA, 0.01, pd.Series([1]).iloc[0]]))

    assert result == ["2026-09-01T00:00:00", None, 0.01, 1]

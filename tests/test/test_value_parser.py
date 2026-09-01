import math
from datetime import date, datetime

from app.utils.value_parser import parse_date, parse_float, parse_int, parse_percent_like, parse_ratio


def test_parse_float_returns_only_finite_numbers():
    assert parse_float("1,234.5") == 1234.5
    assert parse_float(math.inf, default=0.0) == 0.0
    assert parse_float(True) is None
    assert parse_int("42") == 42
    assert parse_int(True) is None


def test_parse_percent_and_ratio_use_decimal_for_percent_text():
    assert parse_percent_like("5%") == 0.05
    assert parse_percent_like("1.5") == 1.5
    assert parse_ratio("50%") == 0.5


def test_parse_date_accepts_iso_values():
    expected = date(2026, 8, 21)
    assert parse_date("2026-08-21T12:00:00") == expected
    assert parse_date(datetime(2026, 8, 21, 12, 0)) == expected
    assert parse_date("invalid") is None

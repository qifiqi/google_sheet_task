import math

import pytest

from app.services.xpl_service import XPLAnalyzer


def test_analyze_uses_second_column_for_two_column_input():
    data = "\n".join(
        [
            "2025/10/5\t0.00%",
            "2025/10/6\t-0.55%",
            "2025/11/3\t14.88%",
            "2025/12/31\t18.76%",
            "2026/1/2\t21.72%",
            "2026/2/2\t30.23%",
            "2026/3/31\t50.29%",
        ]
    )

    result = XPLAnalyzer().analyze(data=data, time_format="auto")

    assert result["status"] == "success"
    assert result["results"]["analysis_mode"] == "single"
    assert result["results"]["sharpe_ratios"]["all"]["sharpe_ratio"] == pytest.approx(3.6535077666)


def test_analyze_auto_calculates_index_and_model_for_three_columns():
    data = "\n".join(
        [
            "2025-10-31 1.00% 2.00%",
            "2025-11-30 2.00% 3.00%",
            "2025-12-31 3.00% 4.00%",
            "2026-01-31 4.00% 5.00%",
            "2026-02-28 5.00% 6.00%",
            "2026-03-31 6.00% 7.00%",
        ]
    )

    result = XPLAnalyzer().analyze(data=data, time_format="auto")

    assert result["status"] == "success"
    metrics = result["results"]
    assert metrics["analysis_mode"] == "dual"
    assert metrics["index_sharpe_ratios"]["all"]["month_count"] == 6
    assert metrics["start_sharpe_ratios"]["all"]["month_count"] == 6
    assert metrics["index_returns_rate"][0]["net_value"] < metrics["start_returns_rate"][0]["net_value"]


def test_analyze_replaces_non_finite_numbers_with_none():
    data = "\n".join(
        [
            "2025-10-31 1.00% 2.00%",
            "2025-11-30 2.00% 3.00%",
            "2025-12-31 3.00% 4.00%",
            "2026-01-31 4.00% 5.00%",
            "2026-02-28 5.00% 6.00%",
            "2026-03-31 6.00% 7.00%",
        ]
    )

    result = XPLAnalyzer().analyze(data=data, time_format="auto")

    assert result["status"] == "success"
    assert not _contains_non_finite_number(result)


def test_sanitize_for_json_replaces_numpy_and_python_non_finite_numbers():
    sanitized = XPLAnalyzer._sanitize_for_json(
        {
            "infinity": float("inf"),
            "nan": float("nan"),
            "nested": [1.0, float("-inf")],
        }
    )

    assert sanitized == {"infinity": None, "nan": None, "nested": [1.0, None]}


def test_parse_input_data_uses_third_column_as_model_return_for_three_columns():
    data = "\n".join(
        [
            "2026-01-01 0.10% 1.20%",
            "2026-01-02 0.20% 1.50%",
        ]
    )

    parsed = XPLAnalyzer()._parse_input_data(data)

    assert [row["daily_return"] for row in parsed] == [0.012, 0.015]
    assert [row["index_return"] for row in parsed] == [0.001, 0.002]
    assert [row["start_return"] for row in parsed] == [0.012, 0.015]


def _contains_non_finite_number(value):
    if isinstance(value, dict):
        return any(_contains_non_finite_number(item) for item in value.values())
    if isinstance(value, list):
        return any(_contains_non_finite_number(item) for item in value)
    if isinstance(value, float):
        return not math.isfinite(value)
    return False

import pytest

from scripts.debug_scaled_return_drawdown import (
    build_metric_rows,
    compute_drawdown_rows,
    normalize_ratio,
    pick_year_drawdown,
)


def test_scaled_return_drawdown_gets_smaller_with_actual_xpl_algorithm():
    rows = build_metric_rows(
        dates=["2024-01-01", "2024-01-02", "2024-01-03"],
        returns=[0.10, -0.30, 0.05],
        ratio=1,
        field="start_return",
    )
    scaled_rows = build_metric_rows(
        dates=["2024-01-01", "2024-01-02", "2024-01-03"],
        returns=[0.10, -0.30, 0.05],
        ratio=0.5,
        field="start_return",
    )

    raw_drawdown = pick_year_drawdown(rows, "start_return", 2024)
    scaled_drawdown = pick_year_drawdown(scaled_rows, "start_return", 2024)

    assert raw_drawdown == pytest.approx(0.3636363636)
    assert scaled_drawdown == pytest.approx(0.1904761905)
    assert scaled_drawdown < raw_drawdown


def test_compute_drawdown_rows_shows_net_value_moves_closer_to_one():
    rows = compute_drawdown_rows(
        dates=["2024-01-01", "2024-01-02", "2024-01-03"],
        returns=[0.10, -0.30, 0.05],
        ratio=0.5,
    )

    assert [row["scaled_return"] for row in rows] == [0.05, -0.15, 0.025]
    assert [row["raw_net_value"] for row in rows] == [1.1, 0.7, 1.05]
    assert [row["scaled_net_value"] for row in rows] == [1.05, 0.85, 1.025]
    assert rows[1]["raw_drawdown"] == pytest.approx(0.3636363636)
    assert rows[1]["scaled_drawdown"] == pytest.approx(0.1904761905)


def test_normalize_ratio_accepts_percent_and_decimal_forms():
    assert normalize_ratio("50") == 0.5
    assert normalize_ratio("50%") == 0.5
    assert normalize_ratio("0.5") == 0.5

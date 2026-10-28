from app.services.performance_analysis.historical_metrics import (
    extract_core_metrics,
    resolve_preview_metrics,
)


def test_extract_core_metrics_reads_canonical_payload():
    metrics = extract_core_metrics({
        "metrics_payload": {
            "metrics": {
                "index_sortino_ratio": [{"year": "all", "sortino_ratio": 1.2}],
                "start_sortino_ratio": [{"year": "all", "sortino_ratio": 2.3}],
                "excess_sharpe": 3.4,
                "excess_sortino": 5.6,
            }
        }
    })

    assert metrics["index_sortino_ratio"] == [{"year": "all", "sortino_ratio": 1.2}]
    assert metrics["start_sortino_ratio"] == [{"year": "all", "sortino_ratio": 2.3}]
    assert metrics["excess_sharpe"] == 3.4
    assert metrics["excess_sortino"] == 5.6


def test_resolve_preview_metrics_preserves_history_without_returns():
    core = {"metrics_payload": {"metrics": {"excess_sharpe": 3.4}}}

    metrics = resolve_preview_metrics(core)

    assert metrics == {"excess_sharpe": 3.4}


def test_resolve_preview_metrics_recalculates_missing_preview_metrics(monkeypatch):
    expected = {
        "excess_sharpe": 3.4,
        "excess_sortino": 5.6,
        "index_sortino_ratio": [{"year": "all", "sortino_ratio": 1.2}],
        "start_sortino_ratio": [{"year": "all", "sortino_ratio": 2.3}],
        "year_index_yearly_max_repair_days": {2025: 20},
        "year_start_yearly_max_repair_days": {2025: 15},
    }

    class Result:
        metrics = expected

    monkeypatch.setattr(
        "app.services.performance_analysis.facade.calculate_v1_metrics",
        lambda rows: Result(),
    )

    metrics = resolve_preview_metrics(
        {},
        return_rows=[
            {"date": "2025-01-01", "index_return": 0.0, "start_return": 0.0},
            {"date": "2025-01-02", "index_return": 0.01, "start_return": 0.02},
        ],
    )

    assert metrics == expected

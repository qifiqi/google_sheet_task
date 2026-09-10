import asyncio
from types import SimpleNamespace

from app.services.performance_analysis import service


def test_weight_combination_yields_requested_metrics(monkeypatch):
    rows = [
        {"date": "2026-01-01", "index_return": 0.01, "start_return": 0.02},
        {"date": "2026-01-02", "index_return": 0.02, "start_return": 0.03},
    ]
    results = [
        SimpleNamespace(
            id=1, return_series_id=None, result={"return_date": rows},
            parameters={"stock_code": "AAA", "stock_name": "Alpha"},
        ),
        SimpleNamespace(
            id=2, return_series_id=None, result={"return_date": rows},
            parameters={"stock_code": "BBB", "stock_name": "Beta"},
        ),
    ]
    monkeypatch.setattr(service.task_repository, "get_required", lambda task_id: {"id": task_id})
    monkeypatch.setattr(service.task_result_repository, "list_preview_entities", lambda *args, **kwargs: results)
    monkeypatch.setattr(
        service,
        "calculate_v1_metrics",
        lambda returns: SimpleNamespace(metrics={
            "index_annualized_rates": [{"year": "all", "annualized_return": 0.1}],
            "start_annualized_rates": [{"year": "all", "annualized_return": 0.2}],
            "index_maximum_drawdown": {"year_maximum_drawdown": [{"year": 2026, "drawdown": -0.1}]},
            "start_maximum_drawdown": {"total_maximum_drawdown": {"drawdown": -0.2}},
        }),
    )

    async def collect():
        return [item async for item in service.performance_analysis_service.weight_combination({"task_id": "task-1", "step": 50})]

    combinations = asyncio.run(collect())

    assert len(combinations) == 3
    payload = combinations[0]["_weight_combination_v1"]
    assert all(sum(stock["ratio"] for stock in item["_weight_combination_v1"]["stocks"]) == 100 for item in combinations)
    assert payload["annualized_rates"]["index"] == [{"year": "all", "annualized_return": 0.1}]
    assert payload["annualized_rates"]["start"] == [{"year": "all", "annualized_return": 0.2}]
    assert payload["year_max_drawdown"]["index"] == [{"year": 2026, "drawdown": -0.1}]
    assert payload["stocks"][0] == {"result_id": 1, "stock_code": "AAA", "stock_name": "Alpha", "ratio": 0}

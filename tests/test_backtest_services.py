import json
from datetime import datetime, timedelta

import pytest

from app.extensions import db
from app.models import BacktestProductResultCache, TaskResult, TaskResultReturn
from app.services.backtest_multi_product_service import (
    BacktestMultiProductService,
    normalize_multi_product_config,
)
from app.services.backtest_training_service import BacktestTrainingService


def _kline_rows(start_date, end_date):
    current = datetime.strptime(start_date, "%Y-%m-%d").date()
    end = datetime.strptime(end_date, "%Y-%m-%d").date()
    rows = []
    while current <= end:
        rows.append({
            "stock_date": current.strftime("%Y-%m-%d"),
            "stock_kp": 9,
            "stock_sp": 10,
        })
        current += timedelta(days=1)
    return rows


def _product(index, *, parameters=None, is_fixed=False):
    return {
        "product_name": f"产品{index}",
        "stock_code": f"TEST{index}",
        "market_type": "cn",
        "ratio": "50",
        "is_fixed": is_fixed,
        "sheet": {"spreadsheet_id": f"sheet-{index}", "sheet_name": "data", "title": "C3"},
        "parameters": parameters or [["p1", "p2"]],
    }


def test_backtest_training_save_result_persists_return_series(app_factory):
    app = app_factory
    with app.app_context():
        service = BacktestTrainingService({}, "task-id", app=app)

        service._save_task_result(
            0,
            {"stock_code": "600000"},
            {"metric": 1},
            True,
            return_date=[
                {"date": "2024-01-01", "index_return": 0.1, "start_return": 0.2},
                {"date": "2024-01-02", "index_return": 0.3, "start_return": 0.4},
            ],
        )

        result = TaskResult.query.filter_by(task_id="task-id").one()
        series = db.session.get(TaskResultReturn, result.return_series_id)
        payload = json.loads(series.returns_json)

        assert result.success is True
        assert payload["dates"] == ["2024-01-01", "2024-01-02"]
        assert payload["index_returns"] == [0.1, 0.3]


def test_backtest_training_full_range_uses_configured_end_date(monkeypatch):
    service = BacktestTrainingService({}, "task-id")
    monkeypatch.setattr(service, "_resolve_cn_stock_quote", lambda stock_code: (stock_code, "1"))
    monkeypatch.setattr(
        service.dfcf_api,
        "get_stock_kline_data",
        lambda *_args, **_kwargs: _kline_rows("2022-01-01", "2025-12-31"),
    )

    combinations, _column_length, kline_map = service._get_all_parameters(
        [2022, 2023, 2024],
        [],
        [["param-a"]],
        "600000",
        include_full_year_range=True,
        end_date="2024-06-30",
    )

    assert combinations == [{
        "parameter": ["param-a"],
        "stock_code": "600000",
        "year": "2022-2024",
        "Kline_key": "2022-2024",
    }]
    assert kline_map["2022-2024"][-1]["stock_date"] == "2024-06-30"


def test_backtest_training_short_listing_history_recent_years_is_allowed(monkeypatch):
    service = BacktestTrainingService({}, "task-id")
    monkeypatch.setattr(service, "_resolve_cn_stock_quote", lambda stock_code: (stock_code, "1"))
    monkeypatch.setattr(
        service.dfcf_api,
        "get_stock_kline_data",
        lambda *_args, **_kwargs: _kline_rows("2023-06-01", "2025-12-31"),
    )

    combinations, _column_length, kline_map = service._get_all_parameters(
        [],
        [5],
        [["param-a"]],
        "600000",
        end_date="2025-06-30",
    )

    assert combinations[0]["Kline_key"] == "2025-2020"
    assert kline_map["2025-2020"][0]["stock_date"] == "2023-06-01"


def test_multi_product_normalize_rejects_parameter_count_mismatch():
    with pytest.raises(ValueError, match="参数行数必须一致"):
        normalize_multi_product_config({
            "start_date": "2024-01-01",
            "end_date": "2024-12-31",
            "products": [
                _product(1, parameters=[["a"], ["b"]]),
                _product(2, parameters=[["a"]]),
            ],
        })


def test_multi_product_fixed_cache_exists_and_gets_cached_payload(app_factory):
    app = app_factory
    with app.app_context():
        config = {
            "fixed_product_batch_id": "batch-1",
            "start_date": "2024-01-01",
            "end_date": "2024-12-31",
        }
        product = _product(1, parameters=[["p1", "p2"]], is_fixed=True)
        cache_key = BacktestMultiProductService._build_fixed_product_cache_key(
            config,
            product,
            ["p1", "p2"],
        )
        db.session.add(BacktestProductResultCache(
            batch_id="batch-1",
            cache_key=cache_key,
            result_json=json.dumps({"metric": 1}),
            returns_json=json.dumps({"dates": ["2024-01-01"]}),
            source_task_id="source",
            source_step_index=0,
        ))
        db.session.commit()

        service = BacktestMultiProductService({}, "task-id", app=app)

        assert BacktestMultiProductService.fixed_product_cache_exists(config, product) is True
        cached = service._get_fixed_product_cache(config, product, ["p1", "p2"])
        assert json.loads(cached["result_json"]) == {"metric": 1}
        assert cached["source_task_id"] == "source"

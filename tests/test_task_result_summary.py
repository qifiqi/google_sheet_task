import json
from types import SimpleNamespace

from app.services.task_result_summary import build_task_result_list_item


def test_build_task_result_list_item_keeps_only_compact_summary():
    result = SimpleNamespace(
        id=12,
        task_id="task-12",
        step_index=3,
        success=True,
        timestamp=None,
        parameters=json.dumps({
            "stock_code": "SOXX",
            "stock_name": "iShares Semiconductor ETF",
            "year": "2026-2021",
            "parameter": ["3.5", "5"],
            "kline": [
                {"stock_date": "2021-07-12", "stock_val": 149.11},
                {"stock_date": "2026-07-10", "stock_val": 578.28},
            ],
        }),
        result=json.dumps({
            "model-a": {"analysis_status": "completed", "D2": "465.21%"},
            "model-b": {"D2": "421.11%"},
        }),
    )

    payload = build_task_result_list_item(result, "SOXX C5", "backtest_training")

    assert payload["task_name"] == "SOXX C5"
    assert payload["summary"] == {
        "stock_code": "SOXX",
        "stock_name": "iShares Semiconductor ETF",
        "period": "2026-2021",
        "kline_date_range": "2021-07-12 至 2026-07-10",
        "parameter_values": ["3.5", "5"],
        "parameter_items": [
            {"label": "参数 1", "value": "3.5"},
            {"label": "参数 2", "value": "5"},
        ],
        "model_count": 2,
        "model_names": ["model-a", "model-b"],
        "analysis_status": "completed",
        "models": [
            {
                "key": "model-a",
                "code": "model-a",
                "name": "model-a",
                "analysis_status": "completed",
                "metrics": {
                    "return": "465.21%", "annualized": None, "max_drawdown": None,
                    "index_return": None, "index_annualized": None, "index_max_drawdown": None,
                    "index_sharpe": None, "model_sharpe": None,
                },
            },
            {
                "key": "model-b",
                "code": "model-b",
                "name": "model-b",
                "analysis_status": None,
                "metrics": {
                    "return": "421.11%", "annualized": None, "max_drawdown": None,
                    "index_return": None, "index_annualized": None, "index_max_drawdown": None,
                    "index_sharpe": None, "model_sharpe": None,
                },
            },
        ],
        "metrics": {
            "return": "465.21%",
            "annualized": None,
            "max_drawdown": None,
            "index_return": None,
            "index_annualized": None,
            "index_max_drawdown": None,
            "index_sharpe": None,
            "model_sharpe": None,
        },
    }
    assert '"kline":' not in json.dumps(payload)


def test_build_task_result_list_item_handles_invalid_json():
    result = SimpleNamespace(
        id=13,
        task_id="task-13",
        step_index=0,
        success=False,
        timestamp=None,
        parameters="not-json",
        result="not-json",
    )

    assert build_task_result_list_item(result, None, "google_sheet")["summary"] == {
        "stock_code": None,
        "stock_name": None,
        "period": None,
        "kline_date_range": None,
        "parameter_values": [],
        "parameter_items": [],
        "model_count": 0,
        "model_names": [],
        "analysis_status": None,
        "models": [],
        "metrics": {
            "return": None,
            "annualized": None,
            "max_drawdown": None,
            "index_return": None,
            "index_annualized": None,
            "index_max_drawdown": None,
            "index_sharpe": None,
            "model_sharpe": None,
        },
    }


def test_build_task_result_list_item_extracts_c_series_metrics():
    result = SimpleNamespace(
        id=14,
        task_id="task-14",
        step_index=1,
        success=True,
        timestamp=None,
        parameters="{}",
        result=json.dumps({
            "sheet-model": {
                "D2:D20": {
                    "D2": "42.10%",
                    "D3": "8.50%",
                    "D4": "-15.20%",
                    "D5": "31.00%",
                    "D6": "6.80%",
                    "D7": "-18.90%",
                },
                "flat_result": {
                    "index_sharpe_ratio": 0.61,
                    "start_sharpe_ratio": 0.82,
                },
            },
        }),
    )

    summary = build_task_result_list_item(result, "C5", "google_sheet_c5")["summary"]

    assert summary["metrics"] == {
        "return": "42.10%",
        "annualized": "8.50%",
        "max_drawdown": "-15.20%",
        "index_return": "31.00%",
        "index_annualized": "6.80%",
        "index_max_drawdown": "-18.90%",
        "index_sharpe": 0.61,
        "model_sharpe": 0.82,
    }
    assert summary["models"] == [{
        "key": "sheet-model",
        "code": "sheet-model",
        "name": "sheet-model",
        "analysis_status": None,
        "metrics": summary["metrics"],
    }]

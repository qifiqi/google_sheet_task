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
    }

import json
from types import SimpleNamespace

from app.services.task_result_summary import (
    build_task_result_detail_presentation,
    build_task_result_list_item,
)


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
    summary = payload["summary"]
    assert summary["stock_code"] == "SOXX"
    assert summary["stock_name"] == "iShares Semiconductor ETF"
    assert summary["period"] == "2026-2021"
    assert summary["kline_date_range"] == "2021-07-12 至 2026-07-10"
    assert summary["parameter_items"] == [
        {"label": "参数 1", "value": "3.5"},
        {"label": "参数 2", "value": "5"},
    ]
    assert summary["model_names"] == ["model-a", "model-b"]
    assert summary["models"][0]["metrics"]["return"] == "465.21%"
    assert summary["models"][1]["metrics"]["return"] == "421.11%"
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

    summary = build_task_result_list_item(result, None, "google_sheet")["summary"]
    assert summary["model_count"] == 1
    assert summary["models"][0]["name"] == "C3"
    assert all(value is None for value in summary["metrics"].values())


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

    assert {key: summary["metrics"][key] for key in (
        "return", "annualized", "max_drawdown", "index_return",
        "index_annualized", "index_max_drawdown", "index_sharpe", "model_sharpe",
    )} == {
        "return": "42.10%", "annualized": "8.50%", "max_drawdown": "-15.20%",
        "index_return": "31.00%", "index_annualized": "6.80%",
        "index_max_drawdown": "-18.90%", "index_sharpe": 0.61, "model_sharpe": 0.82,
    }
    assert summary["models"][0]["name"] == "sheet-model"


def test_build_task_result_list_item_normalizes_c3_array_parameters():
    result = SimpleNamespace(
        id=15,
        task_id="task-15",
        step_index=1,
        success=True,
        timestamp=None,
        parameters=json.dumps([3.1, 0.83, [{"stock_date": "2024-01-02"}, {"stock_date": "2026-07-07"}]]),
        result=json.dumps({
            "I15": "12.50%", "I16": "4.10%", "I17": "-8.20%", "I18": "9.30%",
            "I19": "3.20%", "I20": "-10.10%", "I21": "0.50%", "I22": "0.16%",
            "I23": "12.00%", "analysis_status": "completed",
            "flat_result": {"index_sharpe_ratio": 0.42, "start_sharpe_ratio": 0.68},
        }),
    )

    payload = build_task_result_list_item(
        result,
        "QQQ C3",
        "google_sheet",
        {"stock_code": "QQQ", "year_n": "3y"},
    )

    assert payload["summary"]["stock_code"] == "QQQ"
    assert payload["summary"]["kline_date_range"] == "2024-01-02 至 2026-07-07"
    assert payload["summary"]["parameter_items"] == [
        {"label": "参数 1", "value": "3.1"},
        {"label": "参数 2", "value": "0.83"},
    ]
    assert payload["summary"]["models"] == [{
        "key": "default", "code": "C3", "name": "C3", "analysis_status": "completed",
        "metrics": payload["summary"]["metrics"],
    }]
    assert payload["summary"]["metrics"]["return"] == "12.50%"
    assert payload["summary"]["metrics"]["model_sharpe"] == 0.68


def test_build_task_result_detail_presentation_uses_c7_cell_mapping():
    result = SimpleNamespace(
        result=json.dumps({
            "sheet__model": {
                "D8": "16.20%", "D9": "5.30%", "D10": "-11.40%", "D11": "13.10%",
                "D12": "4.20%", "D13": "-12.20%", "D14": "0.30%", "D15": "0.10%",
                "D16": "8.00%", "D17": "3.10%", "D18": "2.20%", "D19": "1.50%",
                "D20": "0.50%", "D21": 1.8, "D22": 0.8, "D23": "2.00%",
                "D24": 1.6, "D25": 0.7, "D26": "1.60%",
                "flat_result": {"index_sharpe_ratio": 0.5, "start_sharpe_ratio": 0.7},
            },
        }),
    )

    presentation = build_task_result_detail_presentation(result, "google_sheet_C7")
    core = presentation["models"][0]["sections"][0]["items"]
    assert presentation["kind"] == "c7"
    assert core[0] == {"label": "Return%", "value": "16.20%"}
    assert {item["label"]: item["value"] for item in core}["s xpl"] == "0.7000"

import csv
import io
import json
import time

import pytest

from app.extensions import db
from app.models import Permission, Task, TaskLog, TaskResult, TaskResultSummaryIndex
from app.services.model_summary_service import extract_summary_records, model_summary_service


class _User:
    def get_permissions(self):
        return {"task:view", "google_sheet:c3", "google_sheet:c4", "google_sheet:c5", "backtest:view"}


def _task(task_id="task-1", task_type="google_sheet", name="600519"):
    return Task(id=task_id, name=name, task_type=task_type, status="completed", config="{}")


def _result(task_id="task-1", result_id=1, parameters=None, result=None):
    item = TaskResult(
        id=result_id,
        task_id=task_id,
        step_index=0,
        parameters=json.dumps(parameters if parameters is not None else []),
        result=json.dumps(result if result is not None else {}),
        success=True,
    )
    return item


def test_extract_c3_uses_return_beats_as_best_metric():
    task = _task(name="C3-XME-BDL-3Y-1")
    result = _result(
        parameters=[1, 2, [{"stock_date": "2024-01-01"}, {"stock_date": "2024-12-31"}]],
        result={"I15": 0.12, "I16": 0.2, "I18": 0.05},
    )

    rows = extract_summary_records(task, result)

    assert len(rows) == 1
    assert rows[0].best_metric_name == "ReturnBeats"
    assert rows[0].best_metric_value == pytest.approx(0.07)
    assert rows[0].metrics["return_rate"] == 0.12
    assert rows[0].metrics["annualized_rate"] == 0.2
    assert rows[0].metrics["return_beats"] == pytest.approx(0.07)
    assert rows[0].stock_code == "XME"


def test_extract_c3_maps_i15_to_i23_metric_cells():
    task = _task(name="600519")
    result = _result(
        result={
            "I15": "1%",
            "I16": "2%",
            "I17": "-3%",
            "I18": "4%",
            "I19": "5%",
            "I20": "-6%",
            "I21": "7%",
            "I22": "8%",
            "I23": "9%",
        },
    )

    rows = extract_summary_records(task, result)

    assert rows[0].metrics == {
        "return_rate": 0.01,
        "annualized_rate": 0.02,
        "max_drawdown": -0.03,
        "index_return": 0.04,
        "index_annualized_rate": 0.05,
        "index_max_drawdown": -0.06,
        "fee_total": 0.07,
        "fee_annualized": 0.08,
        "turnover_rate": 0.09,
        "return_beats": -0.03,
    }


def test_extract_c3_includes_saved_return_analysis_metrics():
    task = _task(name="600519")
    result = _result(
        result={
            "I15": "1%",
            "I18": "0%",
            "annualized_return_diff": "4%",
            "monthly_excess_return_percentage_last_return": "55%",
            "excess_sharp": "0.88",
            "start_profit_annual": "70%",
            "index_profit_annual": "50%",
            "start_maximum_number_of_backtest_repair_days": "33",
            "excess_of_promissory_note": "0.77",
        },
    )

    rows = extract_summary_records(task, result)

    assert rows[0].metrics["annualized_return_diff"] == 0.04
    assert rows[0].metrics["monthly_excess_return_percentage"] == 0.55
    assert rows[0].metrics["excess_sharp"] == 0.88
    assert rows[0].metrics["start_profit_annual"] == 0.7
    assert rows[0].metrics["index_profit_annual"] == 0.5
    assert rows[0].metrics["start_maximum_number_of_backtest_repair_days"] == 33
    assert rows[0].metrics["excess_of_promissory_note"] == 0.77


def test_extract_c3_includes_nested_flat_result_metrics():
    task = _task(name="600519")
    result = _result(
        result={
            "I15": "1%",
            "I18": "0%",
            "analyze_result": {"monthly_excess_returns": []},
            "flat_result": {
                "annualized_return_diff": "4%",
                "monthly_excess_return_percentage_last_return": "55%",
                "excess_sharp": "0.88",
                "start_profit_annual": "70%",
                "index_profit_annual": "50%",
                "start_maximum_number_of_backtest_repair_days": "33",
                "excess_of_promissory_note": "0.77",
            },
        },
    )

    rows = extract_summary_records(task, result)

    assert rows[0].metrics["annualized_return_diff"] == 0.04
    assert rows[0].metrics["monthly_excess_return_percentage"] == 0.55
    assert rows[0].metrics["excess_sharp"] == 0.88
    assert rows[0].metrics["start_profit_annual"] == 0.7
    assert rows[0].metrics["index_profit_annual"] == 0.5
    assert rows[0].metrics["start_maximum_number_of_backtest_repair_days"] == 33
    assert rows[0].metrics["excess_of_promissory_note"] == 0.77


def test_extract_c5_uses_returnbeats_with_fallback():
    task = _task(task_type="google_sheet_C5", name="普通 C5 任务")
    result = _result(
        parameters={"stock_code": "AAPL", "A1": "1.8", "B1": "4", "year": "2025-2024"},
        result={
            "sheet__model": {
                "D2": "20%",
                "D5": "8%",
                "D11": "",
                "start_return_xpl": {"sharpe_ratio": 2.1},
            }
        },
    )

    rows = extract_summary_records(task, result)

    assert len(rows) == 1
    assert rows[0].stock_code == "AAPL"
    assert rows[0].best_metric_name == "ReturnBeats"
    assert round(rows[0].best_metric_value, 4) == 0.12
    assert rows[0].metrics["start_sharpe_ratio"] == 2.1


def test_extract_c5_maps_nested_xpl_sharpe_ratios_to_summary_metrics():
    task = _task(task_type="google_sheet_C5", name="C5-600776-东方通信")
    result = _result(
        parameters={"stock_code": "600776", "A1": "1.8", "B1": "4", "year": "2026-2023"},
        result={
            "sheet__C5.v20260105-回测-hlg-001": {
                "D2": "22.93%",
                "D5": "21.31%",
                "D11": "0.47%",
                "index_return_xpl": {
                    "sharpe_ratio": "0.4041930158167997",
                    "avg_monthly_return": "0.00693797342048926",
                },
                "start_return_xpl": {
                    "sharpe_ratio": "0.5363163004510634",
                    "avg_monthly_return": "0.006440432118344072",
                },
            }
        },
    )

    rows = extract_summary_records(task, result)

    assert len(rows) == 1
    assert rows[0].metrics["start_sharpe_ratio"] == pytest.approx(0.5363163004510634)
    assert rows[0].metrics["index_sharpe_ratio"] == pytest.approx(0.4041930158167997)


def test_extract_c4_reads_nested_flat_result_metrics():
    task = _task(task_type="google_sheet_C4", name="C4-600776-东方通信")
    result = _result(
        parameters={"stock_code": "600776", "year": "2026-2023"},
        result={
            "sheet__C4.v20260105-回测-hlg-001": {
                "D2": "22.93%",
                "D5": "21.31%",
                "D11": "0.47%",
                "analyze_result": {"monthly_excess_returns": []},
                "flat_result": {
                    "annualized_return_diff": "4%",
                    "start_sharpe_ratio": "0.5363163004510634",
                    "index_sharpe_ratio": "0.4041930158167997",
                    "excess_sharp": "0.88",
                },
            }
        },
    )

    rows = extract_summary_records(task, result)

    assert len(rows) == 1
    assert rows[0].model_name == "C4"
    assert rows[0].metrics["annualized_return_diff"] == pytest.approx(0.04)
    assert rows[0].metrics["start_sharpe_ratio"] == pytest.approx(0.5363163004510634)
    assert rows[0].metrics["index_sharpe_ratio"] == pytest.approx(0.4041930158167997)
    assert rows[0].metrics["excess_sharp"] == pytest.approx(0.88)


def test_extract_c5_keeps_flat_result_sharpe_without_xpl_payload():
    task = _task(task_type="google_sheet_C5", name="C5-600776-东方通信")
    result = _result(
        parameters={"stock_code": "600776", "A1": "1.8", "B1": "4", "year": "2026-2023"},
        result={
            "sheet__C5.v20260105-回测-hlg-001": {
                "D2": "22.93%",
                "D5": "21.31%",
                "D11": "0.47%",
                "flat_result": {
                    "start_sharpe_ratio": "0.5363163004510634",
                    "index_sharpe_ratio": "0.4041930158167997",
                },
            }
        },
    )

    rows = extract_summary_records(task, result)

    assert len(rows) == 1
    assert rows[0].metrics["start_sharpe_ratio"] == pytest.approx(0.5363163004510634)
    assert rows[0].metrics["index_sharpe_ratio"] == pytest.approx(0.4041930158167997)


def test_extract_c5_displays_versioned_model_key_as_c5():
    task = _task(task_type="google_sheet_C5", name="普通 C5 任务")
    result = _result(
        parameters={"stock_code": "AAPL"},
        result={"sheet__C5.v20260105-回测-hlg-003": {"D11": "12%"}},
    )

    rows = extract_summary_records(task, result)

    assert rows[0].model_name == "C5"


def test_extract_c4_displays_model_key_containing_c4_as_c4():
    task = _task(task_type="google_sheet_C4", name="普通 C4 任务")
    result = _result(
        parameters={"stock_code": "600519"},
        result={"sheet__model-c4-alpha": {"D11": "10%"}},
    )

    rows = extract_summary_records(task, result)

    assert rows[0].model_name == "C4"


def test_extract_c4_maps_d2_to_d20_metric_cells():
    task = _task(task_type="google_sheet_C4", name="C4-600519-贵州茅台")
    result = _result(
        parameters={"stock_code": "600519", "year": "2025-2024"},
        result={
            "sheet__model": {
                "D2": "1%",
                "D3": "2%",
                "D4": "-3%",
                "D5": "4%",
                "D6": "5%",
                "D7": "-6%",
                "D8": "7%",
                "D9": "8%",
                "D10": "9%",
                "D11": "10%",
                "D12": "11%",
                "D13": "12%",
                "D14": "13%",
                "D15": "14",
                "D16": "15",
                "D17": "16%",
                "D18": "17",
                "D19": "18",
                "D20": "19%",
            }
        },
    )

    rows = extract_summary_records(task, result)

    assert len(rows) == 1
    assert rows[0].stock_code == "600519"
    assert rows[0].best_metric_value == 0.1
    assert rows[0].metrics["return_rate"] == 0.01
    assert rows[0].metrics["turnover_rate"] == 0.09
    assert rows[0].metrics["max_theoretical_leverage"] == 14
    assert rows[0].metrics["unit_actual_leverage_return"] == 0.19


def test_extract_c5_includes_saved_return_analysis_metrics():
    task = _task(task_type="google_sheet_C5", name="C5-600776-东方通信")
    result = _result(
        parameters={"A1": "1.8", "B1": "4", "year": "2025-2024"},
        result={
            "sheet__model": {
                "D2": "20%",
                "D11": "15%",
                "annualized_return_diff": "6%",
                "monthly_excess_return_percentage_last_return": "66%",
                "excess_sharp": "1.23",
                "start_kama_ratio": "2.2",
                "index_sotino_ratio": "1.1",
                "max_drawdown": "-8%",
            }
        },
    )

    rows = extract_summary_records(task, result)

    assert rows[0].metrics["annualized_return_diff"] == 0.06
    assert rows[0].metrics["monthly_excess_return_percentage"] == 0.66
    assert rows[0].metrics["excess_sharp"] == 1.23
    assert rows[0].metrics["start_kama_ratio"] == 2.2
    assert rows[0].metrics["index_sotino_ratio"] == 1.1
    assert rows[0].metrics["max_drawdown_analysis"] == -0.08


def test_extract_c5_falls_back_to_prefixed_task_name_when_stock_code_missing():
    task = _task(task_type="google_sheet_C5", name="C5-600776-东方通信")
    result = _result(
        parameters={"A1": "1.8", "B1": "4", "year": "2025-2024"},
        result={"sheet__model": {"D11": "15%"}},
    )

    rows = extract_summary_records(task, result)

    assert rows[0].stock_code == "600776"


def test_extract_backtest_uses_global_preview_model_value_columns():
    task = _task(task_type="backtest_training", name="回测任务")
    result = _result(
        parameters={"stock_code": "600519", "year": "2025-2024"},
        result={
            "sheet": {
                "calculate_metrics": {
                    "excess_returns": [
                        {
                            "year": "all",
                            "start_end_date": "2024-01-01 ~ 2025-12-31",
                            "start_annualized_return": 0.12,
                            "index_annualized_return": 0.08,
                            "annualized_return_diff": 0.04,
                        }
                    ],
                    "start_profit_annual": 0.7,
                    "index_profit_annual": 0.5,
                    "start_profit_monthly": [{"year": "all", "profit_monthly_percentage": 0.6}],
                    "index_profit_monthly": [{"year": "all", "profit_monthly_percentage": 0.4}],
                    "start_sharpe_ratios": {
                        "all": {"avg_monthly_return": 0.02, "sharpe_ratio": 1.23}
                    },
                    "index_sharpe_ratios": {
                        "all": {"avg_monthly_return": 0.01, "sharpe_ratio": 0.9}
                    },
                    "start_monthly_return_volatility": 0.03,
                    "monthly_excess_return_percentage": [{"year": "all", "excess_return": 0.55}],
                    "monthly_excess_returns": [{"monthly_excess_return_diff": 0.01}],
                    "monthly_excess_volatility": 0.025,
                    "start_maximum_drawdown": {"total_maximum_drawdown": {"drawdown": -0.18}},
                    "start_maximum_number_of_backtest_repair_days": 33,
                    "excess_maximum_number_of_backtest_repair_days": 21,
                    "start_kama_ratio": [{"year": "all", "kama_ratio": 2.2}],
                    "start_sotino_ratio": [{"year": "all", "sotino_ratio": 1.7}],
                    "excess_sharp": 0.88,
                    "excess_of_promissory_note": 0.77,
                }
            }
        },
    )

    rows = extract_summary_records(task, result)

    assert len(rows) == 1
    assert rows[0].best_metric_name == "年化超额收益"
    assert rows[0].best_metric_value == 0.04
    assert rows[0].metrics["absolute_annualized_return"] == "12.00%"
    assert rows[0].metrics["relative_annualized_excess_return"] == "4.00%"
    assert rows[0].metrics["ratio_sharpe_ratio"] == "1.23"
    assert "index_annualized_rate" not in rows[0].metrics


def test_extract_backtest_fills_metrics_from_calculate_metrics_when_export_format_fails(monkeypatch):
    task = _task(task_type="backtest_training", name="C5-NVDA")
    result = _result(
        parameters={"stock_code": "NVDA", "parameter": [3, 3.5], "year": 2026},
        result={
            "sheet": {
                "calculate_metrics": {
                    "excess_returns": [
                        {
                            "year": "all",
                            "start_annualized_return": 0.32,
                            "annualized_return_diff": 2.5353,
                        }
                    ],
                    "start_profit_annual": 0.8,
                    "start_profit_monthly": [{"year": "all", "profit_monthly_percentage": 0.7}],
                    "start_sharpe_ratios": {
                        "all": {"avg_monthly_return": 0.03, "sharpe_ratio": 1.5}
                    },
                    "monthly_excess_return_percentage": [{"year": "all", "excess_return": 0.6}],
                    "monthly_excess_returns": [{"monthly_excess_return_diff": 0.02}],
                    "monthly_excess_volatility": 0.04,
                    "start_kama_ratio": [{"year": "all", "kama_ratio": 2.1}],
                    "start_sotino_ratio": [{"year": "all", "sotino_ratio": 1.9}],
                    "excess_sharp": 1.2,
                }
            }
        },
    )
    monkeypatch.setattr(
        "app.services.model_summary_service.xpl_analyzer.format_export_file_data",
        lambda _payload: (_ for _ in ()).throw(RuntimeError("format failed")),
    )

    rows = extract_summary_records(task, result)

    assert rows[0].stock_code == "NVDA"
    assert rows[0].best_metric_value == pytest.approx(2.5353)
    assert rows[0].metrics["absolute_annualized_return"] == "32.00%"
    assert rows[0].metrics["absolute_profit_year_percentage"] == "80.00%"
    assert rows[0].metrics["relative_annualized_excess_return"] == "253.53%"
    assert rows[0].metrics["relative_monthly_excess_win_rate"] == "60.00%"
    assert rows[0].metrics["ratio_sharpe_ratio"] == "1.5"
    assert rows[0].metrics["sharpe_excess_sharpe"] == "1.2"


def test_rebuild_marks_best_row(app_factory):
    app = app_factory
    with app.app_context():
        db.session.add(_task())
        db.session.add(_result(result_id=10, result={"I15": 0.1, "I18": 0.01}))
        db.session.add(_result(result_id=11, result={"I15": 0.2, "I18": 0.15}))
        db.session.commit()

        summary = model_summary_service.rebuild(task_id="task-1", reset=True)
        best = TaskResultSummaryIndex.query.filter_by(is_best=True).one()

        assert summary["processed"] == 2
        assert summary["candidate_records"] == 2
        assert summary["indexed"] == 1
        assert best.task_result_id == 10
        assert best.best_metric_value == pytest.approx(0.09)


def test_rebuild_keeps_one_best_row_per_task(app_factory):
    app = app_factory
    with app.app_context():
        db.session.add(_task(task_id="task-a", name="600519"))
        db.session.add(_result(task_id="task-a", result_id=20, result={"I15": 0.1, "I18": 0.01}))
        db.session.add(_result(task_id="task-a", result_id=21, result={"I15": 0.2, "I18": 0.15}))
        db.session.add(_result(task_id="task-a", result_id=22, result={"I15": 0.15, "I18": 0.02}))
        db.session.commit()

        model_summary_service.rebuild(task_id="task-a", reset=True)
        best_rows = TaskResultSummaryIndex.query.filter_by(task_id="task-a", is_best=True).all()

        assert len(best_rows) == 1
        assert best_rows[0].task_result_id == 22
        assert TaskResultSummaryIndex.query.filter_by(task_id="task-a").count() == 1


def test_query_all_results_requires_stock_and_reads_raw_results(app_factory):
    app = app_factory
    with app.app_context():
        db.session.add(_task(task_id="task-a", name="600519"))
        db.session.add(_result(task_id="task-a", result_id=20, result={"I15": 0.1, "I18": 0.01}))
        db.session.add(_result(task_id="task-a", result_id=21, result={"I15": 0.2, "I18": 0.15}))
        db.session.add(_result(task_id="task-a", result_id=22, result={"I15": 0.15, "I18": 0.02}))
        db.session.commit()

        model_summary_service.rebuild(task_id="task-a", reset=True)
        missing_stock = model_summary_service.query(
            _User(),
            {"best_only": "false", "page": 1, "per_page": 10},
        )
        payload = model_summary_service.query(
            _User(),
            {"best_only": "false", "stock_code": "600519", "page": 1, "per_page": 10},
        )

        assert missing_stock["status"] == "error"
        assert TaskResultSummaryIndex.query.filter_by(task_id="task-a").count() == 1
        assert payload["pagination"]["total"] == 3
        assert [item["task_result_id"] for item in payload["items"]] == [22, 21, 20]


def test_query_all_results_fuzzy_matches_task_name_before_loading_results(app_factory):
    app = app_factory
    with app.app_context():
        db.session.add(_task(task_id="task-a", task_type="google_sheet_C5", name="C5-600776-东方通信"))
        db.session.add(_task(task_id="task-b", task_type="google_sheet_C5", name="C5-600519-贵州茅台"))
        db.session.add(_result(
            task_id="task-a",
            result_id=23,
            parameters={"A1": "1.8", "B1": "4", "year": "2025-2024"},
            result={"sheet__model-a": {"D11": "15%"}},
        ))
        db.session.add(_result(
            task_id="task-a",
            result_id=24,
            parameters={"A1": "2.0", "B1": "4", "year": "2025-2024"},
            result={"sheet__model-a": {"D11": "18%"}},
        ))
        db.session.add(_result(
            task_id="task-b",
            result_id=25,
            parameters={"A1": "2.0", "B1": "4", "year": "2025-2024"},
            result={"sheet__model-b": {"D11": "30%"}},
        ))
        db.session.commit()

        payload = model_summary_service.query(
            _User(),
            {
                "best_only": "false",
                "task_type": "google_sheet_C5",
                "stock_code": "东方通信",
                "page": 1,
                "per_page": 10,
            },
        )

        assert payload["status"] == "success"
        assert payload["pagination"]["total"] == 2
        assert [item["task_result_id"] for item in payload["items"]] == [24, 23]
        assert all(item["task_id"] == "task-a" for item in payload["items"])


def test_export_csv_uses_query_filters_and_ignores_pagination(app_factory):
    app = app_factory
    with app.app_context():
        db.session.add(_task(task_id="task-a", name="600519"))
        db.session.add(_task(task_id="task-b", name="600519"))
        db.session.add(_task(task_id="task-c", name="000001"))
        db.session.add(_result(task_id="task-a", result_id=20, result={"I15": 0.2, "I18": 0.01}))
        db.session.add(_result(task_id="task-b", result_id=21, result={"I15": 0.3, "I18": 0.1}))
        db.session.add(_result(task_id="task-c", result_id=22, result={"I15": 0.5, "I18": 0.1}))
        db.session.commit()

        model_summary_service.rebuild(reset=True)
        payload = model_summary_service.export_csv(
            _User(),
            {"stock_code": "600519", "page": 1, "per_page": 1},
        )

        assert payload["status"] == "success"
        rows = list(csv.DictReader(io.StringIO(payload["content"])))
        assert [row["任务名"] for row in rows] == ["600519", "600519"]
        assert [row["结果 ID"] for row in rows] == ["21", "20"]
        assert all(row["产品/股票"] == "600519" for row in rows)
        assert "000001" not in payload["content"]


def test_export_csv_supports_all_results_query(app_factory):
    app = app_factory
    with app.app_context():
        db.session.add(_task(task_id="task-a", name="600519"))
        db.session.add(_result(task_id="task-a", result_id=20, result={"I15": 0.1, "I18": 0.01}))
        db.session.add(_result(task_id="task-a", result_id=21, result={"I15": 0.2, "I18": 0.15}))
        db.session.add(_result(task_id="task-a", result_id=22, result={"I15": 0.15, "I18": 0.02}))
        db.session.commit()

        model_summary_service.rebuild(task_id="task-a", reset=True)
        payload = model_summary_service.export_csv(
            _User(),
            {"best_only": "false", "stock_code": "600519", "page": 1, "per_page": 1},
        )

        assert payload["status"] == "success"
        rows = list(csv.DictReader(io.StringIO(payload["content"])))
        assert [row["结果 ID"] for row in rows] == ["22", "21", "20"]
        assert [row["return beats"] for row in rows] == ["13.00%", "5.00%", "9.00%"]


def test_export_csv_joins_parameter_list_values(app_factory):
    app = app_factory
    with app.app_context():
        db.session.add(_task(task_id="task-c5", task_type="google_sheet_C5", name="C5-600776-东方通信"))
        db.session.add(_result(
            task_id="task-c5",
            result_id=26,
            parameters={"parameter": [4, 0.92, 0.3, 1, 0, 0]},
            result={"sheet__model": {"D11": "18%"}},
        ))
        db.session.commit()

        payload = model_summary_service.export_csv(
            _User(),
            {
                "best_only": "false",
                "task_type": "google_sheet_C5",
                "stock_code": "东方通信",
                "page": 1,
                "per_page": 10,
            },
        )

        assert payload["status"] == "success"
        rows = list(csv.DictReader(io.StringIO(payload["content"])))
        assert rows[0]["参数"] == "4,0.92,0.3,1,0,0"


def test_export_csv_joins_a1_b1_when_parameter_list_missing(app_factory):
    app = app_factory
    with app.app_context():
        db.session.add(_task(task_id="task-c5", task_type="google_sheet_C5", name="C5-002916-深南电路"))
        db.session.add(_result(
            task_id="task-c5",
            result_id=27,
            parameters={"stock_code": "002916", "year": 2025, "A1": 11, "B1": 3},
            result={"sheet__model": {"D11": "18%"}},
        ))
        db.session.commit()

        payload = model_summary_service.export_csv(
            _User(),
            {
                "best_only": "false",
                "task_type": "google_sheet_C5",
                "stock_code": "深南电路",
                "page": 1,
                "per_page": 10,
            },
        )

        assert payload["status"] == "success"
        rows = list(csv.DictReader(io.StringIO(payload["content"])))
        assert rows[0]["参数"] == "11,3"


def test_export_csv_uses_custom_safe_filename(app_factory):
    app = app_factory
    with app.app_context():
        db.session.add(_task(task_id="task-a", name="600519"))
        db.session.add(_result(task_id="task-a", result_id=20, result={"I15": 0.2, "I18": 0.01}))
        db.session.commit()

        model_summary_service.rebuild(task_id="task-a", reset=True)
        payload = model_summary_service.export_csv(
            _User(),
            {
                "stock_code": "600519",
                "filename": "东方通信/全部结果",
                "page": 1,
                "per_page": 10,
            },
        )

        assert payload["status"] == "success"
        assert payload["filename"] == "东方通信_全部结果.csv"


def test_export_csv_preserves_backtest_display_metrics(app_factory):
    app = app_factory
    with app.app_context():
        db.session.add(_task(task_id="task-bt", task_type="backtest_training", name="回测任务"))
        db.session.add(_result(
            task_id="task-bt",
            result_id=30,
            parameters={"stock_code": "000001"},
            result={
                "sheet": {
                    "calculate_metrics": {
                        "excess_returns": [
                            {
                                "year": "all",
                                "start_annualized_return": 0.12,
                                "annualized_return_diff": 0.04,
                            }
                        ],
                        "start_profit_annual": 0.7,
                    }
                }
            },
        ))
        db.session.commit()

        model_summary_service.rebuild(task_id="task-bt", reset=True)
        payload = model_summary_service.export_csv(
            _User(),
            {"task_type": "backtest_training", "page": 1, "per_page": 1},
        )

        assert payload["status"] == "success"
        rows = list(csv.DictReader(io.StringIO(payload["content"])))
        assert rows[0]["年化收益"] == "12.00%"
        assert rows[0]["年化超额收益"] == "4.00%"


def test_export_model_summary_api_returns_csv_download(app_factory, monkeypatch):
    app = app_factory
    monkeypatch.setenv("AUTH_ENABLED", "false")
    with app.app_context():
        db.session.add(Permission(name="查看任务", code="task:view", group="task"))
        db.session.add(Permission(name="查看 C3", code="google_sheet:c3", group="task"))
        db.session.add(_task(task_id="task-a", name="600519"))
        db.session.add(_result(task_id="task-a", result_id=20, result={"I15": 0.2, "I18": 0.01}))
        db.session.commit()

        model_summary_service.rebuild(task_id="task-a", reset=True)

    response = app.test_client().get(
        "/admin/api/model-summary/export",
        query_string={"stock_code": "600519", "filename": "东方通信/全部结果"},
    )

    assert response.status_code == 200
    assert response.content_type == "text/csv; charset=utf-8"
    assert "attachment;" in response.headers["Content-Disposition"]
    assert "filename=\"model_summary.csv\"" in response.headers["Content-Disposition"]
    assert "filename*=UTF-8''%E4%B8%9C%E6%96%B9%E9%80%9A%E4%BF%A1_%E5%85%A8%E9%83%A8%E7%BB%93%E6%9E%9C.csv" in response.headers["Content-Disposition"]
    text = response.data.decode("utf-8-sig")
    rows = list(csv.DictReader(io.StringIO(text)))
    assert rows[0]["产品/股票"] == "600519"
    assert rows[0]["return beats"] == "19.00%"


def test_rebuild_batches_by_task_not_result(app_factory):
    app = app_factory
    with app.app_context():
        db.session.add(_task(task_id="task-a", name="600519"))
        db.session.add(_task(task_id="task-b", name="000001"))
        db.session.add(_result(task_id="task-a", result_id=50, result={"I15": 0.1, "I18": 0.01}))
        db.session.add(_result(task_id="task-a", result_id=51, result={"I15": 0.4, "I18": 0.35}))
        db.session.add(_result(task_id="task-a", result_id=52, result={"I15": 0.2, "I18": 0.02}))
        db.session.add(_result(task_id="task-b", result_id=53, result={"I15": 0.3, "I18": 0.05}))
        db.session.commit()

        summary = model_summary_service.rebuild(reset=True, batch_size=1)
        rows = TaskResultSummaryIndex.query.order_by(TaskResultSummaryIndex.task_id.asc()).all()

        assert summary["processed_tasks"] == 2
        assert summary["processed"] == 4
        assert summary["indexed"] == 2
        assert [(row.task_id, row.task_result_id) for row in rows] == [
            ("task-a", 52),
            ("task-b", 53),
        ]


def test_rebuild_progress_counts_finished_tasks_without_success_results(app_factory):
    app = app_factory
    with app.app_context():
        db.session.add(_task(task_id="task-ok", name="600519"))
        db.session.add(_task(task_id="task-empty", name="000001"))
        running_task = _task(task_id="task-running", name="000002")
        running_task.status = "running"
        db.session.add(running_task)
        db.session.add(_result(task_id="task-ok", result_id=60, result={"I15": 0.2, "I18": 0.05}))
        db.session.commit()

        summary = model_summary_service.rebuild(reset=True, batch_size=1)

        assert summary["processed_tasks"] == 2
        assert summary["processed"] == 1
        assert summary["indexed"] == 1


def test_stock_summary_selects_best_task_result_per_stock(app_factory):
    app = app_factory
    with app.app_context():
        db.session.add(_task(task_id="task-a", name="600519"))
        db.session.add(_task(task_id="task-b", name="600519"))
        db.session.add(_result(task_id="task-a", result_id=30, result={"I15": 0.2, "I18": 0.01}))
        db.session.add(_result(task_id="task-b", result_id=31, result={"I15": 0.4, "I18": 0.3}))
        db.session.commit()

        model_summary_service.rebuild(reset=True)
        payload = model_summary_service.query(_User(), {"summary_type": "stock", "page": 1, "per_page": 10})

        assert payload["pagination"]["total"] == 1
        assert payload["items"][0]["task_id"] == "task-a"
        assert payload["items"][0]["best_metric_value"] == pytest.approx(0.19)


def test_query_all_excludes_backtest_until_backtest_type_selected(app_factory):
    app = app_factory
    with app.app_context():
        db.session.add(_task(task_id="task-c3", task_type="google_sheet", name="600519"))
        db.session.add(_task(task_id="task-bt", task_type="backtest_training", name="回测任务"))
        db.session.add(_result(task_id="task-c3", result_id=70, result={"I15": 0.2, "I18": 0.05}))
        db.session.add(_result(
            task_id="task-bt",
            result_id=71,
            parameters={"stock_code": "000001"},
            result={
                "sheet": {
                    "calculate_metrics": {
                        "excess_returns": [
                            {
                                "year": "all",
                                "start_annualized_return": 0.12,
                                "annualized_return_diff": 0.04,
                            }
                        ]
                    }
                }
            },
        ))
        db.session.commit()

        model_summary_service.rebuild(reset=True)
        all_payload = model_summary_service.query(_User(), {"summary_type": "task", "page": 1, "per_page": 10})
        backtest_payload = model_summary_service.query(
            _User(),
            {"task_type": "backtest_training", "summary_type": "task", "page": 1, "per_page": 10},
        )

        assert [item["task_id"] for item in all_payload["items"]] == ["task-c3"]
        assert [item["task_id"] for item in backtest_payload["items"]] == ["task-bt"]
        assert backtest_payload["columns"][0]["label"] == "年化收益"
        assert all_payload["columns"][0]["label"] == "Return%"


def test_query_tolerates_legacy_truncated_metrics_json(app_factory):
    app = app_factory
    with app.app_context():
        db.session.add(_task(task_id="task-bt", task_type="backtest_training", name="回测任务"))
        db.session.add(
            TaskResultSummaryIndex(
                task_id="task-bt",
                task_result_id=99,
                task_type="backtest_training",
                task_name="回测任务",
                stock_code="000001",
                model_key="回测",
                model_name="回测",
                year_label="all",
                parameter_summary='{"stock_code": "000001"...',
                best_metric_name="年化收益",
                best_metric_value=0.12,
                metrics_json='{"absolute_annualized_return": 0.12...',
                is_best=True,
            )
        )
        db.session.commit()

        payload = model_summary_service.query(
            _User(),
            {"task_type": "backtest_training", "summary_type": "stock", "page": 1, "per_page": 10},
        )

        assert payload["pagination"]["total"] == 1
        assert payload["items"][0]["parameter_summary"] == {}
        assert payload["items"][0]["metrics"] == {}


def test_query_normalizes_legacy_c5_plain_sharpe_metric(app_factory):
    app = app_factory
    with app.app_context():
        db.session.add(_task(task_id="task-c5", task_type="google_sheet_C5", name="C5-600776-东方通信"))
        db.session.add(
            TaskResultSummaryIndex(
                task_id="task-c5",
                task_result_id=100,
                task_type="google_sheet_C5",
                task_name="C5-600776-东方通信",
                stock_code="600776",
                model_key="sheet__C5.v20260105",
                model_name="C5",
                best_metric_name="ReturnBeats",
                best_metric_value=0.12,
                metrics_json='{"sharpe_ratio": 2.1, "index_sharpe_ratio": 0.9}',
                is_best=True,
            )
        )
        db.session.commit()

        payload = model_summary_service.query(
            _User(),
            {"task_type": "google_sheet_C5", "summary_type": "task", "page": 1, "per_page": 10},
        )

        assert payload["columns"][0]["format"] == "percent"
        assert payload["items"][0]["metrics"]["start_sharpe_ratio"] == 2.1
        assert payload["items"][0]["metrics"]["index_sharpe_ratio"] == 0.9


def test_start_rebuild_job_completes_in_background(app_factory):
    app = app_factory
    with app.app_context():
        db.session.add(_task(task_id="task-bg", name="600519"))
        db.session.add(_result(task_id="task-bg", result_id=40, result={"I15": 0.3, "I18": 0.05}))
        db.session.commit()

    job = model_summary_service.start_rebuild_job(app, task_id="task-bg", reset=True)
    for _ in range(100):
        current = model_summary_service.get_rebuild_job(job["job_id"])
        if current and current["status"] in {"completed", "error"}:
            break
        time.sleep(0.05)

    current = model_summary_service.get_rebuild_job(job["job_id"])
    assert current["status"] == "completed"
    assert current["result"]["indexed"] == 1
    with app.app_context():
        task = db.session.get(Task, job["task_id"])
        assert task.status == "completed"
        assert task.current_step == 1
        assert task.total_steps == 1
        assert TaskLog.query.filter_by(task_id=job["task_id"]).count() >= 1

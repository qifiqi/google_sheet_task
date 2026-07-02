import pytest
from io import BytesIO
from zipfile import ZipFile

from openpyxl import Workbook

from app.extensions import db
from app.models import Task
from app.routes.backtest_training import (
    _build_global_preview_workbook,
    _extract_summary_rows,
    _negative_percent_display,
    _with_excess_return_preview_row,
)


def _add_backtest_task(task_id, name="单品回测", status="completed", task_type="backtest_training"):
    db.session.add(Task(
        id=task_id,
        name=name,
        task_type=task_type,
        status=status,
        config="{}",
    ))
    db.session.commit()


def test_batch_export_global_preview_returns_zip(app_factory, monkeypatch):
    app = app_factory
    with app.app_context():
        _add_backtest_task("single-batch-1", name="单品:回测/1")
        monkeypatch.setenv("AUTH_ENABLED", "false")
        monkeypatch.setattr(
            "app.routes.backtest_training.authorize_task_type_action",
            lambda _user, _action, task_type: {"allowed": True, "task_type": task_type},
        )
        monkeypatch.setattr(
            "app.routes.backtest_training._build_global_preview_payload",
            lambda task_id: {"task": {"name": task_id}, "groups": []},
        )

        def fake_workbook(_payload):
            workbook = Workbook()
            workbook.active["A1"] = "ok"
            return workbook

        monkeypatch.setattr("app.routes.backtest_training._build_global_preview_workbook", fake_workbook)
        response = app.test_client().post(
            "/backtest-training/api/global-preview/batch-export",
            json={"task_ids": ["single-batch-1"]},
        )

        assert response.status_code == 200
        assert response.mimetype == "application/zip"
        with ZipFile(BytesIO(response.data)) as archive:
            assert archive.namelist() == ["单品_回测_1_global_preview.xlsx"]


def test_batch_export_global_preview_rejects_empty_selection(app_factory, monkeypatch):
    app = app_factory
    with app.app_context():
        monkeypatch.setenv("AUTH_ENABLED", "false")
        response = app.test_client().post(
            "/backtest-training/api/global-preview/batch-export",
            json={"task_ids": []},
        )

        assert response.status_code == 400
        assert response.get_json()["message"] == "请选择至少一个任务"


def test_batch_export_global_preview_rejects_unfinished_task(app_factory, monkeypatch):
    app = app_factory
    with app.app_context():
        _add_backtest_task("single-running", status="running")
        monkeypatch.setenv("AUTH_ENABLED", "false")
        monkeypatch.setattr(
            "app.routes.backtest_training.authorize_task_type_action",
            lambda _user, _action, task_type: {"allowed": True, "task_type": task_type},
        )
        response = app.test_client().post(
            "/backtest-training/api/global-preview/batch-export",
            json={"task_ids": ["single-running"]},
        )

        assert response.status_code == 400
        assert response.get_json()["task_status"] == "running"


def test_batch_export_global_preview_rejects_too_many_tasks(app_factory, monkeypatch):
    app = app_factory
    with app.app_context():
        monkeypatch.setenv("AUTH_ENABLED", "false")
        response = app.test_client().post(
            "/backtest-training/api/global-preview/batch-export",
            json={"task_ids": [f"task-{index}" for index in range(11)]},
        )

        assert response.status_code == 400
        assert "最多支持 10 个任务" in response.get_json()["message"]


def test_global_preview_workbook_adds_summary_sheet_first():
    payload = {
        "task": {"stock_code": "TEST", "name": "单品回测"},
        "groups": [
            {
                "group_label": "2026-2023 年",
                "year": "2026-2023",
                "period": "",
                "columns": [
                    {
                        "column_key": "result_1",
                        "result_id": 1,
                        "header": "2.5/5",
                        "model_name": "C3",
                        "success": True,
                        "raw_metrics": {
                            "I15": "12%",
                            "I17": "-8%",
                            "I18": "5%",
                            "I20": "-10%",
                        },
                    },
                    {
                        "column_key": "result_2",
                        "result_id": 2,
                        "header": "3/5",
                        "model_name": "C5",
                        "success": True,
                        "raw_metrics": {
                            "D2": "20%",
                            "D4": "-6%",
                            "D5": "7%",
                            "D7": "-9%",
                        },
                    },
                ],
                "rows": [],
            }
        ],
    }

    workbook = _build_global_preview_workbook(payload)
    sheet = workbook.worksheets[0]

    assert sheet.title == "汇总"
    assert workbook.sheetnames[1] == "2026-2023 年"
    assert sheet["A1"].value == "周期"
    assert sheet["B1"].value == "名称"
    assert sheet["C1"].value == "2.5/5"
    assert sheet["D1"].value == "3/5"
    assert sheet["A2"].value == "2026-2023"
    assert sheet["B2"].value == "指数回报"
    assert sheet["C2"].value == pytest.approx(0.05)
    assert sheet["D2"].value == pytest.approx(0.07)
    assert sheet["C3"].value == pytest.approx(0.12)
    assert sheet["D3"].value == pytest.approx(0.20)
    assert sheet["B4"].value == "超额回报"
    assert sheet["C4"].value == pytest.approx(0.07)
    assert sheet["D4"].value == pytest.approx(0.13)
    assert sheet["C5"].value == pytest.approx(-0.10)
    assert sheet["D5"].value == pytest.approx(-0.09)
    assert sheet["C6"].value == pytest.approx(-0.08)
    assert sheet["D6"].value == pytest.approx(-0.06)
    assert sheet["B7"].value == "超额回撤"
    assert sheet["C7"].value == pytest.approx(0.02)
    assert sheet["D7"].value == pytest.approx(0.03)
    assert sheet["C2"].number_format == "0.00%"
    assert sheet["A1"].fill.fgColor.rgb == "00F7E1A1"
    assert sheet["B2"].fill.fgColor.rgb == "00F7E1A1"


def test_global_preview_workbook_writes_percentage_cells_as_numbers():
    payload = {
        "task": {"stock_code": "TEST", "name": "单品回测"},
        "groups": [
            {
                "group_label": "2026-2023 年",
                "year": "2026-2023",
                "period": "",
                "columns": [
                    {
                        "column_key": "result_1",
                        "result_id": 1,
                        "header": "2.5/5",
                        "model_name": "C3",
                        "success": True,
                        "raw_metrics": {
                            "I15": "12%",
                            "I17": "-0.00%",
                            "I18": "5%",
                            "I20": "-10%",
                        },
                    },
                ],
                "rows": [
                    {
                        "category": "回撤",
                        "metric": "年最大回撤",
                        "index_value": "",
                        "values": {"result_1": "0.00%"},
                    },
                ],
            }
        ],
    }

    workbook = _build_global_preview_workbook(payload)
    summary_sheet = workbook["汇总"]
    detail_sheet = workbook["2026-2023 年"]

    assert summary_sheet["C2"].value == pytest.approx(0.05)
    assert summary_sheet["C2"].number_format == "0.00%"
    assert detail_sheet["D3"].value == pytest.approx(0)
    assert detail_sheet["D3"].number_format == "0.00%"


def test_negative_percent_display_keeps_zero_unsigned():
    assert _negative_percent_display(0) == "0.00%"
    assert _negative_percent_display("0.00%") == "0.00%"
    assert _negative_percent_display("-4.00%") == "-4.00%"


def test_single_global_preview_inserts_excess_return_above_annualized_return():
    rows = [
        {
            "category": "绝对收益",
            "metric": "年化收益",
            "index_value": "5.00%",
            "model_value": "12.00%",
        },
        {
            "category": "绝对收益",
            "metric": "盈利年份百分比",
            "index_value": "100.00%",
            "model_value": "100.00%",
        },
    ]
    column = {
        "model_name": "C3",
        "raw_metrics": {
            "I15": "12%",
            "I18": "5%",
        },
    }

    updated_rows = _with_excess_return_preview_row(rows, column)

    assert updated_rows[0] == {
        "category": "绝对收益",
        "metric": "超额回报",
        "index_value": "",
        "model_value": "7.00%",
    }
    assert updated_rows[1]["metric"] == "年化收益"
    assert updated_rows[2]["metric"] == "盈利年份百分比"


def test_single_global_preview_derives_year_max_excess_drawdown_with_string_years():
    calculate_metrics = {
        "excess_returns": [
            {
                "year": "2024",
                "index_annualized_return": 0.10,
                "start_annualized_return": 0.18,
                "annualized_return_diff": 0.08,
                "start_end_date": "2024-01-01 00:00:00/2024-12-31 00:00:00",
            },
            {
                "year": "all",
                "index_annualized_return": 0.10,
                "start_annualized_return": 0.18,
                "annualized_return_diff": 0.08,
                "start_end_date": "2024-01-01 00:00:00/2024-12-31 00:00:00",
            },
        ],
        "index_profit_annual": 1,
        "start_profit_annual": 1,
        "index_profit_monthly": [{"year": "all", "profit_monthly_percentage": 1}],
        "start_profit_monthly": [{"year": "all", "profit_monthly_percentage": 1}],
        "index_sharpe_ratios": {"all": {"avg_monthly_return": 0.01, "sharpe_ratio": 1}},
        "start_sharpe_ratios": {"all": {"avg_monthly_return": 0.02, "sharpe_ratio": 2}},
        "index_monthly_return_volatility": 0.03,
        "start_monthly_return_volatility": 0.04,
        "outperform_year": 1,
        "monthly_excess_return_percentage": [{"year": "all", "excess_return": 1}],
        "monthly_excess_returns": [{
            "date": "2024-01",
            "start_monthly_return": 0.02,
            "monthly_excess_return_diff": 0.01,
        }],
        "monthly_excess_volatility": 0.01,
        "index_maximum_drawdown": {
            "year_maximum_drawdown": [{"year": "2024", "drawdown": 0.10}],
        },
        "start_maximum_drawdown": {
            "year_maximum_drawdown": [{"year": "2024", "drawdown": 0.06}],
            "total_maximum_drawdown": {"drawdown": 0.06},
        },
        "excess_drawdown_winning_rate": 1,
        "index_kama_ratio": [{"year": "all", "kama_ratio": 1}],
        "start_kama_ratio": [{"year": "all", "kama_ratio": 2}],
        "index_sotino_ratio": [{"year": "all", "sotino_ratio": 1}],
        "start_sotino_ratio": [{"year": "all", "sotino_ratio": 2}],
        "excess_sharp": 1,
        "excess_of_promissory_note": 1,
        "start_maximum_number_of_backtest_repair_days": 3,
        "excess_maximum_number_of_backtest_repair_days": 2,
    }

    _period_text, rows = _extract_summary_rows(calculate_metrics, "C3")

    drawdown_row = next(row for row in rows if row["metric"] == "年最大超额回撤")
    assert drawdown_row["model_value"] == "4.00%"


def test_single_global_preview_fallback_keeps_drawdown_values_negative(monkeypatch):
    calculate_metrics = {
        "excess_returns": [
            {
                "year": "2024",
                "annualized_return_diff": 0.08,
            },
            {
                "year": "all",
                "start_annualized_return": 0.18,
                "annualized_return_diff": 0.08,
            },
        ],
        "monthly_excess_returns": [{"monthly_excess_return_diff": 0.01}],
        "index_maximum_drawdown": {
            "year_maximum_drawdown": [{"year": 2024, "drawdown": 0.10}],
        },
        "start_maximum_drawdown": {
            "year_maximum_drawdown": [{"year": 2024, "drawdown": 0.06}],
            "total_maximum_drawdown": {"drawdown": 0.06},
        },
        "excess_drawdown_winning_rate": 0.75,
    }
    monkeypatch.setattr(
        "app.routes.backtest_training.xpl_analyzer.format_export_file_data",
        lambda _payload: (_ for _ in ()).throw(RuntimeError("format failed")),
    )

    _period_text, rows = _extract_summary_rows(calculate_metrics, "C3")

    values = {row["metric"]: row["model_value"] for row in rows}
    assert values["年最大超额回撤"] == "4.00%"
    assert values["超额回撤胜率"] == "75.00%"
    assert values["年最大回撤"] == "-6.00%"

import json
from io import BytesIO
from urllib.parse import unquote

from app.extensions import db
from app.models import Task, TaskResult
from app.routes.backtest_training import _build_backtest_result_export_data
from app.services.backtest_training_api_service import _extract_summary_rows
from app.services.xpl_service import xpl_analyzer


def _add_result(task_type="backtest_training", calculate_metrics=None):
    task = Task(
        id=f"preview-{task_type}",
        name="C3 TEST 回测",
        task_type=task_type,
        status="completed",
        config=json.dumps({"stock_code": "TEST", "model_name": "C3"}),
    )
    task_result = TaskResult(
        task_id=task.id,
        step_index=0,
        parameters="{}",
        result=json.dumps({
            "sheet__title": {"calculate_metrics": calculate_metrics or {}},
        }),
        success=True,
    )
    db.session.add_all([task, task_result])
    db.session.commit()
    return task, task_result


def _allow_backtest_view(monkeypatch):
    monkeypatch.setenv("AUTH_ENABLED", "false")


def _exportable_metrics():
    result = xpl_analyzer.analyze(
        data="\n".join([
            "2025-10-31 1.00% 2.00%",
            "2025-11-30 2.00% 3.00%",
            "2025-12-31 3.00% 4.00%",
            "2026-01-31 4.00% 5.00%",
            "2026-02-28 5.00% 6.00%",
            "2026-03-31 6.00% 7.00%",
        ]),
        time_format="auto",
    )
    return result["results"]


def test_export_preview_page_allows_browser_navigation_without_bearer_token(app_factory):
    response = app_factory.test_client().get(
        "/backtest-training/result/123/export-preview"
    )

    assert response.status_code == 200
    assert b"template-auth.js" in response.data


def test_export_preview_matches_export_formatter(app_factory, monkeypatch):
    app = app_factory
    with app.app_context():
        task, task_result = _add_result(calculate_metrics=_exportable_metrics())
        _allow_backtest_view(monkeypatch)
        expected_export_data = _build_backtest_result_export_data(task_result, task)
        expected_rows = [
            ["" if value is None else str(value) for value in row]
            for row in xpl_analyzer.format_export_file_data(expected_export_data).fillna("").values.tolist()
        ]

        response = app.test_client().get(
            f"/backtest-training/api/task-result/{task_result.id}/export-preview"
        )

        assert response.status_code == 200
        payload = response.get_json()
        assert payload["status"] == "success"
        assert len(payload["rows"]) == 200
        assert all(len(row) == 20 for row in payload["rows"])
        assert payload["rows"] == expected_rows
        assert payload["filename"] == expected_export_data["filename"]
        yearly_repair_days_row = next(
            row for row in payload["rows"] if row[1] == "年最大回测修复天数"
        )
        metrics = expected_export_data["analyze_result"]
        assert yearly_repair_days_row[2] == str(
            max(metrics["year_index_yearly_max_repair_days"].values())
        )
        assert yearly_repair_days_row[3] == str(
            max(metrics["year_start_yearly_max_repair_days"].values())
        )

        page_response = app.test_client().get(
            f"/backtest-training/result/{task_result.id}/export-preview?result_page=1"
        )
        assert page_response.status_code == 200
        assert b"copyAllButton" in page_response.data


def test_global_preview_uses_largest_yearly_repair_days():
    _period_text, rows = _extract_summary_rows({
        "year_index_yearly_max_repair_days": {"2023": 4, "2024": 8},
        "year_start_yearly_max_repair_days": {"2023": 6, "2024": 10},
    }, "C3")

    yearly_repair_days_row = next(
        row for row in rows if row["metric"] == "年最大回测修复天数"
    )

    assert yearly_repair_days_row["index_value"] == "8"
    assert yearly_repair_days_row["model_value"] == "10"


def test_export_preview_download_uses_same_export_data(app_factory, monkeypatch):
    app = app_factory
    with app.app_context():
        task, task_result = _add_result()
        _allow_backtest_view(monkeypatch)
        captured_export_data = {}

        def fake_export_file(export_data):
            captured_export_data.update(export_data)
            return BytesIO(b"csv-content"), "text/csv"

        monkeypatch.setattr(
            "app.routes.backtest_training.xpl_analyzer.export_file",
            fake_export_file,
        )
        response = app.test_client().get(
            f"/backtest-training/api/task-result/{task_result.id}/export-preview/download"
        )

        assert response.status_code == 200
        assert response.data == b"csv-content"
        assert response.mimetype == "text/csv"
        assert captured_export_data == _build_backtest_result_export_data(task_result, task)


def test_export_preview_uses_task_name_as_download_name(app_factory, monkeypatch):
    app = app_factory
    with app.app_context():
        task, task_result = _add_result()
        task.name = "我的回测任务"
        db.session.commit()
        _allow_backtest_view(monkeypatch)
        monkeypatch.setattr(
            "app.routes.backtest_training.xpl_analyzer.export_file",
            lambda _data: (BytesIO(b"csv-content"), "text/csv"),
        )

        response = app.test_client().get(
            f"/backtest-training/api/task-result/{task_result.id}/export-preview/download"
        )

        assert "我的回测任务.csv" in unquote(response.headers["Content-Disposition"])


def test_export_preview_rejects_missing_result(app_factory, monkeypatch):
    app = app_factory
    with app.app_context():
        _allow_backtest_view(monkeypatch)
        response = app.test_client().get(
            "/backtest-training/api/task-result/999999/export-preview"
        )

        assert response.status_code == 404
        assert response.get_json()["message"] == "任务结果不存在"


def test_export_preview_rejects_non_backtest_result(app_factory, monkeypatch):
    app = app_factory
    with app.app_context():
        _task, task_result = _add_result(task_type="google_sheet")
        _allow_backtest_view(monkeypatch)
        response = app.test_client().get(
            f"/backtest-training/api/task-result/{task_result.id}/export-preview"
        )

        assert response.status_code == 400
        assert response.get_json()["message"] == "当前接口仅支持回测任务"


def test_export_preview_allows_result_without_interface_permission(app_factory, monkeypatch):
    app = app_factory
    with app.app_context():
        _task, task_result = _add_result(calculate_metrics=_exportable_metrics())
        monkeypatch.setenv("AUTH_ENABLED", "false")
        response = app.test_client().get(
            f"/backtest-training/api/task-result/{task_result.id}/export-preview"
        )

        assert response.status_code == 200
        assert response.get_json()["status"] == "success"

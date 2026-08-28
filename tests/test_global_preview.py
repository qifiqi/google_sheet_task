from datetime import datetime
from io import BytesIO
from zipfile import ZipFile

from app.extensions import db
from app.models import Task, TaskResult
from app.services.backtest_training_api_service import (
    _build_parameter_header,
    _build_global_preview_payload,
    split_global_preview_payload_by_stock,
)
from app.navigation import DEFAULT_NAVIGATION_MENU, flatten_navigation_items


def _add_task(task_id, task_type, config):
    db.session.add(Task(
        id=task_id,
        name="预览任务",
        task_type=task_type,
        status="completed",
        config=config,
    ))
    db.session.commit()


def test_global_preview_supports_all_c_series_backtests(app_factory, monkeypatch):
    app = app_factory
    with app.app_context():
        _add_task("legacy-preview", "backtest_training", "{}")
        monkeypatch.setenv("AUTH_ENABLED", "false")
        response = app.test_client().get("/global-preview/api/tasks/legacy-preview")

        assert response.status_code == 200
        assert response.get_json()["supported"] is True
        assert "C 系列" in response.get_json()["message"]


def test_global_preview_supports_google_sheet_c7_tasks(app_factory, monkeypatch):
    app = app_factory
    with app.app_context():
        _add_task("c7-preview", "google_sheet_C7", "{}")
        monkeypatch.setenv("AUTH_ENABLED", "false")
        monkeypatch.setattr(
            "app.routes.global_preview._build_global_preview_initial_payload",
            lambda _task_id: {"group_mode": "year", "groups": [], "default_group_key": "", "preview": {"task": {}, "summary": {}, "groups": []}},
        )

        response = app.test_client().get("/global-preview/api/tasks/c7-preview")

        assert response.status_code == 200
        assert response.get_json()["supported"] is True


def test_c7_0_3_preview_page_does_not_require_api_token(app_factory):
    response = app_factory.test_client().get("/global-preview/c7_0_3")

    assert response.status_code == 200


def test_global_preview_is_registered_with_a_page_permission():
    item = next(
        item
        for item in flatten_navigation_items(DEFAULT_NAVIGATION_MENU)
        if item["key"] == "global_preview_c7_0_3"
    )

    assert item["path"] == "/global-preview/c7_0_3"
    assert item["permission"] == "page:global_preview:c7_0_3"


def test_global_preview_uses_c7_a1_b1_as_parameter_header():
    assert _build_parameter_header({"A1": 7, "B1": 3}) == "7 / 3"
    assert _build_parameter_header({"xm": "7", "ml": "3"}) == "7 / 3"


def test_global_preview_exports_multiple_c7_0_3_stocks_as_zip(app_factory, monkeypatch):
    app = app_factory
    with app.app_context():
        _add_task(
            "c7-preview-export",
            "backtest_training",
            '{"c7_model_version":"c7_0_3","sheet":{"title":"C7.0.3"}}',
        )
        monkeypatch.setenv("AUTH_ENABLED", "false")
        db.session.add_all([
            TaskResult(
                task_id="c7-preview-export", step_index=0,
                parameters='{"stock_code":"AAPL","year":"2024"}', result='{"result":{}}', success=True,
            ),
            TaskResult(
                task_id="c7-preview-export", step_index=1,
                parameters='{"stock_code":"MSFT","year":"2024"}', result='{"result":{}}', success=True,
            ),
        ])
        db.session.commit()

        response = app.test_client().get(
            "/global-preview/api/tasks/c7-preview-export/export?export_name=自定义导出名"
        )

        assert response.status_code == 200
        assert response.mimetype == "application/zip"
        with ZipFile(BytesIO(response.data)) as archive:
            assert archive.namelist() == ["自定义导出名_AAPL.xlsx", "自定义导出名_MSFT.xlsx"]
            entry_modified_at = datetime(*archive.getinfo("自定义导出名_AAPL.xlsx").date_time)
            assert entry_modified_at.year >= datetime.now().year - 1


def test_c7_0_3_global_preview_groups_results_by_stock_and_year(app_factory, monkeypatch):
    app = app_factory
    with app.app_context():
        monkeypatch.setattr(
            "app.services.backtest_training_api_service._extract_summary_rows",
            lambda _metrics, _model: ("2024-01-01/2024-12-31", [{
                "category": "绝对收益", "metric": "年化收益", "index_value": "5.00%", "model_value": "10.00%",
            }]),
        )
        task = Task(
            id="c7-preview-multi-stock",
            name="C7.0.3 多股票",
            task_type="backtest_training",
            status="completed",
            config='{"c7_model_version":"c7_0_3","sheet":{"title":"C7.0.3"}}',
        )
        db.session.add(task)
        db.session.flush()
        for step_index, stock_code in enumerate(("000001", "AAPL")):
            db.session.add(TaskResult(
                task_id=task.id,
                step_index=step_index,
                parameters=f'{{"stock_code":"{stock_code}","year":"2024","parameter":["1","2"]}}',
                result='{"result":{"calculate_metrics":{}}}',
                success=True,
            ))
        db.session.commit()

        payload = _build_global_preview_payload(task.id)
        stock_payloads = split_global_preview_payload_by_stock(payload)

        assert payload["summary"]["stock_count"] == 2
        assert {(group["stock_code"], group["year"]) for group in payload["groups"]} == {
            ("000001", "2024"), ("AAPL", "2024"),
        }
        assert [stock_code for stock_code, _payload in stock_payloads] == ["AAPL", "000001"]
        assert all(len(stock_payload["groups"]) == 1 for _stock_code, stock_payload in stock_payloads)


def test_c7_0_3_preview_uses_task_result_version_for_excess_return(app_factory, monkeypatch):
    app = app_factory
    with app.app_context():
        monkeypatch.setattr(
            "app.services.backtest_training_api_service._extract_summary_rows",
            lambda _metrics, _model: ("2024-01-01/2024-12-31", [{
                "category": "绝对收益", "metric": "年化收益", "index_value": "", "model_value": "",
            }]),
        )
        task = Task(
            id="c7-preview-result-version",
            name="C7 回测",
            task_type="google_sheet_C7",
            status="completed",
            config='{"sheets":[{"c7_model_version":"c7_0_3"}]}',
        )
        db.session.add(task)
        db.session.flush()
        db.session.add(TaskResult(
            task_id=task.id,
            step_index=0,
            parameters='{"stock_code":"000001","year":"2024","c7_model_version":"c7_0_3"}',
            result='{"result":{"D2":"100%","D5":"20%","calculate_metrics":{}}}',
            success=True,
        ))
        db.session.commit()

        payload = _build_global_preview_payload(task.id)
        column = payload["groups"][0]["columns"][0]
        excess_return = next(
            row for row in payload["groups"][0]["rows"] if row["metric"] == "超额回报"
        )

        assert column["c7_model_version"] == "c7_0_3"
        assert excess_return["values"][column["column_key"]] == "80.00%"


def test_c7_preview_prefers_sheet_metrics_for_excess_return(app_factory, monkeypatch):
    app = app_factory
    with app.app_context():
        monkeypatch.setattr(
            "app.services.backtest_training_api_service._extract_summary_rows",
            lambda _metrics, _model: ("2024-01-01/2024-12-31", [{
                "category": "绝对收益", "metric": "年化收益", "index_value": "", "model_value": "",
            }]),
        )
        task = Task(
            id="c7-preview-sheet-metrics",
            name="C7 回测",
            task_type="google_sheet_C7",
            status="completed",
            config="{}",
        )
        db.session.add(task)
        db.session.flush()
        db.session.add(TaskResult(
            task_id=task.id,
            step_index=0,
            parameters='{"stock_code":"XOM","year":"2026-2025","c7_model_version":"c7_0_3"}',
            result=(
                '{"result":{"D2":1.4866949361032038,"D5":0.5579996294887919,'
                '"analyze_result":{"excess_returns":['
                '{"year":"all","annualized_return_diff":0.9330320599423205}]}}}'
            ),
            success=True,
        ))
        db.session.commit()

        payload = _build_global_preview_payload(task.id)
        column = payload["groups"][0]["columns"][0]
        excess_return = next(
            row for row in payload["groups"][0]["rows"] if row["metric"] == "超额回报"
        )

        assert excess_return["values"][column["column_key"]] == "92.87%"


def test_c7_0_2_preview_does_not_infer_layout_from_d_column_values(app_factory, monkeypatch):
    app = app_factory
    with app.app_context():
        monkeypatch.setattr(
            "app.services.backtest_training_api_service._extract_summary_rows",
            lambda _metrics, _model: ("", [{
                "category": "绝对收益", "metric": "年化收益", "index_value": "", "model_value": "",
            }]),
        )
        task = Task(
            id="c7-preview-legacy-layout",
            name="C7 回测",
            task_type="google_sheet_C7",
            status="completed",
            config="{}",
        )
        db.session.add(task)
        db.session.flush()
        db.session.add(TaskResult(
            task_id=task.id,
            step_index=0,
            parameters='{"stock_code":"XOM","year":"2024"}',
            result='{"result":{"D2":1,"D5":0.2,"D8":0.8,"D11":0.3,"calculate_metrics":{}}}',
            success=True,
        ))
        db.session.commit()

        payload = _build_global_preview_payload(task.id)
        column = payload["groups"][0]["columns"][0]
        excess_return = next(
            row for row in payload["groups"][0]["rows"] if row["metric"] == "超额回报"
        )

        assert column["c7_model_version"] == "c7_0_2"
        assert excess_return["values"][column["column_key"]] == "50.00%"


def test_c7_preview_falls_back_to_analyze_result_for_excess_return(app_factory, monkeypatch):
    app = app_factory
    with app.app_context():
        monkeypatch.setattr(
            "app.services.backtest_training_api_service._extract_summary_rows",
            lambda _metrics, _model: ("2024-01-01/2024-12-31", [{
                "category": "绝对收益", "metric": "年化收益", "index_value": "", "model_value": "",
            }]),
        )
        task = Task(
            id="c7-preview-analyze-result",
            name="C7 回测",
            task_type="google_sheet_C7",
            status="completed",
            config="{}",
        )
        db.session.add(task)
        db.session.flush()
        db.session.add(TaskResult(
            task_id=task.id,
            step_index=0,
            parameters='{"stock_code":"000001","year":"2024","c7_model_version":"c7_0_3"}',
            result=(
                '{"result":{"D2":"","D5":"","analyze_result":'
                '{"excess_returns":[{"year":"all","annualized_return_diff":0.9287}]}}}'
            ),
            success=True,
        ))
        db.session.commit()

        payload = _build_global_preview_payload(task.id)
        column = payload["groups"][0]["columns"][0]
        excess_return = next(
            row for row in payload["groups"][0]["rows"] if row["metric"] == "超额回报"
        )

        assert excess_return["values"][column["column_key"]] == "92.87%"


def test_c3_and_c5_preview_use_task_type_specific_metric_cells(app_factory, monkeypatch):
    app = app_factory
    with app.app_context():
        monkeypatch.setattr(
            "app.services.backtest_training_api_service._extract_summary_rows",
            lambda _metrics, _model: ("", [{
                "category": "绝对收益", "metric": "年化收益", "index_value": "", "model_value": "",
            }]),
        )
        cases = [
            ("c3-preview-layout", "google_sheet", "C5 名称不应影响 C3", "I15", 0.8, "I18", 0.3, "50.00%"),
            ("c5-preview-layout", "google_sheet_C5", "C3 名称不应影响 C5", "D2", 0.8, "D5", 0.3, "50.00%"),
        ]
        for task_id, task_type, name, left_cell, left_value, right_cell, right_value, _expected in cases:
            task = Task(id=task_id, name=name, task_type=task_type, status="completed", config="{}")
            db.session.add(task)
            db.session.flush()
            db.session.add(TaskResult(
                task_id=task.id,
                step_index=0,
                parameters='{"stock_code":"XOM","year":"2024"}',
                result=(
                    '{"result":{"calculate_metrics":{},"%s":%s,"%s":%s}}'
                    % (left_cell, left_value, right_cell, right_value)
                ),
                success=True,
            ))
        db.session.commit()

        for task_id, _task_type, _name, _left_cell, _left_value, _right_cell, _right_value, expected in cases:
            payload = _build_global_preview_payload(task_id)
            column = payload["groups"][0]["columns"][0]
            excess_return = next(
                row for row in payload["groups"][0]["rows"] if row["metric"] == "超额回报"
            )
            assert excess_return["values"][column["column_key"]] == expected

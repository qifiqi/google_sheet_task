from datetime import datetime
from io import BytesIO
from zipfile import ZipFile

import json

import pandas as pd
import pytest

from app.extensions import db
from app.models import Task, TaskResult, TaskResultReturn
from app.services.backtest_report_query_service import (
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
        response = app.test_client().get("/api/global-preview/tasks/legacy-preview")

        assert response.status_code == 200
        body = response.get_json()
        assert body["data"]["supported"] is True
        assert "C 系列" in body["data"]["message"]


def test_global_preview_supports_google_sheet_c7_tasks(app_factory, monkeypatch):
    app = app_factory
    with app.app_context():
        _add_task("c7-preview", "google_sheet_C7", "{}")
        monkeypatch.setenv("AUTH_ENABLED", "false")
        monkeypatch.setattr(
            "app.routes.global_preview_api.build_global_preview_initial_payload",
            lambda _task_id: {"group_mode": "year", "groups": [], "default_group_key": "", "preview": {"task": {}, "summary": {}, "groups": []}},
        )

        response = app.test_client().get("/api/global-preview/tasks/c7-preview")

        assert response.status_code == 200
        assert response.get_json()["data"]["supported"] is True


def test_single_product_preview_page_redirects_anonymous(app_factory):
    """BUG-17 后页面由服务端守卫：匿名访问 302 到登录页。

    单 Token 模式下守卫由全局网关承担：页面导航（Accept: text/html）
    缺 Token 时 302 到 /login?next=...。
    """
    response = app_factory.test_client().get(
        "/global-preview/single-product",
        headers={"Accept": "text/html"},
    )

    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_single_product_preview_is_registered_with_a_page_permission():
    item = next(
        item
        for item in flatten_navigation_items(DEFAULT_NAVIGATION_MENU)
        if item["key"] == "single_product"
    )

    assert item["path"] == "/global-preview/single-product"
    assert item["permission"] == "page:global_preview:single_product"


def test_global_preview_uses_c7_a1_b1_as_parameter_header():
    assert _build_parameter_header({"A1": 7, "B1": 3}) == "7 / 3"
    assert _build_parameter_header({"xm": "7", "ml": "3"}) == "7 / 3"


def test_global_preview_exports_multiple_c7_0_3_stocks_as_zip(app_factory, monkeypatch):
    app = app_factory
    with app.app_context():
        db.session.add(Task(
            id="c7-preview-export",
            name="自定义导出名",
            task_type="backtest_training",
            status="completed",
            config='{"c7_model_version":"c7_0_3","sheet":{"title":"C7.0.3"}}',
        ))
        db.session.commit()
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

        response = app.test_client().get("/api/exports/global-previews/c7-preview-export/stocks")

        assert response.status_code == 200
        assert response.mimetype == "application/zip"
        with ZipFile(BytesIO(response.data)) as archive:
            assert archive.namelist() == ["自定义导出名_AAPL.xlsx", "自定义导出名_MSFT.xlsx"]
            entry_modified_at = datetime(*archive.getinfo("自定义导出名_AAPL.xlsx").date_time)
            assert entry_modified_at.year >= datetime.now().year - 1


def test_global_preview_stock_zip_honors_export_name(app_factory, monkeypatch):
    app = app_factory
    with app.app_context():
        db.session.add(Task(
            id="c7-preview-export-name",
            name="预览任务",
            task_type="backtest_training",
            status="completed",
            config='{"c7_model_version":"c7_0_3","sheet":{"title":"C7.0.3"}}',
        ))
        db.session.commit()
        monkeypatch.setenv("AUTH_ENABLED", "false")
        db.session.add(TaskResult(
            task_id="c7-preview-export-name", step_index=0,
            parameters='{"stock_code":"AAPL","year":"2024"}', result='{"result":{}}', success=True,
        ))
        db.session.commit()

        response = app.test_client().get(
            "/api/exports/global-previews/c7-preview-export-name/stocks?export_name=批量导出"
        )

        assert response.status_code == 200
        assert response.mimetype == "application/zip"
        content_disposition = response.headers["Content-Disposition"]
        assert 'filename="download.zip"' in content_disposition
        assert "filename*=UTF-8''%E6%89%B9%E9%87%8F%E5%AF%BC%E5%87%BA.zip" in content_disposition


def test_c7_0_3_global_preview_groups_results_by_stock_and_year(app_factory, monkeypatch):
    app = app_factory
    with app.app_context():
        monkeypatch.setattr(
            "app.services.backtest_report_query_service._extract_summary_rows",
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
            "app.services.backtest_report_query_service._extract_summary_rows",
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
            "app.services.backtest_report_query_service._extract_summary_rows",
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


def test_global_preview_upgrades_legacy_metric_aliases(app_factory, monkeypatch):
    app = app_factory
    with app.app_context():
        observed = {}

        def summary_rows(metrics, _model_name):
            observed.update(metrics)
            return "", [{
                "category": "夏普",
                "metric": "超额夏普",
                "index_value": "",
                "model_value": str(metrics.get("excess_sharpe", "")),
            }]

        monkeypatch.setattr(
            "app.services.backtest_report_query_service._extract_summary_rows",
            summary_rows,
        )
        task = Task(
            id="legacy-preview-aliases",
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
            parameters='{"stock_code":"WDC","year":"2026-2025"}',
            result=(
                '{"result":{"calculate_metrics":{' 
                '"excess_sharp":3.92,'
                '"excess_of_promissory_note":33.44,'
                '"index_sotino_ratio":[{"year":"all","sotino_ratio":8.54}],'
                '"start_sotino_ratio":[{"year":"all","sotino_ratio":83.68}]}}}'
            ),
            success=True,
        ))
        db.session.commit()

        payload = _build_global_preview_payload(task.id)

        assert observed["excess_sharpe"] == 3.92
        assert observed["excess_sortino"] == 33.44
        assert observed["index_sortino_ratio"][0]["sortino_ratio"] == 8.54
        assert observed["start_sortino_ratio"][0]["sortino_ratio"] == 83.68
        assert payload["groups"][0]["rows"][0]["values"]


def test_global_preview_recalculates_missing_legacy_metrics_from_return_series(app_factory, monkeypatch):
    # 单 Token 模式：页面/接口网关需远程校验，以免鉴权 mock 用户验证业务逻辑。
    monkeypatch.setenv("AUTH_ENABLED", "false")
    app = app_factory
    with app.app_context():
        observed = {}

        def summary_rows(metrics, _model_name):
            observed.update(metrics)
            return "", [{
                "category": "回撤",
                "metric": "年最大回测修复天数",
                "index_value": str(max(metrics["year_index_yearly_max_repair_days"].values())),
                "model_value": str(max(metrics["year_start_yearly_max_repair_days"].values())),
            }]

        monkeypatch.setattr(
            "app.services.backtest_report_query_service._extract_summary_rows",
            summary_rows,
        )
        task = Task(
            id="legacy-preview-series-fallback",
            name="C7 回测",
            task_type="google_sheet_C7",
            status="completed",
            config="{}",
        )
        db.session.add(task)
        db.session.flush()
        series = TaskResultReturn(
            task_id=task.id,
            stock_code="WDC",
            stock_name="WDC",
            start_return_date=datetime(2025, 1, 1).date(),
            end_return_date=datetime(2025, 1, 3).date(),
            return_length=3,
            stock_date=json.dumps(["2025-01-01", "2025-01-02", "2025-01-03"]),
            index_return=json.dumps([0.0, -0.02, 0.0]),
            start_return=json.dumps([0.0, -0.01, 0.01]),
        )
        db.session.add(series)
        db.session.flush()
        db.session.add(TaskResult(
            task_id=task.id,
            step_index=0,
            parameters='{"stock_code":"WDC","year":"2025"}',
            result='{"result":{"calculate_metrics":{"excess_sharp":3.92}}}',
            return_series_id=series.id,
            success=True,
        ))
        db.session.commit()

        payload = _build_global_preview_payload(task.id)
        row = next(
            item for item in payload["groups"][0]["rows"]
            if item["metric"] == "年最大回测修复天数"
        )

        assert observed["excess_sharpe"] == pytest.approx(3.92)
        assert observed["year_index_yearly_max_repair_days"]
        assert observed["year_start_yearly_max_repair_days"]
        assert row["metric"] == "年最大回测修复天数"



    app = app_factory
    with app.app_context():
        monkeypatch.setattr(
            "app.services.backtest_report_query_service._extract_summary_rows",
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
            "app.services.backtest_report_query_service._extract_summary_rows",
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
            "app.services.backtest_report_query_service._extract_summary_rows",
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


def _add_word_export_preview_task(task_id):
    """构造带一条成功收益序列结果 + 一条失败结果的单品预览任务，返回 (task, series)。"""
    task = Task(
        id=task_id,
        name="C7 回测",
        task_type="google_sheet_C7",
        status="completed",
        config='{"sheet":{"title":"C7.0.3"},"price_mode":"sp_price"}',
    )
    db.session.add(task)
    db.session.flush()
    series = TaskResultReturn(
        task_id=task.id,
        stock_code="WDC",
        stock_name="西部数据",
        start_return_date=datetime(2025, 1, 1).date(),
        end_return_date=datetime(2025, 1, 3).date(),
        return_length=3,
        stock_date=json.dumps(["2025-01-01", "2025-01-02", "2025-01-03"]),
        index_return=json.dumps([0.0, -0.02, 0.0]),
        start_return=json.dumps([0.0, -0.01, 0.01]),
    )
    db.session.add(series)
    db.session.flush()
    db.session.add(TaskResult(
        task_id=task.id,
        step_index=0,
        parameters='{"stock_code":"WDC","year":"2025"}',
        result='{"result":{}}',
        return_series_id=series.id,
        success=True,
    ))
    db.session.add(TaskResult(
        task_id=task.id,
        step_index=1,
        parameters='{"stock_code":"WDC","year":"2025"}',
        result='{"result":{}}',
        success=False,
    ))
    db.session.commit()
    return task, series


def test_global_preview_columns_carry_word_report_payload(app_factory, monkeypatch):
    """导出 Word 弹窗数据源：成功且带收益序列的列附 RPT-S 请求载荷，其余列置 None。"""
    app = app_factory
    with app.app_context():
        monkeypatch.setattr(
            "app.services.backtest_report_query_service._extract_summary_rows",
            lambda _metrics, _model: ("", []),
        )
        task, series = _add_word_export_preview_task("preview-word-payload")

        payload = _build_global_preview_payload(task.id)
        columns = payload["groups"][0]["columns"]

        success_column = columns[0]
        word_payload = success_column["word_report_payload"]
        assert success_column["return_series_id"] == series.id
        assert word_payload["report_type"] == "RPT-S"
        assert word_payload["task_id"] == task.id
        assert word_payload["return_series_id"] == series.id
        assert word_payload["products"] == [{"stock_code": "WDC.US", "product_name": "西部数据"}]
        assert word_payload["metadata"]["model_version"] == "c7.0.3"
        assert word_payload["metadata"]["price_type"] == "收盘价"
        assert columns[1]["word_report_payload"] is None


def test_single_product_word_export_uses_selected_return_series(app_factory, monkeypatch):
    """预览弹窗导出链路：RPT-S + return_series_id 精确导出指定参数的收益序列。"""
    from io import BytesIO

    app = app_factory
    with app.app_context():
        monkeypatch.setattr(
            "app.services.backtest_report_query_service._extract_summary_rows",
            lambda _metrics, _model: ("", []),
        )
        task, series = _add_word_export_preview_task("preview-word-export")

        captured = {}

        def fake_generate_word(word_payload):
            captured["payload"] = word_payload
            return "RPT-S.docx", BytesIO(b"docx")

        monkeypatch.setattr(
            "app.services.export_service.strategy_backtest_report_service.generate_word",
            fake_generate_word,
        )
        monkeypatch.setenv("AUTH_ENABLED", "false")
        response = app.test_client().post(
            "/api/exports/backtest-reports/word",
            json={
                "report_type": "RPT-S",
                "task_id": task.id,
                "return_series_id": series.id,
                "metadata": {"price_type": "开盘价", "risk_free_rate": "3.00%"},
                "runtime_params": {"risk_free_rate": 0.03},
            },
        )

        assert response.status_code == 200
        assert (
            response.mimetype
            == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        )
        payload = captured["payload"]
        assert payload.report_type == "RPT-S"
        assert payload.task_id == task.id
        assert payload.return_series_id == series.id
        # products 未传时为空列表，报告文件名/权重表回落单品默认展示。
        assert payload.products == []
        # 弹窗选项经 export_service 覆盖任务默认：价格类型改展示行，无风险利率进入重算。
        assert payload.metadata["price_type"] == "开盘价"
        assert payload.metadata["risk_free_rate"] == "3.00%"
        assert payload.runtime_params["risk_free_rate"] == 0.03



def test_single_product_preview_page_has_word_export_modal(app_factory, monkeypatch):
    """导出Word 弹窗随页面下发：结果勾选列表 + 全选/清空 + 确认按钮。"""
    monkeypatch.setenv("AUTH_ENABLED", "false")
    response = app_factory.test_client().get("/global-preview/single-product")

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert 'id="wordExportModal"' in body
    assert 'id="wordExportResultList"' in body
    assert 'id="wordExportSelectAllBtn"' in body
    assert 'id="confirmWordExportBtn"' in body

import json
from datetime import datetime
from io import BytesIO
from zipfile import ZipFile

import pytest
from openpyxl import Workbook

from app.extensions import db
from app.models import (
    BacktestProductResultCache,
    BacktestSheetRunLock,
    Permission,
    Task,
    TaskResult,
    TaskResultReturn,
)
from app.services.backtest_training_api_service import _build_zip_member_name
from app.services.export_service import GeneratedFile, export_service
from app.routes.backtest_multi_product import (
    _build_excel_download_name,
    _build_global_preview_workbook,
)
from app.services.backtest_multi_product_service import (
    BACKTEST_MULTI_PRODUCT_TASK_TYPE,
    BacktestMultiProductService,
    _GLOBAL_PREVIEW_CACHE,
    _build_portfolio_return_date,
    _cumulative_returns_to_daily_returns,
    _daily_returns_to_cumulative_returns,
    _derive_metrics,
    _fmt_value,
    _weight_return_date,
    build_multi_product_global_preview_payload,
    build_multi_product_global_preview_word_payload,
    normalize_multi_product_config,
)
from app.services.task.facade import TaskManager
from app.services.task.runtime_view import TaskRuntimeViewService
from app.utils.return_series import build_return_series_fields


def _base_product(index, ratio="50"):
    return {
        "product_index": index,
        "product_name": f"产品{index + 1}",
        "stock_code": f"TEST{index + 1}",
        "market_type": "cn",
        "price_mode": "sp_price",
        "ratio": ratio,
        "sheet": {
            "spreadsheet_id": f"sheet-{index + 1}",
            "sheet_name": "data",
            "title": "C3 model",
        },
        "parameters": [
            ["0.0350%", "1", "2", "3", "4", "5", "6", "7"],
            ["0.0350%", "8", "9", "10", "11", "12", "13", "14"],
        ],
    }


def test_daily_return_weighting_rebuilds_cumulative_returns_by_default():
    first_product_returns = [
        {"date": "2026-01-01", "index_return": 0.1, "start_return": 0.1},
        {"date": "2026-01-02", "index_return": 0.21, "start_return": 0.21},
    ]
    second_product_returns = [
        {"date": "2026-01-01", "index_return": 0.2, "start_return": 0.2},
        {"date": "2026-01-02", "index_return": 0.44, "start_return": 0.44},
    ]
    products = [
        {"product_index": 0, "ratio": "50"},
        {"product_index": 1, "ratio": "50"},
    ]

    daily_returns = _cumulative_returns_to_daily_returns(first_product_returns)
    restored_returns = _daily_returns_to_cumulative_returns(daily_returns)
    weighted_product = _weight_return_date(first_product_returns, "50", False)
    portfolio_returns = _build_portfolio_return_date({
        0: {"return_date": first_product_returns},
        1: {"return_date": second_product_returns},
    }, products)
    # 旧版累计加权算法已停用：传入 legacy 标志也按日收益加权后复利计算。
    legacy_flag_portfolio_returns = _build_portfolio_return_date({
        0: {"return_date": first_product_returns},
        1: {"return_date": second_product_returns},
    }, products, True)

    assert daily_returns[1]["start_return"] == pytest.approx(0.1)
    assert restored_returns[-1]["start_return"] == pytest.approx(0.21)
    assert weighted_product[-1]["start_return"] == pytest.approx(0.1025)
    assert portfolio_returns[-1]["start_return"] == pytest.approx(0.3225)
    assert legacy_flag_portfolio_returns[-1]["start_return"] == pytest.approx(0.3225)


def test_normalize_multi_product_config_allows_ratio_total_not_equal_100():
    config = {
        "start_date": "2024-01-01",
        "end_date": "2024-12-31",
        "products": [_base_product(0, "60"), _base_product(1, "30")],
    }

    normalized = normalize_multi_product_config(config)

    assert [product["ratio"] for product in normalized["products"]] == ["60", "30"]
    assert [product["price_mode"] for product in normalized["products"]] == ["sp_price", "sp_price"]
    assert normalized["weighting_mode"] == "daily_compound"


def test_normalize_multi_product_config_ignores_legacy_weighting_flag():
    """旧版累计加权算法已停用，历史布尔配置不再改变组合算法。"""
    config = {
        "start_date": "2024-01-01",
        "end_date": "2024-12-31",
        "use_legacy_cumulative_return_weighting": True,
        "products": [_base_product(0), _base_product(1)],
    }

    normalized = normalize_multi_product_config(config)

    assert normalized["weighting_mode"] == "daily_compound"


def test_normalize_multi_product_config_defaults_to_vwap_price():
    product_1 = _base_product(0, "60")
    product_2 = _base_product(1, "30")
    product_1.pop("price_mode")
    product_2.pop("price_mode")
    config = {
        "start_date": "2024-01-01",
        "end_date": "2024-12-31",
        "products": [product_1, product_2],
    }

    normalized = normalize_multi_product_config(config)

    assert [product["price_mode"] for product in normalized["products"]] == ["vwap_price", "vwap_price"]


def test_normalize_multi_product_config_keeps_per_product_price_mode():
    config = {
        "start_date": "2024-01-01",
        "end_date": "2024-12-31",
        "products": [
            _base_product(0, "60") | {"price_mode": "kp_price"},
            _base_product(1, "30") | {"price_mode": "vwap_price"},
        ],
    }

    normalized = normalize_multi_product_config(config)

    assert [product["price_mode"] for product in normalized["products"]] == ["kp_price", "vwap_price"]


def test_normalize_multi_product_config_validates_parameter_alignment():
    product_1 = _base_product(0, "50")
    product_2 = _base_product(1, "50")
    product_2["parameters"] = product_2["parameters"][:1]
    config = {
        "start_date": "2024-01-01",
        "end_date": "2024-12-31",
        "products": [product_1, product_2],
    }

    with pytest.raises(ValueError, match="参数行数必须一致"):
        normalize_multi_product_config(config)


def test_build_excel_download_name_uses_task_name_only():
    assert _build_excel_download_name("test-2", "task-id") == "test-2.xlsx"
    assert _build_excel_download_name("任务:多品/回测", "task-id") == "任务_多品_回测.xlsx"


def _add_return_series(task_id, dates, index_returns, start_returns, stock_code="UNKNOWN", stock_name="未知股票"):
    """按拆列后的 TaskResultReturn 结构写入收益序列。"""
    rows = [
        {"stock_date": date_value, "index_return": index_value, "start_return": start_value}
        for date_value, index_value, start_value in zip(dates, index_returns, start_returns)
    ]
    fields = build_return_series_fields(rows, stock_code=stock_code, stock_name=stock_name)
    series = TaskResultReturn(task_id=task_id, **fields)
    db.session.add(series)
    db.session.flush()
    return series


def _add_multi_product_task(task_id, name="多品回测", status="completed", task_type=BACKTEST_MULTI_PRODUCT_TASK_TYPE):
    db.session.add(Task(
        id=task_id,
        name=name,
        task_type=task_type,
        status=status,
        config=json.dumps({
            "start_date": "2024-01-01",
            "end_date": "2024-12-31",
            "products": [_base_product(0, "100")],
        }, ensure_ascii=False),
    ))
    db.session.commit()


def test_multi_product_batch_export_global_preview_returns_zip(app_factory, monkeypatch):
    app = app_factory
    with app.app_context():
        _add_multi_product_task("multi-batch-1", name="多品:组合/1")
        monkeypatch.setenv("AUTH_ENABLED", "false")

        def fake_batch_export(task_ids):
            assert task_ids == ["multi-batch-1"]
            workbook = Workbook()
            workbook.active["A1"] = "ok"
            buffer = BytesIO()
            with ZipFile(buffer, "w") as archive:
                archive.writestr("多品_组合_1_global_preview.xlsx", "fake-excel-bytes")
            buffer.seek(0)
            return GeneratedFile(
                filename="多品回测_全局预览.zip",
                mimetype="application/zip",
                buffer=buffer,
                file_size=buffer.getbuffer().nbytes,
            )

        monkeypatch.setattr(
            "app.services.export_service.export_service.export_global_preview_batch",
            fake_batch_export,
        )
        response = app.test_client().post(
            "/api/exports/global-previews/batch",
            json={"task_ids": ["multi-batch-1"]},
        )

        assert response.status_code == 200
        assert response.mimetype == "application/zip"
        with ZipFile(BytesIO(response.data)) as archive:
            assert archive.namelist() == ["多品_组合_1_global_preview.xlsx"]


def test_multi_product_zip_member_name_sanitizes_task_name():
    used_names: set[str] = set()
    assert (
        _build_zip_member_name("多品:组合/1", "fallback-id", used_names)
        == "多品_组合_1_global_preview.xlsx"
    )
    assert _build_zip_member_name("多品:组合/1", "fallback-id", used_names) != (
        "多品_组合_1_global_preview.xlsx"
    )
    assert _build_zip_member_name("   ", "fallback-id", set()) == "fallback-id_global_preview.xlsx"


def test_multi_product_batch_export_global_preview_rejects_empty_selection(app_factory, monkeypatch):
    app = app_factory
    with app.app_context():
        monkeypatch.setenv("AUTH_ENABLED", "false")
        response = app.test_client().post(
            "/api/exports/global-previews/batch",
            json={"task_ids": []},
        )

        assert response.status_code == 400
        assert response.get_json()["message"] == "请选择至少一个任务"


def test_multi_product_batch_export_global_preview_rejects_unfinished_task(app_factory, monkeypatch):
    app = app_factory
    with app.app_context():
        _add_multi_product_task("multi-running", status="running")
        monkeypatch.setenv("AUTH_ENABLED", "false")
        response = app.test_client().post(
            "/api/exports/global-previews/batch",
            json={"task_ids": ["multi-running"]},
        )

        assert response.status_code == 400
        assert "尚未完成" in response.get_json()["message"]


def test_multi_product_batch_export_global_preview_rejects_too_many_tasks(app_factory, monkeypatch):
    app = app_factory
    with app.app_context():
        monkeypatch.setenv("AUTH_ENABLED", "false")
        response = app.test_client().post(
            "/api/exports/global-previews/batch",
            json={"task_ids": [f"task-{index}" for index in range(11)]},
        )

        assert response.status_code == 400
        assert "最多支持 10 个任务" in response.get_json()["message"]


def test_multi_product_kline_source_requires_same_stock_and_signature():
    service = BacktestMultiProductService({}, "task-id")
    kline = [
        {"stock_date": "2024-01-01", "stock_val": 1},
        {"stock_date": "2024-01-02", "stock_val": 2},
        {"stock_date": "2024-01-03", "stock_val": 3},
    ]
    signature = service._build_kline_signature(kline)
    current = {
        "Kline_key": "2024-01-01~2024-01-03",
        "stock_code": "QQQ",
        "kline_signature": signature,
    }

    assert service._is_same_kline_source(current, dict(current))
    assert not service._is_same_kline_source(current, {**current, "stock_code": "GOOGL"})
    assert not service._is_same_kline_source(
        current,
        {**current, "kline_signature": {**signature, "last": {"stock_date": "2024-01-03", "stock_val": 9}}},
    )


def _make_backtest_task(task_id, *, status, spreadsheet_id, current_step=2):
    return Task(
        id=task_id,
        name=task_id,
        task_type=BACKTEST_MULTI_PRODUCT_TASK_TYPE,
        status=status,
        current_step=current_step,
        config=json.dumps({
            "start_date": "2024-01-01",
            "end_date": "2024-12-31",
            "products": [_base_product(0, "50") | {
                "sheet": {
                    "spreadsheet_id": spreadsheet_id,
                    "sheet_name": "data",
                    "title": "C3 model",
                },
            }, _base_product(1, "50") | {
                "sheet": {
                    "spreadsheet_id": "other-sheet",
                    "sheet_name": "data",
                    "title": "C3 model",
                },
            }],
        }, ensure_ascii=False),
        created_at=datetime.now(),
    )


def test_restart_checkpoint_queues_pending_without_clearing_results(app_factory):
    app = app_factory
    with app.app_context():
        running = _make_backtest_task("running-task", status="running", spreadsheet_id="shared-sheet")
        target = _make_backtest_task("target-task", status="error", spreadsheet_id="shared-sheet", current_step=3)
        db.session.add_all([running, target])
        db.session.add(TaskResult(task_id=target.id, step_index=0, parameters="{}", result="{}", success=True))
        db.session.commit()

        manager = TaskManager()
        target_id = target.id
        result = manager.restart_task(target_id, resume_from_checkpoint=True)
        target = db.session.get(Task, target_id)

        assert result["status"] == "success"
        assert result["queued"] is True
        assert target.status == "pending"
        assert target.current_step == 3
        assert TaskResult.query.filter_by(task_id=target.id).count() == 1


def test_restart_from_scratch_queues_pending_and_clears_results(app_factory):
    app = app_factory
    with app.app_context():
        running = _make_backtest_task("running-task", status="running", spreadsheet_id="shared-sheet")
        target = _make_backtest_task("target-task", status="error", spreadsheet_id="shared-sheet", current_step=3)
        db.session.add_all([running, target])
        db.session.add(TaskResult(task_id=target.id, step_index=0, parameters="{}", result="{}", success=True))
        db.session.add(TaskResultReturn(task_id=target.id, stock_date="2024-01-01", index_return=1, start_return=1))
        db.session.commit()

        manager = TaskManager()
        target_id = target.id
        result = manager.restart_task(target_id, resume_from_checkpoint=False)
        target = db.session.get(Task, target_id)

        assert result["status"] == "success"
        assert result["queued"] is True
        assert target.status == "pending"
        assert target.current_step == 0
        assert TaskResult.query.filter_by(task_id=target.id).count() == 0
        assert TaskResultReturn.query.filter_by(task_id=target.id).count() == 0


def test_runtime_view_reads_return_chart_from_returns_json(app_factory):
    app = app_factory
    with app.app_context():
        task = Task(
            id="return-json-task",
            name="return-json-task",
            task_type="backtest_training",
            status="completed",
            created_at=datetime.now(),
        )
        db.session.add(task)
        return_series = _add_return_series(task.id, ["2024-01-01", "2024-01-02"], [0.1, 0.2], [0.3, 0.4])
        db.session.add(return_series)
        db.session.flush()
        db.session.add(TaskResult(
            task_id=task.id,
            step_index=0,
            parameters="{}",
            result="{}",
            success=True,
            return_series_id=return_series.id,
        ))
        db.session.commit()

        summary = TaskRuntimeViewService(TaskManager()).build_result_summary(task.id)

        assert summary["return_chart"] == [
            {"date": "2024-01-01", "index_return": 0.1, "strategy_return": 0.3},
            {"date": "2024-01-02", "index_return": 0.2, "strategy_return": 0.4},
        ]


def test_multi_product_result_detail_includes_daily_returns_from_return_series(app_factory, monkeypatch):
    app = app_factory
    with app.app_context():
        task = Task(
            id="result-daily-returns-task",
            name="result-daily-returns-task",
            task_type=BACKTEST_MULTI_PRODUCT_TASK_TYPE,
            status="completed",
            created_at=datetime.now(),
        )
        db.session.add(task)
        return_series = _add_return_series(task.id, ["2024-01-01", "2024-01-02"], [0.11, 0.22], [0.33, 0.44])
        db.session.add(return_series)
        db.session.flush()
        task_result = TaskResult(
            task_id=task.id,
            step_index=0,
            parameters="{}",
            result=json.dumps({
                "sheet__title": {
                    "calculate_metrics": {
                        "excess_returns": []
                    },
                    "D2": "1",
                }
            }),
            success=True,
            return_series_id=return_series.id,
        )
        db.session.add(task_result)
        db.session.commit()

        monkeypatch.setenv("AUTH_ENABLED", "false")
        client = app.test_client()
        resp = client.get(f"/backtest-multi-product/api/task-result/{task_result.id}")

        assert resp.status_code == 200
        payload = resp.get_json()
        assert payload["status"] == "success"
        assert payload["result"]["daily_returns"] == {
            "dates": ["2024-01-01", "2024-01-02"],
            "index_returns": [0.11, 0.22],
            "start_returns": [0.33, 0.44],
        }


def test_multi_product_c7_result_detail_normalizes_sheet_units(app_factory, monkeypatch):
    app = app_factory
    with app.app_context():
        task = Task(
            id="multi-c7-result-units",
            name="multi-c7-result-units",
            task_type=BACKTEST_MULTI_PRODUCT_TASK_TYPE,
            status="completed",
            config=json.dumps({"products": [{"sheet": {"title": "C7 model"}}]}),
            created_at=datetime.now(),
        )
        db.session.add(task)
        task_result = TaskResult(
            task_id=task.id,
            step_index=0,
            parameters=json.dumps({"product_index": 0}),
            result=json.dumps({"sheet__title": {
                "calculate_metrics": {"excess_returns": []},
                "D10": "-0.14",
                "D18": "0.01",
                "D22": "122.95%",
            }}),
            success=True,
        )
        db.session.add(task_result)
        db.session.commit()

        monkeypatch.setenv("AUTH_ENABLED", "false")
        response = app.test_client().get(
            f"/backtest-multi-product/api/task-result/{task_result.id}"
        )

        assert response.status_code == 200
        sheet_result = response.get_json()["result"]["sheet_result"]
        assert sheet_result["D10"] == "-14.00%"
        assert sheet_result["D18"] == "1.00%"
        assert sheet_result["D22"] == 1.2295


def test_multi_product_execution_runs_all_parameters_per_product_first(app_factory, monkeypatch):
    app = app_factory
    with app.app_context():
        config = normalize_multi_product_config({
            "start_date": "2024-01-01",
            "end_date": "2024-12-31",
            "products": [_base_product(0, "50"), _base_product(1, "50")],
        })
        task = Task(
            id="execution-order-task",
            name="execution-order-task",
            task_type=BACKTEST_MULTI_PRODUCT_TASK_TYPE,
            status="running",
            config=json.dumps(config, ensure_ascii=False),
            created_at=datetime.now(),
        )
        db.session.add(task)
        db.session.commit()

        task = db.session.get(Task, "execution-order-task")
        service = BacktestMultiProductService({}, task.id)
        call_order = []
        monkeypatch.setattr(service, "_resolve_resume_start_index", lambda _task: 0)
        monkeypatch.setattr(service, "_init_google_sheet", lambda _config: None)
        monkeypatch.setattr(service, "_build_product_kline", lambda product, _config: {
            "kline_key": "2024-01-01~2024-12-31",
            "kline": [
                {"stock_date": "2024-01-01", "stock_val": 1},
                {"stock_date": "2024-12-31", "stock_val": 2},
            ],
            "kline_signature": {"stock_code": product["stock_code"]},
            "column_A_length": 22,
        })

        def fake_execute(_column_a_length, combination, cache_parameters, _config_data, _kline_data_map):
            call_order.append((combination["product_index"], combination["parameter_group_index"]))
            cache_parameters["combination"] = combination
            return True, {}, []

        monkeypatch.setattr(service, "_execute_parameter_combination", fake_execute)

        assert service._execute_products(task, config) == "completed"
        assert call_order == [(0, 0), (0, 1), (1, 0), (1, 1)]


def test_multi_product_resets_kline_cache_once_per_product(app_factory, monkeypatch):
    app = app_factory
    with app.app_context():
        shared_sheet = {
            "spreadsheet_id": "shared-sheet",
            "sheet_name": "data",
            "title": "C3 model",
        }
        config = normalize_multi_product_config({
            "start_date": "2024-01-01",
            "end_date": "2024-12-31",
            "products": [
                _base_product(0, "50") | {"stock_code": "SAME", "sheet": shared_sheet},
                _base_product(1, "50") | {"stock_code": "SAME", "sheet": shared_sheet},
            ],
        })
        task = Task(
            id="product-cache-reset-task",
            name="product-cache-reset-task",
            task_type=BACKTEST_MULTI_PRODUCT_TASK_TYPE,
            status="running",
            config=json.dumps(config, ensure_ascii=False),
            created_at=datetime.now(),
        )
        db.session.add(task)
        db.session.commit()

        task = db.session.get(Task, "product-cache-reset-task")
        service = BacktestMultiProductService({}, task.id)
        cache_empty_by_step = []
        monkeypatch.setattr(service, "_resolve_resume_start_index", lambda _task: 0)
        monkeypatch.setattr(service, "_init_google_sheet", lambda _config: None)
        monkeypatch.setattr(service, "_build_product_kline", lambda product, _config: {
            "kline_key": "2024-01-01~2024-12-31",
            "kline": [
                {"stock_date": "2024-01-01", "stock_val": 1},
                {"stock_date": "2024-12-31", "stock_val": 2},
            ],
            "kline_signature": {"same": "signature"},
            "column_A_length": 22,
        })

        def fake_execute(_column_a_length, combination, cache_parameters, _config_data, _kline_data_map):
            cache_empty_by_step.append((
                combination["product_index"],
                combination["parameter_group_index"],
                not bool(cache_parameters.get("combination")),
            ))
            cache_parameters["combination"] = combination
            return True, {}, []

        monkeypatch.setattr(service, "_execute_parameter_combination", fake_execute)

        assert service._execute_products(task, config) == "completed"
        assert cache_empty_by_step == [
            (0, 0, True),
            (0, 1, False),
            (1, 0, True),
            (1, 1, False),
        ]


def test_backtest_sheet_run_lock_uses_database_rows(app_factory):
    app = app_factory
    with app.app_context():
        manager = TaskManager()

        acquired, locked_task_id, acquired_ids = manager._acquire_backtest_sheet_run_locks(
            ["shared-sheet"],
            "task-1",
            task_type=BACKTEST_MULTI_PRODUCT_TASK_TYPE,
        )

        assert acquired is True
        assert locked_task_id is None
        assert acquired_ids == ["shared-sheet"]
        assert BacktestSheetRunLock.query.filter_by(spreadsheet_id="shared-sheet").count() == 1

        acquired, locked_task_id, acquired_ids = manager._acquire_backtest_sheet_run_locks(
            ["shared-sheet"],
            "task-2",
            task_type=BACKTEST_MULTI_PRODUCT_TASK_TYPE,
        )

        assert acquired is False
        assert locked_task_id == "task-1"
        assert acquired_ids == []

        manager._release_backtest_sheet_run_reservation("shared-sheet", "task-2")
        assert BacktestSheetRunLock.query.filter_by(spreadsheet_id="shared-sheet").count() == 1

        manager._release_backtest_sheet_run_reservation("shared-sheet", "task-1")
        assert BacktestSheetRunLock.query.filter_by(spreadsheet_id="shared-sheet").count() == 0


def test_fixed_product_cache_key_ignores_ratio_and_changes_for_inputs(app_factory):
    app = app_factory
    with app.app_context():
        config = normalize_multi_product_config({
            "start_date": "2024-01-01",
            "end_date": "2024-12-31",
            "fixed_product_batch_id": "batch-1",
            "products": [
                _base_product(0, "25") | {"is_fixed": True},
                _base_product(1, "75"),
            ],
        })
        service = BacktestMultiProductService({}, "cache-key-task")
        product = config["products"][0]
        parameter = product["parameters"][0]

        first_key = service._build_fixed_product_cache_key(config, product, parameter)
        ratio_changed_key = service._build_fixed_product_cache_key(
            config,
            {**product, "ratio": "99"},
            parameter,
        )
        parameter_changed_key = service._build_fixed_product_cache_key(
            config,
            product,
            product["parameters"][1],
        )
        date_changed_key = service._build_fixed_product_cache_key(
            {**config, "end_date": "2025-12-31"},
            product,
            parameter,
        )

        assert first_key == ratio_changed_key
        assert first_key != parameter_changed_key
        assert first_key != date_changed_key


def test_fixed_product_cache_hit_writes_current_task_result_without_execute(app_factory, monkeypatch):
    app = app_factory
    with app.app_context():
        config = normalize_multi_product_config({
            "start_date": "2024-01-01",
            "end_date": "2024-12-31",
            "fixed_product_batch_id": "batch-1",
            "products": [
                _base_product(0, "25") | {"is_fixed": True},
                _base_product(1, "75"),
            ],
        })
        task = Task(
            id="fixed-cache-hit-task",
            name="fixed-cache-hit-task",
            task_type=BACKTEST_MULTI_PRODUCT_TASK_TYPE,
            status="running",
            config=json.dumps(config, ensure_ascii=False),
            created_at=datetime.now(),
        )
        db.session.add(task)
        db.session.commit()

        task_id = task.id
        service = BacktestMultiProductService({}, task.id)
        fixed_product = config["products"][0]
        for group_index, parameter in enumerate(fixed_product["parameters"]):
            cache_key = service._build_fixed_product_cache_key(config, fixed_product, parameter)
            db.session.add(BacktestProductResultCache(
                batch_id="batch-1",
                cache_key=cache_key,
                result_json=json.dumps(_task_result_payload(0.1 + group_index, 0.2 + group_index)),
                returns_json=json.dumps({
                    "dates": ["2024-01-01"],
                    "index_returns": [0.1 + group_index],
                    "start_returns": [0.2 + group_index],
                }),
                source_task_id="source-task",
                source_step_index=group_index,
            ))
        db.session.commit()

        execute_calls = []
        monkeypatch.setattr(service, "_resolve_resume_start_index", lambda _task: 0)
        monkeypatch.setattr(service, "_init_google_sheet", lambda _config: None)
        monkeypatch.setattr(
            "app.services.backtest_multi_product_service.xpl_analyzer.get_calculate_metrics_v1",
            lambda _return_date: {"weighted_metric": 1},
        )
        monkeypatch.setattr(service, "_build_product_kline", lambda product, _config: {
            "kline_key": "2024-01-01~2024-12-31",
            "kline": [
                {"stock_date": "2024-01-01", "stock_val": 1},
                {"stock_date": "2024-12-31", "stock_val": 2},
            ],
            "kline_signature": {"stock_code": product["stock_code"]},
            "column_A_length": 22,
        })

        def fake_execute(_column_a_length, combination, cache_parameters, _config_data, _kline_data_map):
            execute_calls.append((combination["product_index"], combination["parameter_group_index"]))
            cache_parameters["combination"] = combination
            return True, _task_result_payload(0.7, 0.9), [{
                "date": "2024-01-01",
                "index_return": 0.7,
                "start_return": 0.9,
            }]

        monkeypatch.setattr(service, "_execute_parameter_combination", fake_execute)

        assert service._execute_products(task, config) == "completed"
        assert execute_calls == [(1, 0), (1, 1)]

        fixed_results = [
            result.to_dict()
            for result in TaskResult.query.filter_by(task_id=task_id).order_by(TaskResult.step_index.asc()).all()
            if result.to_dict()["parameters"]["product_index"] == 0
        ]
        assert len(fixed_results) == 2
        assert fixed_results[0]["parameters"]["ratio"] == "25"
        assert fixed_results[0]["return_series_id"] is not None
        assert fixed_results[0]["result"]["sheet__title"]["weighted_calculate_metrics"]


def test_fixed_product_cache_hit_advances_progress_when_all_steps_cached(app_factory, monkeypatch):
    app = app_factory
    with app.app_context():
        config = normalize_multi_product_config({
            "start_date": "2024-01-01",
            "end_date": "2024-12-31",
            "fixed_product_batch_id": "batch-progress",
            "products": [
                _base_product(0, "40") | {"is_fixed": True},
                _base_product(1, "60") | {"is_fixed": True},
            ],
        })
        task = Task(
            id="fixed-cache-progress-task",
            name="fixed-cache-progress-task",
            task_type=BACKTEST_MULTI_PRODUCT_TASK_TYPE,
            status="running",
            config=json.dumps(config, ensure_ascii=False),
            created_at=datetime.now(),
        )
        db.session.add(task)
        db.session.commit()

        task_id = task.id
        service = BacktestMultiProductService({}, task_id)
        for product in config["products"]:
            for group_index, parameter in enumerate(product["parameters"]):
                cache_key = service._build_fixed_product_cache_key(config, product, parameter)
                db.session.add(BacktestProductResultCache(
                    batch_id="batch-progress",
                    cache_key=cache_key,
                    result_json=json.dumps(_task_result_payload(0.1 + group_index, 0.2 + group_index)),
                    returns_json=json.dumps({
                        "dates": ["2024-01-01"],
                        "index_returns": [0.1 + group_index],
                        "start_returns": [0.2 + group_index],
                    }),
                    source_task_id="source-task",
                    source_step_index=group_index,
                ))
        db.session.commit()

        monkeypatch.setattr(service, "_resolve_resume_start_index", lambda _task: 0)
        monkeypatch.setattr(
            service,
            "_init_google_sheet",
            lambda _config: pytest.fail("cached fixed products should not initialize Google Sheet"),
        )
        monkeypatch.setattr(
            service,
            "_execute_parameter_combination",
            lambda *_args, **_kwargs: pytest.fail("cached fixed products should not execute combinations"),
        )
        monkeypatch.setattr(
            "app.services.backtest_multi_product_service.xpl_analyzer.get_calculate_metrics_v1",
            lambda _return_date: {"weighted_metric": 1},
        )

        assert service._execute_products(task, config) == "completed"

        progress_task = db.session.get(Task, task_id)
        assert progress_task.current_step == progress_task.total_steps == 4
        assert TaskResult.query.filter_by(task_id=task_id).count() == 4


def test_lock_spreadsheet_ids_skip_cached_fixed_products(app_factory):
    app = app_factory
    with app.app_context():
        config = normalize_multi_product_config({
            "start_date": "2024-01-01",
            "end_date": "2024-12-31",
            "fixed_product_batch_id": "batch-1",
            "products": [
                _base_product(0, "25") | {"is_fixed": True},
                _base_product(1, "75"),
            ],
        })
        service = BacktestMultiProductService({}, "lock-cache-task")
        fixed_product = config["products"][0]
        for group_index, parameter in enumerate(fixed_product["parameters"]):
            cache_key = service._build_fixed_product_cache_key(config, fixed_product, parameter)
            db.session.add(BacktestProductResultCache(
                batch_id="batch-1",
                cache_key=cache_key,
                result_json=json.dumps(_task_result_payload(0.1 + group_index, 0.2 + group_index)),
                returns_json=json.dumps({"dates": [], "index_returns": [], "start_returns": []}),
                source_task_id="source-task",
                source_step_index=group_index,
            ))
        db.session.commit()

        manager = TaskManager()

        assert manager._extract_backtest_spreadsheet_ids_to_lock(
            BACKTEST_MULTI_PRODUCT_TASK_TYPE,
            config,
        ) == ["sheet-2"]


def _task_result_payload(index_return, start_return):
    return {
        "sheet__title": {
            "calculate_metrics": {
                "excess_returns": [{
                    "year": "all",
                    "index_annualized_return": index_return,
                    "start_annualized_return": start_return,
                    "annualized_return_diff": start_return - index_return,
                }],
                "index_profit_annual": 1,
                "start_profit_annual": 1,
                "index_profit_monthly": [{"year": "all", "profit_monthly_percentage": 1}],
                "start_profit_monthly": [{"year": "all", "profit_monthly_percentage": 1}],
                "index_sharpe_ratios": {"all": {"avg_monthly_return": index_return, "sharpe_ratio": 2}},
                "start_sharpe_ratios": {"all": {"avg_monthly_return": start_return, "sharpe_ratio": 3}},
            }
        }
    }


def _task_result_payload_with_year_drawdowns():
    return {
        "sheet__title": {
            "calculate_metrics": {
                "excess_returns": [
                    {
                        "year": "2024",
                        "annualized_return_diff": 0.08,
                    },
                    {
                        "year": "all",
                        "index_annualized_return": 0.10,
                        "start_annualized_return": 0.18,
                        "annualized_return_diff": 0.08,
                    },
                ],
                "index_maximum_drawdown": {
                    "year_maximum_drawdown": [
                        {"year": 2024, "drawdown": 0.10},
                    ],
                },
                "start_maximum_drawdown": {
                    "year_maximum_drawdown": [
                        {"year": "2024", "drawdown": 0.06},
                    ],
                    "total_maximum_drawdown": {"drawdown": 0.06},
                },
                "excess_drawdown_winning_rate": 0.75,
            }
        }
    }


def _task_result_payload_with_returns(index_return, start_return, returns):
    payload = _task_result_payload(index_return, start_return)
    payload["sheet__title"]["return_date"] = returns
    return payload


def _task_result_payload_with_returns_and_weighted(index_return, start_return, weighted_start, returns):
    payload = _task_result_payload_with_returns(index_return, start_return, returns)
    payload["sheet__title"]["weighted_calculate_metrics"] = {
        "excess_returns": [{
            "year": "all",
            "index_annualized_return": weighted_start,
            "start_annualized_return": weighted_start,
            "annualized_return_diff": 0,
        }],
        "index_profit_annual": 1,
        "start_profit_annual": 1,
        "index_profit_monthly": [{"year": "all", "profit_monthly_percentage": 1}],
        "start_profit_monthly": [{"year": "all", "profit_monthly_percentage": 1}],
        "index_sharpe_ratios": {"all": {"avg_monthly_return": weighted_start, "sharpe_ratio": weighted_start}},
        "start_sharpe_ratios": {"all": {"avg_monthly_return": weighted_start, "sharpe_ratio": weighted_start}},
    }
    return payload


def _task_result_payload_with_metadata(index_return, start_return):
    return {
        "return_series_id": 123,
        "sheet__title": _task_result_payload(index_return, start_return)["sheet__title"],
    }


def test_build_multi_product_global_preview_payload_combines_returns_before_metrics(app_factory, monkeypatch):
    app = app_factory
    captured_returns = []

    def fake_metrics(return_date):
        captured_returns.append(return_date)
        total_start = sum(item["start_return"] for item in return_date)
        total_index = sum(item["index_return"] for item in return_date)
        return {
            "excess_returns": [{
                "year": "all",
                "index_annualized_return": total_index,
                "start_annualized_return": total_start,
                "annualized_return_diff": total_start - total_index,
            }],
            "index_profit_annual": 1,
            "start_profit_annual": 1,
            "index_profit_monthly": [{"year": "all", "profit_monthly_percentage": 1}],
            "start_profit_monthly": [{"year": "all", "profit_monthly_percentage": 1}],
            "index_sharpe_ratios": {"all": {"avg_monthly_return": total_index, "sharpe_ratio": total_index}},
            "start_sharpe_ratios": {"all": {"avg_monthly_return": total_start, "sharpe_ratio": total_start}},
        }

    monkeypatch.setattr(
        "app.services.backtest_multi_product_service.xpl_analyzer.get_calculate_metrics_v1",
        fake_metrics,
    )

    with app.app_context():
        config = normalize_multi_product_config({
            "start_date": "2024-01-01",
            "end_date": "2024-12-31",
            "use_legacy_cumulative_return_weighting": True,
            "products": [_base_product(0, "25"), _base_product(1, "75")],
        })
        task = Task(
            id="multi-task",
            name="多品测试",
            task_type=BACKTEST_MULTI_PRODUCT_TASK_TYPE,
            status="completed",
            config=json.dumps(config, ensure_ascii=False),
            created_at=datetime.now(),
        )
        db.session.add(task)
        db.session.add(TaskResult(
            task_id=task.id,
            step_index=0,
            parameters=json.dumps({
                "product_index": 0,
                "product_name": "产品1",
                "stock_code": "TEST1",
                "ratio": "25",
                "parameter_group_index": 0,
                "parameter": config["products"][0]["parameters"][0],
            }, ensure_ascii=False),
            result=json.dumps(_task_result_payload_with_returns(0.10, 0.20, [
                {"date": "2024-01-01", "index_return": 1, "start_return": 2},
                {"date": "2024-01-02", "index_return": 3, "start_return": 4},
            ])),
            success=True,
        ))
        db.session.add(TaskResult(
            task_id=task.id,
            step_index=1,
            parameters=json.dumps({
                "product_index": 1,
                "product_name": "产品2",
                "stock_code": "TEST2",
                "ratio": "75",
                "parameter_group_index": 0,
                "parameter": config["products"][1]["parameters"][0],
            }, ensure_ascii=False),
            result=json.dumps(_task_result_payload_with_returns(0.20, 0.40, [
                {"date": "2024-01-01", "index_return": 10, "start_return": 20},
                {"date": "2024-01-02", "index_return": 30, "start_return": 40},
            ])),
            success=True,
        ))
        first_series = _add_return_series(task.id, ["2024-01-01", "2024-01-02"], [1, 3], [2, 4])
        second_series = _add_return_series(task.id, ["2024-01-01", "2024-01-02"], [10, 30], [20, 40])
        db.session.add_all([first_series, second_series])
        db.session.flush()
        db.session.query(TaskResult).filter_by(task_id=task.id, step_index=0).one().return_series_id = first_series.id
        db.session.query(TaskResult).filter_by(task_id=task.id, step_index=1).one().return_series_id = second_series.id
        db.session.commit()

        payload = build_multi_product_global_preview_payload(task.id)

        assert payload["summary"]["product_count"] == 2
        row = payload["groups"][0]["rows"][0]
        assert row["metric"] == "年化收益"
        assert row["product_values"][0]["weighted_result_value"] == "125.00%"
        assert row["product_values"][1]["weighted_result_value"] == "4142.86%"
        assert row["weighted_index_value"] == "2961.93%"
        assert row["weighted_result_value"] == "4553.57%"
        assert captured_returns[0] == [
            {"date": "2024-01-01", "index_return": 7.75, "start_return": 15.5},
            {"date": "2024-01-02", "index_return": 21.86931818181818, "start_return": 30.035714285714285},
        ]
        assert captured_returns[1] == [
            {"date": "2024-01-01", "index_return": 0.25, "start_return": 0.5},
            {"date": "2024-01-02", "index_return": 0.5625, "start_return": 0.75},
        ]
        assert captured_returns[2] == [
            {"date": "2024-01-01", "index_return": 7.5, "start_return": 15.0},
            {"date": "2024-01-02", "index_return": 19.09090909090909, "start_return": 26.428571428571427},
        ]

        workbook = _build_global_preview_workbook(payload)
        sheet = workbook.active
        assert sheet["A1"].value == ""
        assert sheet["B1"].value == ""
        assert sheet["C1"].value == "产品1"
        assert sheet["F1"].value == "产品2"
        assert sheet["E2"].value == "模型结果（25%）"
        assert sheet["H2"].value == "模型结果（75%）"
        assert sheet["E3"].value == pytest.approx(1.25)
        assert sheet["H3"].value == pytest.approx(41.42857142857143)
        assert sheet["E3"].number_format == "0.00%"
        assert sheet["I2"].value == "比例计算-指数"
        assert sheet["J2"].value == "比例计算-结果"
        assert sheet["C1"].fill.fgColor.rgb == "00FCECC5"
        assert sheet["F1"].fill.fgColor.rgb == "00FCECC5"
        assert sheet["A2"].fill.fgColor.rgb == "00F7E1A1"
        assert sheet["A3"].fill.fgColor.rgb == "00F7E1A1"

        preview_payload = build_multi_product_global_preview_payload(
            task.id,
            ratios_override=[{"ratio": 50}, {"ratio": 50}],
        )
        assert preview_payload["groups"][0]["rows"][0]["weighted_result_value"] == "3171.43%"
        assert json.loads(db.session.get(Task, task.id).config)["products"][0]["ratio"] == "25"


def test_global_preview_word_export_uses_current_ratio_portfolio_returns(app_factory, monkeypatch):
    app = app_factory
    with app.app_context():
        config = normalize_multi_product_config({
            "start_date": "2024-01-01",
            "end_date": "2024-12-31",
            "products": [_base_product(0, "50"), _base_product(1, "50")],
        })
        task = Task(
            id="multi-word-data-task",
            name="多品 Word",
            task_type=BACKTEST_MULTI_PRODUCT_TASK_TYPE,
            status="completed",
            config=json.dumps(config, ensure_ascii=False),
            created_at=datetime.now(),
        )
        db.session.add(task)
        for product_index, returns in enumerate(([
            {"date": "2024-01-01", "index_return": 0.10, "start_return": 0.10},
            {"date": "2024-01-02", "index_return": 0.21, "start_return": 0.21},
        ], [
            {"date": "2024-01-01", "index_return": 0.20, "start_return": 0.20},
            {"date": "2024-01-02", "index_return": 0.44, "start_return": 0.44},
        ])):
            db.session.add(TaskResult(
                task_id=task.id,
                step_index=product_index,
                parameters=json.dumps({
                    "product_index": product_index,
                    "parameter_group_index": 0,
                }),
                result=json.dumps(_task_result_payload_with_returns(0, 0, returns)),
                success=True,
            ))
        db.session.commit()

        payload = build_multi_product_global_preview_word_payload(
            task.id,
            "0",
            ratios_override=[{"ratio": 25}, {"ratio": 75}],
        )

        assert payload["report_type"] == "RPT-M"
        assert [product["ratio"] for product in payload["products"]] == ["25", "75"]
        assert [item["date"] for item in payload["products"][0]["returns"]] == ["2024-01-01", "2024-01-02"]

        captured = {}
        def fake_generate_word(word_payload):
            captured["payload"] = word_payload
            return "RPT-M.docx", BytesIO(b"docx")

        monkeypatch.setattr(
            "app.services.export_service.strategy_backtest_report_service.generate_word",
            fake_generate_word,
        )
        monkeypatch.setenv("AUTH_ENABLED", "false")
        client = app.test_client()
        legacy_response = client.post(
            "/api/exports/backtest-reports/word",
            json={"report_type": "RPT-M", "products": payload["products"]},
        )
        assert legacy_response.status_code == 400

        response = client.post(
            "/api/exports/backtest-reports/word",
            json={
                "report_type": "RPT-M",
                "task_id": task.id,
                "group_key": "0",
                "ratios": [{"ratio": 50}, {"ratio": 50}],
            },
        )

        assert response.status_code == 200
        assert [product["ratio"] for product in captured["payload"]["products"]] == ["50", "50"]


def test_ratio_preview_recalculates_only_changed_product_weighted_metrics(app_factory, monkeypatch):
    app = app_factory
    captured_returns = []
    _GLOBAL_PREVIEW_CACHE.clear()

    def fake_metrics(return_date):
        captured_returns.append(return_date)
        total_start = sum(item["start_return"] for item in return_date)
        total_index = sum(item["index_return"] for item in return_date)
        return {
            "excess_returns": [{
                "year": "all",
                "index_annualized_return": total_index,
                "start_annualized_return": total_start,
                "annualized_return_diff": total_start - total_index,
            }],
            "index_profit_annual": 1,
            "start_profit_annual": 1,
            "index_profit_monthly": [{"year": "all", "profit_monthly_percentage": 1}],
            "start_profit_monthly": [{"year": "all", "profit_monthly_percentage": 1}],
            "index_sharpe_ratios": {"all": {"avg_monthly_return": total_index, "sharpe_ratio": total_index}},
            "start_sharpe_ratios": {"all": {"avg_monthly_return": total_start, "sharpe_ratio": total_start}},
        }

    monkeypatch.setattr(
        "app.services.backtest_multi_product_service.xpl_analyzer.get_calculate_metrics_v1",
        fake_metrics,
    )

    with app.app_context():
        config = normalize_multi_product_config({
            "start_date": "2024-01-01",
            "end_date": "2024-12-31",
            "use_legacy_cumulative_return_weighting": True,
            "products": [_base_product(0, "25"), _base_product(1, "75")],
        })
        task = Task(
            id="ratio-preview-changed-only-task",
            name="比例局部试算测试",
            task_type=BACKTEST_MULTI_PRODUCT_TASK_TYPE,
            status="completed",
            config=json.dumps(config, ensure_ascii=False),
            created_at=datetime.now(),
        )
        db.session.add(task)
        first = TaskResult(
            task_id=task.id,
            step_index=0,
            parameters=json.dumps({"product_index": 0, "ratio": 25, "weighting_mode": "legacy_cumulative", "parameter_group_index": 0}, ensure_ascii=False),
            result=json.dumps(_task_result_payload_with_returns_and_weighted(0.10, 0.20, 0.25, [
                {"date": "2024-01-01", "index_return": 1, "start_return": 2},
                {"date": "2024-01-02", "index_return": 3, "start_return": 4},
            ])),
            success=True,
        )
        second = TaskResult(
            task_id=task.id,
            step_index=1,
            parameters=json.dumps({"product_index": 1, "ratio": 75, "weighting_mode": "legacy_cumulative", "parameter_group_index": 0}, ensure_ascii=False),
            result=json.dumps(_task_result_payload_with_returns_and_weighted(0.20, 0.40, 0.75, [
                {"date": "2024-01-01", "index_return": 10, "start_return": 20},
                {"date": "2024-01-02", "index_return": 30, "start_return": 40},
            ])),
            success=True,
        )
        db.session.add_all([first, second])
        db.session.flush()
        first_series = _add_return_series(task.id, ["2024-01-01", "2024-01-02"], [1, 3], [2, 4])
        second_series = _add_return_series(task.id, ["2024-01-01", "2024-01-02"], [10, 30], [20, 40])
        db.session.add_all([first_series, second_series])
        db.session.flush()
        first.return_series_id = first_series.id
        second.return_series_id = second_series.id
        db.session.commit()

        payload = build_multi_product_global_preview_payload(
            task.id,
            ratios_override=[{"ratio": 25}, {"ratio": 50}],
        )

        row = payload["groups"][0]["rows"][0]
        assert row["product_values"][0]["weighted_result_value"] == "25.00%"
        assert row["product_values"][1]["weighted_result_value"] == "2523.81%"
        assert row["weighted_result_value"] == "2839.29%"
        assert captured_returns == [
            [
                {"date": "2024-01-01", "index_return": 5.25, "start_return": 10.5},
                {"date": "2024-01-02", "index_return": 12.494318181818182, "start_return": 17.892857142857142},
            ],
            [
                {"date": "2024-01-01", "index_return": 5.0, "start_return": 10.0},
                {"date": "2024-01-02", "index_return": 10.454545454545455, "start_return": 15.238095238095237},
            ],
        ]
        assert json.loads(db.session.get(Task, task.id).config)["products"][1]["ratio"] == "75"


def test_build_multi_product_global_preview_derives_year_max_excess_drawdown(app_factory):
    app = app_factory
    with app.app_context():
        config = normalize_multi_product_config({
            "start_date": "2024-01-01",
            "end_date": "2024-12-31",
            "products": [_base_product(0, "100"), _base_product(1, "0")],
        })
        task = Task(
            id="preview-drawdown-task",
            name="多品回撤测试",
            task_type=BACKTEST_MULTI_PRODUCT_TASK_TYPE,
            status="completed",
            config=json.dumps(config, ensure_ascii=False),
            created_at=datetime.now(),
        )
        db.session.add(task)
        db.session.add(TaskResult(
            task_id=task.id,
            step_index=0,
            parameters=json.dumps(
                {"product_index": 0, "ratio": "100", "parameter_group_index": 0},
                ensure_ascii=False,
            ),
            result=json.dumps(_task_result_payload_with_year_drawdowns(), ensure_ascii=False),
            success=True,
        ))
        db.session.commit()

        payload = build_multi_product_global_preview_payload(task.id)

        drawdown_row = next(
            row
            for row in payload["groups"][0]["rows"]
            if row["metric"] == "年最大超额回撤"
        )
        assert drawdown_row["product_values"][0]["result_value"] == "4.00%"
        assert drawdown_row["product_values"][0]["raw_result_value"] == pytest.approx(0.04)
        drawdown_win_rate_row = next(
            row
            for row in payload["groups"][0]["rows"]
            if row["metric"] == "超额回撤胜率"
        )
        assert drawdown_win_rate_row["product_values"][0]["result_value"] == "75.00%"
        max_drawdown_row = next(
            row
            for row in payload["groups"][0]["rows"]
            if row["metric"] == "年最大回撤"
        )
        assert max_drawdown_row["product_values"][0]["result_value"] == "-6.00%"


def test_multi_product_year_max_excess_drawdown_uses_zero_when_no_year_outperforms():
    metrics = _derive_metrics({
        "excess_returns": [
            {"year": "2024", "annualized_return_diff": -0.01},
            {"year": "all", "annualized_return_diff": -0.01},
        ],
        "index_maximum_drawdown": {
            "year_maximum_drawdown": [{"year": "2024", "drawdown": 0.10}],
        },
        "start_maximum_drawdown": {
            "year_maximum_drawdown": [{"year": "2024", "drawdown": 0.12}],
        },
    })

    assert _fmt_value(metrics["year_max_excess_drawdown"], "percent") == "0.00%"


def test_multi_product_derive_metrics_accepts_c7_flat_analyze_result():
    metrics = _derive_metrics({
        "index_annualized_return": 0.1,
        "start_annualized_return": 0.2,
        "annualized_return_diff": 0.1,
        "index_profit_monthly_percentage": 0.5,
        "start_profit_monthly_percentage": 0.6,
        "index_avg_monthly_return_common": 0.01,
        "start_avg_monthly_return_common": 0.02,
        "monthly_excess_return_percentage_last_return": 0.7,
        "avg_monthly_excess_returns": 0.03,
        "start_drawdown": 0.12,
        "index_sharpe_ratio": 1.1,
        "start_sharpe_ratio": 1.2,
    })

    assert metrics["index_annualized_return"] == 0.1
    assert metrics["start_annualized_return"] == 0.2
    assert metrics["monthly_excess_return_percentage"] == 0.7
    assert metrics["avg_monthly_excess_return"] == 0.03
    assert metrics["start_max_drawdown"] == -0.12
    assert metrics["start_sharpe_ratio"] == 1.2


def test_multi_product_derive_metrics_uses_sortino_ratio_scalar_from_year_all():
    metrics = _derive_metrics({
        "index_sortino_ratio": [
            {"year": 2025, "sortino_ratio": 1.2},
            {"year": "all", "sortino_ratio": 2.34},
        ],
        "start_sortino_ratio": [
            {"year": 2025, "sortino_ratio": 3.4},
            {"year": "all", "sortino_ratio": 4.56},
        ],
    })

    assert metrics["index_sortino_ratio"] == pytest.approx(2.34)
    assert metrics["start_sortino_ratio"] == pytest.approx(4.56)


def test_multi_product_global_preview_workbook_writes_percentage_cells_as_numbers():
    payload = {
        "products": [
            {
                "product_index": 0,
                "product_name": "产品1",
                "stock_code": "TEST1",
                "ratio": "25",
            }
        ],
        "groups": [
            {
                "rows": [
                    {
                        "category": "绝对收益",
                        "metric": "年化收益",
                        "product_values": [
                            {
                                "index_value": "5.00%",
                                "result_value": "12.00%",
                                "weighted_result_value": "3.00%",
                            }
                        ],
                        "weighted_index_value": "1.25%",
                        "weighted_result_value": "3.00%",
                    },
                    {
                        "category": "回撤",
                        "metric": "年最大回撤",
                        "product_values": [
                            {
                                "index_value": "-10.00%",
                                "result_value": "0.00%",
                                "weighted_result_value": "0.00%",
                            }
                        ],
                        "weighted_index_value": "-10.00%",
                        "weighted_result_value": "0.00%",
                    },
                ],
            }
        ],
    }

    workbook = _build_global_preview_workbook(payload)
    sheet = workbook.active

    assert sheet["C3"].value == pytest.approx(0.05)
    assert sheet["C3"].number_format == "0.00%"
    assert sheet["D4"].value == pytest.approx(0)
    assert sheet["D4"].number_format == "0.00%"


def test_global_preview_reuses_in_memory_cache_for_same_ratios(app_factory, monkeypatch):
    app = app_factory
    metric_call_count = 0
    _GLOBAL_PREVIEW_CACHE.clear()

    def fake_metrics(return_date):
        nonlocal metric_call_count
        metric_call_count += 1
        total_start = sum(item["start_return"] for item in return_date)
        total_index = sum(item["index_return"] for item in return_date)
        return {
            "excess_returns": [{
                "year": "all",
                "index_annualized_return": total_index,
                "start_annualized_return": total_start,
                "annualized_return_diff": total_start - total_index,
            }],
            "index_profit_annual": 1,
            "start_profit_annual": 1,
            "index_profit_monthly": [{"year": "all", "profit_monthly_percentage": 1}],
            "start_profit_monthly": [{"year": "all", "profit_monthly_percentage": 1}],
            "index_sharpe_ratios": {"all": {"avg_monthly_return": total_index, "sharpe_ratio": total_index}},
            "start_sharpe_ratios": {"all": {"avg_monthly_return": total_start, "sharpe_ratio": total_start}},
        }

    monkeypatch.setattr(
        "app.services.backtest_multi_product_service.xpl_analyzer.get_calculate_metrics_v1",
        fake_metrics,
    )

    with app.app_context():
        config = normalize_multi_product_config({
            "start_date": "2024-01-01",
            "end_date": "2024-12-31",
            "use_legacy_cumulative_return_weighting": True,
            "products": [_base_product(0, "50"), _base_product(1, "50")],
        })
        task = Task(
            id="preview-cache-task",
            name="预览缓存测试",
            task_type=BACKTEST_MULTI_PRODUCT_TASK_TYPE,
            status="completed",
            config=json.dumps(config, ensure_ascii=False),
            created_at=datetime.now(),
        )
        db.session.add(task)
        first = TaskResult(
            task_id=task.id,
            step_index=0,
            parameters=json.dumps({"product_index": 0, "ratio": 50, "weighting_mode": "legacy_cumulative", "parameter_group_index": 0}, ensure_ascii=False),
            result=json.dumps(_task_result_payload_with_returns_and_weighted(0.10, 0.20, 1, [
                {"date": "2024-01-01", "index_return": 1, "start_return": 2},
            ])),
            success=True,
        )
        second = TaskResult(
            task_id=task.id,
            step_index=1,
            parameters=json.dumps({"product_index": 1, "ratio": 50, "weighting_mode": "legacy_cumulative", "parameter_group_index": 0}, ensure_ascii=False),
            result=json.dumps(_task_result_payload_with_returns_and_weighted(0.20, 0.40, 10, [
                {"date": "2024-01-01", "index_return": 10, "start_return": 20},
            ])),
            success=True,
        )
        db.session.add_all([first, second])
        db.session.flush()
        first_series = _add_return_series(task.id, ["2024-01-01"], [1], [2])
        second_series = _add_return_series(task.id, ["2024-01-01"], [10], [20])
        db.session.add_all([first_series, second_series])
        db.session.flush()
        first.return_series_id = first_series.id
        second.return_series_id = second_series.id
        db.session.commit()

        first_payload = build_multi_product_global_preview_payload(task.id)
        calls_after_first = metric_call_count
        second_payload = build_multi_product_global_preview_payload(task.id)

        assert first_payload == second_payload
        assert calls_after_first == 1
        assert metric_call_count == calls_after_first


def test_build_multi_product_global_preview_handles_result_metadata_outside_sheet_payload(app_factory):
    app = app_factory
    with app.app_context():
        config = normalize_multi_product_config({
            "start_date": "2024-01-01",
            "end_date": "2024-12-31",
            "products": [_base_product(0, "25"), _base_product(1, "75")],
        })
        task = Task(
            id="multi-metadata-task",
            name="多品元数据测试",
            task_type=BACKTEST_MULTI_PRODUCT_TASK_TYPE,
            status="completed",
            config=json.dumps(config, ensure_ascii=False),
            created_at=datetime.now(),
        )
        db.session.add(task)
        db.session.add(TaskResult(
            task_id=task.id,
            step_index=0,
            parameters=json.dumps({
                "product_index": 0,
                "product_name": "产品1",
                "stock_code": "TEST1",
                "ratio": "25",
                "parameter_group_index": 0,
                "parameter": config["products"][0]["parameters"][0],
            }, ensure_ascii=False),
            result=json.dumps(_task_result_payload_with_metadata(0.10, 0.20)),
            success=True,
        ))
        db.session.add(TaskResult(
            task_id=task.id,
            step_index=1,
            parameters=json.dumps({
                "product_index": 1,
                "product_name": "产品2",
                "stock_code": "TEST2",
                "ratio": "75",
                "parameter_group_index": 0,
                "parameter": config["products"][1]["parameters"][0],
            }, ensure_ascii=False),
            result=json.dumps(_task_result_payload_with_metadata(0.20, 0.40)),
            success=True,
        ))
        db.session.commit()

        payload = build_multi_product_global_preview_payload(task.id)

        assert payload["summary"]["success_results"] == 2
        row = payload["groups"][0]["rows"][0]
        assert row["product_values"][0]["result_value"] != "-"
        assert row["product_values"][1]["result_value"] != "-"
        assert row["weighted_result_value"] == "-"


def test_build_multi_product_global_preview_uses_common_dates_for_portfolio_returns(app_factory, monkeypatch):
    app = app_factory
    captured_returns = []

    def fake_metrics(return_date):
        captured_returns.append(return_date)
        total_start = sum(item["start_return"] for item in return_date)
        total_index = sum(item["index_return"] for item in return_date)
        return {
            "excess_returns": [{
                "year": "all",
                "index_annualized_return": total_index,
                "start_annualized_return": total_start,
                "annualized_return_diff": total_start - total_index,
            }],
            "index_profit_annual": 1,
            "start_profit_annual": 1,
            "index_profit_monthly": [{"year": "all", "profit_monthly_percentage": 1}],
            "start_profit_monthly": [{"year": "all", "profit_monthly_percentage": 1}],
            "index_sharpe_ratios": {"all": {"avg_monthly_return": total_index, "sharpe_ratio": total_index}},
            "start_sharpe_ratios": {"all": {"avg_monthly_return": total_start, "sharpe_ratio": total_start}},
        }

    monkeypatch.setattr(
        "app.services.backtest_multi_product_service.xpl_analyzer.get_calculate_metrics_v1",
        fake_metrics,
    )

    with app.app_context():
        config = normalize_multi_product_config({
            "start_date": "2024-01-01",
            "end_date": "2024-12-31",
            "use_legacy_cumulative_return_weighting": True,
            "products": [_base_product(0, "25"), _base_product(1, "75")],
        })
        task = Task(
            id="multi-return-task",
            name="多品收益测试",
            task_type=BACKTEST_MULTI_PRODUCT_TASK_TYPE,
            status="completed",
            config=json.dumps(config, ensure_ascii=False),
            created_at=datetime.now(),
        )
        db.session.add(task)
        first = TaskResult(
            task_id=task.id,
            step_index=0,
            parameters=json.dumps({"product_index": 0, "parameter_group_index": 0}, ensure_ascii=False),
            result=json.dumps(_task_result_payload_with_returns(0.50, 0.80, [
                {"date": "2024-01-01", "index_return": 1, "start_return": 2},
                {"date": "2024-01-02", "index_return": 3, "start_return": 4},
            ])),
            success=True,
        )
        second = TaskResult(
            task_id=task.id,
            step_index=1,
            parameters=json.dumps({"product_index": 1, "parameter_group_index": 0}, ensure_ascii=False),
            result=json.dumps(_task_result_payload_with_returns(0.70, 0.90, [
                {"date": "2024-01-01", "index_return": 10, "start_return": 20},
                {"date": "2024-01-02", "index_return": 30, "start_return": 40},
            ])),
            success=True,
        )
        db.session.add_all([first, second])
        db.session.flush()
        first_series = _add_return_series(task.id, ["2024-01-01", "2024-01-02"], [1, 3], [2, 4])
        second_series = _add_return_series(task.id, ["2024-01-02", "2024-01-03"], [30, 50], [40, 60])
        db.session.add_all([first_series, second_series])
        db.session.flush()
        first.return_series_id = first_series.id
        second.return_series_id = second_series.id
        db.session.commit()

        payload = build_multi_product_global_preview_payload(task.id)

        row = payload["groups"][0]["rows"][0]
        assert row["metric"] == "年化收益"
        assert row["product_values"][0]["weighted_result_value"] == "125.00%"
        assert row["product_values"][1]["weighted_result_value"] == "7134.15%"
        assert row["weighted_result_value"] == "3100.00%"
        assert [
            {"date": "2024-01-01", "index_return": 0.25, "start_return": 0.5},
            {"date": "2024-01-02", "index_return": 0.5625, "start_return": 0.75},
        ] in captured_returns
        assert [
            {"date": "2024-01-02", "index_return": 22.5, "start_return": 30.0},
            {"date": "2024-01-03", "index_return": 33.87096774193548, "start_return": 41.34146341463415},
        ] in captured_returns
        assert [
            {"date": "2024-01-02", "index_return": 23.25, "start_return": 31.0},
        ] in captured_returns

        captured_returns.clear()
        preview_payload = build_multi_product_global_preview_payload(
            task.id,
            ratios_override=[{"ratio": 50}, {"ratio": 50}],
        )
        preview_row = preview_payload["groups"][0]["rows"][0]
        assert preview_row["weighted_result_value"] == "2200.00%"
        assert [
            {"date": "2024-01-02", "index_return": 16.5, "start_return": 22.0},
        ] in captured_returns


def test_build_multi_product_global_preview_default_mode_compounds_daily_weighting(
    app_factory, monkeypatch,
):
    """默认（非 legacy）按"累计→日收益→按比例缩放→再复利"加权。"""
    app = app_factory
    captured_returns = []

    def fake_metrics(return_date):
        captured_returns.append(list(return_date))
        total_start = sum(item["start_return"] for item in return_date)
        return {
            "excess_returns": [{
                "year": "all",
                "index_annualized_return": 0,
                "start_annualized_return": total_start,
                "annualized_return_diff": total_start,
            }],
            "index_profit_annual": 1,
            "start_profit_annual": 1,
            "index_profit_monthly": [{"year": "all", "profit_monthly_percentage": 1}],
            "start_profit_monthly": [{"year": "all", "profit_monthly_percentage": 1}],
            "index_sharpe_ratios": {"all": {"avg_monthly_return": 0, "sharpe_ratio": 0}},
            "start_sharpe_ratios": {"all": {"avg_monthly_return": total_start, "sharpe_ratio": total_start}},
        }

    monkeypatch.setattr(
        "app.services.backtest_multi_product_service.xpl_analyzer.get_calculate_metrics_v1",
        fake_metrics,
    )

    with app.app_context():
        config = normalize_multi_product_config({
            "start_date": "2024-01-01",
            "end_date": "2024-12-31",
            "products": [_base_product(0, "50"), _base_product(1, "50")],
        })
        task = Task(
            id="multi-compound-task",
            name="多品复利加权",
            task_type=BACKTEST_MULTI_PRODUCT_TASK_TYPE,
            status="completed",
            config=json.dumps(config, ensure_ascii=False),
            created_at=datetime.now(),
        )
        db.session.add(task)
        result = TaskResult(
            task_id=task.id,
            step_index=0,
            parameters=json.dumps({"product_index": 0, "ratio": "50", "parameter_group_index": 0}, ensure_ascii=False),
            result=json.dumps(_task_result_payload_with_returns(0.50, 0.80, [
                {"date": "2024-01-01", "index_return": 0.10, "start_return": 0.20},
                {"date": "2024-01-02", "index_return": 0.30, "start_return": 0.40},
            ])),
            success=True,
        )
        second = TaskResult(
            task_id=task.id,
            step_index=1,
            parameters=json.dumps({"product_index": 1, "ratio": "50", "parameter_group_index": 0}, ensure_ascii=False),
            result=json.dumps(_task_result_payload_with_returns(0.70, 0.90, [
                {"date": "2024-01-01", "index_return": 0.20, "start_return": 0.30},
                {"date": "2024-01-02", "index_return": 0.40, "start_return": 0.50},
            ])),
            success=True,
        )
        db.session.add_all([result, second])
        db.session.flush()
        series = _add_return_series(
            task.id, ["2024-01-01", "2024-01-02"], [0.10, 0.30], [0.20, 0.40],
        )
        second_series = _add_return_series(
            task.id, ["2024-01-01", "2024-01-02"], [0.20, 0.40], [0.30, 0.50],
        )
        db.session.flush()
        result.return_series_id = series.id
        second.return_series_id = second_series.id
        db.session.commit()

        build_multi_product_global_preview_payload(task.id)

        # 首次调用为组合序列：产品日收益按 50% 加权后跨产品合并再复利。
        # 产品0 索引日收益 [0.10, 1.3/1.1-1]，产品1 [0.20, 1.4/1.2-1]。
        portfolio = captured_returns[0]
        assert portfolio[0]["index_return"] == pytest.approx(0.5 * 0.10 + 0.5 * 0.20)
        index_day2 = (0.5 * (1.3 / 1.1 - 1) + 0.5 * (1.4 / 1.2 - 1))
        assert portfolio[1]["index_return"] == pytest.approx(1.15 * (1 + index_day2) - 1)
        assert portfolio[0]["start_return"] == pytest.approx(0.5 * 0.20 + 0.5 * 0.30)
        start_day2 = (0.5 * (1.4 / 1.2 - 1) + 0.5 * (1.5 / 1.3 - 1))
        assert portfolio[1]["start_return"] == pytest.approx(1.25 * (1 + start_day2) - 1)

        # 单产品 50% 加权：日收益 [0.10, 0.30] 缩放为 [0.05, 0.15]，再复利为累计。
        product_weighted = next(
            item for item in captured_returns[1:]
            if item and item[0]["index_return"] == pytest.approx(0.05)
        )
        assert product_weighted[1]["index_return"] == pytest.approx(
            1.05 * (1 + 0.5 * (1.3 / 1.1 - 1)) - 1
        )
        assert product_weighted[0]["start_return"] == pytest.approx(0.10)
        assert product_weighted[1]["start_return"] == pytest.approx(
            1.10 * (1 + 0.5 * (1.4 / 1.2 - 1)) - 1
        )


def test_build_multi_product_global_preview_returns_dash_without_common_return_dates(app_factory, monkeypatch):
    app = app_factory
    captured_returns = []

    monkeypatch.setattr(
        "app.services.backtest_multi_product_service.xpl_analyzer.get_calculate_metrics_v1",
        lambda return_date: captured_returns.append(return_date) or {},
    )

    with app.app_context():
        config = normalize_multi_product_config({
            "start_date": "2024-01-01",
            "end_date": "2024-12-31",
            "products": [_base_product(0, "50"), _base_product(1, "50")],
        })
        task = Task(
            id="multi-no-common-date-task",
            name="多品无共同日期测试",
            task_type=BACKTEST_MULTI_PRODUCT_TASK_TYPE,
            status="completed",
            config=json.dumps(config, ensure_ascii=False),
            created_at=datetime.now(),
        )
        db.session.add(task)
        first = TaskResult(
            task_id=task.id,
            step_index=0,
            parameters=json.dumps({"product_index": 0, "parameter_group_index": 0}, ensure_ascii=False),
            result=json.dumps(_task_result_payload(0.50, 0.80)),
            success=True,
        )
        second = TaskResult(
            task_id=task.id,
            step_index=1,
            parameters=json.dumps({"product_index": 1, "parameter_group_index": 0}, ensure_ascii=False),
            result=json.dumps(_task_result_payload(0.70, 0.90)),
            success=True,
        )
        db.session.add_all([first, second])
        db.session.flush()
        first_series = _add_return_series(task.id, ["2024-01-01"], [1], [2])
        second_series = _add_return_series(task.id, ["2024-01-02"], [10], [20])
        db.session.add_all([first_series, second_series])
        db.session.flush()
        first.return_series_id = first_series.id
        second.return_series_id = second_series.id
        db.session.commit()

        payload = build_multi_product_global_preview_payload(task.id)
        row = payload["groups"][0]["rows"][0]

        assert row["weighted_index_value"] == "-"
        assert row["weighted_result_value"] == "-"
        assert captured_returns[0] == [
            {"date": "2024-01-01", "index_return": 0.5, "start_return": 1.0},
        ]
        assert captured_returns[1] == [
            {"date": "2024-01-02", "index_return": 5.0, "start_return": 10.0},
        ]

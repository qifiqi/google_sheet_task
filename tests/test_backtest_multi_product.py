import json
from datetime import datetime

import pytest

from app.extensions import db
from app.models import (
    BacktestProductResultCache,
    BacktestSheetRunLock,
    Permission,
    Task,
    TaskResult,
    TaskResultReturn,
)
from app.routes.backtest_multi_product import (
    _build_excel_download_name,
    _build_global_preview_workbook,
)
from app.services.backtest_multi_product_service import (
    BACKTEST_MULTI_PRODUCT_TASK_TYPE,
    BacktestMultiProductService,
    _GLOBAL_PREVIEW_CACHE,
    build_multi_product_global_preview_payload,
    normalize_multi_product_config,
)
from app.services.task.facade import TaskManager
from app.services.task.runtime_view import TaskRuntimeViewService


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


def test_normalize_multi_product_config_allows_ratio_total_not_equal_100():
    config = {
        "start_date": "2024-01-01",
        "end_date": "2024-12-31",
        "products": [_base_product(0, "60"), _base_product(1, "30")],
    }

    normalized = normalize_multi_product_config(config)

    assert [product["ratio"] for product in normalized["products"]] == ["60", "30"]
    assert [product["price_mode"] for product in normalized["products"]] == ["sp_price", "sp_price"]


def test_normalize_multi_product_config_keeps_per_product_price_mode():
    config = {
        "start_date": "2024-01-01",
        "end_date": "2024-12-31",
        "products": [
            _base_product(0, "60") | {"price_mode": "kp_price"},
            _base_product(1, "30") | {"price_mode": "sp_price"},
        ],
    }

    normalized = normalize_multi_product_config(config)

    assert [product["price_mode"] for product in normalized["products"]] == ["kp_price", "sp_price"]


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
        return_series = TaskResultReturn(
            task_id=task.id,
            returns_json=json.dumps({
                "dates": ["2024-01-01", "2024-01-02"],
                "index_returns": [0.1, 0.2],
                "start_returns": [0.3, 0.4],
            }),
        )
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
        db.session.add_all([
            Permission(
                name="查看任务",
                code="task:view",
                group="task",
                description="查看任务",
                route_path="/admin/tasks",
            ),
            Permission(
                name="查看回测任务",
                code="backtest:view",
                group="backtest",
                description="查看回测任务",
                route_path="/backtest/list",
            ),
        ])
        return_series = TaskResultReturn(
            task_id=task.id,
            returns_json=json.dumps({
                "dates": ["2024-01-01", "2024-01-02"],
                "index_returns": [0.11, 0.22],
                "start_returns": [0.33, 0.44],
            }),
        )
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
        first_series = TaskResultReturn(
            task_id=task.id,
            returns_json=json.dumps({
                "dates": ["2024-01-01", "2024-01-02"],
                "index_returns": [1, 3],
                "start_returns": [2, 4],
            }),
        )
        second_series = TaskResultReturn(
            task_id=task.id,
            returns_json=json.dumps({
                "dates": ["2024-01-01", "2024-01-02"],
                "index_returns": [10, 30],
                "start_returns": [20, 40],
            }),
        )
        db.session.add_all([first_series, second_series])
        db.session.flush()
        db.session.query(TaskResult).filter_by(task_id=task.id, step_index=0).one().return_series_id = first_series.id
        db.session.query(TaskResult).filter_by(task_id=task.id, step_index=1).one().return_series_id = second_series.id
        db.session.commit()

        payload = build_multi_product_global_preview_payload(task.id)

        assert payload["summary"]["product_count"] == 2
        row = payload["groups"][0]["rows"][0]
        assert row["metric"] == "年化收益"
        assert row["product_values"][0]["weighted_result_value"] == "150.00%"
        assert row["product_values"][1]["weighted_result_value"] == "4500.00%"
        assert row["weighted_index_value"] == "3100.00%"
        assert row["weighted_result_value"] == "4650.00%"
        assert captured_returns[0] == [
            {"date": "2024-01-01", "index_return": 7.75, "start_return": 15.5},
            {"date": "2024-01-02", "index_return": 23.25, "start_return": 31.0},
        ]
        assert captured_returns[1] == [
            {"date": "2024-01-01", "index_return": 0.25, "start_return": 0.5},
            {"date": "2024-01-02", "index_return": 0.75, "start_return": 1.0},
        ]
        assert captured_returns[2] == [
            {"date": "2024-01-01", "index_return": 7.5, "start_return": 15.0},
            {"date": "2024-01-02", "index_return": 22.5, "start_return": 30.0},
        ]

        workbook = _build_global_preview_workbook(payload)
        sheet = workbook.active
        assert sheet["A1"].value == ""
        assert sheet["B1"].value == ""
        assert sheet["C1"].value == "产品1"
        assert sheet["F1"].value == "产品2"
        assert sheet["E2"].value == "模型结果（25%）"
        assert sheet["H2"].value == "模型结果（75%）"
        assert sheet["E3"].value == "150.00%"
        assert sheet["H3"].value == "4500.00%"
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
        assert preview_payload["groups"][0]["rows"][0]["weighted_result_value"] == "3300.00%"
        assert json.loads(db.session.get(Task, task.id).config)["products"][0]["ratio"] == "25"


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
            parameters=json.dumps({"product_index": 0, "ratio": "25", "parameter_group_index": 0}, ensure_ascii=False),
            result=json.dumps(_task_result_payload_with_returns_and_weighted(0.10, 0.20, 0.25, [
                {"date": "2024-01-01", "index_return": 1, "start_return": 2},
                {"date": "2024-01-02", "index_return": 3, "start_return": 4},
            ])),
            success=True,
        )
        second = TaskResult(
            task_id=task.id,
            step_index=1,
            parameters=json.dumps({"product_index": 1, "ratio": "75", "parameter_group_index": 0}, ensure_ascii=False),
            result=json.dumps(_task_result_payload_with_returns_and_weighted(0.20, 0.40, 0.75, [
                {"date": "2024-01-01", "index_return": 10, "start_return": 20},
                {"date": "2024-01-02", "index_return": 30, "start_return": 40},
            ])),
            success=True,
        )
        db.session.add_all([first, second])
        db.session.flush()
        first_series = TaskResultReturn(
            task_id=task.id,
            returns_json=json.dumps({
                "dates": ["2024-01-01", "2024-01-02"],
                "index_returns": [1, 3],
                "start_returns": [2, 4],
            }),
        )
        second_series = TaskResultReturn(
            task_id=task.id,
            returns_json=json.dumps({
                "dates": ["2024-01-01", "2024-01-02"],
                "index_returns": [10, 30],
                "start_returns": [20, 40],
            }),
        )
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
        assert row["product_values"][1]["weighted_result_value"] == "3000.00%"
        assert row["weighted_result_value"] == "3150.00%"
        assert captured_returns == [
            [
                {"date": "2024-01-01", "index_return": 5.25, "start_return": 10.5},
                {"date": "2024-01-02", "index_return": 15.75, "start_return": 21.0},
            ],
            [
                {"date": "2024-01-01", "index_return": 5.0, "start_return": 10.0},
                {"date": "2024-01-02", "index_return": 15.0, "start_return": 20.0},
            ],
        ]
        assert json.loads(db.session.get(Task, task.id).config)["products"][1]["ratio"] == "75"


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
            parameters=json.dumps({"product_index": 0, "ratio": "50", "parameter_group_index": 0}, ensure_ascii=False),
            result=json.dumps(_task_result_payload_with_returns_and_weighted(0.10, 0.20, 1, [
                {"date": "2024-01-01", "index_return": 1, "start_return": 2},
            ])),
            success=True,
        )
        second = TaskResult(
            task_id=task.id,
            step_index=1,
            parameters=json.dumps({"product_index": 1, "ratio": "50", "parameter_group_index": 0}, ensure_ascii=False),
            result=json.dumps(_task_result_payload_with_returns_and_weighted(0.20, 0.40, 10, [
                {"date": "2024-01-01", "index_return": 10, "start_return": 20},
            ])),
            success=True,
        )
        db.session.add_all([first, second])
        db.session.flush()
        first_series = TaskResultReturn(
            task_id=task.id,
            returns_json=json.dumps({
                "dates": ["2024-01-01"],
                "index_returns": [1],
                "start_returns": [2],
            }),
        )
        second_series = TaskResultReturn(
            task_id=task.id,
            returns_json=json.dumps({
                "dates": ["2024-01-01"],
                "index_returns": [10],
                "start_returns": [20],
            }),
        )
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
        first_series = TaskResultReturn(
            task_id=task.id,
            returns_json=json.dumps({
                "dates": ["2024-01-01", "2024-01-02"],
                "index_returns": [1, 3],
                "start_returns": [2, 4],
            }),
        )
        second_series = TaskResultReturn(
            task_id=task.id,
            returns_json=json.dumps({
                "dates": ["2024-01-02", "2024-01-03"],
                "index_returns": [30, 50],
                "start_returns": [40, 60],
            }),
        )
        db.session.add_all([first_series, second_series])
        db.session.flush()
        first.return_series_id = first_series.id
        second.return_series_id = second_series.id
        db.session.commit()

        payload = build_multi_product_global_preview_payload(task.id)

        row = payload["groups"][0]["rows"][0]
        assert row["metric"] == "年化收益"
        assert row["product_values"][0]["weighted_result_value"] == "150.00%"
        assert row["product_values"][1]["weighted_result_value"] == "7500.00%"
        assert row["weighted_result_value"] == "3100.00%"
        assert [
            {"date": "2024-01-01", "index_return": 0.25, "start_return": 0.5},
            {"date": "2024-01-02", "index_return": 0.75, "start_return": 1.0},
        ] in captured_returns
        assert [
            {"date": "2024-01-02", "index_return": 22.5, "start_return": 30.0},
            {"date": "2024-01-03", "index_return": 37.5, "start_return": 45.0},
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
        first_series = TaskResultReturn(
            task_id=task.id,
            returns_json=json.dumps({
                "dates": ["2024-01-01"],
                "index_returns": [1],
                "start_returns": [2],
            }),
        )
        second_series = TaskResultReturn(
            task_id=task.id,
            returns_json=json.dumps({
                "dates": ["2024-01-02"],
                "index_returns": [10],
                "start_returns": [20],
            }),
        )
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

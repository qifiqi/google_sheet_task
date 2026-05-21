import json
from datetime import datetime

import pytest

from app.extensions import db
from app.models import Task, TaskResult, TaskResultReturn
from app.routes.backtest_multi_product import (
    _build_excel_download_name,
    _build_global_preview_workbook,
)
from app.services.backtest_multi_product_service import (
    BACKTEST_MULTI_PRODUCT_TASK_TYPE,
    BacktestMultiProductService,
    build_multi_product_global_preview_payload,
    normalize_multi_product_config,
)
from app.services.task.facade import TaskManager


def _base_product(index, ratio="50"):
    return {
        "product_index": index,
        "product_name": f"产品{index + 1}",
        "stock_code": f"TEST{index + 1}",
        "market_type": "cn",
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
            return True, {}

        monkeypatch.setattr(service, "_execute_parameter_combination", fake_execute)

        assert service._execute_products(task, config) == "completed"
        assert call_order == [(0, 0), (0, 1), (1, 0), (1, 1)]


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


def test_build_multi_product_global_preview_payload_weights_values(app_factory):
    app = app_factory
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
            result=json.dumps(_task_result_payload(0.10, 0.20)),
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
            result=json.dumps(_task_result_payload(0.20, 0.40)),
            success=True,
        ))
        db.session.commit()

        payload = build_multi_product_global_preview_payload(task.id)

        assert payload["summary"]["product_count"] == 2
        row = payload["groups"][0]["rows"][0]
        assert row["metric"] == "年化收益"
        assert row["product_values"][0]["weighted_result_value"] == "5.00%"
        assert row["product_values"][1]["weighted_result_value"] == "30.00%"
        assert row["weighted_index_value"] == "17.50%"
        assert row["weighted_result_value"] == "35.00%"

        workbook = _build_global_preview_workbook(payload)
        sheet = workbook.active
        assert sheet["A1"].value == ""
        assert sheet["B1"].value == ""
        assert sheet["C1"].value == "产品1"
        assert sheet["F1"].value == "产品2"
        assert sheet["E2"].value == "模型结果（25%）"
        assert sheet["H2"].value == "模型结果（75%）"
        assert sheet["E3"].value == "5.00%"
        assert sheet["H3"].value == "30.00%"
        assert sheet["I2"].value == "比例计算-指数"
        assert sheet["J2"].value == "比例计算-结果"
        assert sheet["C1"].fill.fgColor.rgb == "00FCECC5"
        assert sheet["F1"].fill.fgColor.rgb == "00FCECC5"
        assert sheet["A2"].fill.fgColor.rgb == "00F7E1A1"
        assert sheet["A3"].fill.fgColor.rgb == "00F7E1A1"

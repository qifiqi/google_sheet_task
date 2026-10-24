import json
from datetime import datetime

from app.extensions import db
from app.models import BacktestProductResultCache, SheetExecutionLock, Task
from app.services.sheet_execution_lock_service import get_sheet_execution_lock_service
from app.services.task.facade import TaskManager


def _backtest_task(task_id, *, status="pending", task_type="backtest_training", sheet_id="sheet-1", products=None):
    config = {
        "sheets": [{"spreadsheet_id": sheet_id, "sheet_name": "data"}],
        "parameters": [["p1"]],
    }
    if products is not None:
        config = {"products": products}
    return Task(
        id=task_id,
        name=task_id,
        task_type=task_type,
        status=status,
        config=json.dumps(config, ensure_ascii=False),
        created_at=datetime.now(),
    )


def test_sheet_lock_acquire_conflict_and_release(app_factory):
    app = app_factory
    with app.app_context():
        manager = TaskManager()
        service = get_sheet_execution_lock_service()

        acquired, holder, acquired_ids = service.acquire_for_task(
            "task-1", "backtest_training", ["sheet-1"]
        )
        conflict, conflict_task_id, _ = service.acquire_for_task(
            "task-2", "backtest_training", ["sheet-1"]
        )

        assert acquired is True
        assert acquired_ids == ["sheet-1"]
        assert conflict is False
        assert conflict_task_id == "task-1"

        # 仅持锁者可释放：task-2 释放不动 task-1 的锁。
        service.release_sheets(["sheet-1"], "task-2")
        assert SheetExecutionLock.query.filter_by(spreadsheet_id="sheet-1").count() == 1

        service.release_sheets(["sheet-1"], "task-1")
        assert SheetExecutionLock.query.filter_by(spreadsheet_id="sheet-1").count() == 0

        assert manager  # facade 仍可实例化（统一入口承载）


def test_extract_backtest_multi_product_locks_skips_cached_fixed_product(app_factory):
    app = app_factory
    with app.app_context():
        product_fixed = {
            "product_name": "fixed",
            "stock_code": "AAA",
            "is_fixed": True,
            "sheet": {"spreadsheet_id": "fixed-sheet"},
            "parameters": [["1"]],
        }
        product_live = {
            "product_name": "live",
            "stock_code": "BBB",
            "sheet": {"spreadsheet_id": "live-sheet"},
            "parameters": [["1"]],
        }
        config = {
            "fixed_product_batch_id": "batch-1",
            "start_date": "2024-01-01",
            "end_date": "2024-12-31",
            "products": [product_fixed, product_live],
        }
        from app.services.backtest_multi_product_service import BacktestMultiProductService
        fixed_cache_key = BacktestMultiProductService._build_fixed_product_cache_key(
            config,
            product_fixed,
            ["1"],
        )
        db.session.add(BacktestProductResultCache(
            batch_id="batch-1",
            cache_key=fixed_cache_key,
            result_json="{}",
        ))
        db.session.commit()

        manager = TaskManager()
        ids = manager._extract_sheets_to_lock(
            "backtest_multi_product",
            config,
        )

        assert ids == ["live-sheet"]


def test_start_task_queues_when_same_sheet_lock_held(app_factory):
    """统一执行锁语义：同 sheet 被其他任务持锁时，启动转为排队而非失败。

    与任务状态无关——即使持锁任务行不是 running（异常残留），执行锁仍是唯一权威。
    """
    app = app_factory
    with app.app_context():
        holder = _backtest_task("holder", status="running", sheet_id="sheet-1")
        pending = _backtest_task("pending", status="pending", sheet_id="sheet-1")
        db.session.add_all([holder, pending])
        db.session.add(SheetExecutionLock(
            spreadsheet_id="sheet-1", task_id="holder", task_type="backtest_training",
        ))
        db.session.commit()

        manager = TaskManager()

        result = manager.start_task(pending.id)
        assert result.queued
        assert "同一 Google Sheet 正在被其他任务执行" in result.message
        refreshed = db.session.get(Task, pending.id)
        assert refreshed.status == "pending"
        assert refreshed.error_message.startswith("[SHEET_QUEUED]")


def test_start_task_acquires_lock_cross_task_type(app_factory):
    """锁键只认 spreadsheet_id：C 系任务与回测任务互斥同一 sheet。"""
    app = app_factory
    with app.app_context():
        db.session.add(SheetExecutionLock(
            spreadsheet_id="sheet-1", task_id="c3-holder", task_type="google_sheet",
        ))
        pending = _backtest_task("bt-pending", status="pending", sheet_id="sheet-1")
        db.session.add(pending)
        db.session.commit()

        manager = TaskManager()

        result = manager.start_task(pending.id)
        assert result.queued

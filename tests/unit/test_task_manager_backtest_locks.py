import json
from datetime import datetime

from app.extensions import db
from app.models import BacktestProductResultCache, BacktestSheetRunLock, Task
from app.services.task.facade import TaskManager


def _backtest_task(task_id, *, status="pending", task_type="backtest_training", sheet_id="sheet-1", products=None):
    config = {
        "sheet": {"spreadsheet_id": sheet_id, "sheet_name": "data"},
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


def test_backtest_lock_acquire_conflict_and_release(app_factory):
    app = app_factory
    with app.app_context():
        manager = TaskManager()

        acquired, locked_task_id = manager._acquire_backtest_sheet_run_lock(
            "sheet-1",
            "task-1",
            task_type="backtest_training",
        )
        conflict, conflict_task_id = manager._acquire_backtest_sheet_run_lock(
            "sheet-1",
            "task-2",
            task_type="backtest_training",
        )

        assert acquired is True
        assert locked_task_id is None
        assert conflict is False
        assert conflict_task_id == "task-1"

        manager._release_backtest_sheet_run_reservation("sheet-1", "task-2")
        assert BacktestSheetRunLock.query.filter_by(spreadsheet_id="sheet-1").count() == 1

        manager._release_backtest_sheet_run_reservation("sheet-1", "task-1")
        assert BacktestSheetRunLock.query.filter_by(spreadsheet_id="sheet-1").count() == 0


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
        ids = manager._extract_backtest_spreadsheet_ids_to_lock(
            "backtest_multi_product",
            config,
        )

        assert ids == ["live-sheet"]


def test_start_backtest_queues_when_same_sheet_running(app_factory):
    app = app_factory
    with app.app_context():
        running = _backtest_task("running", status="running", sheet_id="sheet-1")
        pending = _backtest_task("pending", status="pending", sheet_id="sheet-1")
        db.session.add_all([running, pending])
        db.session.commit()

        manager = TaskManager()

        assert manager.start_task(pending.id) is False
        assert "同一个 Google Sheet 已有回测任务正在运行" in manager.get_start_error(pending.id)
        assert db.session.get(Task, pending.id).status == "pending"

import pytest

from sqlalchemy import inspect, text

from app.extensions import db
from app.models import GoogleSheet, ScheduledTask, Task
from app.services.sheet_execution_lock_service import (
    _MemoryBackend,
    sheet_execution_lock_service,
)
from app.startup import (
    cleanup_stale_sheet_execution_locks,
    ensure_google_sheet_registry_schema,
    ensure_scheduled_task_schema,
    ensure_task_result_summary_index_schema,
)


@pytest.fixture(autouse=True)
def _isolated_sheet_lock_backend():
    """全局锁服务用独立内存后端，用例间互不残留。"""
    sheet_execution_lock_service._backend = _MemoryBackend()
    yield
    sheet_execution_lock_service._backend = None


def test_ensure_google_sheet_registry_schema_is_portable(app_factory):
    with app_factory.app_context():
        ensure_google_sheet_registry_schema()
        sheet = GoogleSheet(
            name="C7 sheet",
            spreadsheet_id="same-sheet",
            table_type="c7",
        )
        db.session.add(sheet)
        db.session.commit()
        assert sheet.registry_scope == "c_series"


def test_ensure_scheduled_task_schema_adds_lock_fields_to_legacy_table(app_factory):
    db.session.execute(
        text(
            """
            CREATE TABLE scheduled_tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name VARCHAR(255) NOT NULL,
                description TEXT,
                cron_expression VARCHAR(100) NOT NULL,
                task_type VARCHAR(50),
                task_function VARCHAR(255) NOT NULL,
                task_params TEXT,
                is_active BOOLEAN,
                last_run_time DATETIME,
                next_run_time DATETIME,
                run_count INTEGER,
                created_at DATETIME,
                updated_at DATETIME
            )
            """
        )
    )
    db.session.commit()

    ensure_scheduled_task_schema()

    inspector = inspect(db.engine)
    columns = {column["name"] for column in inspector.get_columns("scheduled_tasks")}
    indexes = inspector.get_indexes("scheduled_tasks")

    assert "is_running" in columns
    assert "running_instance_id" in columns
    assert not any(index.get("column_names") == ["is_running"] for index in indexes)

    db.session.add(
        ScheduledTask(
            name="legacy scheduler task",
            cron_expression="0 0 * * *",
            task_function="cleanup_completed_tasks",
        )
    )
    db.session.commit()

    assert ScheduledTask.query.count() == 1
    assert ScheduledTask.query.first().is_running is False


def test_cleanup_stale_sheet_execution_locks_keeps_running_task_locks(app_factory):
    running_task = Task(id="running-lock-task", name="running", task_type="backtest_training", status="running")
    completed_task = Task(id="completed-lock-task", name="completed", task_type="backtest_training", status="completed")
    db.session.add_all([running_task, completed_task])
    sheet_execution_lock_service.acquire_for_task("running-lock-task", "backtest_training", ["running-sheet"])
    sheet_execution_lock_service.acquire_for_task("completed-lock-task", "backtest_training", ["completed-sheet"])
    sheet_execution_lock_service.acquire_for_task("missing-task", "backtest_training", ["missing-sheet"])
    db.session.commit()

    cleanup_stale_sheet_execution_locks()

    assert sheet_execution_lock_service.find_conflict(["running-sheet"]) == "running-lock-task"
    assert sheet_execution_lock_service.find_conflict(["completed-sheet"]) is None
    assert sheet_execution_lock_service.find_conflict(["missing-sheet"]) is None


def test_ensure_task_result_summary_index_schema_adds_period_key_to_legacy_table(app_factory):
    db.session.execute(
        text(
            """
            CREATE TABLE task_result_summary_index (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id VARCHAR(36) NOT NULL,
                task_result_id INTEGER NOT NULL,
                task_type VARCHAR(50) NOT NULL,
                task_name VARCHAR(255),
                stock_code VARCHAR(64),
                stock_name VARCHAR(255),
                model_key VARCHAR(255) NOT NULL DEFAULT 'default',
                model_name VARCHAR(255),
                year_label VARCHAR(64),
                kline_range VARCHAR(128),
                parameter_summary TEXT,
                best_metric_name VARCHAR(100),
                best_metric_value FLOAT,
                metrics_json TEXT,
                is_best BOOLEAN NOT NULL DEFAULT 0,
                result_timestamp DATETIME,
                created_at DATETIME NOT NULL,
                updated_at DATETIME NOT NULL
            )
            """
        )
    )
    db.session.commit()

    ensure_task_result_summary_index_schema()

    inspector = inspect(db.engine)
    columns = {column["name"] for column in inspector.get_columns("task_result_summary_index")}
    indexes = inspector.get_indexes("task_result_summary_index")

    assert "period_key" in columns
    assert not any(index.get("name") == "idx_result_summary_period_key" for index in indexes)

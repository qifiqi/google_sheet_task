from datetime import datetime, timedelta
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect, text

from app.extensions import db
from app.models import (
    BacktestSheetRunLock,
    Permission,
    Role,
    Task,
    TaskLog,
    TaskResult,
    TaskResultReturn,
    TaskResultSummaryIndex,
    User,
)
from app.services import scheduled_task_worker
from app.services.task.facade import TaskManager
from app.utils.auth import create_access_token


def _headers(user):
    return {"Authorization": f"Bearer {create_access_token(user.id, token_version=user.token_version)}"}


def _create_task_records(task_id="task-1"):
    task = Task(id=task_id, name="task", task_type="backtest_training", config="{}")
    db.session.add(task)
    db.session.flush()
    result = TaskResult(task_id=task.id, step_index=0, parameters="{}", result="{}")
    series = TaskResultReturn(
        task_id=task.id,
        stock_date="[]",
        index_return="[]",
        start_return="[]",
        return_length=0,
    )
    log = TaskLog(task_id=task.id, message="message")
    db.session.add_all([result, series, log])
    db.session.flush()
    summary = TaskResultSummaryIndex(
        task_id=task.id,
        task_result_id=result.id,
        task_type=task.task_type,
        model_key="default",
    )
    db.session.add(summary)
    db.session.commit()
    return task, result, series


def test_models_have_no_foreign_keys_and_keep_relationships(app_factory):
    app = app_factory
    with app.app_context():
        inspector = inspect(db.engine)
        assert all(not inspector.get_foreign_keys(table) for table in inspector.get_table_names())

        permission = Permission(name="管理用户", code="user:manage", group="user")
        role = Role(name="管理员", code="admin", permissions=[permission])
        user = User(username="admin", password_hash="hash", roles=[role])
        db.session.add_all([permission, role, user])
        db.session.flush()
        task = Task(id="task-relations", name="task", created_by_user_id=user.id)
        db.session.add(task)
        db.session.flush()
        result = TaskResult(task_id=task.id, step_index=0, parameters="{}", result="{}")
        db.session.add_all([result, TaskLog(task_id=task.id, message="message"), TaskResultReturn(task_id=task.id)])
        db.session.flush()
        db.session.add(TaskResultSummaryIndex(task_id=task.id, task_result_id=result.id, task_type="google_sheet", model_key="default"))
        db.session.commit()
        db.session.expire_all()

        stored_task = db.session.get(Task, task.id)
        assert stored_task.created_by.username == "admin"
        assert stored_task.logs.count() == 1
        assert stored_task.results.count() == 1
        assert stored_task.returns_return.count() == 1
        assert stored_task.results.first().summary_indexes.count() == 1
        assert db.session.get(User, user.id).roles[0].permissions[0].code == "user:manage"


def test_historical_migrations_do_not_create_foreign_keys():
    migrations_dir = Path(__file__).parents[1] / "migrations" / "versions"
    blocked_calls = ("create_foreign_key(", "ForeignKeyConstraint(", "ForeignKey(")

    for migration_path in migrations_dir.glob("*.py"):
        if migration_path.name == "20260810_remove_fks.py":
            continue
        source = migration_path.read_text(encoding="utf-8")
        assert not any(call in source for call in blocked_calls), migration_path.name


def test_summary_index_does_not_create_duplicate_single_column_indexes(app_factory):
    app = app_factory
    with app.app_context():
        indexes = inspect(db.engine).get_indexes("t_param_task_result_summary_index")
        indexed_columns = [tuple(index["column_names"]) for index in indexes]

        assert indexed_columns.count(("best_metric_value",)) == 1
        assert indexed_columns.count(("created_at",)) == 1


def test_models_omit_unused_and_redundant_indexes(app_factory):
    app = app_factory
    expected_absent_indexes = {
        "t_param_tasks": {"ix_tasks_status", "ix_tasks_task_type"},
        "t_param_task_logs": {"ix_task_logs_task_id", "ix_task_logs_level", "idx_level_timestamp"},
        "t_param_task_results": {"ix_task_results_task_id", "ix_task_results_step_index", "ix_task_results_success"},
        "t_param_backtest_product_result_cache": {
            "ix_backtest_product_result_cache_batch_id",
            "ix_backtest_product_result_cache_cache_key",
            "ix_backtest_product_result_cache_created_at",
            "ix_backtest_product_result_cache_source_task_id",
        },
        "t_param_backtest_sheet_run_locks": {"ix_backtest_sheet_run_locks_spreadsheet_id"},
        "t_param_task_result_summary_index": {
            "ix_task_result_summary_index_task_id",
            "ix_task_result_summary_index_task_result_id",
            "ix_task_result_summary_index_task_type",
            "ix_task_result_summary_index_stock_code",
            "ix_task_result_summary_index_stock_name",
            "ix_task_result_summary_index_year_label",
        },
        "t_param_stock_metadata": {
            "ix_stock_metadata_stock_code",
            "ix_stock_metadata_market_type",
            "ix_stock_metadata_created_at",
            "idx_stock_metadata_name",
            "idx_stock_metadata_exchange_market",
        },
        "t_param_task_templates": {"ix_task_templates_name"},
        "t_param_google_sheet_tokens": {"ix_google_sheet_tokens_is_active"},
        "t_param_google_sheet": {"ix_google_sheet_is_active"},
        "t_param_navigation_menu_items": {"ix_navigation_menu_items_parent_key"},
        "t_param_scheduled_tasks": {
            "idx_active_next_run",
            "idx_type_active",
            "ix_scheduled_tasks_is_running",
            "ix_scheduled_tasks_next_run_time",
        },
    }

    with app.app_context():
        inspector = inspect(db.engine)
        for table_name, unwanted_indexes in expected_absent_indexes.items():
            index_names = {index["name"] for index in inspector.get_indexes(table_name)}
            assert unwanted_indexes.isdisjoint(index_names)





    app = app_factory
    with app.app_context():
        db.session.execute(text("""
            CREATE TABLE xpl_analysis_jobs (
                id INTEGER PRIMARY KEY,
                task_id VARCHAR(36) NOT NULL,
                task_result_id INTEGER NOT NULL,
                return_series_id INTEGER NOT NULL
            )
        """))
        task, result, series = _create_task_records("task-delete")
        task_id = task.id
        db.session.add(BacktestSheetRunLock(spreadsheet_id="sheet-1", task_id=task_id, task_type=task.task_type))
        db.session.execute(text("""
            INSERT INTO xpl_analysis_jobs (task_id, task_result_id, return_series_id)
            VALUES (:task_id, :result_id, :series_id)
        """), {"task_id": task_id, "result_id": result.id, "series_id": series.id})
        db.session.commit()

        assert TaskManager().delete_task(task_id) is True

        # delete_task 在嵌套 app context 的独立 session 中提交，这里清掉本会话缓存后再断言
        db.session.expire_all()
        assert db.session.get(Task, task_id) is None
        assert TaskLog.query.filter_by(task_id=task_id).count() == 0
        assert TaskResult.query.filter_by(task_id=task_id).count() == 0
        assert TaskResultReturn.query.filter_by(task_id=task_id).count() == 0
        assert TaskResultSummaryIndex.query.filter_by(task_id=task_id).count() == 0
        assert BacktestSheetRunLock.query.filter_by(task_id=task_id).count() == 0
        assert db.session.execute(text("SELECT COUNT(*) FROM xpl_analysis_jobs")).scalar() == 0


def test_result_cleanup_clears_summary_and_xpl_dependencies(app_factory, monkeypatch):
    app = app_factory
    monkeypatch.setattr(scheduled_task_worker.time, "sleep", lambda _seconds: None)
    with app.app_context():
        db.session.execute(text("""
            CREATE TABLE xpl_analysis_jobs (
                id INTEGER PRIMARY KEY,
                task_id VARCHAR(36) NOT NULL,
                task_result_id INTEGER NOT NULL,
                return_series_id INTEGER NOT NULL
            )
        """))
        task, result, series = _create_task_records("task-result-cleanup")
        result.timestamp = datetime.now() - timedelta(days=30)
        db.session.execute(text("""
            INSERT INTO xpl_analysis_jobs (task_id, task_result_id, return_series_id)
            VALUES (:task_id, :result_id, :series_id)
        """), {"task_id": task.id, "result_id": result.id, "series_id": series.id})
        db.session.commit()
        task_id = task.id
        result_id = result.id

        assert scheduled_task_worker.cleanup_old_results({"days": 10, "batch_size": 10, "delay": 0}) is True

        assert db.session.get(Task, task_id) is not None
        assert db.session.get(TaskResult, result_id) is None
        assert TaskResultSummaryIndex.query.filter_by(task_result_id=result_id).count() == 0
        assert db.session.execute(text("SELECT COUNT(*) FROM xpl_analysis_jobs")).scalar() == 0


def test_user_and_role_deletion_clear_business_associations(app_factory):
    app = app_factory
    with app.app_context():
        manage = Permission(name="管理用户", code="user:manage", group="user")
        admin_role = Role(name="管理员", code="admin", permissions=[manage])
        admin = User(username="admin", password_hash="hash", token_version=0, roles=[admin_role])
        creator = User(username="creator", password_hash="hash")
        removable_role = Role(name="临时角色", code="temporary")
        creator.roles = [removable_role]
        db.session.add_all([manage, admin_role, admin, creator, removable_role])
        db.session.flush()
        db.session.add(Task(id="task-created", name="task", created_by_user_id=creator.id))
        db.session.commit()
        creator_id = creator.id
        removable_role_id = removable_role.id

        client = app.test_client()
        response = client.delete(f"/api/admin/users/{creator_id}", headers=_headers(admin))
        assert response.status_code == 200
        assert db.session.get(Task, "task-created").created_by_user_id is None
        assert db.session.execute(text("SELECT COUNT(*) FROM t_param_user_roles WHERE user_id = :user_id"), {"user_id": creator_id}).scalar() == 0

        response = client.delete(f"/api/admin/roles/{removable_role_id}", headers=_headers(admin))
        assert response.status_code == 200
        assert db.session.execute(text("SELECT COUNT(*) FROM t_param_user_roles WHERE role_id = :role_id"), {"role_id": removable_role_id}).scalar() == 0
        assert db.session.execute(text("SELECT COUNT(*) FROM t_param_role_permissions WHERE role_id = :role_id"), {"role_id": removable_role_id}).scalar() == 0

import os

from sqlalchemy import inspect, text

from app.extensions import db
from app.models import (
    BacktestProductResultCache,
    BacktestSheetRunLock,
    GoogleSheetToken,
    NavigationMenuItem,
    ScheduledTask,
    StockMetadata,
    SystemConfig,
    Task,
    TaskLog,
    TaskResult,
    TaskResultSummaryIndex,
    XplAnalysisJob,
)
from app.utils.logger import get_logger, initialize_logging


def ensure_google_sheet_token_schema():
    inspector = inspect(db.engine)
    if 'google_sheet_tokens' not in inspector.get_table_names():
        return
    columns = {column['name'] for column in inspector.get_columns('google_sheet_tokens')}
    if 'current_in_use_count' not in columns:
        db.session.execute(
            text('ALTER TABLE google_sheet_tokens ADD COLUMN current_in_use_count INTEGER NOT NULL DEFAULT 0')
        )
        db.session.commit()


def ensure_user_schema():
    inspector = inspect(db.engine)
    if 'user' not in inspector.get_table_names():
        return
    columns = {column['name'] for column in inspector.get_columns('user')}
    if 'token_version' not in columns:
        db.session.execute(text('ALTER TABLE "user" ADD COLUMN token_version INTEGER NOT NULL DEFAULT 0'))
    if 'mobile' not in columns:
        db.session.execute(text('ALTER TABLE "user" ADD COLUMN mobile VARCHAR(32)'))
    if 'is_alert_oncall' not in columns:
        db.session.execute(text('ALTER TABLE "user" ADD COLUMN is_alert_oncall BOOLEAN NOT NULL DEFAULT 0'))
    db.session.commit()


def ensure_task_schema():
    inspector = inspect(db.engine)
    if 'tasks' not in inspector.get_table_names():
        return
    columns = {column['name'] for column in inspector.get_columns('tasks')}
    if 'created_by_user_id' not in columns:
        db.session.execute(text('ALTER TABLE tasks ADD COLUMN created_by_user_id INTEGER'))
        db.session.commit()
        indexes = {index['name'] for index in inspector.get_indexes('tasks')}
        if 'ix_tasks_created_by_user_id' not in indexes:
            db.session.execute(text('CREATE INDEX ix_tasks_created_by_user_id ON tasks (created_by_user_id)'))
            db.session.commit()


def ensure_task_result_schema():
    inspector = inspect(db.engine)
    if 'task_results' not in inspector.get_table_names():
        return
    columns = {column['name'] for column in inspector.get_columns('task_results')}
    if 'return_series_id' not in columns:
        db.session.execute(text('ALTER TABLE task_results ADD COLUMN return_series_id INTEGER'))
        db.session.commit()
    indexes = {index['name'] for index in inspector.get_indexes('task_results')}
    if 'ix_task_results_return_series_id' not in indexes:
        db.session.execute(text('CREATE INDEX ix_task_results_return_series_id ON task_results (return_series_id)'))
        db.session.commit()


def ensure_scheduled_task_schema():
    inspector = inspect(db.engine)
    if 'scheduled_tasks' not in inspector.get_table_names():
        return

    columns = {column['name'] for column in inspector.get_columns('scheduled_tasks')}
    changed = False
    if 'is_running' not in columns:
        db.session.execute(
            text('ALTER TABLE scheduled_tasks ADD COLUMN is_running BOOLEAN NOT NULL DEFAULT FALSE')
        )
        changed = True
    if 'running_instance_id' not in columns:
        db.session.execute(text('ALTER TABLE scheduled_tasks ADD COLUMN running_instance_id VARCHAR(100)'))
        changed = True
    if changed:
        db.session.commit()

    indexes = inspector.get_indexes('scheduled_tasks')
    has_is_running_index = any(
        index.get('column_names') == ['is_running']
        for index in indexes
    )
    if not has_is_running_index:
        db.session.execute(text('CREATE INDEX ix_scheduled_tasks_is_running ON scheduled_tasks (is_running)'))
    db.session.commit()


def ensure_task_result_summary_index_schema():
    inspector = inspect(db.engine)
    if 'task_result_summary_index' not in inspector.get_table_names():
        TaskResultSummaryIndex.__table__.create(db.engine)
        return
    columns = {column['name'] for column in inspector.get_columns('task_result_summary_index')}
    changed = False
    if 'stock_name' not in columns:
        db.session.execute(text('ALTER TABLE task_result_summary_index ADD COLUMN stock_name VARCHAR(255)'))
        changed = True
    if 'period_key' not in columns:
        db.session.execute(text('ALTER TABLE task_result_summary_index ADD COLUMN period_key VARCHAR(32)'))
        changed = True
    if changed:
        db.session.commit()
    indexes = {index['name'] for index in inspector.get_indexes('task_result_summary_index')}
    if 'ix_task_result_summary_index_stock_name' not in indexes:
        db.session.execute(text('CREATE INDEX ix_task_result_summary_index_stock_name ON task_result_summary_index (stock_name)'))
        db.session.commit()
    if 'idx_result_summary_period_key' not in indexes:
        db.session.execute(text('CREATE INDEX idx_result_summary_period_key ON task_result_summary_index (period_key)'))
        db.session.commit()


def ensure_stock_metadata_schema():
    inspector = inspect(db.engine)
    if 'stock_metadata' not in inspector.get_table_names():
        StockMetadata.__table__.create(db.engine)


def ensure_backtest_runtime_schema():
    inspector = inspect(db.engine)
    table_names = set(inspector.get_table_names())
    if 'backtest_product_result_cache' not in table_names:
        BacktestProductResultCache.__table__.create(db.engine)
    if 'backtest_sheet_run_locks' not in table_names:
        BacktestSheetRunLock.__table__.create(db.engine)


def ensure_task_result_return_schema():
    inspector = inspect(db.engine)
    if 'task_results_return' not in inspector.get_table_names():
        return
    columns = {column['name'] for column in inspector.get_columns('task_results_return')}
    if 'returns_json' not in columns:
        db.session.execute(text('ALTER TABLE task_results_return ADD COLUMN returns_json TEXT'))
        db.session.commit()


def ensure_xpl_analysis_job_schema():
    inspector = inspect(db.engine)
    if 'xpl_analysis_jobs' not in inspector.get_table_names():
        XplAnalysisJob.__table__.create(db.engine)
        return

    indexes = {index['name'] for index in inspector.get_indexes('xpl_analysis_jobs')}
    if 'idx_xpl_jobs_status_created' not in indexes:
        db.session.execute(
            text('CREATE INDEX idx_xpl_jobs_status_created ON xpl_analysis_jobs (status, created_at)')
        )
        db.session.commit()
    if 'idx_xpl_jobs_task_status' not in indexes:
        db.session.execute(
            text('CREATE INDEX idx_xpl_jobs_task_status ON xpl_analysis_jobs (task_id, status)')
        )
        db.session.commit()


def ensure_navigation_menu_schema():
    inspector = inspect(db.engine)
    if 'navigation_menu_items' not in inspector.get_table_names():
        NavigationMenuItem.__table__.create(db.engine)
        return

    columns = {column['name'] for column in inspector.get_columns('navigation_menu_items')}
    column_definitions = {
        'key': 'VARCHAR(100) NOT NULL',
        'label': 'VARCHAR(100) NOT NULL DEFAULT \'\'',
        'path': 'VARCHAR(255)',
        'permission': 'VARCHAR(100)',
        'parent_key': 'VARCHAR(100)',
        'sort_order': 'INTEGER NOT NULL DEFAULT 0',
        'is_visible': 'BOOLEAN NOT NULL DEFAULT 1',
        'created_at': 'DATETIME',
        'updated_at': 'DATETIME',
    }
    changed = False
    for column_name, definition in column_definitions.items():
        if column_name not in columns:
            db.session.execute(text(f'ALTER TABLE navigation_menu_items ADD COLUMN {column_name} {definition}'))
            changed = True
    if changed:
        db.session.commit()

    indexes = {index['name'] for index in inspector.get_indexes('navigation_menu_items')}
    if 'idx_navigation_menu_parent_sort' not in indexes:
        db.session.execute(
            text('CREATE INDEX idx_navigation_menu_parent_sort ON navigation_menu_items (parent_key, sort_order)')
        )
    if 'ix_navigation_menu_items_parent_key' not in indexes:
        db.session.execute(text('CREATE INDEX ix_navigation_menu_items_parent_key ON navigation_menu_items (parent_key)'))
    if 'ix_navigation_menu_items_is_visible' not in indexes:
        db.session.execute(text('CREATE INDEX ix_navigation_menu_items_is_visible ON navigation_menu_items (is_visible)'))
    db.session.commit()


def reset_google_sheet_token_occupancy():
    if GoogleSheetToken.query.filter(GoogleSheetToken.current_in_use_count != 0).count() > 0:
        GoogleSheetToken.query.update({'current_in_use_count': 0}, synchronize_session=False)
        db.session.commit()


def reset_google_sheet_occupancy():
    from app.models import GoogleSheet

    if GoogleSheet.query.filter(GoogleSheet.is_in_use == True).count() > 0:
        GoogleSheet.query.update({'is_in_use': False, 'current_task_id': None}, synchronize_session=False)
        db.session.commit()


def cleanup_stale_backtest_sheet_run_locks():
    stale_locks = (
        BacktestSheetRunLock.query.outerjoin(Task, BacktestSheetRunLock.task_id == Task.id)
        .filter((Task.id.is_(None)) | (Task.status != 'running'))
        .all()
    )
    if not stale_locks:
        return
    for lock in stale_locks:
        db.session.delete(lock)
    db.session.commit()


def register_shell_context(app):
    @app.shell_context_processor
    def make_shell_context():
        return {
            'db': db,
            'Task': Task,
            'TaskLog': TaskLog,
            'TaskResult': TaskResult,
            'SystemConfig': SystemConfig,
            'ScheduledTask': ScheduledTask,
            'GoogleSheetToken': GoogleSheetToken,
            'BacktestProductResultCache': BacktestProductResultCache,
            'BacktestSheetRunLock': BacktestSheetRunLock,
        }


def register_cli(app):
    @app.cli.command()
    def init_db():
        db.create_all()
        ensure_google_sheet_token_schema()
        ensure_user_schema()
        ensure_task_schema()
        ensure_task_result_schema()
        ensure_scheduled_task_schema()
        ensure_task_result_return_schema()
        ensure_task_result_summary_index_schema()
        ensure_xpl_analysis_job_schema()
        ensure_stock_metadata_schema()
        ensure_backtest_runtime_schema()
        ensure_navigation_menu_schema()
        print('数据库初始化完成')

    @app.cli.command()
    def init_default_config():
        from app.seed_data import seed_default_data

        seed_default_data(app)
        print('默认配置、权限、导航菜单和定时任务初始化完成')


def check_and_cleanup_dead_tasks(app):
    from app.services.task import task_manager

    logger = get_logger('startup')
    with app.app_context():
        try:
            running_tasks = Task.query.filter_by(status='running').all()
            for task in running_tasks:
                status_check = task_manager.check_local_task_status(task.id)
                if not status_check.get('can_restart'):
                    continue
                task.status = 'pending'
                task.error_message = None
                task.end_time = None
                task_manager.add_task_log(
                    task.id,
                    'info',
                    f"应用重启时检测到任务中断，已重置为待启动状态: {status_check.get('restart_reason')}",
                )
            db.session.commit()
        except Exception as exc:
            logger.error(f'检查任务状态时出错: {exc}')


def init_scheduler(app):
    from app.services.scheduler_service import scheduler_service

    logger = get_logger('scheduler')
    with app.app_context():
        try:
            scheduler_service.start(delay_seconds=30, app=app)
            logger.info('定时任务调度器初始化完成')
        except Exception as exc:
            logger.error(f'初始化定时任务调度器失败: {exc}')


def init_task_watchdog(app):
    from app.services.task_watchdog import task_watchdog

    logger = get_logger('watchdog')
    try:
        task_watchdog.start(app)
        logger.info('任务看门狗线程已启动')
    except Exception as exc:
        logger.error(f'启动任务看门狗线程失败: {exc}')


def bootstrap_app(app):
    os.makedirs('data', exist_ok=True)
    os.makedirs('logs', exist_ok=True)
    initialize_logging()
    with app.app_context():
        db.create_all()
        ensure_google_sheet_token_schema()
        ensure_user_schema()
        ensure_task_schema()
        ensure_task_result_schema()
        ensure_scheduled_task_schema()
        ensure_task_result_return_schema()
        ensure_task_result_summary_index_schema()
        ensure_xpl_analysis_job_schema()
        ensure_stock_metadata_schema()
        ensure_backtest_runtime_schema()
        ensure_navigation_menu_schema()
        reset_google_sheet_token_occupancy()
        reset_google_sheet_occupancy()
        cleanup_stale_backtest_sheet_run_locks()
    check_and_cleanup_dead_tasks(app)
    init_scheduler(app)
    init_task_watchdog(app)

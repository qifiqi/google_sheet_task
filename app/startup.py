"""应用进程启动编排与历史数据库兼容处理。

数据库结构的长期来源应是 Alembic migration。这里的 ``ensure_*`` 函数仅用于
兼容尚未完成迁移的历史数据库，避免服务因为缺少新增列或索引而无法启动。
"""

import json
import os

from sqlalchemy import Boolean, String, Text, cast, case, func, inspect, text, update
from werkzeug.security import generate_password_hash

from app.config import PERMISSIONS, init_config
from app.extensions import db
from app.models import (
    BacktestProductResultCache,
    BacktestSheetRunLock,
    GoogleSheetToken,
    NavigationMenuItem,
    Permission,
    Role,
    ScheduledTask,
    StockMetadata,
    SystemConfig,
    Task,
    TaskLog,
    TaskResult,
    TaskResultSummaryIndex,
    User,
)
from app.navigation import (
    DEFAULT_NAVIGATION_MENU,
    flatten_navigation_items,
    sync_navigation_permissions,
)
from app.utils.logger import get_logger, initialize_logging


def _quoted_identifier(name):
    return db.engine.dialect.identifier_preparer.quote(name)


def _add_column(table_name, column_name, definition):
    db.session.execute(
        text(
            f"ALTER TABLE {_quoted_identifier(table_name)} "
            f"ADD COLUMN {_quoted_identifier(column_name)} {definition}"
        )
    )


def _ensure_model_index(model, index_name):
    index = next(index for index in model.__table__.indexes if index.name == index_name)
    index.create(db.engine, checkfirst=True)


def normalize_boolean_columns():
    """Normalize boolean values imported from databases with text booleans."""
    inspector = inspect(db.engine)
    existing_tables = set(inspector.get_table_names())
    true_values = ('1', 't', 'true', 'y', 'yes', 'on')
    false_values = ('0', 'f', 'false', 'n', 'no', 'off')

    for table in db.metadata.tables.values():
        if table.name not in existing_tables:
            continue
        existing_columns = {column['name'] for column in inspector.get_columns(table.name)}
        for column in table.columns:
            if not isinstance(column.type, Boolean) or column.name not in existing_columns:
                continue
            normalized = func.lower(func.trim(cast(column, String(8))))
            value = case(
                (column.is_(None), None),
                (normalized.in_(true_values), True),
                (normalized.in_(false_values), False),
                else_=column,
            )
            db.session.execute(update(table).values({column: value}))
    db.session.commit()


def ensure_google_sheet_token_schema():
    inspector = inspect(db.engine)
    if 'google_sheet_tokens' not in inspector.get_table_names():
        return
    columns = {column['name'] for column in inspector.get_columns('google_sheet_tokens')}
    if 'current_in_use_count' not in columns:
        _add_column('google_sheet_tokens', 'current_in_use_count', 'INTEGER NOT NULL DEFAULT 0')
        db.session.commit()


def ensure_google_sheet_registry_schema():
    """Apply the portable Google Sheet registry uniqueness rule."""
    inspector = inspect(db.engine)
    if 'google_sheet' not in inspector.get_table_names():
        return

    columns = {column['name'] for column in inspector.get_columns('google_sheet')}
    if 'registry_scope' not in columns:
        _add_column('google_sheet', 'registry_scope', 'VARCHAR(32)')

    from app.models import GoogleSheet, google_sheet_registry_scope

    for sheet in GoogleSheet.query.all():
        sheet.registry_scope = google_sheet_registry_scope(sheet.table_type)
    db.session.commit()

    current_inspector = inspect(db.engine)
    index_names = {index['name'] for index in current_inspector.get_indexes('google_sheet')}
    index_names.update(
        constraint['name']
        for constraint in current_inspector.get_unique_constraints('google_sheet')
        if constraint.get('name')
    )
    if 'uk_google_sheet_spreadsheet_registry_scope' not in index_names:
        # The model expresses this rule as a UniqueConstraint, while the
        # migration creates a named unique index.  Build the index directly
        # so legacy databases can be repaired without assuming either shape.
        registry_index = db.Index(
            'uk_google_sheet_spreadsheet_registry_scope',
            GoogleSheet.__table__.c.spreadsheet_id,
            GoogleSheet.__table__.c.registry_scope,
            unique=True,
        )
        registry_index.create(db.engine, checkfirst=True)


def ensure_user_schema():
    inspector = inspect(db.engine)
    if 'user' not in inspector.get_table_names():
        return
    columns = {column['name'] for column in inspector.get_columns('user')}
    if 'token_version' not in columns:
        _add_column('user', 'token_version', 'INTEGER NOT NULL DEFAULT 0')
    if 'mobile' not in columns:
        _add_column('user', 'mobile', 'VARCHAR(32)')
    if 'is_alert_oncall' not in columns:
        _add_column('user', 'is_alert_oncall', 'BOOLEAN NOT NULL DEFAULT FALSE')
    db.session.commit()


def ensure_task_schema():
    inspector = inspect(db.engine)
    if 'tasks' not in inspector.get_table_names():
        return
    columns = {column['name'] for column in inspector.get_columns('tasks')}
    if 'created_by_user_id' not in columns:
        _add_column('tasks', 'created_by_user_id', 'INTEGER')
        db.session.commit()
        _ensure_model_index(Task, 'ix_tasks_created_by_user_id')
        db.session.commit()


def ensure_task_result_schema():
    inspector = inspect(db.engine)
    if 'task_results' not in inspector.get_table_names():
        return
    columns = {column['name'] for column in inspector.get_columns('task_results')}
    if 'return_series_id' not in columns:
        _add_column('task_results', 'return_series_id', 'INTEGER')
        db.session.commit()
    # ix_task_results_return_series_id 已随 20260905_drop_return_series_idx 迁移移除
    # （零查询引用，见 docs/design/api-model-query-audit/02 §3），不再启动期补建。
    db.session.commit()


def ensure_scheduled_task_schema():
    inspector = inspect(db.engine)
    if 'scheduled_tasks' not in inspector.get_table_names():
        return

    columns = {column['name'] for column in inspector.get_columns('scheduled_tasks')}
    changed = False
    if 'is_running' not in columns:
        _add_column('scheduled_tasks', 'is_running', 'BOOLEAN NOT NULL DEFAULT FALSE')
        changed = True
    if 'running_instance_id' not in columns:
        _add_column('scheduled_tasks', 'running_instance_id', 'VARCHAR(100)')
        changed = True
    if changed:
        db.session.commit()


def ensure_task_result_summary_index_schema():
    inspector = inspect(db.engine)
    if 'task_result_summary_index' not in inspector.get_table_names():
        TaskResultSummaryIndex.__table__.create(db.engine, checkfirst=True)
        return
    columns = {column['name'] for column in inspector.get_columns('task_result_summary_index')}
    changed = False
    if 'stock_name' not in columns:
        _add_column('task_result_summary_index', 'stock_name', 'VARCHAR(255)')
        changed = True
    if 'period_key' not in columns:
        _add_column('task_result_summary_index', 'period_key', 'VARCHAR(32)')
        changed = True
    if 'market_type' not in columns:
        _add_column('task_result_summary_index', 'market_type', 'VARCHAR(8)')
        changed = True
    if changed:
        db.session.commit()
    from app.models import summary_market_type

    for item in TaskResultSummaryIndex.query.filter(
        (TaskResultSummaryIndex.market_type.is_(None))
        | (TaskResultSummaryIndex.market_type == "")
    ).all():
        item.market_type = summary_market_type(item.stock_code)
    db.session.commit()
    indexes = {index['name'] for index in inspector.get_indexes('task_result_summary_index')}
    if 'idx_result_summary_type_market_best' not in indexes:
        market_index = next(
            index
            for index in TaskResultSummaryIndex.__table__.indexes
            if index.name == 'idx_result_summary_type_market_best'
        )
        market_index.create(db.engine, checkfirst=True)


def ensure_stock_metadata_schema():
    inspector = inspect(db.engine)
    if 'stock_metadata' not in inspector.get_table_names():
        StockMetadata.__table__.create(db.engine,checkfirst=True)


def ensure_backtest_runtime_schema():
    inspector = inspect(db.engine)
    table_names = set(inspector.get_table_names())
    if 'backtest_product_result_cache' not in table_names:
        BacktestProductResultCache.__table__.create(db.engine, checkfirst=True)
    if 'backtest_sheet_run_locks' not in table_names:
        BacktestSheetRunLock.__table__.create(db.engine, checkfirst=True)


def ensure_task_result_return_schema():
    """补齐老库的收益序列拆分字段；旧 returns_json 不再写入。"""
    inspector = inspect(db.engine)
    table_name = next(
        (name for name in ("t_param_task_results_return", "task_results_return")
         if name in inspector.get_table_names()),
        None,
    )
    if not table_name:
        return
    columns = {column["name"] for column in inspector.get_columns(table_name)}
    definitions = {
        "stock_code": "VARCHAR(20)",
        "stock_name": "VARCHAR(20)",
        "start_return_date": "DATE",
        "end_return_date": "DATE",
        "return_length": "INTEGER",
    }
    changed = False
    for name, definition in definitions.items():
        if name not in columns:
            _add_column(table_name, name, definition)
            changed = True
    if changed:
        db.session.commit()


def ensure_task_log_schema():
    """兼容旧库，将任务日志内容列升级为 TEXT。"""
    inspector = inspect(db.engine)
    table_name = "t_param_task_logs"
    if table_name not in inspector.get_table_names():
        return

    message_column = next(
        (column for column in inspector.get_columns(table_name) if column["name"] == "message"),
        None,
    )
    if message_column is None or isinstance(message_column["type"], Text):
        return

    quoted_table = _quoted_identifier(table_name)
    quoted_column = _quoted_identifier("message")
    dialect_name = db.engine.dialect.name
    if dialect_name == "mysql":
        db.session.execute(text(
            f"ALTER TABLE {quoted_table} MODIFY COLUMN {quoted_column} TEXT NOT NULL"
        ))
    elif dialect_name == "postgresql":
        db.session.execute(text(
            f"ALTER TABLE {quoted_table} ALTER COLUMN {quoted_column} TYPE TEXT"
        ))
    else:
        return
    db.session.commit()


def ensure_task_result_payload_schema():
    """兼容旧 MySQL 库，扩大任务结果 JSON 字段容量。"""
    inspector = inspect(db.engine)
    table_name = "t_param_task_results"
    if table_name not in inspector.get_table_names():
        return

    columns = {
        column["name"]: column
        for column in inspector.get_columns(table_name)
    }
    dialect_name = db.engine.dialect.name
    if dialect_name == "mysql":
        payload_columns = [name for name in ("result", "parameters") if name in columns]
        if not payload_columns:
            return
        needs_upgrade = any(
            str(columns[name]["type"]).upper() not in {"MEDIUMTEXT", "LONGTEXT"}
            for name in payload_columns
        )
        if needs_upgrade:
            clauses = ", ".join(
                f"MODIFY COLUMN {_quoted_identifier(name)} MEDIUMTEXT NULL"
                for name in payload_columns
            )
            db.session.execute(text(
                f"ALTER TABLE {_quoted_identifier(table_name)} {clauses}"
            ))
    elif dialect_name == "postgresql":
        for name in ("result", "parameters", "error_message"):
            if name in columns and not isinstance(columns[name]["type"], Text):
                db.session.execute(text(
                    f"ALTER TABLE {_quoted_identifier(table_name)} "
                    f"ALTER COLUMN {_quoted_identifier(name)} TYPE TEXT"
                ))
    else:
        return
    db.session.commit()


def ensure_navigation_menu_schema():
    inspector = inspect(db.engine)
    if 'navigation_menu_items' not in inspector.get_table_names():
        NavigationMenuItem.__table__.create(db.engine, checkfirst=True)
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
        'created_at': 'TIMESTAMP',
        'updated_at': 'TIMESTAMP',
    }
    changed = False
    for column_name, definition in column_definitions.items():
        if column_name not in columns:
            _add_column('navigation_menu_items', column_name, definition)
            changed = True
    if changed:
        db.session.commit()

    _ensure_model_index(NavigationMenuItem, 'idx_navigation_menu_parent_sort')
    _ensure_model_index(NavigationMenuItem, 'ix_navigation_menu_items_is_visible')
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
    """注册 ``flask shell`` 的快捷对象；不会访问数据库或启动后台线程。"""
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
    """注册显式执行的运维命令；注册命令本身不初始化数据库。"""
    @app.cli.command()
    def init_db():
        # Flask CLI 会自动提供 app context，因此这里可以复用完整 schema 初始化。
        _initialize_database_schema()
        print('数据库初始化完成')

    @app.cli.command()
    def init_default_config():
        init_config()
        print('默认配置初始化完成')


def init_rbac():
    """幂等同步内置权限、角色及首次安装的管理员账号。"""
    logger = get_logger('rbac')

    for group, code, name, route_path in PERMISSIONS:
        perm = Permission.query.filter_by(code=code).first()
        if not perm:
            db.session.add(Permission(group=group, code=code, name=name, route_path=route_path))
        elif perm.route_path != route_path:
            perm.route_path = route_path
    db.session.commit()

    # 接口级细粒度权限已移除，只保留页面权限（page:*）；
    # 这里幂等清理历史遗留的非 page 权限行及其角色关联。
    legacy_permissions = Permission.query.filter(~Permission.code.like('page:%')).all()
    if legacy_permissions:
        for role in Role.query.all():
            role.permissions = [p for p in role.permissions if p.code.startswith('page:')]
        for perm in legacy_permissions:
            db.session.delete(perm)
        db.session.commit()
        logger.info('已清理 %d 个历史接口级权限', len(legacy_permissions))

    admin_role = Role.query.filter_by(code='admin').first()
    if not admin_role:
        admin_role = Role(name='管理员', code='admin', description='系统管理员，拥有全部权限', is_system=True)
        db.session.add(admin_role)
        db.session.commit()
    admin_role.permissions = Permission.query.all()
    db.session.commit()

    developer_role = Role.query.filter_by(code='developer').first()
    if not developer_role:
        db.session.add(Role(
            name='开发',
            code='developer',
            description='开发内置角色，用于值班与告警筛选',
            is_system=True,
        ))
        db.session.commit()

    if not User.query.filter_by(username='admin').first():
        admin_user = User(
            username='admin',
            password_hash=generate_password_hash('admin123'),
            is_active=True,
        )
        admin_user.roles = [admin_role]
        db.session.add(admin_user)
        db.session.commit()
        logger.info('已创建默认管理员用户 admin / admin123')

def init_navigation_menu():
    """幂等写入默认导航，并兼容旧版 ``nav_menu`` 系统配置。"""
    logger = get_logger('navigation')
    nav_config = SystemConfig.query.filter_by(key='nav_menu').first()
    has_existing_items = NavigationMenuItem.query.count() > 0
    source_menu = DEFAULT_NAVIGATION_MENU
    should_seed_missing = not has_existing_items

    if nav_config and nav_config.value:
        try:
            nav_data = json.loads(nav_config.value)
            if isinstance(nav_data, list) and nav_data:
                source_menu = nav_data
                should_seed_missing = True
        except (TypeError, ValueError):
            logger.warning('旧 system_configs.nav_menu 解析失败，将使用默认导航菜单初始化')

    default_rows = flatten_navigation_items(source_menu)
    permission_map = _build_nav_permission_map()
    existing = {item.key: item for item in NavigationMenuItem.query.all()}

    if has_existing_items and not should_seed_missing:
        _normalize_existing_navigation_menu()
        _seed_missing_default_navigation_items(default_rows, permission_map, existing)
        sync_navigation_permissions(NavigationMenuItem.query.all())
        if nav_config:
            db.session.delete(nav_config)
        db.session.commit()
        return

    for row in default_rows:
        key = row.get('key')
        if not key:
            continue

        path = _normalize_nav_path(row.get('path'))
        expected_permission = permission_map.get(path) or row.get('permission')
        item = existing.get(key)
        if not item:
            db.session.add(NavigationMenuItem(
                key=key,
                label=_normalize_nav_label(key, row.get('label') or key),
                path=path,
                permission=expected_permission,
                parent_key=row.get('parent_key'),
                sort_order=row.get('sort_order') or 0,
                is_visible=True,
            ))
            continue

        if nav_config:
            item.label = _normalize_nav_label(key, row.get('label') or item.label)
            item.path = path
            item.permission = expected_permission
            item.parent_key = row.get('parent_key')
            item.sort_order = row.get('sort_order') or 0

    if nav_config:
        db.session.delete(nav_config)

    sync_navigation_permissions(NavigationMenuItem.query.all())
    db.session.commit()


def _seed_missing_default_navigation_items(default_rows, permission_map, existing):
    for row in default_rows:
        key = row.get('key')
        if not key or key in existing:
            continue
        path = _normalize_nav_path(row.get('path'))
        db.session.add(NavigationMenuItem(
            key=key,
            label=_normalize_nav_label(key, row.get('label') or key),
            path=path,
            permission=permission_map.get(path) or row.get('permission'),
            parent_key=row.get('parent_key'),
            sort_order=row.get('sort_order') or 0,
            is_visible=True,
        ))


def _normalize_existing_navigation_menu():
    permission_map = _build_nav_permission_map()
    default_rows = {
        row.get('key'): row
        for row in flatten_navigation_items(DEFAULT_NAVIGATION_MENU)
        if row.get('key')
    }
    for item in NavigationMenuItem.query.all():
        item.path = _normalize_nav_path(item.path)
        default_row = default_rows.get(item.key)
        item.label = _normalize_nav_label(
            item.key,
            default_row.get('label') if default_row else item.label,
        )
        if default_row:
            item.parent_key = default_row.get('parent_key')
            item.sort_order = default_row.get('sort_order') or 0
            if default_row.get('path'):
                item.path = _normalize_nav_path(default_row.get('path'))
        expected_permission = permission_map.get(item.path)
        if expected_permission:
            item.permission = expected_permission


def _build_nav_permission_map():
    return {
        '/admin': 'page:admin:dashboard',
        '/admin/': 'page:admin:dashboard',
        '/admin/tasks': 'page:admin:tasks',
        '/admin/templates': 'page:admin:templates',
        '/admin/results': 'page:admin:results',
        '/admin/model-summary': 'page:admin:model_summary',
        '/admin/scheduler': 'page:admin:scheduler',
        '/admin/config': 'page:admin:config',
        '/admin/navigation': 'page:admin:navigation',
        '/admin/google-sheets': 'page:admin:google_sheets',
        '/admin/logs': 'page:admin:logs',
        '/admin/users': 'page:admin:users',
        '/admin/roles': 'page:admin:roles',
        '/task/list?version=c3': 'page:google_sheet:c3',
        '/task/list?version=c4': 'page:google_sheet:c4',
        '/task/list?version=c5': 'page:google_sheet:c5',
        '/task/create/c3': 'page:google_sheet:c3',
        '/task/create/c4': 'page:google_sheet:c4',
        '/task/create/c5': 'page:google_sheet:c5',
        '/google-sheet/?version=c3': 'page:google_sheet:c3',
        '/google-sheet/?version=c4': 'page:google_sheet:c4',
        '/google-sheet/?version=c5': 'page:google_sheet:c5',
        '/google-sheet/?version=c31': 'page:google_sheet:c3',
        '/backtest/list': 'page:backtest:list',
        '/backtest-training/list': 'page:backtest:list',
        '/backtest/create': 'page:backtest:create',
        '/backtest-training/create': 'page:backtest:create',
        '/backtest-multi/list': 'page:backtest_multi_product:list',
        '/backtest-multi/create': 'page:backtest_multi_product:create',
        '/backtest-multi-product/list': 'page:backtest_multi_product:list',
        '/backtest-multi-product/create': 'page:backtest_multi_product:create',
        '/global-preview/c7_0_3': 'page:global_preview:c7_0_3',
    }


def _normalize_nav_path(path):
    legacy_path_map = {
        '/task/list?version=c3': '/google-sheet/?version=c3',
        '/task/list?version=c4': '/google-sheet/?version=c4',
        '/task/list?version=c5': '/google-sheet/?version=c5',
        '/task/create': '/google-sheet/create',
        '/task/create/c3': '/google-sheet/?version=c3',
        '/task/create/c4': '/google-sheet/?version=c4',
        '/task/create/c5': '/google-sheet/?version=c5',
        '/backtest/list': '/backtest-training/list',
        '/backtest/create': '/backtest-training/create',
        '/backtest-multi/list': '/backtest-multi-product/list',
        '/backtest-multi/create': '/backtest-multi-product/create',
    }
    return legacy_path_map.get(path, path)


def _normalize_nav_label(key, label):
    if key == 'backtest' and label == '数据回测':
        return '单品数据回测'
    return label


def check_and_cleanup_dead_tasks(app):
    """将本进程不存在的运行中任务标记为待恢复状态。

    ``TaskManager.running_tasks`` 是进程内内存状态；Web 进程重启后必须以数据库
    任务状态为准重新协调，不能继续把这些任务视为仍在执行。
    """
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
    """启动调度器并确保默认清理任务存在。

    调度器是进程内单例，同一数据库同一时刻只能由一个 serving worker 启动。
    """
    from app.services.scheduler_service import scheduler_service

    logger = get_logger('scheduler')
    with app.app_context():
        try:
            scheduler_service.start(delay_seconds=30, app=app)
            scheduler_service.create_default_tasks()
            logger.info('定时任务调度器初始化完成')
        except Exception as exc:
            logger.error(f'初始化定时任务调度器失败: {exc}')


def init_task_watchdog(app):
    """启动进程内任务看门狗；多 worker/多副本会产生重复巡检。"""
    from app.services.task_watchdog import task_watchdog

    logger = get_logger('watchdog')
    try:
        task_watchdog.start(app)
        logger.info('任务看门狗线程已启动')
    except Exception as exc:
        logger.error(f'启动任务看门狗线程失败: {exc}')


def _prepare_runtime_directories():
    """创建运行时目录，供日志和本地 token/临时数据使用。"""
    os.makedirs('data', exist_ok=True)
    os.makedirs('logs', exist_ok=True)


def _initialize_database_schema():
    """创建缺失表并执行历史数据库的增量兼容修补。

    部署环境应先执行 ``flask db upgrade``。在全部历史库完成迁移前，此函数保留
    ``db.create_all`` 与 ``ensure_*`` 作为兼容兜底；不要在业务代码中调用它。
    调用方必须已处于 Flask app context 中。
    """
    db.create_all()
    normalize_boolean_columns()

    # 顺序保持与旧 bootstrap 一致，避免历史库修补之间产生依赖变化。
    for schema_repair in (
        ensure_google_sheet_token_schema,
        ensure_google_sheet_registry_schema,
        ensure_user_schema,
        ensure_task_schema,
        ensure_task_result_schema,
        ensure_scheduled_task_schema,
        ensure_task_result_return_schema,
        ensure_task_log_schema,
        ensure_task_result_payload_schema,
        ensure_task_result_summary_index_schema,
        ensure_stock_metadata_schema,
        ensure_backtest_runtime_schema,
        ensure_navigation_menu_schema,
    ):
        schema_repair()


def _recover_runtime_resources():
    """清理上一个进程遗留的 token、Sheet 占用和回测锁。

    这些字段代表进程内执行状态，不是应被永久保留的业务数据。
    """
    reset_google_sheet_token_occupancy()
    reset_google_sheet_occupancy()
    cleanup_stale_backtest_sheet_run_locks()


def _initialize_system_metadata():
    """幂等初始化运行必需的配置、RBAC 和导航元数据。"""
    init_config()
    init_rbac()
    init_navigation_menu()


def _start_background_components(app):
    """启动依赖当前 Flask 进程的后台组件。"""
    init_scheduler(app)
    init_task_watchdog(app)


def bootstrap_app(app):
    """完成 serving worker 的启动准备。

    此函数会启动调度器和看门狗等进程内线程，因此只能在一个 Gunicorn worker
    （且一个部署副本）中调用一次。数据库 migration 应在容器启动前单独完成。
    """
    _prepare_runtime_directories()
    initialize_logging()

    with app.app_context():
        # _initialize_database_schema()
        _recover_runtime_resources()
        _initialize_system_metadata()

    check_and_cleanup_dead_tasks(app)
    _start_background_components(app)

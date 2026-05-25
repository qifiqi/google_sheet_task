import json
import os

from sqlalchemy import inspect, text
from werkzeug.security import generate_password_hash

from app.config import PERMISSIONS, init_config
from app.extensions import db
from app.models import (
    GoogleSheetToken,
    NavigationMenuItem,
    Permission,
    Role,
    ScheduledTask,
    SystemConfig,
    Task,
    TaskLog,
    TaskResult,
    TaskResultSummaryIndex,
    User,
)
from app.navigation import DEFAULT_NAVIGATION_MENU, flatten_navigation_items
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
        }


def register_cli(app):
    @app.cli.command()
    def init_db():
        db.create_all()
        ensure_google_sheet_token_schema()
        ensure_user_schema()
        ensure_task_schema()
        ensure_scheduled_task_schema()
        ensure_task_result_summary_index_schema()
        ensure_navigation_menu_schema()
        print('数据库初始化完成')

    @app.cli.command()
    def init_default_config():
        init_config()
        print('默认配置初始化完成')


def init_rbac():
    logger = get_logger('rbac')

    for group, code, name, route_path in PERMISSIONS:
        perm = Permission.query.filter_by(code=code).first()
        if not perm:
            db.session.add(Permission(group=group, code=code, name=name, route_path=route_path))
        elif perm.route_path != route_path:
            perm.route_path = route_path
    db.session.commit()

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
            scheduler_service.create_default_tasks()
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
        ensure_scheduled_task_schema()
        ensure_task_result_summary_index_schema()
        ensure_navigation_menu_schema()
        reset_google_sheet_token_occupancy()
        reset_google_sheet_occupancy()
        init_config()
        init_rbac()
        init_navigation_menu()
    check_and_cleanup_dead_tasks(app)
    init_scheduler(app)
    init_task_watchdog(app)

import json
import os

from sqlalchemy import inspect, text
from werkzeug.security import generate_password_hash

from app.config import NAV_MENU, PERMISSIONS, init_config
from app.extensions import db
from app.models import (
    GoogleSheetToken,
    Permission,
    Role,
    ScheduledTask,
    SystemConfig,
    Task,
    TaskLog,
    TaskResult,
    User,
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

    nav_config = SystemConfig.query.filter_by(key='nav_menu').first()
    if not nav_config:
        db.session.add(SystemConfig(
            key='nav_menu',
            value=json.dumps(NAV_MENU, ensure_ascii=False),
            description='前端导航菜单结构(JSON)，支持 permission 字段按角色过滤',
        ))
        db.session.commit()
        return

    try:
        nav_data = json.loads(nav_config.value or '[]')
    except (TypeError, ValueError):
        nav_data = []

    permission_map = {
        '/admin': 'page:admin:dashboard',
        '/admin/': 'page:admin:dashboard',
        '/admin/tasks': 'page:admin:tasks',
        '/admin/templates': 'page:admin:templates',
        '/admin/results': 'page:admin:results',
        '/admin/scheduler': 'page:admin:scheduler',
        '/admin/config': 'page:admin:config',
        '/admin/google-sheets': 'page:admin:google_sheets',
        '/admin/logs': 'page:admin:logs',
        '/admin/users': 'page:admin:users',
        '/admin/roles': 'page:admin:roles',
        '/task/list?version=c3': 'page:google_sheet:c3',
        '/task/list?version=c4': 'page:google_sheet:c4',
        '/task/list?version=c5': 'page:google_sheet:c5',
        '/google-sheet/?version=c3': 'page:google_sheet:c3',
        '/google-sheet/?version=c4': 'page:google_sheet:c4',
        '/google-sheet/?version=c5': 'page:google_sheet:c5',
        '/google-sheet/?version=c31': 'page:google_sheet:c3',
        '/backtest/list': 'page:backtest:list',
        '/backtest-training/list': 'page:backtest:list',
        '/backtest/create': 'page:backtest:create',
        '/backtest-training/create': 'page:backtest:create',
    }

    changed = False
    for item in nav_data:
        changed = _sync_nav_permissions(item, permission_map) or changed
    if changed:
        nav_config.value = json.dumps(nav_data, ensure_ascii=False)
        db.session.commit()


def _sync_nav_permissions(item, permission_map):
    changed = False
    expected = permission_map.get(item.get('path'))
    if expected and item.get('permission') != expected:
        item['permission'] = expected
        changed = True
    for child in item.get('children') or []:
        changed = _sync_nav_permissions(child, permission_map) or changed
    return changed


def check_and_cleanup_dead_tasks(app):
    from app.services.task_manager import task_manager

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
                task_manager._add_task_log(
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
        reset_google_sheet_token_occupancy()
        reset_google_sheet_occupancy()
        init_config()
        init_rbac()
    check_and_cleanup_dead_tasks(app)
    init_scheduler(app)
    init_task_watchdog(app)

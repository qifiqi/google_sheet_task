import json

from werkzeug.security import generate_password_hash

from app.config import PERMISSIONS, init_config
from app.extensions import db
from app.models import NavigationMenuItem, Permission, Role, SystemConfig, User
from app.navigation import (
    DEFAULT_NAVIGATION_MENU,
    build_nav_permission_map,
    flatten_navigation_items,
    normalize_nav_label,
    normalize_nav_path,
)
from app.utils.logger import get_logger


def seed_default_data(app=None, include_scheduler=True):
    """Seed default database data that should not run during app startup."""
    if app is None:
        init_config()
        init_rbac()
        init_navigation_menu()
        if include_scheduler:
            init_default_scheduled_tasks()
        return

    with app.app_context():
        init_config()
        init_rbac()
        init_navigation_menu()
        if include_scheduler:
            init_default_scheduled_tasks(app)


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
    permission_map = build_nav_permission_map()
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

        path = normalize_nav_path(row.get('path'))
        expected_permission = permission_map.get(path) or row.get('permission')
        item = existing.get(key)
        if not item:
            db.session.add(NavigationMenuItem(
                key=key,
                label=normalize_nav_label(key, row.get('label') or key),
                path=path,
                permission=expected_permission,
                parent_key=row.get('parent_key'),
                sort_order=row.get('sort_order') or 0,
                is_visible=True,
            ))
            continue

        if nav_config:
            item.label = normalize_nav_label(key, row.get('label') or item.label)
            item.path = path
            item.permission = expected_permission
            item.parent_key = row.get('parent_key')
            item.sort_order = row.get('sort_order') or 0

    if nav_config:
        db.session.delete(nav_config)

    db.session.commit()


def init_default_scheduled_tasks(app=None):
    from app.services.scheduler_service import scheduler_service

    if app is not None:
        scheduler_service.app = app
    scheduler_service.create_default_tasks()


def _seed_missing_default_navigation_items(default_rows, permission_map, existing):
    for row in default_rows:
        key = row.get('key')
        if not key or key in existing:
            continue
        path = normalize_nav_path(row.get('path'))
        db.session.add(NavigationMenuItem(
            key=key,
            label=normalize_nav_label(key, row.get('label') or key),
            path=path,
            permission=permission_map.get(path) or row.get('permission'),
            parent_key=row.get('parent_key'),
            sort_order=row.get('sort_order') or 0,
            is_visible=True,
        ))


def _normalize_existing_navigation_menu():
    permission_map = build_nav_permission_map()
    default_rows = {
        row.get('key'): row
        for row in flatten_navigation_items(DEFAULT_NAVIGATION_MENU)
        if row.get('key')
    }
    for item in NavigationMenuItem.query.all():
        item.path = normalize_nav_path(item.path)
        default_row = default_rows.get(item.key)
        item.label = normalize_nav_label(
            item.key,
            default_row.get('label') if default_row else item.label,
        )
        if default_row:
            item.parent_key = default_row.get('parent_key')
            item.sort_order = default_row.get('sort_order') or 0
            if default_row.get('path'):
                item.path = normalize_nav_path(default_row.get('path'))
        expected_permission = permission_map.get(item.path)
        if expected_permission:
            item.permission = expected_permission

"""认证与用户/角色/权限管理 API"""
from flask import Blueprint, request, abort
from werkzeug.security import generate_password_hash, check_password_hash
from app.models import NavigationMenuItem, Permission, Role, Task, User, db, role_permissions, user_roles
from app.repositories.sdk_client import SdkDataAccessError, SdkOperationError
from app.repositories.sys_user_repository import SysUserRepository
from app.services.remote_identity_service import RemoteIdentityService
# TODO: 用户、角色、权限及导航菜单等待远程 Identity/AccessControl 接口后再迁移。
from app.navigation import sync_navigation_permissions
from app.utils.auth import (
    create_access_token, create_refresh_token, decode_token,
    login_required, permission_required,
)
from app.utils.api_response import success, error
import jwt

auth_api_bp = Blueprint('auth_api', __name__)
legacy_identity_bp = Blueprint('legacy_identity', __name__)
DEV_ROLE_CODES = {'developer'}


@auth_api_bp.before_request
def disable_local_identity_management():
    """用户/RBAC 管理已移交主 Web，保留认证接口以兼容现有 JWT。"""
    if request.path.startswith(('/api/admin/users', '/api/admin/roles', '/api/admin/permissions', '/api/auth/password')):
        abort(404)


def _is_dev_role(role):
    """判断角色是否为允许接收告警的开发者角色。"""
    return str(getattr(role, 'code', '') or '').strip().lower() in DEV_ROLE_CODES


def _can_alert_oncall(role_ids=None, user=None):
    """判断指定角色或用户是否具备值班告警资格。"""
    if role_ids is not None:
        if not role_ids:
            return False
        roles = Role.query.filter(Role.id.in_(role_ids)).all()
        return any(_is_dev_role(role) for role in roles)
    return any(_is_dev_role(role) for role in (user.roles if user else []))


# ==================== Auth ====================

@auth_api_bp.route('/auth/login', methods=['POST'])
def login():
    """使用主 Web 用户服务校验账号，并签发本地 JWT。"""
    data = request.get_json() or {}
    username = data.get('username', '').strip()
    password = data.get('password', '')
    if not username or not password:
        return error('用户名和密码不能为空')

    try:
        remote_record = SysUserRepository().login(username, password)
    except SdkOperationError:
        return error('用户名或密码错误', http_status=401)
    except SdkDataAccessError:
        return error('远程用户服务暂不可用', http_status=503)
    if not remote_record:
        return error('用户名或密码错误', http_status=401)
    user_id = remote_record.get('userid', remote_record.get('id'))
    if user_id is None:
        return error('远程登录响应缺少用户标识', http_status=502)
    user = RemoteIdentityService().get_user(user_id, username)
    if not user:
        return error('账号不存在或已禁用', http_status=401)

    return success(data={
        'access_token': create_access_token(user.id),
        'refresh_token': create_refresh_token(user.id),
        'user': user.to_dict(include_permissions=True),
    })


@auth_api_bp.route('/auth/refresh', methods=['POST'])
def refresh():
    """校验刷新令牌后，为仍有效的远程用户换发访问令牌。"""
    data = request.get_json() or {}
    token = data.get('refresh_token', '')
    try:
        payload = decode_token(token)
        if payload.get('type') != 'refresh':
            return error('令牌类型错误')
    except jwt.ExpiredSignatureError:
        return error('刷新令牌已过期', http_status=401)
    except jwt.InvalidTokenError:
        return error('无效刷新令牌', http_status=401)

    user_id = payload.get('user_id', payload.get('userid'))
    if user_id is None:
        return error('令牌缺少用户标识', http_status=401)
    try:
        user = RemoteIdentityService().get_user(user_id)
    except SdkDataAccessError:
        return error('远程用户服务暂不可用', http_status=503)
    if not user:
        return error('用户不存在或已禁用', http_status=401)

    return success(data={
        'access_token': create_access_token(user.id),
        'user': user.to_dict(include_permissions=True),
    })


@auth_api_bp.route('/auth/me', methods=['GET'])
@login_required
def get_me():
    """返回当前 JWT 对应的远程用户身份与权限信息。"""
    from flask import g
    user = g.current_user
    return success(data=user.to_dict(include_permissions=True))


@auth_api_bp.route('/auth/logout', methods=['POST'])
@login_required
def logout():
    """保留登出成功响应；JWT 无状态失效由客户端清除令牌完成。"""
    return success(message='退出登录成功')


@auth_api_bp.route('/auth/password', methods=['PUT'])
@login_required
def change_password():
    """已废弃的本地改密兼容入口；请求会被蓝图前置钩子拒绝。"""
    from flask import g
    data = request.get_json() or {}
    old_pwd = data.get('old_password', '')
    new_pwd = data.get('new_password', '')
    if not old_pwd or not new_pwd:
        return error('旧密码和新密码不能为空')
    if len(new_pwd) < 6:
        return error('新密码长度不能少于6位')

    user = g.current_user
    if not check_password_hash(user.password_hash, old_pwd):
        return error('旧密码错误')

    user.password_hash = generate_password_hash(new_pwd)
    db.session.commit()
    return success(message='密码修改成功')


# ==================== User Management ====================

@legacy_identity_bp.route('/admin/users', methods=['GET'])
@login_required
@permission_required('user:view', 'user:manage')
def list_users():
    """已废弃的本地用户列表入口；请求会被蓝图前置钩子拒绝。"""
    users = User.query.all()
    return success(data=[u.to_dict() for u in users])


@legacy_identity_bp.route('/admin/users', methods=['POST'])
@login_required
@permission_required('user:manage')
def create_user():
    """已废弃的本地用户创建入口；请求会被蓝图前置钩子拒绝。"""
    data = request.get_json() or {}
    username = data.get('username', '').strip()
    password = data.get('password', '')
    mobile = (data.get('mobile') or '').strip() or None
    role_ids = data.get('role_ids', [])

    if not username or not password:
        return error('用户名和密码不能为空')
    if User.query.filter_by(username=username).first():
        return error('用户名已存在')

    user = User(
        username=username,
        password_hash=generate_password_hash(password),
        mobile=mobile,
        is_active=data.get('is_active', True),
        is_alert_oncall=bool(data.get('is_alert_oncall', False)) and _can_alert_oncall(role_ids=role_ids),
    )
    if role_ids:
        user.roles = Role.query.filter(Role.id.in_(role_ids)).all()
    db.session.add(user)
    db.session.commit()
    return success(data=user.to_dict(), message='用户创建成功')


@legacy_identity_bp.route('/admin/users/<int:user_id>', methods=['PUT'])
@login_required
@permission_required('user:manage')
def update_user(user_id):
    """已废弃的本地用户更新入口；请求会被蓝图前置钩子拒绝。"""
    user = User.query.get(user_id)
    if not user:
        return error('用户不存在', http_status=404)

    data = request.get_json() or {}
    if 'mobile' in data:
        user.mobile = (data.get('mobile') or '').strip() or None
    if 'is_active' in data:
        user.is_active = data['is_active']
    if 'password' in data and data['password']:
        user.password_hash = generate_password_hash(data['password'])
    if 'role_ids' in data:
        user.roles = Role.query.filter(Role.id.in_(data['role_ids'])).all()
    if 'is_alert_oncall' in data or 'role_ids' in data:
        user.is_alert_oncall = bool(data.get('is_alert_oncall', user.is_alert_oncall)) and _can_alert_oncall(user=user)
    db.session.commit()
    return success(data=user.to_dict(), message='用户更新成功')


@legacy_identity_bp.route('/admin/users/<int:user_id>', methods=['DELETE'])
@login_required
@permission_required('user:manage')
def delete_user(user_id):
    """已废弃的本地用户删除入口；请求会被蓝图前置钩子拒绝。"""
    user = User.query.get(user_id)
    if not user:
        return error('用户不存在', http_status=404)
    Task.query.filter_by(created_by_user_id=user.id).update(
        {Task.created_by_user_id: None},
        synchronize_session=False,
    )
    db.session.execute(user_roles.delete().where(user_roles.c.user_id == user.id))
    db.session.delete(user)
    db.session.commit()
    return success(message='用户删除成功')


# ==================== Role Management ====================

@legacy_identity_bp.route('/admin/roles', methods=['GET'])
@login_required
@permission_required('user:view', 'user:manage')
def list_roles():
    """已废弃的本地角色列表入口；请求会被蓝图前置钩子拒绝。"""
    roles = Role.query.all()
    return success(data=[r.to_dict(include_permissions=True) for r in roles])


@legacy_identity_bp.route('/admin/roles', methods=['POST'])
@login_required
@permission_required('user:manage')
def create_role():
    """已废弃的本地角色创建入口；请求会被蓝图前置钩子拒绝。"""
    data = request.get_json() or {}
    name = data.get('name', '').strip()
    code = data.get('code', '').strip()
    if not name or not code:
        return error('角色名称和编码不能为空')
    if Role.query.filter_by(code=code).first():
        return error('角色编码已存在')

    role = Role(name=name, code=code, description=data.get('description', ''))
    perm_ids = data.get('permission_ids', [])
    if perm_ids:
        role.permissions = Permission.query.filter(Permission.id.in_(perm_ids)).all()
    db.session.add(role)
    db.session.commit()
    return success(data=role.to_dict(include_permissions=True), message='角色创建成功')


@legacy_identity_bp.route('/admin/roles/<int:role_id>', methods=['PUT'])
@login_required
@permission_required('user:manage')
def update_role(role_id):
    """已废弃的本地角色更新入口；请求会被蓝图前置钩子拒绝。"""
    role = Role.query.get(role_id)
    if not role:
        return error('角色不存在', http_status=404)

    data = request.get_json() or {}
    if 'name' in data:
        role.name = data['name']
    if 'description' in data:
        role.description = data['description']
    if 'permission_ids' in data:
        role.permissions = Permission.query.filter(Permission.id.in_(data['permission_ids'])).all()
    db.session.commit()
    return success(data=role.to_dict(include_permissions=True), message='角色更新成功')


@legacy_identity_bp.route('/admin/roles/<int:role_id>', methods=['DELETE'])
@login_required
@permission_required('user:manage')
def delete_role(role_id):
    """已废弃的本地角色删除入口；请求会被蓝图前置钩子拒绝。"""
    role = Role.query.get(role_id)
    if not role:
        return error('角色不存在', http_status=404)
    if role.is_system:
        return error('系统内置角色不可删除')
    db.session.execute(user_roles.delete().where(user_roles.c.role_id == role.id))
    db.session.execute(role_permissions.delete().where(role_permissions.c.role_id == role.id))
    db.session.delete(role)
    db.session.commit()
    return success(message='角色删除成功')


# ==================== Permission Query ====================

@legacy_identity_bp.route('/admin/permissions', methods=['GET'])
@login_required
@permission_required('user:view', 'user:manage')
def list_permissions():
    """已废弃的本地权限列表入口；请求会被蓝图前置钩子拒绝。"""
    sync_navigation_permissions(NavigationMenuItem.query.all())
    db.session.commit()
    perms = Permission.query.order_by(Permission.group, Permission.code).all()
    grouped = {}
    for p in perms:
        grouped.setdefault(p.group, []).append(p.to_dict())
    return success(data=grouped)

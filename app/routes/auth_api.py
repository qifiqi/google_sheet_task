"""认证与用户/角色/权限管理 API"""
from datetime import datetime
from flask import Blueprint, request
from werkzeug.security import generate_password_hash, check_password_hash
from app.models import User, Role, Permission, db
from app.utils.auth import (
    create_access_token, create_refresh_token, decode_token,
    login_required, permission_required, extract_token_version,
)
from app.utils.api_response import success, error
import jwt

auth_api_bp = Blueprint('auth_api', __name__)
DEV_ROLE_CODES = {'developer'}


def _is_dev_role(role):
    return str(getattr(role, 'code', '') or '').strip().lower() in DEV_ROLE_CODES


def _can_alert_oncall(role_ids=None, user=None):
    if role_ids is not None:
        if not role_ids:
            return False
        roles = Role.query.filter(Role.id.in_(role_ids)).all()
        return any(_is_dev_role(role) for role in roles)
    return any(_is_dev_role(role) for role in (user.roles if user else []))


# ==================== Auth ====================

@auth_api_bp.route('/auth/login', methods=['POST'])
def login():
    data = request.get_json() or {}
    username = data.get('username', '').strip()
    password = data.get('password', '')
    if not username or not password:
        return error('用户名和密码不能为空')

    user = User.query.filter_by(username=username).first()
    if not user or not check_password_hash(user.password_hash, password):
        return error('用户名或密码错误')
    if not user.is_active:
        return error('账号已被禁用')

    user.token_version = int(user.token_version or 0) + 1
    token_version = int(user.token_version or 0)
    user.last_login = datetime.utcnow()
    db.session.commit()

    return success(data={
        'access_token': create_access_token(user.id, token_version=token_version),
        'refresh_token': create_refresh_token(user.id, token_version=token_version),
        'user': user.to_dict(include_permissions=True),
    })


@auth_api_bp.route('/auth/refresh', methods=['POST'])
def refresh():
    data = request.get_json() or {}
    token = data.get('refresh_token', '')
    try:
        payload = decode_token(token)
        if payload.get('type') != 'refresh':
            return error('令牌类型错误')
        token_version = extract_token_version(payload)
    except jwt.ExpiredSignatureError:
        return error('刷新令牌已过期', http_status=401)
    except jwt.InvalidTokenError:
        return error('无效刷新令牌', http_status=401)

    user = User.query.get(payload['user_id'])
    if not user or not user.is_active:
        return error('用户不存在或已禁用', http_status=401)
    if int(user.token_version or 0) != token_version:
        return error('登录状态已失效，请重新登录', http_status=401)

    return success(data={
        'access_token': create_access_token(user.id, token_version=int(user.token_version or 0)),
        'user': user.to_dict(include_permissions=True),
    })


@auth_api_bp.route('/auth/me', methods=['GET'])
@login_required
def get_me():
    from flask import g
    user = g.current_user
    return success(data=user.to_dict(include_permissions=True))


@auth_api_bp.route('/auth/logout', methods=['POST'])
@login_required
def logout():
    from flask import g
    user = g.current_user
    user.token_version = int(user.token_version or 0) + 1
    db.session.commit()
    return success(message='退出登录成功')


@auth_api_bp.route('/auth/password', methods=['PUT'])
@login_required
def change_password():
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

@auth_api_bp.route('/admin/users', methods=['GET'])
@login_required
@permission_required('user:view', 'user:manage')
def list_users():
    users = User.query.all()
    return success(data=[u.to_dict() for u in users])


@auth_api_bp.route('/admin/users', methods=['POST'])
@login_required
@permission_required('user:manage')
def create_user():
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


@auth_api_bp.route('/admin/users/<int:user_id>', methods=['PUT'])
@login_required
@permission_required('user:manage')
def update_user(user_id):
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


@auth_api_bp.route('/admin/users/<int:user_id>', methods=['DELETE'])
@login_required
@permission_required('user:manage')
def delete_user(user_id):
    user = User.query.get(user_id)
    if not user:
        return error('用户不存在', http_status=404)
    db.session.delete(user)
    db.session.commit()
    return success(message='用户删除成功')


# ==================== Role Management ====================

@auth_api_bp.route('/admin/roles', methods=['GET'])
@login_required
@permission_required('user:view', 'user:manage')
def list_roles():
    roles = Role.query.all()
    return success(data=[r.to_dict(include_permissions=True) for r in roles])


@auth_api_bp.route('/admin/roles', methods=['POST'])
@login_required
@permission_required('user:manage')
def create_role():
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


@auth_api_bp.route('/admin/roles/<int:role_id>', methods=['PUT'])
@login_required
@permission_required('user:manage')
def update_role(role_id):
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


@auth_api_bp.route('/admin/roles/<int:role_id>', methods=['DELETE'])
@login_required
@permission_required('user:manage')
def delete_role(role_id):
    role = Role.query.get(role_id)
    if not role:
        return error('角色不存在', http_status=404)
    if role.is_system:
        return error('系统内置角色不可删除')
    db.session.delete(role)
    db.session.commit()
    return success(message='角色删除成功')


# ==================== Permission Query ====================

@auth_api_bp.route('/admin/permissions', methods=['GET'])
@login_required
@permission_required('user:view', 'user:manage')
def list_permissions():
    perms = Permission.query.order_by(Permission.group, Permission.code).all()
    grouped = {}
    for p in perms:
        grouped.setdefault(p.group, []).append(p.to_dict())
    return success(data=grouped)

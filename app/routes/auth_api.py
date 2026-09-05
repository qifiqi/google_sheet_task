"""认证与用户/角色/权限管理 API（数据层：rbac_repository + task_repository）。

- 删用户原子性：user_roles 清理 + Task.created_by_user_id 置空在同一个
  transaction() 内完成（断点/回滚语义与迁移前一致）；
- 路由内不写 try/except 兜底，异常交 app/errors.py 全局处理器转信封。
"""
from datetime import datetime

import jwt
from flask import Blueprint, request
from werkzeug.security import check_password_hash, generate_password_hash

from app.exceptions import NotFoundError
from app.repositories import navigation_repository, rbac_repository, task_repository
from app.navigation import sync_navigation_permissions
from app.utils.api_response import error, success
from app.utils.request_parsing import parse_body
from app.utils.auth import (
    create_access_token, create_refresh_token, decode_token,
    login_required, extract_token_version,
)
from app.schemas.auth import ChangePasswordSchema, CreateRoleSchema, CreateUserSchema

auth_api_bp = Blueprint('auth_api', __name__)
DEV_ROLE_CODES = {'developer'}


def _role_code(role) -> str:
    """角色编码读取：兼容 dict（repository 返回）与 ORM 实体。"""
    if isinstance(role, dict):
        return str(role.get("code") or "").strip().lower()
    return str(getattr(role, "code", "") or "").strip().lower()


def _can_alert_oncall(role_ids=None, user=None):
    if role_ids is not None:
        if not role_ids:
            return False
        return any(
            _role_code(role) in DEV_ROLE_CODES
            for role in rbac_repository.list_roles_by_ids(role_ids)
        )
    user_data = user
    if user_data is None:
        return False
    return any(
        _role_code(role) in DEV_ROLE_CODES
        for role in user_data.get("roles", [])
    )


# ==================== Auth ====================

@auth_api_bp.route('/auth/login', methods=['POST'])
def login():
    data = request.get_json() or {}
    username = str(data.get('username') or '').strip()
    password = data.get('password') or ''
    if not username or not password:
        return error('用户名和密码不能为空')

    credentials = rbac_repository.get_user_credentials(username)
    if not credentials or not check_password_hash(credentials["password_hash"], password):
        return error('用户名或密码错误')
    if not credentials["is_active"]:
        return error('账号已被禁用')

    # 登录不递增 token_version：同一账号多端登录互不影响。
    # 版本号仅在登出/改密/管理员重置时递增以吊销存量令牌。
    token_version = int(credentials["token_version"] or 0)
    rbac_repository.update_last_login(credentials["id"], datetime.utcnow())

    user = rbac_repository.get_user(credentials["id"], include_permissions=True)
    return success(data={
        'access_token': create_access_token(user["id"], token_version=token_version),
        'refresh_token': create_refresh_token(user["id"], token_version=token_version),
        'user': user,
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

    user = rbac_repository.get_user(payload['user_id'], include_permissions=True)
    if not user or not user["is_active"]:
        return error('用户不存在或已禁用', http_status=401)
    state = rbac_repository.get_user_state(payload['user_id'])
    if int(state["token_version"] or 0) != token_version:
        return error('登录状态已失效，请重新登录', http_status=401)

    # 滑动续期：refresh 时轮换 refresh_token，活跃用户不再被 7 天硬上限强制下线。
    current_version = int(state["token_version"] or 0)
    return success(data={
        'access_token': create_access_token(user["id"], token_version=current_version),
        'refresh_token': create_refresh_token(user["id"], token_version=current_version),
        'user': user,
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
    rbac_repository.update_user(
        user.id,
        {"token_version": int(user.token_version or 0) + 1},
    )
    return success(message='退出登录成功')


@auth_api_bp.route('/auth/password', methods=['PUT'])
@login_required
def change_password():
    from flask import g
    data = parse_body(ChangePasswordSchema)
    old_pwd = data.old_password
    new_pwd = data.new_password
    if not old_pwd or not new_pwd:
        return error('旧密码和新密码不能为空')
    if len(new_pwd) < 6:
        return error('新密码长度不能少于6位')

    user = g.current_user
    if not check_password_hash(user.password_hash, old_pwd):
        return error('旧密码错误')

    # 改密后吊销所有存量会话（含当前会话），需重新登录。
    rbac_repository.update_user(user.id, {
        "password_hash": generate_password_hash(new_pwd),
        "token_version": int(user.token_version or 0) + 1,
    })
    return success(message='密码修改成功，所有已登录会话已失效，请重新登录')


# ==================== User Management ====================

@auth_api_bp.route('/admin/users', methods=['GET'])
@login_required
def list_users():
    return success(data=rbac_repository.list_users())


@auth_api_bp.route('/admin/users', methods=['POST'])
@login_required
def create_user():
    data = parse_body(CreateUserSchema)
    username = data.username.strip()
    password = data.password
    mobile = (data.mobile or '').strip() or None
    role_ids = data.role_ids

    if not username or not password:
        return error('用户名和密码不能为空')
    if rbac_repository.username_exists(username):
        return error('用户名已存在')

    user = rbac_repository.create_user(
        username,
        generate_password_hash(password),
        role_ids=role_ids or None,
        mobile=mobile,
        is_active=data.is_active,
        is_alert_oncall=data.is_alert_oncall and _can_alert_oncall(role_ids=role_ids),
    )
    return success(data=user, message='用户创建成功')


@auth_api_bp.route('/admin/users/<int:user_id>', methods=['PUT'])
@login_required
def update_user(user_id):
    user = rbac_repository.get_user(user_id)
    if not user:
        raise NotFoundError('用户不存在')

    data = request.get_json() or {}
    fields = {}
    if 'mobile' in data:
        fields["mobile"] = (data.get('mobile') or '').strip() or None
    if 'is_active' in data:
        fields["is_active"] = data['is_active']
    if 'password' in data and data['password']:
        fields["password_hash"] = generate_password_hash(data['password'])
        # 管理员重置密码后吊销该用户所有存量会话。
        state = rbac_repository.get_user_state(user_id)
        fields["token_version"] = int(state["token_version"] or 0) + 1

    updated = rbac_repository.update_user(
        user_id,
        fields,
        role_ids=data.get('role_ids') if 'role_ids' in data else None,
    )

    # is_alert_oncall 依赖更新后的角色集合，须在角色写入之后计算。
    if 'is_alert_oncall' in data or 'role_ids' in data:
        refreshed = rbac_repository.get_user(user_id)
        alert_flag = bool(
            data.get('is_alert_oncall', refreshed["is_alert_oncall"])
        ) and _can_alert_oncall(user=refreshed)
        updated = rbac_repository.update_user(user_id, {"is_alert_oncall": alert_flag})

    return success(data=updated, message='用户更新成功')


@auth_api_bp.route('/admin/users/<int:user_id>', methods=['DELETE'])
@login_required
def delete_user(user_id):
    # 存在性检查用轻量投影：不能经 to_dict 触碰 roles 关联，
    # 否则关联行进入 session 后与 delete_user 内的显式清理叠加成双重删除（StaleDataError）。
    if not rbac_repository.get_user_state(user_id):
        raise NotFoundError('用户不存在')
    with rbac_repository.transaction():
        task_repository.clear_created_by(user_id, commit=False)
        rbac_repository.delete_user(user_id, commit=False)
    return success(message='用户删除成功')


# ==================== Role Management ====================

@auth_api_bp.route('/admin/roles', methods=['GET'])
@login_required
def list_roles():
    return success(data=rbac_repository.list_roles(include_permissions=True))


@auth_api_bp.route('/admin/roles', methods=['POST'])
@login_required
def create_role():
    data = parse_body(CreateRoleSchema)
    name = data.name.strip()
    code = data.code.strip()
    if not name or not code:
        return error('角色名称和编码不能为空')
    if rbac_repository.role_code_exists(code):
        return error('角色编码已存在')

    role = rbac_repository.create_role(
        code,
        name,
        permission_ids=data.permission_ids or None,
        description=data.description,
    )
    return success(data=role, message='角色创建成功')


@auth_api_bp.route('/admin/roles/<int:role_id>', methods=['PUT'])
@login_required
def update_role(role_id):
    role = rbac_repository.get_role(role_id)
    if not role:
        raise NotFoundError('角色不存在')

    data = request.get_json() or {}
    fields = {}
    if 'name' in data:
        fields["name"] = data['name']
    if 'description' in data:
        fields["description"] = data['description']
    updated = rbac_repository.update_role(
        role_id,
        fields,
        permission_ids=data.get('permission_ids') if 'permission_ids' in data else None,
    )
    return success(data=updated, message='角色更新成功')


@auth_api_bp.route('/admin/roles/<int:role_id>', methods=['DELETE'])
@login_required
def delete_role(role_id):
    role = rbac_repository.get_role(role_id)
    if not role:
        raise NotFoundError('角色不存在')
    if role["is_system"]:
        return error('系统内置角色不可删除')
    rbac_repository.delete_role(role_id)
    return success(message='角色删除成功')


# ==================== Permission Query ====================

@auth_api_bp.route('/admin/permissions', methods=['GET'])
@login_required
def list_permissions():
    with rbac_repository.transaction():
        sync_navigation_permissions(navigation_repository.list_all_entities())
    grouped = {}
    for perm in rbac_repository.list_permissions():
        grouped.setdefault(perm["group"], []).append(perm)
    return success(data=grouped)

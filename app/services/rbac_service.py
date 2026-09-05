"""RBAC 认证态与用户/角色/权限服务（数据层：rbac_repository + task_repository）。

认证/用户/角色编排收敛于此；token 签发与鉴权仍经 app.utils.auth
（登录热路径缓存留在 auth 层，B5 契约）。
凭证/权限类校验失败抛 ValidationError（400）或 UnauthorizedError（401），
与历史 error() 信封的 HTTP 语义逐条对齐。
"""

from __future__ import annotations

from datetime import datetime

import jwt
from werkzeug.security import check_password_hash, generate_password_hash

from app.exceptions import NotFoundError, UnauthorizedError, ValidationError
from app.navigation import sync_navigation_permissions
from app.repositories import navigation_repository, rbac_repository, task_repository
from app.utils.auth import (
    create_access_token,
    create_refresh_token,
    decode_token,
    extract_token_version,
)

# 值班告警仅对开发角色开放（is_alert_oncall 的角色白名单）
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

def login_user(username: str, password: str) -> dict:
    """账号密码登录：校验凭证并签发双 token；失败抛 ValidationError。"""
    if not username or not password:
        raise ValidationError("用户名和密码不能为空")

    credentials = rbac_repository.get_user_credentials(username)
    if not credentials or not check_password_hash(credentials["password_hash"], password):
        raise ValidationError("用户名或密码错误")
    if not credentials["is_active"]:
        raise ValidationError("账号已被禁用")

    # 登录不递增 token_version：同一账号多端登录互不影响。
    # 版本号仅在登出/改密/管理员重置时递增以吊销存量令牌。
    token_version = int(credentials["token_version"] or 0)
    rbac_repository.update_last_login(credentials["id"], datetime.utcnow())

    user = rbac_repository.get_user(credentials["id"], include_permissions=True)
    return {
        'access_token': create_access_token(user["id"], token_version=token_version),
        'refresh_token': create_refresh_token(user["id"], token_version=token_version),
        'user': user,
    }


def refresh_tokens(token: str) -> dict:
    """刷新令牌轮换（滑动续期）；无效/过期/状态失效抛 UnauthorizedError。"""
    try:
        payload = decode_token(token)
        if payload.get('type') != 'refresh':
            raise ValidationError("令牌类型错误")
        token_version = extract_token_version(payload)
    except jwt.ExpiredSignatureError:
        raise UnauthorizedError("刷新令牌已过期")
    except jwt.InvalidTokenError:
        raise UnauthorizedError("无效刷新令牌")

    user = rbac_repository.get_user(payload['user_id'], include_permissions=True)
    if not user or not user["is_active"]:
        raise UnauthorizedError("用户不存在或已禁用")
    state = rbac_repository.get_user_state(payload['user_id'])
    if int(state["token_version"] or 0) != token_version:
        raise UnauthorizedError("登录状态已失效，请重新登录")

    # 滑动续期：refresh 时轮换 refresh_token，活跃用户不再被 7 天硬上限强制下线。
    current_version = int(state["token_version"] or 0)
    return {
        'access_token': create_access_token(user["id"], token_version=current_version),
        'refresh_token': create_refresh_token(user["id"], token_version=current_version),
        'user': user,
    }


def logout_user(user) -> None:
    """登出：递增 token_version 吊销存量令牌。"""
    rbac_repository.update_user(
        user.id,
        {"token_version": int(user.token_version or 0) + 1},
    )


def change_password(user, old_pwd: str, new_pwd: str) -> None:
    """修改密码并吊销所有存量会话（含当前会话）；校验失败抛 ValidationError。"""
    if not old_pwd or not new_pwd:
        raise ValidationError("旧密码和新密码不能为空")
    if len(new_pwd) < 6:
        raise ValidationError("新密码长度不能少于6位")
    if not check_password_hash(user.password_hash, old_pwd):
        raise ValidationError("旧密码错误")

    rbac_repository.update_user(user.id, {
        "password_hash": generate_password_hash(new_pwd),
        "token_version": int(user.token_version or 0) + 1,
    })


# ==================== User Management ====================

def list_users() -> list:
    return rbac_repository.list_users()


def create_user(*, username: str, password: str, mobile, role_ids,
                is_active: bool, is_alert_oncall: bool) -> dict:
    """创建用户；用户名重复抛 ValidationError。"""
    if not username or not password:
        raise ValidationError("用户名和密码不能为空")
    if rbac_repository.username_exists(username):
        raise ValidationError("用户名已存在")

    return rbac_repository.create_user(
        username,
        generate_password_hash(password),
        role_ids=role_ids or None,
        mobile=mobile,
        is_active=is_active,
        is_alert_oncall=is_alert_oncall and _can_alert_oncall(role_ids=role_ids),
    )


def update_user(user_id: int, data: dict) -> dict:
    """更新用户字段/角色/密码重置；is_alert_oncall 依赖更新后角色集合后置计算。"""
    user = rbac_repository.get_user(user_id)
    if not user:
        raise NotFoundError("用户不存在")

    fields = {}
    if 'mobile' in data:
        fields["mobile"] = (data.get('mobile') or '').strip() or None
    if 'is_active' in data:
        fields["is_active"] = data['is_active']
    if 'password' in data and data['password']:
        # 管理员重置密码后吊销该用户所有存量会话。
        fields["password_hash"] = generate_password_hash(data['password'])
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

    return updated


def delete_user(user_id: int) -> None:
    """删除用户：Task.created_by 置空与用户删除同事务（原子性，B1 契约）。"""
    # 存在性检查用轻量投影：不能经 to_dict 触碰 roles 关联，
    # 否则关联行进入 session 后与 delete_user 内的显式清理叠加成双重删除（StaleDataError）。
    if not rbac_repository.get_user_state(user_id):
        raise NotFoundError("用户不存在")
    with rbac_repository.transaction():
        task_repository.clear_created_by(user_id, commit=False)
        rbac_repository.delete_user(user_id, commit=False)


# ==================== Role Management ====================

def list_roles() -> list:
    return rbac_repository.list_roles(include_permissions=True)


def create_role(*, name: str, code: str, permission_ids, description) -> dict:
    """创建角色；编码重复抛 ValidationError。"""
    if not name or not code:
        raise ValidationError("角色名称和编码不能为空")
    if rbac_repository.role_code_exists(code):
        raise ValidationError("角色编码已存在")

    return rbac_repository.create_role(
        code,
        name,
        permission_ids=permission_ids or None,
        description=description,
    )


def update_role(role_id: int, data: dict) -> dict:
    role = rbac_repository.get_role(role_id)
    if not role:
        raise NotFoundError("角色不存在")

    fields = {}
    if 'name' in data:
        fields["name"] = data['name']
    if 'description' in data:
        fields["description"] = data['description']
    return rbac_repository.update_role(
        role_id,
        fields,
        permission_ids=data.get('permission_ids') if 'permission_ids' in data else None,
    )


def delete_role(role_id: int) -> None:
    role = rbac_repository.get_role(role_id)
    if not role:
        raise NotFoundError("角色不存在")
    if role["is_system"]:
        raise ValidationError("系统内置角色不可删除")
    rbac_repository.delete_role(role_id)


# ==================== Permission Query ====================

def list_permissions_grouped() -> dict:
    """权限清单（先幂等同步导航权限，再按 group 分组）。"""
    with rbac_repository.transaction():
        sync_navigation_permissions(navigation_repository.list_all_entities())
    grouped = {}
    for perm in rbac_repository.list_permissions():
        grouped.setdefault(perm["group"], []).append(perm)
    return grouped

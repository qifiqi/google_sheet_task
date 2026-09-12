"""认证与用户/角色/权限管理 API。

认证态与用户/角色/权限编排经 auth_service（token 签发与鉴权在
app.utils.auth，缓存留在 auth 层）；路由层只做 HTTP 解析与统一信封。
删用户的同事务原子性（user_roles 清理 + Task.created_by 置空）在服务层保持。
"""

from flask import Blueprint, request

from app.services import auth_service
from app.utils.api_response import success
from app.utils.request_parsing import parse_body
from app.utils.auth import login_required, admin_required
from app.schemas.auth import (
    ChangePasswordSchema,
    CreateRoleSchema,
    CreateUserSchema,
    LoginSchema,
    RefreshSchema,
    UpdateRoleSchema,
    UpdateUserSchema,
)

auth_api_bp = Blueprint('auth_api', __name__)


# ==================== Auth ====================

@auth_api_bp.route('/auth/login', methods=['POST'])
def login():
    data = parse_body(LoginSchema)
    return success(data=auth_service.login_user(data.username.strip(), data.password))


@auth_api_bp.route('/auth/refresh', methods=['POST'])
def refresh():
    data = parse_body(RefreshSchema)
    return success(data=auth_service.refresh_tokens(data.refresh_token))


@auth_api_bp.route('/auth/me', methods=['GET'])
@login_required
def get_me():
    from flask import g
    return success(data=g.current_user.to_dict(include_permissions=True))


@auth_api_bp.route('/auth/logout', methods=['POST'])
@login_required
def logout():
    from flask import g
    auth_service.logout_user(g.current_user)
    return success(message='退出登录成功')


@auth_api_bp.route('/auth/password', methods=['PUT'])
@login_required
def change_password():
    from flask import g
    data = parse_body(ChangePasswordSchema)
    auth_service.change_password(g.current_user, data.old_password, data.new_password)
    return success(message='密码修改成功，所有已登录会话已失效，请重新登录')


# ==================== User Management ====================

@auth_api_bp.route('/admin/users', methods=['GET'])
@login_required
def list_users():
    return success(data=auth_service.list_users())


@auth_api_bp.route('/admin/users', methods=['POST'])
@admin_required
def create_user():
    data = parse_body(CreateUserSchema)
    user = auth_service.create_user(
        username=data.username.strip(),
        password=data.password,
        mobile=(data.mobile or '').strip() or None,
        role_ids=data.role_ids,
        is_active=data.is_active,
        is_alert_oncall=data.is_alert_oncall,
    )
    return success(data=user, message='用户创建成功')


@auth_api_bp.route('/admin/users/<int:user_id>', methods=['PUT'])
@admin_required
def update_user(user_id):
    data = parse_body(UpdateUserSchema)
    updated = auth_service.update_user(user_id, data.model_dump(exclude_unset=True))
    return success(data=updated, message='用户更新成功')


@auth_api_bp.route('/admin/users/<int:user_id>', methods=['DELETE'])
@admin_required
def delete_user(user_id):
    auth_service.delete_user(user_id)
    return success(message='用户删除成功')


# ==================== Role Management ====================

@auth_api_bp.route('/admin/roles', methods=['GET'])
@login_required
def list_roles():
    return success(data=auth_service.list_roles())


@auth_api_bp.route('/admin/roles', methods=['POST'])
@admin_required
def create_role():
    data = parse_body(CreateRoleSchema)
    role = auth_service.create_role(
        name=data.name.strip(),
        code=data.code.strip(),
        permission_ids=data.permission_ids,
        description=data.description,
    )
    return success(data=role, message='角色创建成功')


@auth_api_bp.route('/admin/roles/<int:role_id>', methods=['PUT'])
@admin_required
def update_role(role_id):
    data = parse_body(UpdateRoleSchema)
    updated = auth_service.update_role(role_id, data.model_dump(exclude_unset=True))
    return success(data=updated, message='角色更新成功')


@auth_api_bp.route('/admin/roles/<int:role_id>', methods=['DELETE'])
@admin_required
def delete_role(role_id):
    auth_service.delete_role(role_id)
    return success(message='角色删除成功')


# ==================== Permission Query ====================

@auth_api_bp.route('/admin/permissions', methods=['GET'])
@login_required
def list_permissions():
    return success(data=auth_service.list_permissions_grouped())

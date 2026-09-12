"""认证域请求 Schema（登录/改密/用户/角色管理）。"""

from pydantic import Field

from app.schemas.common import APIModel


class LoginSchema(APIModel):
    """POST /api/auth/login。空值由服务层校验并给出统一文案。"""

    username: str = ""
    password: str = ""


class RefreshSchema(APIModel):
    """POST /api/auth/refresh。"""

    refresh_token: str = ""


class ChangePasswordSchema(APIModel):
    old_password: str = Field(min_length=1)
    new_password: str = Field(min_length=1)


class CreateUserSchema(APIModel):
    username: str = Field(min_length=1)
    password: str = Field(min_length=1)
    mobile: str | None = None
    role_ids: list[int] = []
    is_active: bool = True
    is_alert_oncall: bool = False


class UpdateUserSchema(APIModel):
    """PUT /api/admin/users/<id>；exclude_unset 传递部分更新语义。"""

    mobile: str | None = None
    is_active: bool | None = None
    password: str | None = None
    role_ids: list[int] | None = None
    is_alert_oncall: bool | None = None


class UpdateRoleSchema(APIModel):
    """PUT /api/admin/roles/<id>。"""

    name: str | None = None
    description: str | None = None
    permission_ids: list[int] | None = None


class CreateRoleSchema(APIModel):
    name: str = Field(min_length=1)
    code: str = Field(min_length=1)
    description: str = ""
    permission_ids: list[int] = []

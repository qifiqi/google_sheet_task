"""认证域请求 Schema（登录/改密/用户/角色管理）。"""

from pydantic import Field

from app.schemas.common import APIModel


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


class CreateRoleSchema(APIModel):
    name: str = Field(min_length=1)
    code: str = Field(min_length=1)
    description: str = ""
    permission_ids: list[int] = []

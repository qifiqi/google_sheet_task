# remote_identity_service.py
"""
远程身份服务：
从已校验的 JWT 中获取用户 ID，并通过 SDK 查询主 Web 的 sys_user。
本服务不再查询本地 User 表；用户禁用或冻结时拒绝登录态访问。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.repositories.sys_user_repository import SysUserRepository


@dataclass
class RemoteUser:
    id: int
    username: str
    is_active: bool = True

    # Legacy task services still consume this method, but API-level local RBAC
    # has been deliberately retired.  The main Web controls route visibility.
    def get_permissions(self) -> set[str]:
        """远程身份 DTO 暂不维护本地权限集合。"""
        return set()

    def to_dict(self, include_permissions: bool = False) -> dict[str, Any]:
        """将远程用户 DTO 转换为认证接口兼容的字典。"""
        data = {"id": self.id, "username": self.username, "is_active": self.is_active, "roles": []}
        if include_permissions:
            data["permissions"] = []
        return data


class RemoteIdentityService:
    def __init__(self, repository: SysUserRepository | None = None) -> None:
        """注入远程用户仓储，生产环境默认使用标准实现。"""
        self.repository = repository or SysUserRepository()

    def get_user(self, subject: int | str, fallback_username: str | None = None) -> RemoteUser | None:
        """按远程用户标识读取并构造可供认证使用的身份 DTO。"""
        record = self.repository.get_by_id(subject)
        if not record:
            return None
        # ``is_frozen`` is the SDK's explicit disabled-state field.  Do not
        # infer semantics from the opaque 0/1 ``user_status`` enum.
        frozen = record.get("is_frozen")
        is_frozen = (
            frozen if isinstance(frozen, bool)
            else str(frozen or "").strip().lower() in {"1", "true", "yes", "on"}
        )
        if record.get("is_active") is False or is_frozen:
            return None
        user_id = record.get("userid", record.get("id", subject))
        return RemoteUser(id=int(user_id), username=str(record.get("username") or fallback_username or user_id))

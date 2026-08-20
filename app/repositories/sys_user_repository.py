"""JWT 身份校验使用的远程 ``sys_user`` 查询。"""

from __future__ import annotations

from typing import Any

from app.repositories.sdk_client import StockSdkAdapter


class SysUserRepository:
    """封装用户身份读取和登录接口，隔离生成 SDK 的响应格式。"""

    def __init__(self, client: StockSdkAdapter | None = None) -> None:
        """允许测试传入替身客户端，生产环境使用统一 SDK 适配器。"""
        self.client = client or StockSdkAdapter()

    def get_by_id(self, user_id: int | str) -> dict[str, Any] | None:
        """按用户主键读取 JWT 校验所需的身份信息。"""
        raw = self.client.call("sys_user", "get_by_id", {"id": int(user_id)})
        return dict(raw) if isinstance(raw, dict) else None

    def login(self, username: str, password: str) -> dict[str, Any] | None:
        """调用远程登录接口；凭据仅透传，不在本层记录日志。"""
        raw = self.client.call(
            "sys_user", "login", {"user_name": username, "user_password": password}
        )
        return dict(raw) if isinstance(raw, dict) else None

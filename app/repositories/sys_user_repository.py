"""远程 ``sys_user`` 身份、路由表与登录数据访问。"""

from __future__ import annotations

import threading
import time
from typing import Any

from app.repositories.sdk_client import SdkProtocolError, StockSdkAdapter


_ROLE_LIST_CACHE_TTL_SECONDS = 60
_MAX_CACHED_TOKENS = 64


class SysUserRepository:
    """封装用户身份读取、路由表与登录接口，隔离远程响应格式。

    ``GetUserInfo`` / ``GetUserRoleList`` 的用户凭据只能走 ``Token``
    请求头，因此身份读取方法都显式接收 ``token`` 参数，由 SDK 适配器
    绑定到对应客户端；登录接口使用服务级客户端（不绑定用户 Token）。
    """

    def __init__(self, client: StockSdkAdapter | None = None) -> None:
        """允许测试传入替身客户端，生产环境使用统一 SDK 适配器。"""
        self.client = client or StockSdkAdapter()
        self._role_list_cache: dict[tuple[str, int], tuple[float, list[dict[str, Any]]]] = {}
        self._role_list_lock = threading.Lock()

    def get_by_id(self, user_id: int | str) -> dict[str, Any] | None:
        """按用户主键读取身份信息（旧网关模式兼容入口）。"""
        raw = self.client.call("sys_user", "get_by_id", {"id": int(user_id)})
        return dict(raw) if isinstance(raw, dict) else None

    def get_user_info(self, token: str) -> dict[str, Any] | None:
        """用请求头 Token 调用 ``GetUserInfo`` 校验身份。

        该端点不接收请求体，凭据只走 ``Token`` 请求头；返回原始身份
        字典（``userid`` / ``username`` / ``last_login_time`` 等），
        响应不是对象时返回 ``None``。
        """
        raw = self.client.call("sys_user", "get_user_info", {}, token=token)
        return dict(raw) if isinstance(raw, dict) else None

    def login(self, username: str, password: str) -> Any:
        """调用远程登录接口；凭据仅透传，不在本层记录日志。

        返回原始 ``ret_obj``：可能是包含用户信息的对象，也可能是纯
        字符串 Token（不同远程版本返回结构不统一），由服务层提取。
        """
        return self.client.call(
            "sys_user", "login", {"user_name": username, "user_password": password}
        )

    def get_user_role_list(
        self,
        token: str,
        *,
        use_cache: bool = True,
    ) -> list[dict[str, Any]]:
        """用请求头 Token 读取用户可访问的模型（路由表）数组。

        与主 Web 前端 ``$.ajaxs`` 的调用契约一致: 请求体恒为空 JSON
        ``{}``（携带 ``application/json``），凭据只走 ``Token`` 请求头。
        主站返回的模型数据本身无序，路由表顺序由前端按 ``order_num``
        排序。结果按 Token 短暂缓存，避免每个请求都回源远程服务，
        ``use_cache=False`` 用于强制回源刷新。
        """
        cache_key = str(token or "")
        if use_cache:
            cached = self._read_role_list_cache(cache_key)
            if cached is not None:
                return cached

        raw = self.client.call(
            "sys_user",
            "get_user_role_list",
            { "sys_type": 1},
            token=token,
        )
        if raw is None:
            rows: list[dict[str, Any]] = []
        elif not isinstance(raw, list):
            raise SdkProtocolError("远程路由表接口返回格式异常")
        else:
            rows = [dict(item) for item in raw if isinstance(item, dict)]

        if use_cache:
            self._write_role_list_cache(cache_key, rows)
        return rows

    def _read_role_list_cache(self, key: str) -> list[dict[str, Any]] | None:
        """在 TTL 内读取该 Token 的路由表缓存。"""
        now = time.monotonic()
        with self._role_list_lock:
            cached = self._role_list_cache.get(key)
            if cached and now - cached[0] < _ROLE_LIST_CACHE_TTL_SECONDS:
                return cached[1]
            if cached:
                self._role_list_cache.pop(key, None)
        return None

    def _write_role_list_cache(
        self,
        key: str,
        rows: list[dict[str, Any]],
    ) -> None:
        """写入路由表缓存并清理过期条目，避免缓存无限增长。"""
        now = time.monotonic()
        with self._role_list_lock:
            if len(self._role_list_cache) >= _MAX_CACHED_TOKENS:
                expired = [
                    item_key
                    for item_key, (stamp, _) in self._role_list_cache.items()
                    if now - stamp >= _ROLE_LIST_CACHE_TTL_SECONDS
                ]
                for item_key in expired:
                    self._role_list_cache.pop(item_key, None)
            self._role_list_cache[key] = (now, rows)

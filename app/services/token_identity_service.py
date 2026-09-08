"""单 Token 子服务身份校验。

本服务作为主 Web（stock.stplan.cn）的子服务运行，不自己签发或存储
账号凭据，鉴权流程:

1. 前端/调用方在请求头 ``Token`` 字段携带主 Web 登录后颁发的单一 JWT;
2. 本服务把该 Token 写入 ``Token`` 请求头，原样转发给远程
   ``POST /api/SysUser/GetUserInfo`` 校验有效性，成功时取得
   ``userid`` / ``username`` 等用户身份;
3. 路由表（菜单权限）通过 ``POST /api/SysUser/GetUserRoleList`` 获取，
   返回 ``model_id / model_name / model_code / parent_model_id /
   order_num / model_link`` 等模型数组，供菜单服务组装成树。

远程接口返回信封为 ``{"ret_code", "ret_msg", "ret_count", "ret_obj"}``;
Token 无效或缺失时 GetUserInfo 返回 ``ret_code=401``（HTTP 仍为 200，
由 SDK 适配器转成业务异常）。两个接口均不接收请求体参数，凭据只走
请求头。
"""

from __future__ import annotations

import threading
import time
from typing import Any

from stock_sdk import StockClient
from stock_sdk.exceptions import StockSdkError

from app.repositories.sdk_client import SdkDataAccessError, StockSdkAdapter


_TOKEN_INVALID_CODE = 401
_ROLE_LIST_CACHE_TTL_SECONDS = 60
_MAX_CACHED_TOKENS = 64
# 远程登录接口返回 Token 的候选字段名（不同版本字段名不统一，逐一兼容）。
_LOGIN_TOKEN_KEYS = ("token", "Token", "access_token", "jwt")


def _extract_login_token(ret_obj: Any) -> str:
    """从远程 ``SysUser/Login`` 响应对象中提取登录 Token。"""
    if isinstance(ret_obj, str):
        candidate = ret_obj.strip()
        if candidate:
            return candidate
    elif isinstance(ret_obj, Mapping):
        for key in _LOGIN_TOKEN_KEYS:
            value = ret_obj.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    raise TokenIdentityError("远程登录接口未返回有效 Token")


class TokenIdentityError(SdkDataAccessError):
    """Token 校验失败（无效、过期或远程身份服务不可用）。"""


class TokenInvalidError(TokenIdentityError):
    """远程服务明确拒绝当前 Token（业务码 401）。"""


class RemoteTokenUser:
    """请求头 Token 经 GetUserInfo 校验通过后的轻量远程用户对象。

    兼容旧本地 ``User`` ORM 的常用读取方式（``id`` / ``username`` /
    ``get_permissions`` / ``to_dict``），但不承载任何本地数据库状态。
    """

    def __init__(self, info: dict[str, Any]) -> None:
        """以 GetUserInfo 返回字段构造；``userid`` 必须存在。"""
        self.id = info.get('userid')
        self.userid = self.id
        self.username = str(info.get('username') or '')
        self.last_login = info.get('last_login_time')
        self.is_active = True
        self.roles = []

    def get_permissions(self) -> set[str]:
        """兼容旧调用方；单 Token 模式下不再维护本地权限码集合。

        页面/接口权限统一由 GetUserRoleList 路由表控制
        （见 ``app/routes/meta_api.py``），本地权限码已停用。
        """
        return set()

    def to_dict(self, include_permissions: bool = False) -> dict[str, Any]:
        """转换为前端 ``/auth/me`` 兼容的用户响应结构。"""
        data = {
            'id': self.id,
            'userid': self.userid,
            'username': self.username,
            'is_active': self.is_active,
            'created_at': None,
            'last_login': self.last_login,
            'roles': [],
        }
        if include_permissions:
            data['permissions'] = sorted(self.get_permissions())
        return data


class TokenIdentityService:
    """基于请求头单 Token 的远程身份与路由表读取服务。

    GetUserInfo / GetUserRoleList 是无请求体端点，用户 Token 只能通过
    ``Token`` 请求头传递，而 SDK 客户端凭据在构造时绑定，因此这里按
    Token 缓存独立 ``StockClient``，避免每个请求都重建连接池，也避免
    与服务级 ``STOCK_API_TOKEN`` 的全局客户端互相干扰。
    """

    def __init__(self, client_factory=None) -> None:
        """注入客户端工厂，便于测试替换远程客户端。"""
        self._client_factory = client_factory or (
            lambda token: StockSdkAdapter._build_client(token=token)
        )
        self._clients: dict[str, StockClient] = {}
        self._clients_lock = threading.Lock()
        self._service_client: StockClient | None = None
        self._role_list_cache: dict[str, tuple[float, list[dict[str, Any]]]] = {}
        self._role_list_lock = threading.Lock()

    def _client_for(self, token: str) -> StockClient:
        """取该 Token 对应的 SDK 客户端，缺失时按集中配置创建。"""
        cached = self._clients.get(token)
        if cached is not None:
            return cached
        with self._clients_lock:
            client = self._clients.get(token)
            if client is not None:
                return client
            if len(self._clients) >= _MAX_CACHED_TOKENS:
                # 简单防膨胀: 超限时整体清空，身份调用频率低，重建成本可接受。
                self._clients.clear()
            client = self._client_factory(token)
            self._clients[token] = client
            return client

    def _service_client_for_login(self) -> StockClient:
        """登录用的服务级客户端（不绑定用户 Token，仅一次性创建）。"""
        if self._service_client is None:
            self._service_client = self._client_factory(None)
        return self._service_client

    def login(self, username: str, password: str) -> dict[str, Any]:
        """账号密码登录：代理远程 ``POST /api/SysUser/Login``。

        成功返回 ``{"token": str, "info": dict}``；账号密码被远程拒绝时抛
        :class:`TokenInvalidError`，远程服务不可用时抛
        :class:`SdkDataAccessError`。
        """
        if not str(username or "").strip() or not str(password or ""):
            raise TokenInvalidError("请输入用户名和密码")

        client = self._service_client_for_login()
        try:
            response = client.sys_user.login({
                "user_name": str(username).strip(),
                "user_password": str(password),
            })
        except StockSdkError as exc:
            raise SdkDataAccessError(f"远程登录服务暂不可用: {exc}") from exc

        if not response.is_success:
            # 远程以业务码表示账号密码错误等登录失败；消息原样透出。
            raise TokenInvalidError(str(response.ret_msg or "用户名或密码错误"))

        ret_obj = response.ret_obj
        token = _extract_login_token(ret_obj)
        info = dict(ret_obj) if isinstance(ret_obj, dict) else {}
        return {"token": token, "info": info}

    def _call_identity(self, token: str, operation: str):
        """用指定 Token 调用 sys_user 身份端点并统一翻译响应与异常。

        直接调用生成的无参端点方法（GetUserInfo / GetUserRoleList 均不
        接收请求体，凭据走 ``Token`` 请求头）; 远端以业务码 401 表示
        登录失效，转换为 :class:`TokenInvalidError`。
        """
        client = self._client_for(token)
        group = getattr(client, "sys_user")
        method = getattr(group, operation)
        try:
            response = method()
        except StockSdkError as exc:
            raise SdkDataAccessError(f"远程身份服务暂不可用: {exc}") from exc

        if not response.is_success:
            if response.ret_code == _TOKEN_INVALID_CODE:
                raise TokenInvalidError(str(response.ret_msg or "登录已失效, 请重新登陆"))
            raise TokenIdentityError(
                f"远程身份接口失败 (ret_code={response.ret_code}): {response.ret_msg}"
            )
        return response.ret_obj

    def get_user_info(self, token: str) -> dict[str, Any]:
        """用请求头 Token 调用 GetUserInfo 校验身份，失败时抛出异常。

        成功返回 ``{"userid": int, "username": str, "last_login_time": ...}``。
        """
        raw_token = str(token or "").strip()
        if not raw_token:
            raise TokenInvalidError("请求缺少 Token")

        info = self._call_identity(raw_token, "get_user_info")
        if not isinstance(info, dict) or not info.get("userid"):
            raise TokenIdentityError("远程身份接口未返回有效用户信息")
        return dict(info)

    def get_user_role_list(
        self,
        token: str,
        *,
        use_cache: bool = True,
    ) -> list[dict[str, Any]]:
        """用请求头 Token 读取用户可访问的模型（路由表）列表。

        结果按 Token 短暂缓存，避免每个请求都回源远程服务;
        ``use_cache=False`` 用于强制回源刷新。
        """
        raw_token = str(token or "").strip()
        if not raw_token:
            raise TokenInvalidError("请求缺少 Token")

        if use_cache:
            cached = self._read_role_list_cache(raw_token)
            if cached is not None:
                return cached

        rows = self._call_identity(raw_token, "get_user_role_list")
        if rows is None:
            rows = []
        if not isinstance(rows, list):
            raise TokenIdentityError("远程路由表接口返回格式异常")
        result = [dict(item) for item in rows if isinstance(item, dict)]

        if use_cache:
            self._write_role_list_cache(raw_token, result)
        return result

    def get_user_model_codes(self, token: str) -> list[str]:
        """返回用户路由表中的全部模型代码，供权限判断使用。"""
        return [
            str(row.get("model_code") or "")
            for row in self.get_user_role_list(token)
            if row.get("model_code")
        ]

    def _read_role_list_cache(self, token: str) -> list[dict[str, Any]] | None:
        """在 TTL 内读取该 Token 的路由表缓存。"""
        now = time.monotonic()
        with self._role_list_lock:
            cached = self._role_list_cache.get(token)
            if cached and now - cached[0] < _ROLE_LIST_CACHE_TTL_SECONDS:
                return cached[1]
            if cached:
                self._role_list_cache.pop(token, None)
        return None

    def _write_role_list_cache(self, token: str, rows: list[dict[str, Any]]) -> None:
        """写入路由表缓存并清理过期条目，避免缓存无限增长。"""
        now = time.monotonic()
        with self._role_list_lock:
            if len(self._role_list_cache) >= _MAX_CACHED_TOKENS:
                expired = [
                    key
                    for key, (stamp, _) in self._role_list_cache.items()
                    if now - stamp >= _ROLE_LIST_CACHE_TTL_SECONDS
                ]
                for key in expired:
                    self._role_list_cache.pop(key, None)
            self._role_list_cache[token] = (now, rows)


_token_identity_service = TokenIdentityService()


def get_token_identity_service() -> TokenIdentityService:
    """返回进程级单例，供鉴权与导航接口共用缓存。"""
    return _token_identity_service

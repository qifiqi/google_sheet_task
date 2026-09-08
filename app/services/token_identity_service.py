"""单 Token 子服务身份校验。

本服务作为主 Web（stock.stplan.cn）的子服务运行，不自己签发或存储
账号凭据，鉴权流程:

1. 前端/调用方在请求头 ``Token`` 字段携带主 Web 登录后颁发的单一 JWT;
2. 本服务经数据层（``app/repositories``）把该 Token 写入 ``Token``
   请求头，原样转发给远程 ``POST /api/SysUser/GetUserInfo`` 校验
   有效性，成功时取得 ``userid`` / ``username`` 等用户身份;
3. 路由表（菜单权限）通过 ``POST /api/SysUser/GetUserRoleList`` 获取，
   返回 ``model_id / model_name / model_code / parent_model_id /
   order_num / model_link`` 等模型数组，供菜单服务组装成树。

远程接口返回信封为 ``{"ret_code", "ret_msg", "ret_count", "ret_obj"}``;
Token 无效或缺失时 GetUserInfo 返回 ``ret_code=401``（HTTP 仍为 200，
由数据层转成业务异常后在这里翻译为 :class:`TokenInvalidError`）。
``GetUserInfo`` 不接收请求体；``GetUserRoleList`` 仅携带 ``sys_type``
（当前系统固定为 ``1``）。按 Token 的客户端缓存与路由表 TTL 缓存
均由数据层维护，本服务只负责异常语义翻译与身份 DTO。
"""

from __future__ import annotations

from typing import Any, Mapping

from app.repositories.sdk_client import SdkDataAccessError, SdkOperationError
from app.repositories.sys_user_repository import SysUserRepository


_TOKEN_INVALID_CODE = 401
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

    远程 IO（含按 Token 的客户端缓存与路由表 TTL 缓存）全部由
    :class:`SysUserRepository` 承担；这里把数据层的业务码异常翻译为
    鉴权语义: 401 → :class:`TokenInvalidError`（登录失效），
    其余远程失败 → :class:`TokenIdentityError`（服务不可用）。
    """

    def __init__(self, repository: SysUserRepository | None = None) -> None:
        """注入用户仓储，便于测试替换远程数据访问。"""
        self._repository = repository or SysUserRepository()

    def _call_identity(self, func, *args, **kwargs):
        """统一翻译数据层异常，保持鉴权调用方（401/503）契约不变。"""
        try:
            return func(*args, **kwargs)
        except SdkOperationError as exc:
            if exc.code == _TOKEN_INVALID_CODE:
                raise TokenInvalidError(str(exc) or "登录已失效, 请重新登陆") from exc
            raise TokenIdentityError(
                f"远程身份接口失败 (ret_code={exc.code}): {exc}"
            ) from exc
        except SdkDataAccessError as exc:
            raise TokenIdentityError(f"远程身份服务暂不可用: {exc}") from exc

    def login(self, username: str, password: str) -> dict[str, Any]:
        """账号密码登录：代理远程 ``POST /api/SysUser/Login``。

        成功返回 ``{"token": str, "info": dict}``；账号密码被远程拒绝时抛
        :class:`TokenInvalidError`，远程服务不可用时抛
        :class:`SdkDataAccessError`。
        """
        if not str(username or "").strip() or not str(password or ""):
            raise TokenInvalidError("请输入用户名和密码")

        try:
            ret_obj = self._repository.login(str(username).strip(), str(password))
        except SdkOperationError as exc:
            # 远程以业务码表示账号密码错误等登录失败；消息原样透出。
            raise TokenInvalidError(str(exc) or "用户名或密码错误") from exc
        except SdkDataAccessError as exc:
            raise SdkDataAccessError(f"远程登录服务暂不可用: {exc}") from exc

        token = _extract_login_token(ret_obj)
        info = dict(ret_obj) if isinstance(ret_obj, dict) else {}
        return {"token": token, "info": info}

    def get_user_info(self, token: str) -> dict[str, Any]:
        """用请求头 Token 调用 GetUserInfo 校验身份，失败时抛出异常。

        成功返回 ``{"userid": int, "username": str, "last_login_time": ...}``。
        """
        raw_token = str(token or "").strip()
        if not raw_token:
            raise TokenInvalidError("请求缺少 Token")

        info = self._call_identity(self._repository.get_user_info, raw_token)
        if not isinstance(info, dict) or not info.get("userid"):
            raise TokenIdentityError("远程身份接口未返回有效用户信息")
        return info

    def get_user_role_list(
        self,
        token: str,
        *,
        sys_type: int = 1,
        use_cache: bool = True,
    ) -> list[dict[str, Any]]:
        """用请求头 Token 读取用户可访问的模型（路由表）列表。

        当前系统 ``sys_type`` 固定为 ``1``；路由表缓存由数据层维护，
        ``use_cache=False`` 用于强制回源刷新。
        """
        raw_token = str(token or "").strip()
        if not raw_token:
            raise TokenInvalidError("请求缺少 Token")

        return self._call_identity(
            self._repository.get_user_role_list,
            raw_token,
            sys_type=sys_type,
            use_cache=use_cache,
        )

    def get_user_model_codes(self, token: str) -> list[str]:
        """返回用户路由表中的全部模型代码，供权限判断使用。"""
        return [
            str(row.get("model_code") or "")
            for row in self.get_user_role_list(token)
            if row.get("model_code")
        ]


_token_identity_service = TokenIdentityService()


def get_token_identity_service() -> TokenIdentityService:
    """返回进程级单例，供鉴权与导航接口共用缓存。"""
    return _token_identity_service

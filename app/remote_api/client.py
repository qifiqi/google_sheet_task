"""DY.Stock.Api 的统一远程调用出口。

所有远程 HTTP 请求只经本模块发出（Repository 通过控制器具体函数、
KlineService 通过 ``stock_api`` 单例间接使用）。本模块负责：

- 集中配置读取（``STOCK_BASE_URL`` / ``STOCK_API_TIMEOUT`` /
  ``STOCK_API_TOKEN``）与按 Token 缓存的 ``RemoteTransport``；
- 出站载荷布尔编码（远端布尔字段以 0/1 整型承载，JSON ``true``/``false``
  会在远端模型绑定阶段解析失败）；
- 统一响应信封（``ret_code / ret_msg / ret_count / ret_obj``）解包；
- 传输异常到 ``app/remote_api/exceptions.py`` 异常体系的翻译。

用户 Token 只能通过 ``Token`` 请求头传递（如身份校验接口），而客户端
凭据在构造时绑定，因此这里按 Token 缓存独立传输实例，避免每个请求都
重建连接池，也避免与服务级 ``STOCK_API_TOKEN`` 的全局传输互相干扰。
"""

from __future__ import annotations

import contextvars
import ipaddress
import json
import logging
import os
import socket
import threading
from collections.abc import Mapping
from typing import Any
from urllib.parse import urlsplit

import requests

from app.remote_api.exceptions import (
    RemoteApiConfigError,
    RemoteApiDuplicateKeyError,
    RemoteApiError,
    RemoteApiNotFoundError,
    RemoteApiOperationError,
    RemoteApiProtocolError,
)


logger = logging.getLogger(__name__)


# 请求域用户 Token：网关校验通过后写入（before_request），统一调用器对
# token=None 的服务级调用优先采用它——业务数据访问以实际用户身份过主站
# 按角色鉴权（远端 param_* 接口按 Token 对应角色做 403 鉴权）。任务 worker
# 线程经 facade 空上下文提交、不继承该值，回退服务级 STOCK_API_TOKEN。
_REQUEST_USER_TOKEN: contextvars.ContextVar[str] = contextvars.ContextVar(
    "remote_request_user_token"
)


def set_request_user_token(token: str) -> None:
    """请求域内登记当前用户 Token（网关 before_request 调用）。"""
    _REQUEST_USER_TOKEN.set(str(token or "").strip())


def clear_request_user_token() -> None:
    """清除请求域用户 Token（teardown_request 调用，防线程池线程串号）。"""
    _REQUEST_USER_TOKEN.set("")


def get_request_user_token() -> str:
    """读取请求域用户 Token；未设置时为空串。"""
    return _REQUEST_USER_TOKEN.get("")


def encode_remote_body(payload: Any) -> Any:
    """递归把出站载荷中的布尔值编码为远端约定的 0/1 整型。

    字符串 ``"true"`` 与数字 ``1`` 等非布尔类型原样保留。
    """
    if isinstance(payload, bool):
        return int(payload)
    if isinstance(payload, Mapping):
        return {key: encode_remote_body(value) for key, value in payload.items()}
    if isinstance(payload, (list, tuple)):
        return [encode_remote_body(item) for item in payload]
    return payload


def _validate_remote_host(base_url: str, *, allow_private: bool = False) -> None:
    """校验远端基地址 host：默认拒绝环回/私有/保留网段（SSRF 加固）。

    基地址来自运维配置而非用户输入；这里在传输构造期解析 DNS 并逐地址
    校验，误配 localhost/内网地址时直接失败，而不是静默把 Token 凭据
    发往受限网段。主站部署在内网（如 stockapi.jaspil.cn → 172.18.x）时，
    经 ``STOCK_BASE_URL_ALLOW_PRIVATE=true`` 显式放行私网网段。
    """
    hostname = urlsplit(base_url).hostname
    if not hostname:
        raise RemoteApiConfigError("STOCK_BASE_URL 缺少主机名")
    if allow_private:
        return
    try:
        addr_infos = socket.getaddrinfo(hostname, None)
    except socket.gaierror as exc:
        raise RemoteApiConfigError(f"STOCK_BASE_URL 主机解析失败: {hostname}") from exc
    for info in addr_infos:
        ip = ipaddress.ip_address(info[4][0])
        if (
            ip.is_loopback
            or ip.is_private
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_multicast
            or ip.is_unspecified
        ):
            raise RemoteApiConfigError(
                f"STOCK_BASE_URL 指向受限地址（{hostname} → {ip}），"
                "拒绝环回/私有/保留网段；内网部署可配置 "
                "STOCK_BASE_URL_ALLOW_PRIVATE=true 放行"
            )


class RemoteTransport:
    """单凭据的极薄同步 HTTP 传输。

    实例在构造时绑定 ``Token`` 请求头凭据与超时配置；服务级调用传入
    ``token=None``（凭据回退 ``STOCK_API_TOKEN``），用户身份调用传入
    登录颁发的用户 Token。
    """

    def __init__(
        self,
        *,
        token: str | None = None,
        base_url: str,
        timeout: float,
    ) -> None:
        """绑定凭据与目标地址；网络会话在实例内复用。"""
        self.token = token
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._session = requests.Session()
        self._session.headers.update({"Accept": "application/json"})

    def request(
        self,
        method: str,
        path: str,
        payload: Mapping[str, Any],
        timeout: float | None = None,
    ) -> dict[str, Any]:
        """发送一次请求并返回统一响应信封字典。

        与主 Web 前端 ``$.ajaxs`` 的契约一致：请求体恒为 JSON 编码的
        ``payload``，空载荷也发送 ``{}`` 并携带
        ``Content-Type: application/json``——远端 ``[FromBody]`` 接口在
        请求体缺失或 Content-Type 不符时返回 HTTP 415。传输错误与 HTTP
        错误翻译为本模块异常。``timeout`` 按次覆盖实例超时（秒）。
        """
        headers: dict[str, str] = {}
        if self.token:
            headers["Token"] = self.token
        resolved_timeout = self.timeout if timeout is None else timeout
        # 连接超时单独收紧：主站域名存在内网/公网双 A 记录，解析到不可达
        # 记录时快速失败（读超时仍按配置值）。
        connect_timeout = min(5.0, resolved_timeout)
        try:
            response = self._session.request(
                method,
                f"{self.base_url}{path}",
                json=dict(payload or {}),
                headers=headers,
                timeout=(connect_timeout, resolved_timeout),
            )
        except requests.ConnectTimeout as exc:
            # 仅对"连接建立超时"重试一次：请求未发出、幂等安全，且新连接会
            # 重新解析 DNS，有机会换到可达记录。
            try:
                response = self._session.request(
                    method,
                    f"{self.base_url}{path}",
                    json=dict(payload or {}),
                    headers=headers,
                    timeout=(connect_timeout, resolved_timeout),
                )
            except requests.RequestException as retry_exc:
                raise RemoteApiError(
                    f"远程数据服务连接失败: {retry_exc}"
                ) from retry_exc
        except requests.Timeout as exc:
            raise RemoteApiError(f"远程数据服务请求超时: {path}") from exc
        except requests.RequestException as exc:
            raise RemoteApiError(f"远程数据服务连接失败: {exc}") from exc
        if response.status_code >= 400:
            # 错误响应不保证是 JSON；无论返回 JSON、纯文本还是 HTML，
            # 都保留原始内容交给日志记录，避免丢失服务端错误原因。
            try:
                detail = response.json() if response.content else ""
            except ValueError:
                detail = response.text
            raise RemoteApiError(
                f"远程数据服务 HTTP {response.status_code}: {detail}"
            )
        if not response.content:
            raise RemoteApiProtocolError("远程数据服务返回空响应体")
        try:
            envelope = response.json()
        except ValueError as exc:
            raise RemoteApiProtocolError("远程数据服务响应不是 JSON") from exc
        if not isinstance(envelope, dict):
            raise RemoteApiProtocolError("远程响应不符合统一信封约定")
        return envelope


class StockApiClient:
    """远程接口统一调用器：控制器经属性分组暴露具体接口函数。

    用法（具体接口均为 ``app/remote_api/controllers/`` 下的命名方法，
    IDE 可直接跳转与检索调用链）::

        from app.remote_api import stock_api

        rows = stock_api.stock_data.get_data_all_list({"stock_code": "600000.SH"})
        stock_api.param_tasks.modify_or_add({"id": task_id, ...})

    身份校验等按用户上下文的调用通过 ``token=`` 传用户 Token，由本类
    路由到对应缓存传输实例。
    """

    # 按 Token 缓存的传输实例数量上限；超限时整体清空，身份调用频率低，
    # 重建成本可接受。
    _MAX_CACHED_TRANSPORTS = 64

    def __init__(self) -> None:
        """服务级与各用户 Token 的传输实例按需创建并缓存。"""
        self._transports: dict[str | None, RemoteTransport] = {}
        self._transports_lock = threading.Lock()
        # 服务级 401 自动重登：thread-local 标志防递归（登录调用自身的 401
        # 不再触发重登），锁 + 代数计数把并发 401 合并为一次重登。
        self._service_relogin_lock = threading.Lock()
        self._service_token_generation = 0
        self._relogin_tls = threading.local()
        # 控制器分组：与远程 Swagger 控制器一一对应（属性名即仓储层
        # group_name），具体接口函数见各控制器模块。
        from app.remote_api.controllers import bind_controllers

        bind_controllers(self)

    @staticmethod
    def _get_setting(name: str, default: Any = None) -> Any:
        """优先从 Flask 配置读取；离线场景才回退到环境变量。"""
        try:
            from flask import current_app, has_app_context

            if has_app_context():
                return current_app.config.get(name, default)
        except RuntimeError:
            pass
        return os.environ.get(name, default)

    @classmethod
    def _build_transport(cls, token: str | None = None) -> RemoteTransport:
        """根据集中配置构造 HTTP 传输，避免业务代码自行读取环境变量。"""
        base_url = str(cls._get_setting("STOCK_BASE_URL", "") or "").strip()
        if not base_url:
            raise RemoteApiConfigError(
                "STOCK_BASE_URL 未配置，无法使用远程数据访问服务"
            )
        if not base_url.lower().startswith(("http://", "https://")):
            raise RemoteApiConfigError(
                "STOCK_BASE_URL 必须以 http:// 或 https:// 开头"
            )
        allow_private = str(
            cls._get_setting("STOCK_BASE_URL_ALLOW_PRIVATE", "") or ""
        ).strip().lower() in {"1", "true", "yes", "on"}
        _validate_remote_host(base_url, allow_private=allow_private)
        try:
            timeout = float(cls._get_setting("STOCK_API_TIMEOUT", 10.0))
        except (TypeError, ValueError) as exc:
            raise RemoteApiConfigError("STOCK_API_TIMEOUT 必须是正数") from exc
        if timeout <= 0:
            raise RemoteApiConfigError("STOCK_API_TIMEOUT 必须大于 0")
        resolved_token = str(
            token or cls._get_setting("STOCK_API_TOKEN", "") or ""
        ).strip()
        return RemoteTransport(
            token=resolved_token or None,
            base_url=base_url,
            timeout=timeout,
        )

    def _effective_token(self, token: str | None) -> str | None:
        """解析本次调用的实际凭据：显式 token > 请求域用户 token > 服务级。

        重登路径（thread-local 标志内）不采用请求域 token——登录调用必须
        以服务级凭据形态发出；请求域 token 为空（任务线程/调度器/启动钩子）
        时回退 ``None`` → ``STOCK_API_TOKEN``（失效时自动重登）。
        """
        if token is not None:
            return token
        if not getattr(self._relogin_tls, "active", False):
            request_token = get_request_user_token()
            if request_token:
                return request_token
        return None

    def _transport_for(self, token: str | None) -> RemoteTransport:
        """取该 Token 对应的 HTTP 传输，缺失时按集中配置创建。"""
        cached = self._transports.get(token)
        if cached is not None:
            return cached
        with self._transports_lock:
            transport = self._transports.get(token)
            if transport is not None:
                return transport
            if len(self._transports) >= self._MAX_CACHED_TRANSPORTS:
                self._transports.clear()
            transport = self._build_transport(token)
            self._transports[token] = transport
            return transport

    @staticmethod
    def _safe_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
        """脱敏后返回请求载荷，供详细日志使用。"""
        sensitive_names = (
            "token",
            "password",
            "secret",
            "authorization",
            "credential",
            "cookie",
        )

        def sanitize(value: Any, key: str = "") -> Any:
            if any(name in key.lower() for name in sensitive_names):
                return "***"
            if isinstance(value, Mapping):
                return {
                    str(item_key): sanitize(item_value, str(item_key))
                    for item_key, item_value in value.items()
                }
            if isinstance(value, (list, tuple)):
                return [sanitize(item) for item in value]
            return value

        return sanitize(payload)

    def request(
        self,
        method: str,
        path: str,
        payload: Mapping[str, Any] | None = None,
        *,
        token: str | None = None,
        timeout: float | None = None,
    ) -> Any:
        """调用一个远程接口，并仅返回解包后的 ``ret_obj``。"""
        ret_obj, _ = self.request_with_count(
            method, path, payload, token=token, timeout=timeout
        )
        return ret_obj

    def request_with_count(
        self,
        method: str,
        path: str,
        payload: Mapping[str, Any] | None = None,
        *,
        token: str | None = None,
        timeout: float | None = None,
        probe: bool = False,
    ) -> tuple[Any, int | None]:
        """调用远程接口并返回 ``(ret_obj, ret_count)``。

        ``ret_count`` 是统一信封携带的记录计数（分页查询的匹配总数）；
        远端未返回时为 ``None``。分页仓储用它在 ``ret_obj`` 缺少 total
        字段时派生总数。``timeout`` 按次覆盖单请求超时（秒）。
        ``probe=True`` 用于能力探测：失败只记 debug，不打 warning 堆栈。
        """
        # 唯一出站出口统一完成布尔 → 0/1 编码（远端布尔字段以整型承载，
        # JSON true/false 会在远端模型绑定阶段解析失败）。
        body = encode_remote_body(dict(payload or {}))
        effective_token = self._effective_token(token)
        transport = self._transport_for(effective_token)

        # 所有远程 HTTP 请求都汇集到这里；仅记录字段名，避免日志泄漏
        # Token、收益序列及任务参数等可能很大的敏感请求内容。
        logger.info(
            "远程接口调用开始: %s %s payload_fields=%s",
            method,
            path,
            ",".join(sorted(str(key) for key in body)),
        )
        try:
            envelope = transport.request(method, path, body, timeout=timeout)
        except RemoteApiError as exc:
            if probe:
                logger.debug(
                    "远程能力探测失败: %s %s error=%s", method, path, exc
                )
            else:
                logger.warning(
                    "远程接口调用失败: %s %s error=%s message=%s request_payload=%s",
                    method,
                    path,
                    exc.__class__.__name__,
                    str(exc),
                    json.dumps(self._safe_payload(body), ensure_ascii=False, default=str),
                    exc_info=True,
                )
            raise

        code = envelope.get("ret_code", envelope.get("retCode"))
        message = str(
            envelope.get("ret_msg", envelope.get("retMsg")) or "远程数据服务拒绝请求"
        )
        if code != 200:
            logger.warning(
                "远程接口返回业务失败: %s %s code=%s",
                method,
                path,
                code,
            )
            # 服务级凭据失效（后台任务线程无用户上下文，无法像前端那样重新
            # 登录）：自动重登换新后单次重试，重试仍 401 则原样抛出。
            if (
                code == 401
                and effective_token is None
                and not getattr(self._relogin_tls, "active", False)
                and self._try_service_relogin()
            ):
                self._relogin_tls.active = True
                try:
                    return self.request_with_count(
                        method, path, payload, token=token, timeout=timeout
                    )
                finally:
                    self._relogin_tls.active = False
            # 远端服务以 409 或稳定错误码标识唯一键冲突，供锁和幂等写入处理。
            if code == 409 or "DUPLICATE_KEY" in message.upper():
                raise RemoteApiDuplicateKeyError(message, code=code)
            if code == 404:
                raise RemoteApiNotFoundError(message, code=code)
            raise RemoteApiOperationError(message, code=code)
        ret_count = envelope.get("ret_count", envelope.get("retCount"))
        try:
            ret_count = int(ret_count) if ret_count is not None else None
        except (TypeError, ValueError):
            ret_count = None
        return envelope.get("ret_obj", envelope.get("retObj")), ret_count

    # ---- 服务级凭据自动重登 ----

    # 远端登录接口返回 Token 的候选字段名（不同版本字段名不统一，逐一兼容，
    # 与 token_identity_service._LOGIN_TOKEN_KEYS 同源）。
    _LOGIN_TOKEN_KEYS = ("token", "Token", "access_token", "jwt")

    def _try_service_relogin(self) -> bool:
        """服务级调用 401 时用 ``STOCK_API_USERNAME/PASSWORD`` 自动重登换新。

        后台任务线程无用户上下文，服务级 Token 失效后无法人工重登；这里经
        ``SysUser/Login`` 换新并整体替换 ``None`` 凭据的缓存传输。凭据缺失
        或重登失败返回 False（沿用原 401 抛错，不给任务线程伪装成功）。
        登录请求在 thread-local 标志内发出，自身 401 不会递归触发重登；
        并发 401 经锁 + 代数计数合并为一次重登，其余线程直接复用新传输。
        """
        username = str(self._get_setting("STOCK_API_USERNAME", "") or "").strip()
        password = self._get_setting("STOCK_API_PASSWORD", "") or ""
        if not username or not password:
            return False
        generation = self._service_token_generation
        with self._service_relogin_lock:
            if self._service_token_generation != generation:
                # 其他线程已完成重登：调用方直接以新传输重试即可。
                return True
            self._relogin_tls.active = True
            try:
                ret_obj = self.sys_user.login(
                    {"user_name": username, "user_password": password}
                )
            except RemoteApiError as exc:
                logger.warning(
                    "服务级 Token 自动重登失败: %s: %s",
                    exc.__class__.__name__,
                    exc,
                )
                return False
            finally:
                self._relogin_tls.active = False
            token = self._extract_login_token(ret_obj)
            if not token:
                logger.warning("服务级 Token 自动重登失败: 远端未返回有效 Token")
                return False
            with self._transports_lock:
                self._transports[None] = self._build_transport(token)
                self._service_token_generation += 1
            logger.info("服务级 Token 已自动重登换新")
            return True

    @classmethod
    def _extract_login_token(cls, ret_obj: Any) -> str:
        """从登录响应对象提取 Token（兼容纯字符串与多字段名对象形态）。"""
        if isinstance(ret_obj, str):
            return ret_obj.strip()
        if isinstance(ret_obj, Mapping):
            for key in cls._LOGIN_TOKEN_KEYS:
                value = ret_obj.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()
        return ""

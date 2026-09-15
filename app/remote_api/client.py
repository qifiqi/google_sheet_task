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

import json
import logging
import os
import threading
from collections.abc import Mapping
from typing import Any

import requests

from app.remote_api.exceptions import (
    RemoteApiConfigError,
    RemoteApiNotFoundError,
    RemoteApiOperationError,
    RemoteApiProtocolError,
)


logger = logging.getLogger(__name__)


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
    ) -> dict[str, Any]:
        """发送一次请求并返回统一响应信封字典。

        与主 Web 前端 ``$.ajaxs`` 的契约一致：请求体恒为 JSON 编码的
        ``payload``，空载荷也发送 ``{}`` 并携带
        ``Content-Type: application/json``——远端 ``[FromBody]`` 接口在
        请求体缺失或 Content-Type 不符时返回 HTTP 415。传输错误与 HTTP
        错误翻译为本模块异常。
        """
        headers: dict[str, str] = {}
        if self.token:
            headers["Token"] = self.token
        try:
            response = self._session.request(
                method,
                f"{self.base_url}{path}",
                json=dict(payload or {}),
                headers=headers,
                timeout=self.timeout,
            )
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
    ) -> Any:
        """调用一个远程接口，并仅返回解包后的 ``ret_obj``。"""
        ret_obj, _ = self.request_with_count(method, path, payload, token=token)
        return ret_obj

    def request_with_count(
        self,
        method: str,
        path: str,
        payload: Mapping[str, Any] | None = None,
        *,
        token: str | None = None,
    ) -> tuple[Any, int | None]:
        """调用远程接口并返回 ``(ret_obj, ret_count)``。

        ``ret_count`` 是统一信封携带的记录计数（分页查询的匹配总数）；
        远端未返回时为 ``None``。分页仓储用它在 ``ret_obj`` 缺少 total
        字段时派生总数。
        """
        # 唯一出站出口统一完成布尔 → 0/1 编码（远端布尔字段以整型承载，
        # JSON true/false 会在远端模型绑定阶段解析失败）。
        body = encode_remote_body(dict(payload or {}))
        transport = self._transport_for(token)

        # 所有远程 HTTP 请求都汇集到这里；仅记录字段名，避免日志泄漏
        # Token、收益序列及任务参数等可能很大的敏感请求内容。
        logger.info(
            "远程接口调用开始: %s %s payload_fields=%s",
            method,
            path,
            ",".join(sorted(str(key) for key in body)),
        )
        try:
            envelope = transport.request(method, path, body)
        except RemoteApiError as exc:
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

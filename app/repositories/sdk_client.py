"""生成的 ``stock_sdk`` 的统一接入点。

Repository 只能通过本模块调用 SDK，避免把 SDK 响应对象、配置读取和
传输异常扩散到服务层。
"""

from __future__ import annotations

import logging
import os
from collections.abc import Mapping
from typing import Any

from stock_sdk import StockClient
from stock_sdk.exceptions import StockSdkError


logger = logging.getLogger(__name__)


class SdkDataAccessError(RuntimeError):
    """Repository 与远程数据服务交互时的基础异常。"""


class SdkConfigurationError(SdkDataAccessError):
    """远程数据服务缺少必要配置时抛出。"""


class SdkProtocolError(SdkDataAccessError):
    """远程响应不符合生成 SDK 约定时抛出。"""


class SdkOperationError(SdkDataAccessError):
    """远程服务已接收请求但业务校验失败时抛出。"""

    def __init__(self, message: str, *, code: int | None = None) -> None:
        """保存远程业务错误消息及可选错误码。"""
        super().__init__(message)
        self.code = code


class SdkDuplicateKeyError(SdkOperationError):
    """远程唯一约束冲突；调用方必须避免覆盖既有记录。"""


class SdkNotFoundError(SdkOperationError):
    """远程服务明确返回记录不存在时抛出。"""


class SdkFilterUnavailableError(SdkDataAccessError):
    """SDK 未声明所需业务筛选能力时抛出。"""


class StockSdkAdapter:
    """调用 SDK 分组接口，并向上层只返回解包后的 ``ret_obj``。"""

    def __init__(self, client: StockClient | Any | None = None) -> None:
        """允许注入 SDK 客户端；缺省时按集中配置延迟创建。"""
        self._client = client

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
    def _build_client(cls) -> StockClient:
        """根据集中配置构造 SDK 客户端，避免业务代码自行读取环境变量。"""
        base_url = str(cls._get_setting("STOCK_BASE_URL", "") or "").strip()
        if not base_url:
            raise SdkConfigurationError(
                "STOCK_BASE_URL 未配置，无法使用远程数据访问服务"
            )
        try:
            timeout = float(cls._get_setting("STOCK_API_TIMEOUT", 10.0))
        except (TypeError, ValueError) as exc:
            raise SdkConfigurationError("STOCK_API_TIMEOUT 必须是正数") from exc
        if timeout <= 0:
            raise SdkConfigurationError("STOCK_API_TIMEOUT 必须大于 0")
        return StockClient(
            base_url=base_url,
            token=str(cls._get_setting("STOCK_API_TOKEN", "") or "") or None,
            timeout=timeout,
        )

    def call(self, group_name: str, operation: str, payload: Mapping[str, Any]) -> Any:
        """调用一个 SDK 接口，并仅返回解包后的 ``ret_obj``。

        SDK 传输错误和远端业务失败会转换为本模块定义的异常，防止服务层
        依赖生成代码的具体响应类型。
        """
        if self._client is None:
            self._client = self._build_client()
        try:
            group = getattr(self._client, group_name)
            method = getattr(group, operation)
        except AttributeError as exc:
            raise SdkProtocolError(
                f"stock_sdk 未提供接口: {group_name}.{operation}"
            ) from exc

        try:
            response = method(dict(payload))
        except StockSdkError as exc:
            logger.warning(
                "远程数据接口调用失败: group=%s operation=%s error=%s",
                group_name,
                operation,
                exc.__class__.__name__,
            )
            raise SdkDataAccessError("远程数据服务暂不可用") from exc

        if not getattr(response, "is_success", False):
            code = getattr(response, "ret_code", None)
            message = str(getattr(response, "ret_msg", "") or "远程数据服务拒绝请求")
            logger.warning(
                "远程数据接口返回业务失败: group=%s operation=%s code=%s",
                group_name,
                operation,
                code,
            )
            # 远端服务以 409 或稳定错误码标识唯一键冲突，供锁和幂等写入处理。
            if code == 409 or "DUPLICATE_KEY" in message.upper():
                raise SdkDuplicateKeyError(message, code=code)
            if code == 404:
                raise SdkNotFoundError(message, code=code)
            raise SdkOperationError(message, code=code)
        return getattr(response, "ret_obj", None)

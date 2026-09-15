"""远程接口控制器的公共基类：通用调用器 ``_make_request``。

每个控制器（对应远程 Swagger 的一个 URL 分组，如 ``/api/StockData``）
继承本基类，把每个具体接口写成命名方法：方法体内一行
``self._make_request(HTTP 方法, 路径, 载荷)``，接口契约写在 docstring
的 curl 示例里。新增远程接口时在对应控制器文件追加一个方法即可。
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.remote_api.client import StockApiClient


class ControllerApi:
    """控制器基类：持有统一调用器，不做任何端点解析。"""

    def __init__(self, client: "StockApiClient") -> None:
        self._client = client

    def _make_request(
        self,
        method: str,
        path: str,
        payload: Mapping[str, Any] | None = None,
        *,
        token: str | None = None,
    ) -> Any:
        """通用调用器：发送请求并返回解包后的 ``ret_obj``。"""
        return self._client.request(method, path, payload, token=token)

    def _make_request_with_count(
        self,
        method: str,
        path: str,
        payload: Mapping[str, Any] | None = None,
        *,
        token: str | None = None,
    ) -> tuple[Any, int | None]:
        """分页接口专用：返回 ``(ret_obj, ret_count)``。

        ``ret_count`` 为信封携带的匹配总记录数，远端未返回时为 None。
        """
        return self._client.request_with_count(method, path, payload, token=token)

"""导航接口使用的远程 ``sys_model`` 数据访问。"""

from __future__ import annotations

from typing import Any

from app.repositories.sdk_client import StockSdkAdapter


class SysModelRepository:
    """读取远程模型表，避免 SDK 响应对象泄漏到导航接口。"""

    def __init__(self, client: StockSdkAdapter | None = None) -> None:
        """注入统一 SDK 适配器，便于测试远程模型数据。"""
        self.client = client or StockSdkAdapter()

    def list_all(self, *, page_size: int = 500) -> list[dict[str, Any]]:
        """按远端分页协议读取全部模型，并保持菜单排序顺序。"""
        page_index = 1
        models: list[dict[str, Any]] = []
        while True:
            raw = self.client.call(
                "sys_model",
                "get_data_by_page_list",
                {
                    "page_index": page_index,
                    "page_size": page_size,
                    "order_field": "order_num",
                    "order_type": "asc",
                },
            )
            if isinstance(raw, list):
                page = raw
            elif isinstance(raw, dict):
                page = next(
                    (raw[key] for key in ("items", "list", "records", "data")
                     if isinstance(raw.get(key), list)),
                    [],
                )
            else:
                page = []

            models.extend(dict(item) for item in page if isinstance(item, dict))
            if len(page) < page_size:
                return models
            page_index += 1

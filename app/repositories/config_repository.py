"""系统配置记录的远程 CRUD 访问。"""

from __future__ import annotations

from typing import Any

from app.repositories.base import SdkCrudRepository


class SystemConfigRepository(SdkCrudRepository):
    """封装系统配置的 SDK 分组，并提供按配置键查询的兼容方法。"""
    group_name = "param_system_configs"

    def list_all(self) -> list[dict[str, Any]]:
        """按 SDK 分页协议读取全部配置记录。"""
        page_index = 1
        items: list[dict[str, Any]] = []
        while True:
            page = self.list_page(
                page_index=page_index,
                page_size=200,
                order_field="key",
                order_type="asc",
            )
            items.extend(page["items"])
            if not page["items"] or len(items) >= page["total"]:
                return items
            page_index += 1

    def get_by_key(self, key: str) -> dict[str, Any] | None:
        """按配置键定位记录；服务端尚未提供专用筛选接口。"""
        return next((item for item in self.list_all() if item.get("key") == key), None)

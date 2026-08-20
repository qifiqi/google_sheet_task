# menu_service.py
"""
菜单服务：
通过 SDK 读取主 Web 的 sys_model 路由表，将扁平数据组装成前端需要的树形菜单。
仅允许本站绝对路径，过滤外部链接；菜单结果按用户短暂缓存。
"""
from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from typing import Any
import time


class MenuService:
    _cache: dict[str, tuple[float, list[dict[str, Any]]]] = {}
    cache_ttl_seconds = 60

    def __init__(self, repository) -> None:
        """保存远程模型仓储，用于构建导航菜单。"""
        self.repository = repository

    def get_menu(
        self,
        *,
        cache_key: str,
        is_available: Callable[[str], bool] | None = None,
    ) -> list[dict[str, Any]]:
        """从远程模型表读取菜单，并按可访问路由过滤。"""
        now = time.monotonic()
        cached = self._cache.get(cache_key)
        if cached and now - cached[0] < self.cache_ttl_seconds:
            return cached[1]
        menu = self.build_tree(self.repository.list_all(), is_available=is_available)
        self._cache[cache_key] = (now, menu)
        return menu

    @staticmethod
    def build_tree(
        rows: Iterable[Mapping[str, Any]],
        *,
        is_available: Callable[[str], bool] | None = None,
    ) -> list[dict[str, Any]]:
        """将远程模型平面记录构造成按父级排列的菜单树。"""
        nodes: dict[int, dict[str, Any]] = {}
        for row in rows:
            try:
                model_id = int(row.get("model_id"))
            except (TypeError, ValueError):
                continue
            if model_id in nodes:
                continue
            link = str(row.get("model_link") or "").strip()
            # Only same-origin absolute paths are accepted. ``//host/path`` is
            # deliberately rejected to prevent an open redirect.
            is_local_link = bool(link) and link.startswith("/") and not link.startswith("//")
            available = is_local_link and (is_available(link) if is_available else True)
            nodes[model_id] = {
                "model_id": model_id,
                "model_name": str(row.get("model_name") or ""),
                "model_code": str(row.get("model_code") or ""),
                "model_icon": str(row.get("model_icon") or ""),
                "model_link": link if is_local_link else "",
                "parent_model_id": int(row.get("parent_model_id") or 0),
                "order_num": int(row.get("order_num") or 0),
                "model_type": row.get("model_type"),
                "available": available,
                "disabled": bool(link) and not available,
                "children": [],
            }

        roots: list[dict[str, Any]] = []
        for node in nodes.values():
            parent = nodes.get(node["parent_model_id"])
            if parent and parent is not node:
                parent["children"].append(node)
            else:
                roots.append(node)

        def sort_tree(items: list[dict[str, Any]]) -> None:
            """递归按菜单序号和模型主键稳定排序。"""
            items.sort(key=lambda item: (item["order_num"], item["model_id"]))
            for item in items:
                sort_tree(item["children"])
                if not item["children"]:
                    item.pop("children")

        sort_tree(roots)
        return roots

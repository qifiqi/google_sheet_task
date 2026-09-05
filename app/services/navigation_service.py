"""导航菜单服务（数据层：navigation_repository）。

路由层（meta/nav、导航管理）统一经本服务访问导航数据，
不再直接感知 repository。
"""

from __future__ import annotations

from app.repositories import navigation_repository


def list_visible_entities():
    """可见导航菜单实体列表（排序/权限过滤由调用方完成，保持原语义）。"""
    return navigation_repository.list_visible_entities()

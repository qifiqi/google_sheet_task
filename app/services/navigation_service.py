"""导航菜单服务（数据层：navigation_repository）。

meta/nav 与导航管理 CRUD 统一经本服务；实体 → 管理端 payload 的序列化、
payload 校验与 sync_navigation_permissions 编排收敛于此。
"""

from __future__ import annotations

from app.exceptions import NotFoundError, ValidationError
from app.navigation import sync_navigation_permissions
from app.repositories import navigation_repository
from app.services.config_manager import coerce_bool


def list_visible_entities():
    """可见导航菜单实体列表（meta/nav 消费，排序/权限过滤由调用方完成）。"""
    return navigation_repository.list_visible_entities()


def _menu_item_payload(item):
    """实体 → 管理端 payload（键与归位前一致）。"""
    return {
        "id": item.id,
        "key": item.key,
        "label": item.label,
        "path": item.path or "",
        "permission": item.permission or "",
        "parent_key": item.parent_key or "",
        "sort_order": item.sort_order or 0,
        "is_visible": bool(item.is_visible),
        "created_at": item.created_at.isoformat() if item.created_at else None,
        "updated_at": item.updated_at.isoformat() if item.updated_at else None,
    }


def _normalize_blank(value):
    text = str(value or "").strip()
    return text or None


def _coerce_sort_order(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _validate_menu_payload(data: dict, item_id=None) -> dict:
    """管理端 payload 校验；失败抛 ValidationError（400 语义）。"""
    key = str(data.get("key") or "").strip()
    label = str(data.get("label") or "").strip()
    path = _normalize_blank(data.get("path"))
    permission = _normalize_blank(data.get("permission"))
    parent_key = _normalize_blank(data.get("parent_key"))

    if not key:
        raise ValidationError("缺少路由 key")
    if not label:
        raise ValidationError("缺少菜单名称")
    if parent_key == key:
        raise ValidationError("父级菜单不能选择自己")

    duplicate = navigation_repository.get_by_key(key)
    if duplicate and duplicate["id"] != item_id:
        raise ValidationError("路由 key 已存在")

    if parent_key:
        parent = navigation_repository.get_by_key(parent_key)
        if not parent:
            raise ValidationError("父级菜单不存在")
        if parent["path"]:
            raise ValidationError("父级菜单不能是可跳转路由")

    is_visible = coerce_bool(data.get("is_visible"), default=False)
    if is_visible and path and not permission:
        raise ValidationError("开启显示的页面路由必须填写权限码")

    return {
        "key": key,
        "label": label,
        "path": path,
        "permission": permission,
        "parent_key": parent_key,
        "sort_order": _coerce_sort_order(data.get("sort_order")),
        "is_visible": is_visible,
    }


def list_menu_items() -> list[dict]:
    """管理端路由表全量列表（parent_key, sort_order, id 排序）。"""
    items = [
        _menu_item_payload(item)
        for item in navigation_repository.list_all_entities()
    ]
    items.sort(key=lambda item: (item["parent_key"] or "", item["sort_order"], item["id"]))
    return items


def create_menu_item(data: dict) -> dict:
    """新增路由记录（默认不可见），并同步页面权限。"""
    payload = _validate_menu_payload(data)
    with navigation_repository.transaction():
        item = navigation_repository.create_entity(payload, commit=False)
        sync_navigation_permissions([item])
    return _menu_item_payload(item)


def update_menu_item(item_id: int, data: dict) -> dict:
    """更新路由记录，并同步页面权限。"""
    item = navigation_repository.get_entity(item_id)
    if not item:
        raise NotFoundError("路由记录不存在")

    payload = _validate_menu_payload(data, item_id=item_id)
    with navigation_repository.transaction():
        for key, value in payload.items():
            setattr(item, key, value)
        sync_navigation_permissions([item])
    return _menu_item_payload(item)


def delete_menu_item(item_id: int) -> None:
    """删除路由记录；存在子菜单时拒绝。"""
    item = navigation_repository.get_entity(item_id)
    if not item:
        raise NotFoundError("路由记录不存在")

    if navigation_repository.count_children(item.key):
        raise ValidationError("请先删除或移动子菜单")

    navigation_repository.delete(item_id)

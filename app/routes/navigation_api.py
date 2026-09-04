"""侧边栏导航菜单 API（自 config_api.py 归位，URL 不变）。

数据层：navigation_repository；sync_navigation_permissions（范围外模块）
依赖实体属性，经 navigation_repository 实体出口交接。
"""

from flask import Blueprint, request

from app.exceptions import BadRequestError, NotFoundError
from app.navigation import sync_navigation_permissions
from app.repositories import navigation_repository
from app.utils.api_response import success
from app.utils.auth import login_required

navigation_api_bp = Blueprint('navigation_api', __name__)


def _navigation_menu_payload(item):
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


def _coerce_bool(value, default=False):
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def _coerce_sort_order(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _normalize_blank(value):
    text = str(value or "").strip()
    return text or None


def _validate_navigation_payload(data, item_id=None):
    key = str(data.get("key") or "").strip()
    label = str(data.get("label") or "").strip()
    path = _normalize_blank(data.get("path"))
    permission = _normalize_blank(data.get("permission"))
    parent_key = _normalize_blank(data.get("parent_key"))

    if not key:
        return None, "缺少路由 key"
    if not label:
        return None, "缺少菜单名称"
    if parent_key == key:
        return None, "父级菜单不能选择自己"

    duplicate = navigation_repository.get_by_key(key)
    if duplicate and duplicate["id"] != item_id:
        return None, "路由 key 已存在"

    if parent_key:
        parent = navigation_repository.get_by_key(parent_key)
        if not parent:
            return None, "父级菜单不存在"
        if parent["path"]:
            return None, "父级菜单不能是可跳转路由"

    is_visible = _coerce_bool(data.get("is_visible"), default=False)
    if is_visible and path and not permission:
        return None, "开启显示的页面路由必须填写权限码"

    return {
        "key": key,
        "label": label,
        "path": path,
        "permission": permission,
        "parent_key": parent_key,
        "sort_order": _coerce_sort_order(data.get("sort_order")),
        "is_visible": is_visible,
    }, None


@navigation_api_bp.route('/navigation-menu-items', methods=['GET'])
@login_required
def list_navigation_menu_items():
    """获取侧边栏路由表"""
    items = [
        _navigation_menu_payload(item)
        for item in navigation_repository.list_all_entities()
    ]
    items.sort(key=lambda item: (item["parent_key"] or "", item["sort_order"], item["id"]))
    return success(data={"items": items})


@navigation_api_bp.route('/navigation-menu-items', methods=['POST'])
@login_required
def create_navigation_menu_item():
    """新增侧边栏路由表记录，默认不可见，避免新页面直接暴露"""
    data = request.get_json() or {}
    payload, error_message = _validate_navigation_payload(data)
    if error_message:
        raise BadRequestError(error_message)

    with navigation_repository.transaction():
        item = navigation_repository.create_entity(payload, commit=False)
        sync_navigation_permissions([item])
    return success(
        data={"item": _navigation_menu_payload(item)},
        message="路由已新增，默认按可见开关和权限控制侧边栏展示",
    )


@navigation_api_bp.route('/navigation-menu-items/<int:item_id>', methods=['PUT'])
@login_required
def update_navigation_menu_item(item_id):
    """更新侧边栏路由表记录"""
    item = navigation_repository.get_entity(item_id)
    if not item:
        raise NotFoundError("路由记录不存在")

    data = request.get_json() or {}
    payload, error_message = _validate_navigation_payload(data, item_id=item_id)
    if error_message:
        raise BadRequestError(error_message)

    with navigation_repository.transaction():
        for key, value in payload.items():
            setattr(item, key, value)
        sync_navigation_permissions([item])
    return success(data={"item": _navigation_menu_payload(item)}, message="路由已更新")


@navigation_api_bp.route('/navigation-menu-items/<int:item_id>', methods=['DELETE'])
@login_required
def delete_navigation_menu_item(item_id):
    """删除侧边栏路由表记录"""
    item = navigation_repository.get_entity(item_id)
    if not item:
        raise NotFoundError("路由记录不存在")

    if navigation_repository.count_children(item.key):
        raise BadRequestError("请先删除或移动子菜单")

    navigation_repository.delete(item_id)
    return success(message="路由已删除")

"""侧边栏导航菜单 API（自 config_api.py 归位，URL 不变）。

CRUD 编排、payload 校验与权限同步在 navigation_service；
路由层只做 HTTP 解析与统一信封。
"""

from flask import Blueprint, request

from app.services import navigation_service
from app.utils.api_response import success
from app.utils.auth import login_required

navigation_api_bp = Blueprint('navigation_api', __name__)


@navigation_api_bp.route('/navigation-menu-items', methods=['GET'])
@login_required
def list_navigation_menu_items():
    """获取侧边栏路由表"""
    return success(data={"items": navigation_service.list_menu_items()})


@navigation_api_bp.route('/navigation-menu-items', methods=['POST'])
@login_required
def create_navigation_menu_item():
    """新增侧边栏路由表记录，默认不可见，避免新页面直接暴露"""
    item = navigation_service.create_menu_item(request.get_json() or {})
    return success(
        data={"item": item},
        message="路由已新增，默认按可见开关和权限控制侧边栏展示",
    )


@navigation_api_bp.route('/navigation-menu-items/<int:item_id>', methods=['PUT'])
@login_required
def update_navigation_menu_item(item_id):
    """更新侧边栏路由表记录"""
    item = navigation_service.update_menu_item(item_id, request.get_json() or {})
    return success(data={"item": item}, message="路由已更新")


@navigation_api_bp.route('/navigation-menu-items/<int:item_id>', methods=['DELETE'])
@login_required
def delete_navigation_menu_item(item_id):
    """删除侧边栏路由表记录"""
    navigation_service.delete_menu_item(item_id)
    return success(message="路由已删除")

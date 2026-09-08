"""元数据 API — 为前端提供版本、枚举、导航等静态配置。

鉴权与路由表模式（单 Token 子服务模式，2026-09 启用）:

- 导航路由表仅保留拉取接口：``/api/meta/nav`` 与 ``/api/navigation/menu``
  按请求头 Token 调用远程 ``POST /api/SysUser/GetUserRoleList``，
  与主站前端（``SIDEBAR-GUIDE.md``）一致返回平铺模型数组。本接口是
  纯代理：不做排序、不过滤、不组树（排序与组树由本站前端完成），
  仅把站内相对路径的图标地址归一化为绝对地址。菜单目标以权限系统
  配置的 ``model_link`` 为准（运维约定填本站可达路径）。
  本地 ``NavigationMenuItem`` 菜单管理已注释，不再维护本地路由表。
- 枚举值已从 ``app.models`` 迁至 ``app.domain_constants``（纯常量，
  不涉及数据库），此处 import 仅为兼容旧引用路径。
"""
import os
import re

from flask import Blueprint, current_app, g
from app.models import (
    GoogleSheetTableType,
    GoogleSheetTokenTaskType,
    StockMarketType,
    TaskStatus,
    TaskType,
)
# 本地路由表与全量 sys_model 分支停用后不再引用：
# from app.models import NavigationMenuItem
# from app.repositories.sys_model_repository import SysModelRepository
# from app.navigation import build_navigation_tree
from app.repositories.sdk_client import SdkDataAccessError, SdkOperationError
from app.utils.api_response import success
from app.utils.auth import login_required
from app.utils.auth import get_request_token

meta_api_bp = Blueprint('meta_api', __name__)

# 绝对地址（http(s):// 或协议相对 //host）图标不参与归一化（文档第 5 节）。
_ABSOLUTE_ICON_RE = re.compile(r'^(?:[a-z]+:)?//', re.IGNORECASE)


# @meta_api_bp.route('/meta/versions', methods=['GET'])
# def get_versions():
#     """返回可用的任务版本列表"""
#     versions = [
#         {"value": "c3", "label": "C3", "create_url": "/google-sheet/create"},
#         {"value": "c4", "label": "C4", "create_url": "/google-sheet/create?version=c4"},
#         {"value": "c5", "label": "C5", "create_url": "/google-sheet/create?version=c5"},
#         {"value": "C7", "label": "C7", "create_url": "/google-sheet/create?version=c7"},
#         {"value": "c31", "label": "C31 批量", "create_url": "/google-sheet/create?version=c31"},
#         {"value": "backtest_training", "label": "回测训练", "create_url": "/backtest-training/create"},
#         {"value": "backtest_multi_product", "label": "多品数据回测", "create_url": "/backtest-multi-product/create"},
#     ]
#     return success(data=versions)


@meta_api_bp.route('/meta/enums', methods=['GET'])
def get_enums():
    """返回前端需要的所有枚举值"""
    return success(data={
        "google_sheet_table_types": GoogleSheetTableType.choices(),
        "google_sheet_token_task_types": GoogleSheetTokenTaskType.choices(),
        "task_statuses": TaskStatus.choices(),
        "task_status_editable": TaskStatus.editable_choices(),
        "task_types": TaskType.choices(),
        "stock_markets": StockMarketType.choices(),
    })


@meta_api_bp.route('/meta/nav', methods=['GET'])
@login_required
def get_nav():
    """按请求头 Token 读取远程路由表（GetUserRoleList）。

    返回平铺模型数组（``model_id / model_name / model_code /
    parent_model_id / order_num / model_icon / model_link`` 等），
    排序与两级组树由前端完成；``model_link`` 由权限系统配置保证
    指向本站可达路径。原本地路由表 / 全量 sys_model 分支注释保留。
    """
    return _remote_role_menu_response()


@meta_api_bp.route('/navigation/menu', methods=['GET'])
@login_required
def get_navigation_menu():
    """为前端提供稳定菜单接口；与 /meta/nav 同源（GetUserRoleList）。"""
    return _remote_role_menu_response()


def _remote_role_menu_response():
    """用请求头 Token 拉取 GetUserRoleList 并原样返回模型数组。"""

    token = get_request_token()
    if not token:
        return {'code': 401, 'data': None, 'message': '未提供认证令牌'}, 401
    try:
        rows = _get_role_menu_rows(token)
    except (SdkDataAccessError, SdkOperationError):
        return {'code': 503, 'data': None, 'message': '远程菜单服务暂不可用'}, 503
    return success(data={"items": rows})


def _get_role_menu_rows(token):
    """读取路由表；除图标地址归一化外不改动远程返回的行数据。"""
    from app.services.token_identity_service import get_token_identity_service

    role_rows = get_token_identity_service().get_user_role_list(token)
    return [
        {**row, 'model_icon': _normalize_icon_url(row.get('model_icon'))}
        for row in role_rows
    ]


def _normalize_icon_url(icon) -> str:
    """按文档第 5 节归一化菜单图标地址。

    已是绝对地址（http(s):// 或协议相对 //）的原样返回；站内相对
    路径拼主站 API 基址（前端不感知 ``STOCK_BASE_URL``）。
    """
    raw = str(icon or '').strip()
    if not raw or _ABSOLUTE_ICON_RE.match(raw):
        return raw
    base = str(
        current_app.config.get('STOCK_BASE_URL')
        or os.environ.get('STOCK_BASE_URL')
        or ''
    ).rstrip('/')
    return f"{base}/{raw.lstrip('/')}" if base else raw


# ---------- 旧导航实现（本地路由表 / 全量 sys_model），注释保留 ----------
# def _local_menu_response():
#     """按本地用户权限过滤 NavigationMenuItem 并构造旧版导航响应。"""
#     user_permissions = g.current_user.get_permissions()
#     rows = (
#         NavigationMenuItem.query
#         .filter_by(is_visible=True)
#         .order_by(NavigationMenuItem.sort_order.asc(), NavigationMenuItem.id.asc())
#         .all()
#     )
#     rows = sorted(rows, key=lambda item: (item.parent_key or '', item.sort_order, item.id))
#
#     def has_permission(required_permission):
#         """支持 view 权限由同资源 manage 权限隐式满足的旧规则。"""
#         if not required_permission or required_permission in user_permissions:
#             return True
#         return required_permission.endswith(':view') and (
#             f"{required_permission.split(':', 1)[0]}:manage" in user_permissions
#         )
#
#     def filter_items(items):
#         """递归移除当前用户无权访问的菜单节点。"""
#         result = []
#         for item in items:
#             if item.get('permission') and not has_permission(item['permission']):
#                 continue
#             children = filter_items(item.get('children', []))
#             if children:
#                 result.append({**item, 'children': children})
#             elif 'children' not in item:
#                 result.append(item)
#         return result
#
#     return success(data={
#         'items': filter_items(build_navigation_tree(rows)),
#         'page_permissions': [
#             {'path': item.path, 'permission': item.permission}
#             for item in rows
#             if item.path and (item.permission or '').startswith('page:')
#         ],
#     })
#
#
# def _menu_response():
#     """构造当前用户可访问的远程菜单响应。"""
#     try:
#         return success(data={"items": _get_remote_menu()})
#     except (SdkDataAccessError, SdkOperationError):
#         return {"code": 503, "data": None, "message": "远程菜单服务暂不可用"}, 503
#
#
# def _get_remote_menu():
#     """读取远程模型菜单，并用本地路由判断其可用性。"""
#     user_id = getattr(getattr(g, "current_user", None), "id", "anonymous")
#     def is_local_route(link: str) -> bool:
#         """判断远程菜单链接是否对应当前应用的可访问 GET 路由。"""
#         path = link.split("?", 1)[0]
#         try:
#             current_app.url_map.bind("").match(path, method="GET")
#             return True
#         except NotFound:
#             return False
#
#     return MenuService(SysModelRepository()).get_menu(
#         cache_key=str(user_id), is_available=is_local_route,
#     )

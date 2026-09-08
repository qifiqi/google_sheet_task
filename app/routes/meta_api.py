"""元数据 API — 为前端提供版本、枚举、导航等静态配置。

鉴权与路由表模式（单 Token 子服务模式，2026-09 启用）:

- 导航路由表仅保留拉取接口：``/api/meta/nav`` 与 ``/api/navigation/menu``
  按请求头 Token 调用远程 ``POST /api/SysUser/GetUserRoleList``
  （经 ``MenuService.build_tree`` 组树并只保留映射到本站路由的条目）。
  本地 ``NavigationMenuItem`` 菜单管理与全量 ``sys_model`` 分支已注释，
  不再维护本地路由表。
- 枚举值已从 ``app.models`` 迁至 ``app.domain_constants``（纯常量，
  不涉及数据库），此处 import 仅为兼容旧引用路径。
"""
from flask import Blueprint, current_app, g
from werkzeug.exceptions import NotFound
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
from app.services.menu_service import MenuService
from app.utils.api_response import success
from app.utils.auth import login_required

meta_api_bp = Blueprint('meta_api', __name__)

# 远程路由表 model_code -> 本站页面路径映射。
# GetUserRoleList 返回的 model_link 是主站视图路径（/views/*.html），
# 本子服务只展示映射到本站路由的条目；分组节点（无链接）由子节点
# 保留情况决定。新增本站页面时在此登记对应模型代码即可。
# 注意: 映射目标应为前端 Vue 路由可达的路径；``/admin/eastmoney-kline``
# 当前由 Flask 模板提供，Vue 端访问需先在前端注册对应路由或在
# nginx 为该路径单独配置反向代理。
REMOTE_MODEL_ROUTE_MAP = {
    'eastMoneyKlineManage': '/admin/eastmoney-kline',
}


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

    单 Token 子服务模式下，菜单来自当前用户在主 Web 被授权的模型列表;
    仅保留 REMOTE_MODEL_ROUTE_MAP 中映射到本站路由的条目。
    原本地路由表 / 全量 sys_model 分支注释保留。
    """
    return _remote_role_menu_response()


@meta_api_bp.route('/navigation/menu', methods=['GET'])
@login_required
def get_navigation_menu():
    """为前端提供稳定菜单接口；与 /meta/nav 同源（GetUserRoleList）。"""
    return _remote_role_menu_response()


def _remote_role_menu_response():
    """用请求头 Token 拉取 GetUserRoleList 并组装本站菜单树。"""
    from app.utils.auth import get_request_token

    token = get_request_token()
    if not token:
        return {'code': 401, 'data': None, 'message': '未提供认证令牌'}, 401
    try:
        rows = _get_role_menu_rows(token)
    except (SdkDataAccessError, SdkOperationError):
        return {'code': 503, 'data': None, 'message': '远程菜单服务暂不可用'}, 503
    return success(data={"items": rows})


def _get_role_menu_rows(token):
    """把 GetUserRoleList 模型数组转换为前端 key/label/path 菜单树。"""
    from app.services.menu_service import MenuService
    from app.services.token_identity_service import get_token_identity_service

    role_rows = get_token_identity_service().get_user_role_list(token)

    def is_local_route(link: str) -> bool:
        """判断映射后的菜单链接是否对应当前应用的可访问 GET 路由。"""
        path = link.split("?", 1)[0]
        try:
            current_app.url_map.bind("").match(path, method="GET")
            return True
        except NotFound:
            return False

    # 仅保留映射到本站路由的模型与分组节点（无链接的父级）。
    scoped_rows = []
    for row in role_rows:
        local_path = REMOTE_MODEL_ROUTE_MAP.get(str(row.get('model_code') or ''))
        if local_path:
            scoped = dict(row)
            scoped['model_link'] = local_path
            scoped_rows.append(scoped)
        elif not str(row.get('model_link') or '').strip():
            scoped_rows.append(dict(row))

    tree = MenuService.build_tree(scoped_rows, is_available=is_local_route)
    return _to_vue_menu_items(tree)


def _to_vue_menu_items(tree):
    """把 sys_model 菜单树转换为前端侧边栏使用的 key/label/path 结构。

    - 叶子节点: 有可用本站链接时输出 ``{key, label, path}``;
    - 分组节点: 无链接，仅当子树非空时保留 ``children``。
    前端 AppSidebar 依赖 ``item.path`` 区分页面项与分组项。
    """
    result = []
    for node in tree:
        children = _to_vue_menu_items(node.get('children') or [])
        link = str(node.get('model_link') or '')
        if link:
            if node.get('available') and node.get('model_code'):
                result.append({
                    'key': str(node['model_code']),
                    'label': str(node.get('model_name') or node['model_code']),
                    'path': link,
                })
            continue
        if children:
            result.append({
                'key': str(node.get('model_code') or node.get('model_id')),
                'label': str(node.get('model_name') or ''),
                'children': children,
            })
    return result


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

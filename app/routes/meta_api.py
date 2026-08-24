"""元数据 API — 为前端提供版本、枚举、导航等静态配置"""
from flask import Blueprint, current_app, g
from werkzeug.exceptions import NotFound
from app.models import (
    GoogleSheetTableType,
    GoogleSheetTokenTaskType,
    NavigationMenuItem,
    StockMarketType,
    TaskStatus,
    TaskType,
)
from app.repositories.sys_model_repository import SysModelRepository
from app.repositories.sdk_client import SdkDataAccessError, SdkOperationError
from app.services.menu_service import MenuService
from app.navigation import build_navigation_tree
from app.utils.api_response import success
from app.utils.auth import login_required

meta_api_bp = Blueprint('meta_api', __name__)


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
    """默认返回本地路由表；主 Web 网关启用时代理远程 sys_model。"""
    if current_app.config.get('REMOTE_IDENTITY_GATEWAY_ENABLED', False):
        return _menu_response()
    return _local_menu_response()


@meta_api_bp.route('/navigation/menu', methods=['GET'])
@login_required
def get_navigation_menu():
    """为前端提供稳定菜单接口；该接口不直接调用远程服务。"""
    return _menu_response()


def _local_menu_response():
    """按本地用户权限过滤 NavigationMenuItem 并构造旧版导航响应。"""
    user_permissions = g.current_user.get_permissions()
    rows = (
        NavigationMenuItem.query
        .filter_by(is_visible=True)
        .order_by(NavigationMenuItem.sort_order.asc(), NavigationMenuItem.id.asc())
        .all()
    )
    rows = sorted(rows, key=lambda item: (item.parent_key or '', item.sort_order, item.id))

    def has_permission(required_permission):
        """支持 view 权限由同资源 manage 权限隐式满足的旧规则。"""
        if not required_permission or required_permission in user_permissions:
            return True
        return required_permission.endswith(':view') and (
            f"{required_permission.split(':', 1)[0]}:manage" in user_permissions
        )

    def filter_items(items):
        """递归移除当前用户无权访问的菜单节点。"""
        result = []
        for item in items:
            if item.get('permission') and not has_permission(item['permission']):
                continue
            children = filter_items(item.get('children', []))
            if children:
                result.append({**item, 'children': children})
            elif 'children' not in item:
                result.append(item)
        return result

    return success(data={
        'items': filter_items(build_navigation_tree(rows)),
        'page_permissions': [
            {'path': item.path, 'permission': item.permission}
            for item in rows
            if item.path and (item.permission or '').startswith('page:')
        ],
    })


def _menu_response():
    """构造当前用户可访问的远程菜单响应。"""
    try:
        return success(data={"items": _get_remote_menu()})
    except (SdkDataAccessError, SdkOperationError):
        return {"code": 503, "data": None, "message": "远程菜单服务暂不可用"}, 503


def _get_remote_menu():
    """读取远程模型菜单，并用本地路由判断其可用性。"""
    user_id = getattr(getattr(g, "current_user", None), "id", "anonymous")
    def is_local_route(link: str) -> bool:
        """判断远程菜单链接是否对应当前应用的可访问 GET 路由。"""
        path = link.split("?", 1)[0]
        try:
            current_app.url_map.bind("").match(path, method="GET")
            return True
        except NotFound:
            return False

    return MenuService(SysModelRepository()).get_menu(
        cache_key=str(user_id), is_available=is_local_route,
    )

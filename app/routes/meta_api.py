"""元数据 API — 为前端提供版本、枚举、导航等静态配置。

鉴权与路由表模式（单 Token 子服务模式，db-to-http 迁移启用）:

- ``/api/meta/nav`` 按请求头 Token 调用远程
  ``POST /api/SysUser/GetUserRoleList`` 读取路由表，并在服务端把远端
  平铺模型行（``model_name / model_link / parent_model_id / order_num``）
  组装成本站前端既有契约的树形结构（``{label, path, children}``），
  前端渲染代码零改动。仅允许站内绝对路径，外部链接过滤；
  ``page_permissions`` 固定返回空数组（本地权限码已停用，页面守卫
  以路由表可见性为准）。
- 本地 ``NavigationMenuItem`` 菜单管理随本地 RBAC 一并停用。
"""
import re

from flask import Blueprint
from app.models import (
    GoogleSheetTableType,
    GoogleSheetTokenTaskType,
    StockMarketType,
    TaskStatus,
    TaskType,
)
from app.remote_api import RemoteApiError, RemoteApiOperationError
from app.utils.api_response import success
from app.utils.auth import login_required, get_request_token

meta_api_bp = Blueprint('meta_api', __name__)

# 绝对地址（http(s):// 或协议相对 //host）链接不属于站内路由，直接过滤。
_ABSOLUTE_LINK_RE = re.compile(r'^(?:[a-z]+:)?//', re.IGNORECASE)


@meta_api_bp.route('/meta/versions', methods=['GET'])
def get_versions():
    """返回可用的任务版本列表"""
    versions = [
        {"value": "c3", "label": "C3", "create_url": "/google-sheet/create"},
        {"value": "c4", "label": "C4", "create_url": "/google-sheet/create?version=c4"},
        {"value": "c5", "label": "C5", "create_url": "/google-sheet/create?version=c5"},
        {"value": "c7", "label": "C7", "create_url": "/google-sheet/create?version=c7"},
        {"value": "c31", "label": "C31 批量", "create_url": "/google-sheet/create?version=c31"},
        {"value": "backtest_training", "label": "回测训练", "create_url": "/backtest-training/create"},
        {"value": "backtest_multi_product", "label": "多品数据回测", "create_url": "/backtest-multi-product/create"},
    ]
    return success(data=versions)


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
    """按请求头 Token 读取远程路由表（GetUserRoleList）并组装旧版菜单树。

    前端契约保持不变：``{items: [{label, path, children?}]}``。
    """
    token = get_request_token()
    if not token:
        return {'code': 401, 'data': None, 'message': '未提供认证令牌'}, 401
    try:
        from app.services.token_identity_service import get_token_identity_service

        rows = get_token_identity_service().get_user_role_list(token)
    except (RemoteApiError, RemoteApiOperationError):
        return {'code': 503, 'data': None, 'message': '远程菜单服务暂不可用'}, 503
    return success(data={"items": _build_menu_tree(rows), "page_permissions": []})


def _build_menu_tree(rows):
    """远端平铺模型行 → 前端旧契约树（label/path/children，order_num 排序）。

    仅接受站内绝对路径（/ 开头且非 //）；外部链接与空链接丢弃；
    父节点在远端缺失时按根节点处理。
    """
    nodes: dict[int, dict] = {}
    for row in rows or []:
        try:
            model_id = int(row.get("model_id"))
        except (TypeError, ValueError):
            continue
        if model_id in nodes:
            continue
        path = str(row.get("model_link") or "").strip()
        if not path or path.startswith("//") or _ABSOLUTE_LINK_RE.match(path):
            continue
        nodes[model_id] = {
            "label": str(row.get("model_name") or ""),
            "path": path,
            "parent_model_id": _safe_int(row.get("parent_model_id")),
            "order_num": _safe_int(row.get("order_num")),
            "children": [],
        }

    roots = []
    for node in nodes.values():
        parent = nodes.get(node["parent_model_id"])
        if parent is not None and parent is not node:
            parent["children"].append(node)
        else:
            roots.append(node)

    def _sort(items):
        items.sort(key=lambda item: item["order_num"])
        for item in items:
            if item.get("children"):
                _sort(item["children"])
            else:
                item.pop("children", None)
            item.pop("order_num", None)

    _sort(roots)
    return roots


def _safe_int(value):
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0

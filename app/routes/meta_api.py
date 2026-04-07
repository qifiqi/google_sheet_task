"""元数据 API — 为前端提供版本、枚举、导航等静态配置"""
import json
from flask import Blueprint
from app.models import GoogleSheetTableType, GoogleSheetTokenTaskType, SystemConfig
from app.utils.api_response import success
from app.utils.auth import login_required

meta_api_bp = Blueprint('meta_api', __name__)


@meta_api_bp.route('/meta/versions', methods=['GET'])
def get_versions():
    """返回可用的任务版本列表"""
    versions = [
        {"value": "c3", "label": "C3", "create_url": "/google-sheet/create"},
        {"value": "c4", "label": "C4", "create_url": "/google-sheet/create?version=c4"},
        {"value": "c5", "label": "C5", "create_url": "/google-sheet/create?version=c5"},
        {"value": "c31", "label": "C31 批量", "create_url": "/google-sheet/create?version=c31"},
        {"value": "backtest_training", "label": "回测训练", "create_url": "/backtest-training/create"},
    ]
    return success(data=versions)


@meta_api_bp.route('/meta/enums', methods=['GET'])
def get_enums():
    """返回前端需要的所有枚举值"""
    return success(data={
        "google_sheet_table_types": GoogleSheetTableType.choices(),
        "google_sheet_token_task_types": GoogleSheetTokenTaskType.choices(),
    })


@meta_api_bp.route('/meta/nav', methods=['GET'])
@login_required
def get_nav():
    """返回当前用户有权访问的导航菜单，从 system_configs.nav_menu 读取并按权限过滤"""
    from flask import g

    user_perms = g.current_user.get_permissions()

    config = SystemConfig.query.filter_by(key='nav_menu').first()
    if not config or not config.value:
        return success(data=[])

    try:
        all_nav = json.loads(config.value)
    except (ValueError, TypeError):
        return success(data=[])

    def filter_nav(items):
        result = []
        for item in items:
            perm = item.get('permission')
            if perm and perm not in user_perms:
                continue
            if 'children' in item:
                children = filter_nav(item['children'])
                if children:
                    result.append({**item, 'children': children})
            else:
                result.append(item)
        return result

    return success(data=filter_nav(all_nav))

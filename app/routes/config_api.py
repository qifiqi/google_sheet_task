"""配置管理 API（数据层：system_config_repository + navigation_repository）。

/config POST 仍走 config_manager（保持缓存语义：update_configs 内部负责
写库 + 负缓存刷新；repository 只管行级读写）。
"""
from flask import Blueprint, request

from app.exceptions import BadRequestError, NotFoundError, ServiceError
from app.navigation import sync_navigation_permissions
from app.repositories import navigation_repository, system_config_repository
from app.services.config_manager import get_config_manager
from app.utils.api_response import success
from app.schemas.config import ConfigBatchSchema, SystemConfigUpdateSchema
from app.utils.auth import login_required
from app.utils.request_parsing import parse_body
from app.utils.logger import get_logger

logger = get_logger(__name__)

config_api_bp = Blueprint('config_api', __name__)


@config_api_bp.route('/config', methods=['GET'])
@login_required
def get_config():
    """获取系统配置"""
    config_manager = get_config_manager()
    configs = config_manager.get_all_configs(force_refresh=True)
    return success(data={"config": configs})


@config_api_bp.route('/config', methods=['POST'])
@login_required
def update_config():
    """更新系统配置"""
    data = parse_body(ConfigBatchSchema).root
    if not data:
        raise BadRequestError("请求数据为空")

    logger.info(f"接收到配置更新请求: {len(data)} 个配置项, keys={list(data.keys())}")

    config_manager = get_config_manager()
    updated = config_manager.update_configs(data)
    if updated:
        logger.info("配置更新成功，缓存已刷新")
        return success(message="配置更新成功，已立即生效")
    raise ServiceError("配置更新失败")


@config_api_bp.route('/config/validate', methods=['GET'])
@login_required
def validate_config():
    """验证配置状态"""
    config_manager = get_config_manager()

    rows = system_config_repository.list_rows()
    db_configs = {row["key"]: row["value"] for row in rows}

    cache_configs = config_manager.get_cache_snapshot()
    gs_config = config_manager.get_google_sheet_config()

    return success(data={
        "validation": {
            "database_configs": db_configs,
            "cache_configs": cache_configs,
            "google_sheet_config": gs_config,
            "cache_size": len(cache_configs),
            "db_size": len(db_configs),
        }
    })


@config_api_bp.route('/system-configs', methods=['GET'])
@login_required
def list_system_configs():
    """获取 system_configs 配置列表"""
    return success(data={"configs": system_config_repository.list_rows()})


@config_api_bp.route('/system-configs/<string:key>', methods=['PUT'])
@login_required
def update_system_config(key):
    """更新单条配置"""
    data = parse_body(SystemConfigUpdateSchema).root

    fields = {}
    if 'value' in data:
        fields["value"] = data['value']
    if 'description' in data:
        fields["description"] = data['description']

    updated = system_config_repository.update(key, fields)
    if updated is None:
        raise NotFoundError("配置不存在")

    try:
        get_config_manager().refresh_cache()
    except Exception as e:
        logger.warning(f"更新配置后刷新缓存失败: {e}")

    return success(data={"config": updated})


def _navigation_menu_payload(item):
    """实体 → 管理端 payload（键与迁移前一致）。"""
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


@config_api_bp.route('/navigation-menu-items', methods=['GET'])
@login_required
def list_navigation_menu_items():
    """获取侧边栏路由表"""
    items = [
        _navigation_menu_payload(item)
        for item in navigation_repository.list_all_entities()
    ]
    items.sort(key=lambda item: (item["parent_key"] or "", item["sort_order"], item["id"]))
    return success(data={"items": items})


@config_api_bp.route('/navigation-menu-items', methods=['POST'])
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


@config_api_bp.route('/navigation-menu-items/<int:item_id>', methods=['PUT'])
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


@config_api_bp.route('/navigation-menu-items/<int:item_id>', methods=['DELETE'])
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


@config_api_bp.route('/logs', methods=['GET'])
@login_required
def get_logs():
    """获取系统日志"""
    import os
    import re
    from app.config import Config

    limit = request.args.get('limit', 100, type=int)
    level_filter = request.args.get('level', '')
    search = request.args.get('search', '')
    date_filter = request.args.get('date', '')
    task_id_filter = request.args.get('task_id', '')

    log_file = Config.LOG_FILE
    parsed_logs = []

    if os.path.exists(log_file):
        with open(log_file, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            recent_lines = lines[-limit*3:] if len(lines) > limit*3 else lines

            log_pattern = r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3}) - ([^-]+) - (\w+) - (.+)'

            for line in recent_lines:
                line = line.strip()
                if not line:
                    continue

                match = re.match(log_pattern, line)
                if match:
                    timestamp_str, source, level, message = match.groups()

                    try:
                        from datetime import datetime
                        timestamp = datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S,%f')
                        iso_timestamp = timestamp.isoformat()
                    except Exception:
                        iso_timestamp = timestamp_str

                    log_entry = {
                        'timestamp': iso_timestamp,
                        'level': level.lower(),
                        'message': message.strip(),
                        'source': source.strip()
                    }

                    if level_filter and log_entry['level'] != level_filter.lower():
                        continue
                    if search and search.lower() not in log_entry['message'].lower():
                        continue
                    if date_filter and not iso_timestamp.startswith(date_filter):
                        continue
                    if task_id_filter:
                        task_pattern = f"[Task-{task_id_filter[:8]}]"
                        if task_pattern not in log_entry['message'] and task_id_filter not in log_entry['message']:
                            continue

                    parsed_logs.append(log_entry)
                else:
                    parsed_logs.append({
                        'timestamp': '',
                        'level': 'info',
                        'message': line,
                        'source': 'unknown'
                    })

            parsed_logs.reverse()
            parsed_logs = parsed_logs[:limit]

    return success(data={"logs": parsed_logs})


@config_api_bp.route('/logs/latest', methods=['GET'])
@login_required
def get_latest_logs():
    """获取最新的日志"""
    import os
    import re
    from app.config import Config

    since = request.args.get('since', '')
    limit = request.args.get('limit', 50, type=int)

    log_file = Config.LOG_FILE
    latest_logs = []

    if os.path.exists(log_file):
        with open(log_file, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            recent_lines = lines[-limit*2:] if len(lines) > limit*2 else lines

            log_pattern = r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3}) - ([^-]+) - (\w+) - (.+)'

            for line in recent_lines:
                line = line.strip()
                if not line:
                    continue

                match = re.match(log_pattern, line)
                if match:
                    timestamp_str, source, level, message = match.groups()

                    try:
                        from datetime import datetime
                        timestamp = datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S,%f')
                        iso_timestamp = timestamp.isoformat()
                    except Exception:
                        iso_timestamp = timestamp_str

                    if since and iso_timestamp <= since:
                        continue

                    log_entry = {
                        'timestamp': iso_timestamp,
                        'level': level.lower(),
                        'message': message.strip(),
                        'source': source.strip()
                    }

                    latest_logs.append(log_entry)

            latest_logs.sort(key=lambda x: x['timestamp'])
            latest_logs = latest_logs[-limit:]

    return success(data={"logs": latest_logs})

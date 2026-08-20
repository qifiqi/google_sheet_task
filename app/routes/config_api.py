from flask import Blueprint, request, jsonify
from app.services.config_manager import get_config_manager
from app.models import NavigationMenuItem, db
from app.repositories.config_repository import SystemConfigRepository
from app.navigation import sync_navigation_permissions
from app.utils.logger import get_logger
from app.utils.auth import login_required, permission_required

logger = get_logger(__name__)

config_api_bp = Blueprint('config_api', __name__)
legacy_navigation_bp = Blueprint('legacy_navigation', __name__)


def _system_config_repository():
    """创建系统配置远程 CRUD 仓储，供路由的只读和普通写入调用。"""
    return SystemConfigRepository()

@config_api_bp.route('/config', methods=['GET'])
@login_required
@permission_required('config:view')
def get_config():
    """获取系统配置"""
    try:
        config_manager = get_config_manager()
        config_manager.refresh_cache()
        configs = config_manager.get_all_configs()
        logger.debug(f"返回配置数据: {configs}")
        return jsonify({"status": "success", "config": configs})
    except Exception as e:
        logger.error(f"获取配置失败: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500

@config_api_bp.route('/config', methods=['POST'])
@login_required
@permission_required('config:manage')
def update_config():
    """更新系统配置"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({"status": "error", "message": "请求数据为空"}), 400

        logger.info(f"接收到配置更新请求: {data}")

        config_manager = get_config_manager()
        success = config_manager.update_configs(data)
        if success:
            config_manager.refresh_cache()
            logger.info("配置更新成功，缓存已刷新")
            return jsonify({"status": "success", "message": "配置更新成功，已立即生效"})
        return jsonify({"status": "error", "message": "配置更新失败"}), 500
    except Exception as e:
        logger.error(f"更新配置失败: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500

@config_api_bp.route('/config/validate', methods=['GET'])
@login_required
@permission_required('config:view')
def validate_config():
    """验证配置状态"""
    try:
        config_manager = get_config_manager()

        # 以 SDK 返回的普通字典构造当前远端配置快照。
        db_configs = {
            config.get("key"): config.get("value")
            for config in _system_config_repository().list_all()
            if config.get("key")
        }

        cache_configs = config_manager._cache.copy()
        gs_config = config_manager.get_google_sheet_config()

        return jsonify({
            "status": "success",
            "validation": {
                "database_configs": db_configs,
                "cache_configs": cache_configs,
                "google_sheet_config": gs_config,
                "cache_size": len(cache_configs),
                "db_size": len(db_configs)
            }
        })
    except Exception as e:
        logger.error(f"验证配置失败: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500

@config_api_bp.route('/system-configs', methods=['GET'])
@login_required
@permission_required('config:view')
def list_system_configs():
    """获取 system_configs 配置列表"""
    try:
        # 配置列表统一经 SDK 获取，不再直接查询 SystemConfig ORM 模型。
        configs = _system_config_repository().list_all()
        return jsonify({
            "status": "success",
            "configs": configs
        })
    except Exception as e:
        logger.error(f"获取 system_configs 列表失败: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500

@config_api_bp.route('/system-configs/<string:key>', methods=['PUT'])
@login_required
@permission_required('config:manage')
def update_system_config(key):
    """更新单条配置"""
    try:
        data = request.get_json() or {}

        if 'value' not in data and 'description' not in data:
            return jsonify({"status": "error", "message": "缺少需要更新的字段"}), 400

        # 远端记录包含主键，更新时原样携带以保持 modify_or_add 的更新语义。
        repository = _system_config_repository()
        cfg = repository.get_by_key(key)
        if not cfg:
            return jsonify({"status": "error", "message": "配置不存在"}), 404

        if 'value' in data:
            cfg["value"] = data.get('value')
        if 'description' in data:
            cfg["description"] = data.get('description')
        cfg = repository.save(cfg)

        try:
            get_config_manager().refresh_cache()
        except Exception as e:
            logger.warning(f"更新配置后刷新缓存失败: {e}")

        return jsonify({"status": "success", "config": cfg})
    except Exception as e:
        logger.error(f"更新 system_config 失败: key={key}, err={str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500


def _navigation_menu_payload(item):
    """将导航菜单模型转换为配置接口响应载荷。"""
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
    """将请求值兼容转换为布尔值。"""
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def _coerce_sort_order(value):
    """将排序字段转换为非负整数。"""
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _normalize_blank(value):
    """将空白文本规范为 ``None``。"""
    text = str(value or "").strip()
    return text or None


def _validate_navigation_payload(data, item_id=None):
    """校验导航菜单请求载荷及其父子关系约束。"""
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

    duplicate = NavigationMenuItem.query.filter_by(key=key).first()
    if duplicate and duplicate.id != item_id:
        return None, "路由 key 已存在"

    if parent_key:
        parent = NavigationMenuItem.query.filter_by(key=parent_key).first()
        if not parent:
            return None, "父级菜单不存在"
        if parent.path:
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
@permission_required('navigation:view')
def list_navigation_menu_items():
    """获取侧边栏路由表"""
    items = NavigationMenuItem.query.order_by(NavigationMenuItem.sort_order, NavigationMenuItem.id).all()
    return jsonify({"status": "success", "items": [_navigation_menu_payload(item) for item in items]})


@config_api_bp.route('/navigation-menu-items', methods=['POST'])
@login_required
@permission_required('navigation:manage')
def create_navigation_menu_item():
    """新增侧边栏路由表记录，默认不可见，避免新页面直接暴露"""
    return jsonify({"status": "error", "message": "本地路由表已停用"}), 404
    try:
        data = request.get_json() or {}
        payload, error_message = _validate_navigation_payload(data)
        if error_message:
            return jsonify({"status": "error", "message": error_message}), 400

        item = NavigationMenuItem(**payload)
        db.session.add(item)
        db.session.flush()
        sync_navigation_permissions([item])
        db.session.commit()
        return jsonify({
            "status": "success",
            "message": "路由已新增，默认按可见开关和权限控制侧边栏展示",
            "item": _navigation_menu_payload(item),
        })
    except Exception as e:
        db.session.rollback()
        logger.error(f"新增导航菜单失败: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500


@config_api_bp.route('/navigation-menu-items/<int:item_id>', methods=['PUT'])
@login_required
@permission_required('navigation:manage')
def update_navigation_menu_item(item_id):
    """更新侧边栏路由表记录"""
    return jsonify({"status": "error", "message": "本地路由表已停用"}), 404
    try:
        item = db.session.get(NavigationMenuItem, item_id)
        if not item:
            return jsonify({"status": "error", "message": "路由记录不存在"}), 404

        data = request.get_json() or {}
        payload, error_message = _validate_navigation_payload(data, item_id=item_id)
        if error_message:
            return jsonify({"status": "error", "message": error_message}), 400

        for key, value in payload.items():
            setattr(item, key, value)
        sync_navigation_permissions([item])
        db.session.commit()
        return jsonify({
            "status": "success",
            "message": "路由已更新",
            "item": _navigation_menu_payload(item),
        })
    except Exception as e:
        db.session.rollback()
        logger.error(f"更新导航菜单失败: item_id={item_id}, err={str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500


@config_api_bp.route('/navigation-menu-items/<int:item_id>', methods=['DELETE'])
@login_required
@permission_required('navigation:manage')
def delete_navigation_menu_item(item_id):
    """删除侧边栏路由表记录"""
    return jsonify({"status": "error", "message": "本地路由表已停用"}), 404
    try:
        item = db.session.get(NavigationMenuItem, item_id)
        if not item:
            return jsonify({"status": "error", "message": "路由记录不存在"}), 404

        child_count = NavigationMenuItem.query.filter_by(parent_key=item.key).count()
        if child_count:
            return jsonify({"status": "error", "message": "请先删除或移动子菜单"}), 400

        db.session.delete(item)
        db.session.commit()
        return jsonify({"status": "success", "message": "路由已删除"})
    except Exception as e:
        db.session.rollback()
        logger.error(f"删除导航菜单失败: item_id={item_id}, err={str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500

@config_api_bp.route('/logs', methods=['GET'])
@login_required
@permission_required('config:view')
def get_logs():
    """获取系统日志"""
    try:
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
                        except:
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

        return jsonify({"status": "success", "logs": parsed_logs})
    except Exception as e:
        logger.error(f"获取日志失败: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500

@config_api_bp.route('/logs/latest', methods=['GET'])
@login_required
@permission_required('config:view')
def get_latest_logs():
    """获取最新的日志"""
    try:
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
                        except:
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

        return jsonify({"status": "success", "logs": latest_logs})
    except Exception as e:
        logger.error(f"获取最新日志失败: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500

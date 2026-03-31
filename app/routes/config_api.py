from flask import Blueprint, request, jsonify
from app.services.config_manager import get_config_manager
from app.models import SystemConfig, db
from app.utils.logger import get_logger

logger = get_logger(__name__)

config_api_bp = Blueprint('config_api', __name__)

@config_api_bp.route('/config', methods=['GET'])
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
def validate_config():
    """验证配置状态"""
    try:
        config_manager = get_config_manager()

        db_configs = {}
        configs = SystemConfig.query.all()
        for config in configs:
            db_configs[config.key] = config.value

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
def list_system_configs():
    """获取 system_configs 配置列表"""
    try:
        configs = SystemConfig.query.order_by(SystemConfig.key.asc()).all()
        return jsonify({
            "status": "success",
            "configs": [c.to_dict() for c in configs]
        })
    except Exception as e:
        logger.error(f"获取 system_configs 列表失败: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500

@config_api_bp.route('/system-configs/<string:key>', methods=['PUT'])
def update_system_config(key):
    """更新单条配置"""
    try:
        data = request.get_json() or {}

        if 'value' not in data and 'description' not in data:
            return jsonify({"status": "error", "message": "缺少需要更新的字段"}), 400

        cfg = SystemConfig.query.filter_by(key=key).first()
        if not cfg:
            return jsonify({"status": "error", "message": "配置不存在"}), 404

        if 'value' in data:
            cfg.value = data.get('value')
        if 'description' in data:
            cfg.description = data.get('description')

        db.session.commit()

        try:
            get_config_manager().refresh_cache()
        except Exception as e:
            logger.warning(f"更新配置后刷新缓存失败: {e}")

        return jsonify({"status": "success", "config": cfg.to_dict()})
    except Exception as e:
        db.session.rollback()
        logger.error(f"更新 system_config 失败: key={key}, err={str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500

@config_api_bp.route('/logs', methods=['GET'])
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

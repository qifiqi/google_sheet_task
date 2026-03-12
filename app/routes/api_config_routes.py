from flask import jsonify, request

from app.models import SystemConfig, db
from app.services.config_manager import get_config_manager
from app.utils.logger import get_logger

logger = get_logger(__name__)


def register_config_routes(api_bp):
    """注册配置相关路由。"""

    @api_bp.route("/config", methods=["GET"])
    def get_config():
        """获取系统配置。"""
        try:
            config_manager = get_config_manager()
            config_manager.refresh_cache()
            configs = config_manager.get_all_configs()
            logger.debug(f"返回配置数据: {configs}")
            return jsonify({"status": "success", "config": configs})
        except Exception as exc:
            logger.error(f"获取配置失败: {str(exc)}")
            return jsonify({"status": "error", "message": str(exc)}), 500

    @api_bp.route("/config", methods=["POST"])
    def update_config():
        """更新系统配置。"""
        try:
            data = request.get_json()
            if not data:
                return jsonify({"status": "error", "message": "请求数据为空"}), 400

            logger.info(f"接收到配置更新请求: {data}")
            config_manager = get_config_manager()
            success = config_manager.update_configs(data)
            if not success:
                return jsonify({"status": "error", "message": "配置更新失败"}), 500

            config_manager.refresh_cache()
            logger.info("配置更新成功，缓存已刷新")
            return jsonify({"status": "success", "message": "配置更新成功，已立即生效"})
        except Exception as exc:
            logger.error(f"更新配置失败: {str(exc)}")
            return jsonify({"status": "error", "message": str(exc)}), 500

    @api_bp.route("/config/validate", methods=["GET"])
    def validate_config():
        """验证配置状态。"""
        try:
            config_manager = get_config_manager()
            db_configs = {}
            configs = SystemConfig.query.all()
            for config in configs:
                db_configs[config.key] = config.value

            cache_configs = config_manager._cache.copy()
            gs_config = config_manager.get_google_sheet_config()
            return jsonify(
                {
                    "status": "success",
                    "validation": {
                        "database_configs": db_configs,
                        "cache_configs": cache_configs,
                        "google_sheet_config": gs_config,
                        "cache_size": len(cache_configs),
                        "db_size": len(db_configs),
                    },
                }
            )
        except Exception as exc:
            logger.error(f"验证配置失败: {str(exc)}")
            return jsonify({"status": "error", "message": str(exc)}), 500

    @api_bp.route("/system-configs", methods=["GET"])
    def list_system_configs():
        """获取 system_configs 列表。"""
        try:
            configs = SystemConfig.query.order_by(SystemConfig.key.asc()).all()
            return jsonify({"status": "success", "configs": [config.to_dict() for config in configs]})
        except Exception as exc:
            logger.error(f"获取 system_configs 列表失败: {str(exc)}")
            return jsonify({"status": "error", "message": str(exc)}), 500

    @api_bp.route("/system-configs/<string:key>", methods=["PUT"])
    def update_system_config(key):
        """更新单条配置。"""
        try:
            data = request.get_json() or {}
            if "value" not in data and "description" not in data:
                return jsonify({"status": "error", "message": "缺少需要更新的字段"}), 400

            cfg = SystemConfig.query.filter_by(key=key).first()
            if not cfg:
                return jsonify({"status": "error", "message": "配置不存在"}), 404

            if "value" in data:
                cfg.value = data.get("value")
            if "description" in data:
                cfg.description = data.get("description")

            db.session.commit()
            try:
                get_config_manager().refresh_cache()
            except Exception as exc:
                logger.warning(f"更新配置后刷新缓存失败: {exc}")

            return jsonify({"status": "success", "config": cfg.to_dict()})
        except Exception as exc:
            db.session.rollback()
            logger.error(f"更新 system_config 失败: key={key}, err={str(exc)}")
            return jsonify({"status": "error", "message": str(exc)}), 500

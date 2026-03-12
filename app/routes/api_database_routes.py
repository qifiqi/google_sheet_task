from flask import jsonify

from app.utils.logger import get_logger

logger = get_logger(__name__)


def register_database_routes(api_bp):
    """注册数据库运维相关路由。"""

    @api_bp.route("/database/status", methods=["GET"])
    def get_database_status():
        """获取数据库状态。"""
        try:
            from app.utils.db_monitor import DatabaseMonitor

            report = DatabaseMonitor.get_full_report()
            return jsonify({"status": "success", "report": report})
        except Exception as exc:
            logger.error(f"获取数据库状态失败: {str(exc)}")
            return jsonify({"status": "error", "message": str(exc)}), 500

    @api_bp.route("/database/vacuum", methods=["POST"])
    def vacuum_database():
        """压缩数据库。"""
        try:
            from app.utils.db_monitor import DatabaseMonitor

            result = DatabaseMonitor.vacuum_database()
            if result.get("success"):
                return jsonify({"status": "success", "result": result})
            return jsonify({"status": "error", "message": result.get("message", result.get("error"))}), 400
        except Exception as exc:
            logger.error(f"压缩数据库失败: {str(exc)}")
            return jsonify({"status": "error", "message": str(exc)}), 500

    @api_bp.route("/database/suggestions", methods=["GET"])
    def get_optimization_suggestions():
        """获取数据库优化建议。"""
        try:
            from app.utils.db_monitor import DatabaseMonitor

            suggestions = DatabaseMonitor.suggest_optimizations()
            return jsonify({"status": "success", "suggestions": suggestions})
        except Exception as exc:
            logger.error(f"获取优化建议失败: {str(exc)}")
            return jsonify({"status": "error", "message": str(exc)}), 500

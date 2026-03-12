from flask import jsonify, request

from app.models import TaskResult, db
from app.utils.logger import get_logger

logger = get_logger(__name__)


def register_result_routes(api_bp):
    """注册结果相关路由。"""

    @api_bp.route("/results", methods=["GET"])
    def get_results():
        """获取任务结果列表。"""
        try:
            page = request.args.get("page", 1, type=int)
            per_page = request.args.get("per_page", 20, type=int)
            task_id = request.args.get("task_id")

            query = TaskResult.query
            if task_id:
                query = query.filter_by(task_id=task_id)

            pagination = query.order_by(TaskResult.timestamp.desc()).paginate(
                page=page,
                per_page=per_page,
                error_out=False,
            )
            results = [result.to_dict() for result in pagination.items]
            return jsonify(
                {
                    "results": results,
                    "total": pagination.total,
                    "pages": pagination.pages,
                    "current_page": page,
                }
            )
        except Exception as exc:
            logger.error(f"获取结果列表失败: {str(exc)}")
            return jsonify({"status": "error", "message": str(exc)}), 500

    @api_bp.route("/results/<int:result_id>", methods=["GET"])
    def get_result(result_id):
        """获取任务结果详情。"""
        try:
            result = TaskResult.query.get(result_id)
            if not result:
                return jsonify({"status": "error", "message": "结果不存在"}), 404
            return jsonify(result.to_dict())
        except Exception as exc:
            logger.error(f"获取结果详情失败: {str(exc)}")
            return jsonify({"status": "error", "message": str(exc)}), 500

    @api_bp.route("/results/<int:result_id>", methods=["DELETE"])
    def delete_result(result_id):
        """删除任务结果。"""
        try:
            result = TaskResult.query.get(result_id)
            if not result:
                return jsonify({"status": "error", "message": "结果不存在"}), 404

            db.session.delete(result)
            db.session.commit()
            return jsonify({"status": "success", "message": "结果已删除"})
        except Exception as exc:
            db.session.rollback()
            logger.error(f"删除结果失败: {str(exc)}")
            return jsonify({"status": "error", "message": str(exc)}), 500

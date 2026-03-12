import json
import queue

from flask import Response, jsonify, request

from app.models import Task
from app.services.config_schema import normalize_task_config, validate_task_config
from app.services.task_manager import task_manager
from app.services.task_runtime_registry import task_runtime_registry
from app.utils.logger import get_logger

logger = get_logger(__name__)


def register_task_routes(api_bp):
    """注册任务相关路由。"""

    @api_bp.route("/tasks", methods=["GET", "POST"])
    def tasks():
        """获取任务列表或创建新任务。"""
        try:
            if request.method == "GET":
                task_type = request.args.get("task_type")
                tasks_data = task_manager.get_all_tasks(task_type=task_type)
                return jsonify({"status": "success", "tasks": tasks_data})

            data = request.get_json() or {}
            config = data.get("config")
            if not config:
                return jsonify({"status": "error", "message": "config is required"}), 400

            name = data.get("name", "未命名任务")
            description = data.get("description", "")
            task_type = data.get("task_type", "google_sheet")

            normalized_config = normalize_task_config(config, task_type=task_type)
            validate_task_config(normalized_config, task_type=task_type)

            task_id = task_manager.create_task(name, description, task_type, normalized_config)
            if task_manager.start_task(task_id):
                return jsonify({"status": "success", "task_id": task_id, "message": "任务创建并启动成功"})
            return jsonify({"status": "error", "task_id": task_id, "message": "任务创建成功，但启动失败"})
        except ValueError as exc:
            logger.warning(f"创建任务参数校验失败: {str(exc)}")
            return jsonify({"status": "error", "message": str(exc)}), 400
        except Exception as exc:
            logger.error(f"创建任务失败: {str(exc)}")
            return jsonify({"status": "error", "message": str(exc)}), 500

    @api_bp.route("/tasks/<task_id>", methods=["GET"])
    def get_task(task_id):
        """获取任务详情。"""
        try:
            task = task_manager.get_task_status(task_id)
            if not task:
                return jsonify({"status": "error", "message": "任务不存在"}), 404
            return jsonify({"status": "success", "task": task})
        except Exception as exc:
            logger.error(f"获取任务详情失败: {str(exc)}")
            return jsonify({"status": "error", "message": str(exc)}), 500

    @api_bp.route("/tasks/<task_id>/config", methods=["PUT"])
    def update_task_config(task_id):
        """更新任务配置。"""
        try:
            data = request.get_json()
            if not data:
                return jsonify({"status": "error", "message": "request body is required"}), 400

            config = data.get("config")
            if not config:
                return jsonify({"status": "error", "message": "config is required"}), 400

            name = data.get("name")
            description = data.get("description")
            task = Task.query.get(task_id)
            if not task:
                return jsonify({"status": "error", "message": "任务不存在"}), 404

            normalized_config = normalize_task_config(config, task_type=task.task_type)
            validate_task_config(normalized_config, task_type=task.task_type)
            result = task_manager.update_task_config(task_id, normalized_config, name, description)

            if result["status"] == "success":
                return jsonify(result)
            return jsonify(result), 400
        except ValueError as exc:
            logger.warning(f"更新任务配置参数校验失败: {str(exc)}")
            return jsonify({"status": "error", "message": str(exc)}), 400
        except Exception as exc:
            logger.error(f"更新任务配置失败: {str(exc)}")
            return jsonify({"status": "error", "message": str(exc)}), 500

    @api_bp.route("/tasks/<task_id>/cancel", methods=["POST"])
    def cancel_task(task_id):
        """取消任务。"""
        try:
            success = task_manager.cancel_task(task_id)
            if success:
                return jsonify({"status": "success", "message": "任务已取消"})
            return jsonify({"status": "error", "message": "取消任务失败"}), 400
        except Exception as exc:
            logger.error(f"取消任务失败: {str(exc)}")
            return jsonify({"status": "error", "message": str(exc)}), 500

    @api_bp.route("/tasks/<task_id>", methods=["DELETE"])
    def delete_task(task_id):
        """删除任务。"""
        try:
            success = task_manager.delete_task(task_id)
            if success:
                return jsonify({"status": "success", "message": "任务已删除"})
            return jsonify({"status": "error", "message": "删除任务失败"}), 400
        except Exception as exc:
            logger.error(f"删除任务失败: {str(exc)}")
            return jsonify({"status": "error", "message": str(exc)}), 500

    @api_bp.route("/tasks/<task_id>/logs", methods=["GET"])
    def get_task_logs(task_id):
        """获取任务日志。"""
        try:
            logs = task_manager.get_task_logs(task_id)
            return jsonify({"status": "success", "logs": logs})
        except Exception as exc:
            logger.error(f"获取任务日志失败: {str(exc)}")
            return jsonify({"status": "error", "message": str(exc)}), 500

    @api_bp.route("/tasks/<task_id>/results", methods=["GET"])
    def get_task_results(task_id):
        """获取任务结果。"""
        try:
            page = request.args.get("page", type=int)
            per_page = request.args.get("per_page", type=int)

            if page is not None and per_page is not None:
                data = task_manager.get_task_results(task_id, page=page, per_page=per_page)
                return jsonify(
                    {
                        "status": "success",
                        "results": data["items"],
                        "total": data["total"],
                        "pages": data["pages"],
                        "current_page": data["current_page"],
                        "per_page": data["per_page"],
                        "total_success": data.get("total_success"),
                        "total_failed": data.get("total_failed"),
                    }
                )

            results = task_manager.get_task_results(task_id)
            return jsonify({"status": "success", "results": results})
        except Exception as exc:
            logger.error(f"获取任务结果失败: {str(exc)}")
            return jsonify({"status": "error", "message": str(exc)}), 500

    @api_bp.route("/tasks/<task_id>/status-check", methods=["GET"])
    def check_task_status(task_id):
        """检查任务本地状态。"""
        try:
            status_check = task_manager.check_local_task_status(task_id)
            return jsonify({"status": "success", "status_check": status_check})
        except Exception as exc:
            logger.error(f"检查任务状态失败: {str(exc)}")
            return jsonify({"status": "error", "message": str(exc)}), 500

    @api_bp.route("/tasks/<task_id>/restart", methods=["POST"])
    def restart_task(task_id):
        """重启任务。"""
        try:
            data = request.get_json() or {}
            resume_from_checkpoint = data.get("resume_from_checkpoint", True)

            result = task_manager.restart_task(task_id, resume_from_checkpoint)
            if result["status"] == "success":
                return jsonify(result)
            return jsonify(result), 400
        except Exception as exc:
            logger.error(f"重启任务失败: {str(exc)}")
            return jsonify({"status": "error", "message": str(exc)}), 500

    @api_bp.route("/tasks/<task_id>/create-restart", methods=["POST"])
    def create_restart_task_api(task_id):
        """基于原任务创建新的重启任务。"""
        try:
            new_task_id = task_manager.create_restart_task(task_id)
            if task_manager.start_task(new_task_id):
                return jsonify(
                    {
                        "status": "success",
                        "new_task_id": new_task_id,
                        "message": "重启任务创建并启动成功",
                    }
                )
            return jsonify(
                {
                    "status": "success",
                    "new_task_id": new_task_id,
                    "message": "重启任务创建成功，但启动失败",
                }
            )
        except Exception as exc:
            logger.error(f"创建重启任务失败: {str(exc)}")
            return jsonify({"status": "error", "message": str(exc)}), 500

    @api_bp.route("/tasks/<task_id>/events")
    def task_events_stream(task_id):
        """SSE 事件流。"""

        def event_stream():
            if not task_runtime_registry.has_task_event_queue(task_id):
                yield f"data: {json.dumps({'type': 'error', 'data': 'Task not found'})}\n\n"
                return

            event_queue = task_runtime_registry.get_task_event_queue(task_id)
            try:
                while True:
                    try:
                        event = event_queue.get(timeout=1)
                        yield f"data: {json.dumps(event)}\n\n"
                    except queue.Empty:
                        yield f"data: {json.dumps({'type': 'heartbeat'})}\n\n"

                    if not task_runtime_registry.has_task_event_queue(task_id):
                        break
            except GeneratorExit:
                pass
            except Exception as exc:
                yield f"data: {json.dumps({'type': 'error', 'data': str(exc)})}\n\n"

        return Response(event_stream(), mimetype="text/event-stream")

    @api_bp.route("/tasks/<task_id>/confirm", methods=["POST"])
    def confirm_task(task_id):
        """确认任务继续执行。"""
        try:
            data = request.get_json()
            confirmed = data.get("confirmed", False) if data else False

            event_queue = task_runtime_registry.get_task_event_queue(task_id)
            if not event_queue:
                return jsonify({"status": "error", "message": "任务事件队列不存在"}), 400

            event_queue.put({"type": "confirmation", "data": {"confirmed": confirmed}})
            return jsonify({"status": "success", "message": "确认已发送"})
        except Exception as exc:
            logger.error(f"确认任务失败: {str(exc)}")
            return jsonify({"status": "error", "message": str(exc)}), 500

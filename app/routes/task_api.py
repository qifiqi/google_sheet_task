import json
from io import BytesIO

from flask import Blueprint, g, jsonify, request, send_file

from app.extensions import db
from app.models import Task
from app.services.export_file_service import build_task_export
from app.services.task import TaskRuntimeViewService, task_manager
from app.utils.auth import login_required, permission_required
from app.utils.logger import get_logger
from app.utils.task_authorization import (
    authorize_task_type_action,
    filter_task_dicts_by_action,
    filter_task_types_by_action,
)

logger = get_logger(__name__)

task_api_bp = Blueprint('task_api', __name__)
runtime_view_service = TaskRuntimeViewService(task_manager)

TASK_ACTION_LABELS = {
    "view": "查看",
    "create": "创建",
    "delete": "删除",
    "cancel": "取消",
    "restart": "重启",
}


def _task_permission_denied(action: str, task_type: str | None, decision: dict, task_id: str | None = None):
    action_label = TASK_ACTION_LABELS.get(action, action)
    normalized_type = decision.get("task_type") or str(task_type or "全部")
    missing_permissions = decision.get("missing_permissions") or []
    missing_text = "、".join(missing_permissions) if missing_permissions else "未知"
    message = f"权限不足，无法{action_label}{normalized_type}任务；当前缺少: {missing_text}"

    return jsonify({
        "status": "error",
        "message": message,
        "task_id": task_id,
        "task_type": normalized_type,
        "action": action,
        "required_permissions": decision.get("required_permissions") or [],
        "missing_permissions": missing_permissions,
    }), 403


def _get_task_or_404(task_id: str):
    task = db.session.get(Task, task_id)
    if not task:
        return None, jsonify({"status": "error", "message": "任务不存在"}), 404
    return task, None, None

@task_api_bp.route('/tasks', methods=['GET', 'POST'])
@login_required
@permission_required('task:view', 'task:create')
def tasks():
    """获取任务列表 / 创建任务"""
    try:
        if request.method == 'GET':
            task_type = request.args.get('task_type')
            page = request.args.get('page', type=int)
            per_page = request.args.get('per_page', type=int)
            task_status = request.args.get('status')
            keyword = request.args.get('keyword', '', type=str)
            current_user = getattr(g, "current_user", None)
            allowed_task_types = None

            if task_type:
                decision = authorize_task_type_action(current_user, "view", task_type)
                if not decision["allowed"]:
                    return _task_permission_denied("view", task_type, decision)
            else:
                base_view_decision = authorize_task_type_action(current_user, "view", None)
                if not base_view_decision["allowed"]:
                    return _task_permission_denied("view", "全部", base_view_decision)
                distinct_task_types = [item[0] for item in Task.query.with_entities(Task.task_type).distinct().all()]
                allowed_task_types = filter_task_types_by_action(current_user, "view", distinct_task_types)

            default_page = page or 1
            default_per_page = per_page or 10

            if not task_type and not allowed_task_types:
                return jsonify({
                    "status": "success",
                    "tasks": [],
                    "pagination": {
                        "page": default_page,
                        "per_page": default_per_page,
                        "total": 0,
                        "pages": 0,
                        "has_prev": False,
                        "has_next": False,
                        "prev_num": None,
                        "next_num": None,
                    },
                    "statistics": {
                        "total_tasks": 0,
                        "completed_tasks": 0,
                        "running_tasks": 0,
                        "error_tasks": 0,
                        "pending_tasks": 0,
                        "today_new_tasks": 0,
                        "success_rate": 0,
                        "error_rate": 0,
                        "avg_duration_minutes": 0,
                    },
                })

            data = task_manager.get_tasks_paginated(
                page=default_page,
                per_page=default_per_page,
                task_type=task_type,
                task_types=allowed_task_types if not task_type else None,
                status=task_status,
                keyword=keyword,
            )
            data["tasks"] = filter_task_dicts_by_action(current_user, "view", data.get("tasks", []))
            return jsonify({
                "status": "success",
                "tasks": data["tasks"],
                "pagination": data["pagination"],
                "statistics": data["statistics"],
            })

        data = request.get_json() or {}
        config = data.get('config')
        if config:
            name = data.get('name', '未命名任务')
            description = data.get('description', '')
            task_type = data.get('task_type', 'google_sheet')
            current_user = getattr(g, "current_user", None)
            decision = authorize_task_type_action(current_user, "create", task_type)
            if not decision["allowed"]:
                return _task_permission_denied("create", task_type, decision)
            response, status_code = task_manager.create_and_start_task(
                name,
                description,
                task_type,
                config,
                created_by_user_id=getattr(current_user, "id", None),
            )
            return jsonify(response), status_code

        return jsonify({"status": "error", "message": "任务配置为空"}), 400

    except ValueError as e:
        logger.warning(f"处理任务接口校验失败: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 400
    except Exception as e:
        logger.error(f"处理任务接口失败: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500

@task_api_bp.route('/tasks/batch-create', methods=['POST'])
@login_required
@permission_required('task:create')
def batch_create_tasks():
    """C31 批量创建接口"""
    try:
        decision = authorize_task_type_action(getattr(g, "current_user", None), "create", "google_sheet")
        if not decision["allowed"]:
            return _task_permission_denied("create", "google_sheet", decision)

        data = request.get_json() or {}
        logger.info("C31 batch create request: %s", json.dumps(data, ensure_ascii=False, default=str))

        response, status_code = task_manager.batch_create_and_start_task(
            data,
            created_by_user_id=getattr(getattr(g, "current_user", None), "id", None),
        )
        if status_code == 200:
            response["debug_message"] = "已调用原有 C3 创建流程；当前仍为占位版批量接口"
        return jsonify(response), status_code

    except ValueError as e:
        logger.warning(f"批量创建接口校验失败: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 400
    except Exception as e:
        logger.error(f"批量创建接口失败: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500

@task_api_bp.route('/tasks/<task_id>', methods=['GET', 'DELETE'])
@login_required
@permission_required('task:view', 'task:delete')
def task_detail(task_id):
    """获取/删除任务详情"""
    try:
        task_obj, error_response, status_code = _get_task_or_404(task_id)
        if not task_obj:
            return error_response, status_code

        action = "view" if request.method == 'GET' else "delete"
        decision = authorize_task_type_action(getattr(g, "current_user", None), action, task_obj.task_type)
        if not decision["allowed"]:
            return _task_permission_denied(action, task_obj.task_type, decision, task_id=task_id)

        if request.method == 'GET':
            task = task_manager.get_task_status(task_id)
            if not task:
                return jsonify({"status": "error", "message": "任务不存在"}), 404
            return jsonify({"status": "success", "task": task})

        success = task_manager.delete_task(task_id)
        if success:
            return jsonify({"status": "success", "message": "任务已删除"})
        return jsonify({"status": "error", "message": "删除任务失败"}), 400
    except Exception as e:
        logger.error(f"处理任务详情失败: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500

@task_api_bp.route('/tasks/<task_id>/config', methods=['PUT'])
@login_required
@permission_required('task:create')
def update_task_config(task_id):
    """更新任务配置"""
    try:
        task_obj, error_response, status_code = _get_task_or_404(task_id)
        if not task_obj:
            return error_response, status_code

        decision = authorize_task_type_action(getattr(g, "current_user", None), "create", task_obj.task_type)
        if not decision["allowed"]:
            return _task_permission_denied("create", task_obj.task_type, decision, task_id=task_id)

        data = request.get_json()
        if not data:
            return jsonify({"status": "error", "message": "请求数据为空"}), 400

        config = data.get('config')
        if not config:
            return jsonify({"status": "error", "message": "配置信息不能为空"}), 400

        result = task_manager.update_task_config(
            task_id,
            config,
            data.get('name'),
            data.get('description'),
            data.get('status'),
        )

        if result["status"] == "success":
            return jsonify(result)
        return jsonify(result), 400

    except Exception as e:
        logger.error(f"更新任务配置失败: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500

@task_api_bp.route('/tasks/<task_id>/cancel', methods=['POST'])
@login_required
@permission_required('task:cancel')
def cancel_task(task_id):
    """取消任务"""
    try:
        task_obj, error_response, status_code = _get_task_or_404(task_id)
        if not task_obj:
            return error_response, status_code

        decision = authorize_task_type_action(getattr(g, "current_user", None), "cancel", task_obj.task_type)
        if not decision["allowed"]:
            return _task_permission_denied("cancel", task_obj.task_type, decision, task_id=task_id)

        success = task_manager.cancel_task(task_id)
        if success:
            return jsonify({"status": "success", "message": "任务已取消"})
        return jsonify({"status": "error", "message": "取消任务失败"}), 400
    except Exception as e:
        logger.error(f"取消任务失败: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500

@task_api_bp.route('/tasks/<task_id>/logs', methods=['GET'])
@login_required
@permission_required('task:view')
def get_task_logs(task_id):
    """获取任务日志"""
    try:
        task_obj, error_response, status_code = _get_task_or_404(task_id)
        if not task_obj:
            return error_response, status_code

        decision = authorize_task_type_action(getattr(g, "current_user", None), "view", task_obj.task_type)
        if not decision["allowed"]:
            return _task_permission_denied("view", task_obj.task_type, decision, task_id=task_id)

        logs = task_manager.get_task_logs(task_id)
        return jsonify({"status": "success", "logs": logs})
    except Exception as e:
        logger.error(f"获取任务日志失败: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500

@task_api_bp.route('/tasks/<task_id>/results', methods=['GET'])
@login_required
@permission_required('task:view')
def get_task_results(task_id):
    """获取任务结果"""
    try:
        task_obj, error_response, status_code = _get_task_or_404(task_id)
        if not task_obj:
            return error_response, status_code

        decision = authorize_task_type_action(getattr(g, "current_user", None), "view", task_obj.task_type)
        if not decision["allowed"]:
            return _task_permission_denied("view", task_obj.task_type, decision, task_id=task_id)

        page = request.args.get('page', type=int)
        per_page = request.args.get('per_page', type=int)

        if page is not None and per_page is not None:
            data = task_manager.get_task_results(task_id, page=page, per_page=per_page)
            return jsonify({
                "status": "success",
                "results": data["items"],
                "total": data["total"],
                "pages": data["pages"],
                "current_page": data["current_page"],
                "per_page": data["per_page"],
                "total_success": data.get("total_success"),
                "total_failed": data.get("total_failed"),
            })

        results = task_manager.get_task_results(task_id)
        return jsonify({"status": "success", "results": results})
    except Exception as e:
        logger.error(f"获取任务结果失败: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500


@task_api_bp.route('/tasks/<task_id>/export', methods=['GET'])
@login_required
@permission_required('task:view')
def export_task_results(task_id):
    """导出任务结果。"""
    try:
        task_obj, error_response, status_code = _get_task_or_404(task_id)
        if not task_obj:
            return error_response, status_code

        decision = authorize_task_type_action(getattr(g, "current_user", None), "view", task_obj.task_type)
        if not decision["allowed"]:
            return _task_permission_denied("view", task_obj.task_type, decision, task_id=task_id)

        results = task_manager.get_task_results(task_id)
        export_file = build_task_export(task_obj, results)
        buffer = BytesIO()
        export_file.workbook.save(buffer)
        buffer.seek(0)

        return send_file(
            buffer,
            mimetype=export_file.mimetype,
            as_attachment=True,
            download_name=export_file.filename,
        )
    except ValueError as e:
        logger.warning(f"导出任务结果校验失败: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 400
    except Exception as e:
        logger.error(f"导出任务结果失败: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500

@task_api_bp.route('/tasks/<task_id>/status-check', methods=['GET'])
@login_required
@permission_required('task:view')
def check_task_status(task_id):
    """检查任务本地状态"""
    try:
        task_obj, error_response, status_code = _get_task_or_404(task_id)
        if not task_obj:
            return error_response, status_code

        decision = authorize_task_type_action(getattr(g, "current_user", None), "view", task_obj.task_type)
        if not decision["allowed"]:
            return _task_permission_denied("view", task_obj.task_type, decision, task_id=task_id)

        status_check = task_manager.check_local_task_status(task_id)
        return jsonify({"status": "success", "status_check": status_check})
    except Exception as e:
        logger.error(f"检查任务状态失败: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500

@task_api_bp.route('/tasks/<task_id>/stop-confirmation', methods=['GET'])
@login_required
@permission_required('task:view')
def get_task_stop_confirmation(task_id):
    """确认任务是否已经完全停止"""
    try:
        task_obj, error_response, status_code = _get_task_or_404(task_id)
        if not task_obj:
            return error_response, status_code

        decision = authorize_task_type_action(
            getattr(g, "current_user", None),
            "view",
            task_obj.task_type,
        )
        if not decision["allowed"]:
            return _task_permission_denied(
                "view",
                task_obj.task_type,
                decision,
                task_id=task_id,
            )

        stop_confirmation = runtime_view_service.build_stop_confirmation(task_id)

        return jsonify({
            "status": "success",
            **stop_confirmation,
        })
    except Exception as e:
        logger.error(f"获取任务停止确认失败: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500

@task_api_bp.route('/tasks/<task_id>/restart', methods=['POST'])
@login_required
@permission_required('task:restart')
def restart_task(task_id):
    """重启任务"""
    try:
        task_obj, error_response, status_code = _get_task_or_404(task_id)
        if not task_obj:
            return error_response, status_code

        decision = authorize_task_type_action(getattr(g, "current_user", None), "restart", task_obj.task_type)
        if not decision["allowed"]:
            return _task_permission_denied("restart", task_obj.task_type, decision, task_id=task_id)

        data = request.get_json() or {}
        resume_from_checkpoint = data.get('resume_from_checkpoint', True)

        result = task_manager.restart_task(task_id, resume_from_checkpoint)
        if result["status"] == "success":
            return jsonify(result)
        return jsonify(result), 400
    except Exception as e:
        logger.error(f"重启任务失败: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500

@task_api_bp.route('/tasks/<task_id>/create-restart', methods=['POST'])
@login_required
@permission_required('task:restart')
def create_restart_task_api(task_id):
    """基于原任务创建新的重启任务"""
    try:
        task_obj, error_response, status_code = _get_task_or_404(task_id)
        if not task_obj:
            return error_response, status_code

        decision = authorize_task_type_action(getattr(g, "current_user", None), "restart", task_obj.task_type)
        if not decision["allowed"]:
            return _task_permission_denied("restart", task_obj.task_type, decision, task_id=task_id)

        new_task_id = task_manager.create_restart_task(task_id)

        if task_manager.start_task(new_task_id):
            return jsonify({
                "status": "success",
                "new_task_id": new_task_id,
                "message": "重启任务创建并启动成功"
            })
        start_error = task_manager.get_start_error(new_task_id)
        if task_obj.task_type in ("backtest_training", "backtest_multi_product") and "已有回测任务正在运行" in start_error:
            return jsonify({
                "status": "success",
                "new_task_id": new_task_id,
                "message": start_error,
                "queued": True,
            })
        return jsonify({
            "status": "error",
            "new_task_id": new_task_id,
            "message": f"重启任务创建成功，但启动失败: {start_error}",
            "start_error": start_error,
        }), 400
    except Exception as e:
        logger.error(f"创建重启任务失败: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500

@task_api_bp.route('/tasks/<task_id>/system-logs', methods=['GET'])
@login_required
@permission_required('task:view')
def get_task_system_logs(task_id):
    """获取任务相关的系统日志"""
    try:
        task_obj, error_response, status_code = _get_task_or_404(task_id)
        if not task_obj:
            return error_response, status_code

        decision = authorize_task_type_action(getattr(g, "current_user", None), "view", task_obj.task_type)
        if not decision["allowed"]:
            return _task_permission_denied("view", task_obj.task_type, decision, task_id=task_id)

        import os
        import re
        from app.config import Config

        limit = request.args.get('limit', 200, type=int)
        level_filter = request.args.get('level', '')

        log_file = Config.LOG_FILE
        task_logs = []

        if os.path.exists(log_file):
            with open(log_file, 'r', encoding='utf-8') as f:
                lines = f.readlines()
                log_pattern = r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3}) - ([^-]+) - (\w+) - (.+)'
                task_patterns = [f"[Task-{task_id[:8]}]", f"任务 {task_id}", task_id]

                for line in lines:
                    line = line.strip()
                    if not line:
                        continue

                    contains_task_info = any(pattern in line for pattern in task_patterns)
                    if not contains_task_info:
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
                            'source': source.strip(),
                            'task_id': task_id
                        }

                        if level_filter and log_entry['level'] != level_filter.lower():
                            continue

                        task_logs.append(log_entry)

                task_logs.sort(key=lambda x: x['timestamp'])
                task_logs = task_logs[-limit:]

        return jsonify({
            "status": "success",
            "logs": task_logs,
            "task_id": task_id,
            "total_found": len(task_logs)
        })
    except Exception as e:
        logger.error(f"获取任务系统日志失败: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500

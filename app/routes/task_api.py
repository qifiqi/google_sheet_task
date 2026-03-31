from flask import Blueprint, request, jsonify, Response
import json
import queue
from app.services.task_manager import task_manager
from app.models import Task
from app.utils.logger import get_logger

logger = get_logger(__name__)

task_api_bp = Blueprint('task_api', __name__)

@task_api_bp.route('/tasks', methods=['GET', 'POST'])
def tasks():
    """获取任务列表 / 创建任务"""
    try:
        if request.method == 'GET':
            task_type = request.args.get('task_type')
            page = request.args.get('page', type=int)
            per_page = request.args.get('per_page', type=int)
            task_status = request.args.get('status')
            keyword = request.args.get('keyword', '', type=str)

            use_pagination = page is not None or per_page is not None or bool(task_status) or bool(keyword)
            if use_pagination:
                data = task_manager.get_tasks_paginated(
                    page=page or 1,
                    per_page=per_page or 10,
                    task_type=task_type,
                    status=task_status,
                    keyword=keyword,
                )
                return jsonify({
                    "status": "success",
                    "tasks": data["tasks"],
                    "pagination": data["pagination"],
                    "statistics": data["statistics"],
                })

            tasks = task_manager.get_all_tasks(task_type=task_type)
            return jsonify({"status": "success", "tasks": tasks})

        data = request.get_json() or {}
        config = data.get('config')
        if config:
            name = data.get('name', '未命名任务')
            description = data.get('description', '')
            task_type = data.get('task_type', 'google_sheet')
            response, status_code = task_manager.create_and_start_task(name, description, task_type, config)
            return jsonify(response), status_code

        return jsonify({"status": "error", "message": "任务配置为空"}), 400

    except ValueError as e:
        logger.warning(f"处理任务接口校验失败: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 400
    except Exception as e:
        logger.error(f"处理任务接口失败: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500

@task_api_bp.route('/tasks/batch-create', methods=['POST'])
def batch_create_tasks():
    """C31 批量创建接口"""
    try:
        data = request.get_json() or {}
        logger.info("C31 batch create request: %s", json.dumps(data, ensure_ascii=False, default=str))

        response, status_code = task_manager.batch_create_and_start_task(data)
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
def task_detail(task_id):
    """获取/删除任务详情"""
    try:
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
def update_task_config(task_id):
    """更新任务配置"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({"status": "error", "message": "请求数据为空"}), 400

        config = data.get('config')
        if not config:
            return jsonify({"status": "error", "message": "配置信息不能为空"}), 400

        result = task_manager.update_task_config(task_id, config, data.get('name'), data.get('description'))

        if result["status"] == "success":
            return jsonify(result)
        return jsonify(result), 400

    except Exception as e:
        logger.error(f"更新任务配置失败: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500

@task_api_bp.route('/tasks/<task_id>/cancel', methods=['POST'])
def cancel_task(task_id):
    """取消任务"""
    try:
        success = task_manager.cancel_task(task_id)
        if success:
            return jsonify({"status": "success", "message": "任务已取消"})
        return jsonify({"status": "error", "message": "取消任务失败"}), 400
    except Exception as e:
        logger.error(f"取消任务失败: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500

@task_api_bp.route('/tasks/<task_id>/logs', methods=['GET'])
def get_task_logs(task_id):
    """获取任务日志"""
    try:
        logs = task_manager.get_task_logs(task_id)
        return jsonify({"status": "success", "logs": logs})
    except Exception as e:
        logger.error(f"获取任务日志失败: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500

@task_api_bp.route('/tasks/<task_id>/results', methods=['GET'])
def get_task_results(task_id):
    """获取任务结果"""
    try:
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

@task_api_bp.route('/tasks/<task_id>/status-check', methods=['GET'])
def check_task_status(task_id):
    """检查任务本地状态"""
    try:
        status_check = task_manager.check_local_task_status(task_id)
        return jsonify({"status": "success", "status_check": status_check})
    except Exception as e:
        logger.error(f"检查任务状态失败: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500

@task_api_bp.route('/tasks/<task_id>/stop-confirmation', methods=['GET'])
def get_task_stop_confirmation(task_id):
    """确认任务是否已经完全停止"""
    try:
        import time
        task = Task.query.get(task_id)
        if not task:
            return jsonify({"status": "error", "message": "任务不存在"}), 404

        status_check = task_manager.check_local_task_status(task_id)
        thread = task_manager.running_tasks.get(task_id)
        stop_event = task_manager.task_stop_events.get(task_id)
        thread_alive = bool(thread and thread.is_alive())
        stop_requested = bool(stop_event and stop_event.is_set())
        stop_confirmed = (task.status != 'running') and (not thread_alive)

        return jsonify({
            "status": "success",
            "task_id": task_id,
            "db_status": task.status,
            "thread_alive": thread_alive,
            "memory_running": status_check.get("memory_running", thread_alive),
            "stop_requested": stop_requested,
            "stop_confirmed": stop_confirmed,
            "current_step": task.current_step,
            "total_steps": task.total_steps,
            "status_check": status_check,
            "checked_at": time.time(),
        })
    except Exception as e:
        logger.error(f"获取任务停止确认失败: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500

@task_api_bp.route('/tasks/<task_id>/restart', methods=['POST'])
def restart_task(task_id):
    """重启任务"""
    try:
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
def create_restart_task_api(task_id):
    """基于原任务创建新的重启任务"""
    try:
        new_task_id = task_manager.create_restart_task(task_id)

        if task_manager.start_task(new_task_id):
            return jsonify({
                "status": "success",
                "new_task_id": new_task_id,
                "message": "重启任务创建并启动成功"
            })
        return jsonify({
            "status": "success",
            "new_task_id": new_task_id,
            "message": "重启任务创建成功，但启动失败"
        })
    except Exception as e:
        logger.error(f"创建重启任务失败: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500

@task_api_bp.route('/tasks/<task_id>/events')
def task_events_stream(task_id):
    """SSE事件流，用于任务状态更新和确认请求"""
    def event_stream():
        if task_id not in task_manager.task_events:
            yield f"data: {json.dumps({'type': 'error', 'data': 'Task not found'})}\n\n"
            return

        event_queue = task_manager.task_events[task_id]

        try:
            while True:
                try:
                    event = event_queue.get(timeout=1)
                    yield f"data: {json.dumps(event)}\n\n"
                except queue.Empty:
                    yield f"data: {json.dumps({'type': 'heartbeat'})}\n\n"

                if task_id not in task_manager.task_events:
                    break

        except GeneratorExit:
            pass
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'data': str(e)})}\n\n"

    return Response(event_stream(), mimetype='text/event-stream')

@task_api_bp.route('/tasks/<task_id>/confirm', methods=['POST'])
def confirm_task(task_id):
    """确认任务继续执行"""
    try:
        data = request.get_json()
        confirmed = data.get('confirmed', False) if data else False

        if task_id in task_manager.task_events:
            task_manager.task_events[task_id].put({
                "type": "confirmation",
                "data": {"confirmed": confirmed}
            })
            return jsonify({"status": "success", "message": "确认已发送"})
        return jsonify({"status": "error", "message": "任务事件队列不存在"}), 400
    except Exception as e:
        logger.error(f"确认任务失败: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500

@task_api_bp.route('/tasks/<task_id>/system-logs', methods=['GET'])
def get_task_system_logs(task_id):
    """获取任务相关的系统日志"""
    try:
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

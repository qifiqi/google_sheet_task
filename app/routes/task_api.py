"""任务 API。

说明：
- create/start/restart/update-config 等执行链响应由 task_manager 服务层构造，
  路由保持透传；
- 服务层仍以 ValueError 表达请求校验失败（400 语义），本层显式翻译为
  BadRequestError，待服务层改抛语义异常后移除。
"""
import json

from flask import Blueprint, g, jsonify, request

from app.exceptions import BadRequestError, NotFoundError
from app.schemas.task import TaskCreateSchema, TasksBatchCreateSchema, TaskRestartSchema
from app.services.task import TaskRuntimeViewService, task_manager
from app.utils.api_response import error, success
from app.utils.request_parsing import parse_body
from app.utils.auth import login_required
from app.utils.logger import get_logger

logger = get_logger(__name__)

task_api_bp = Blueprint('task_api', __name__)
runtime_view_service = TaskRuntimeViewService(task_manager)


@task_api_bp.route('/tasks', methods=['GET', 'POST'])
@login_required
def tasks():
    """获取任务列表 / 创建任务"""
    if request.method == 'GET':
        task_type = request.args.get('task_type')
        page = request.args.get('page', type=int)
        per_page = request.args.get('per_page', type=int)
        task_status = request.args.get('status')
        keyword = request.args.get('keyword', '', type=str)
        allowed_task_types = None

        if not task_type:
            allowed_task_types = task_manager.get_distinct_task_types()

        default_page = page or 1
        default_per_page = per_page or 10

        if not task_type and not allowed_task_types:
            return success(data=task_manager.get_empty_tasks_page(
                default_page, default_per_page
            ))

        data = task_manager.get_tasks_paginated(
            page=default_page,
            per_page=default_per_page,
            task_type=task_type,
            task_types=allowed_task_types if not task_type else None,
            status=task_status,
            keyword=keyword,
        )
        return success(data={
            "tasks": data["tasks"],
            "pagination": data["pagination"],
            "statistics": data["statistics"],
        })

    data = parse_body(TaskCreateSchema)
    current_user = getattr(g, "current_user", None)
    response, status_code = task_manager.create_and_start_task(
        data.name,
        data.description,
        data.task_type,
        data.config,
        created_by_user_id=getattr(current_user, "id", None),
    )
    return jsonify(response), status_code


@task_api_bp.route('/tasks/batch-create', methods=['POST'])
@login_required
def batch_create_tasks():
    """C31 批量创建接口"""
    data = parse_body(TasksBatchCreateSchema).root
    logger.info("C31 batch create request: %s", json.dumps(data, ensure_ascii=False, default=str))

    try:
        response, status_code = task_manager.batch_create_and_start_task(
            data,
            created_by_user_id=getattr(getattr(g, "current_user", None), "id", None),
        )
    except ValueError as exc:
        # 服务层以 ValueError 表达请求校验失败（400 语义）。
        raise BadRequestError(str(exc))
    if status_code == 200:
        response["debug_message"] = "已调用原有 C3 创建流程；当前仍为占位版批量接口"
    return jsonify(response), status_code


@task_api_bp.route('/tasks/<task_id>', methods=['GET', 'DELETE'])
@login_required
def task_detail(task_id):
    """获取/删除任务详情"""
    task_manager.get_required_task(task_id)

    if request.method == 'GET':
        task = task_manager.get_task_status(task_id)
        if not task:
            raise NotFoundError("任务不存在")
        return success(data={"task": task})

    deleted = task_manager.delete_task(task_id)
    if deleted:
        return success(message="任务已删除")
    raise BadRequestError("删除任务失败")


@task_api_bp.route('/tasks/<task_id>/config', methods=['PUT'])
@login_required
def update_task_config(task_id):
    """更新任务配置"""
    task_manager.get_required_task(task_id)

    data = request.get_json()
    if not data:
        raise BadRequestError("请求数据为空")

    config = data.get('config')
    if not config:
        raise BadRequestError("配置信息不能为空")

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


@task_api_bp.route('/tasks/<task_id>/cancel', methods=['POST'])
@login_required
def cancel_task(task_id):
    """取消任务"""
    task_manager.get_required_task(task_id)

    cancelled = task_manager.cancel_task(task_id)
    if cancelled:
        return success(message="任务已取消")
    raise BadRequestError("取消任务失败")


@task_api_bp.route('/tasks/<task_id>/logs', methods=['GET'])
@login_required
def get_task_logs(task_id):
    """获取任务日志"""
    task_manager.get_required_task(task_id)

    logs = task_manager.get_task_logs(task_id)
    return success(data={"logs": logs})


@task_api_bp.route('/tasks/<task_id>/status-check', methods=['GET'])
@login_required
def check_task_status(task_id):
    """检查任务本地状态"""
    task_manager.get_required_task(task_id)

    status_check = task_manager.check_local_task_status(task_id)
    return success(data={"status_check": status_check})


@task_api_bp.route('/tasks/<task_id>/stop-confirmation', methods=['GET'])
@login_required
def get_task_stop_confirmation(task_id):
    """确认任务是否已经完全停止"""
    task_manager.get_required_task(task_id)

    stop_confirmation = runtime_view_service.build_stop_confirmation(task_id)

    return success(data=stop_confirmation)


@task_api_bp.route('/tasks/<task_id>/restart', methods=['POST'])
@login_required
def restart_task(task_id):
    """重启任务"""
    task_manager.get_required_task(task_id)

    data = parse_body(TaskRestartSchema)

    result = task_manager.restart_task(task_id, data.resume_from_checkpoint)
    if result["status"] == "success":
        return jsonify(result)
    return jsonify(result), 400


@task_api_bp.route('/tasks/<task_id>/create-restart', methods=['POST'])
@login_required
def create_restart_task_api(task_id):
    """基于原任务创建新的重启任务"""
    task_obj = task_manager.get_required_task_entity(task_id)

    new_task_id = task_manager.create_restart_task(task_id)

    if task_manager.start_task(new_task_id):
        return success(
            data={"new_task_id": new_task_id},
            message="重启任务创建并启动成功",
        )
    start_error = task_manager.get_start_error(new_task_id)
    if task_obj.task_type in ("backtest_training", "backtest_multi_product") and "已有回测任务正在运行" in start_error:
        return success(
            data={"new_task_id": new_task_id, "queued": True},
            message=start_error,
        )
    return error(
        f"重启任务创建成功，但启动失败: {start_error}",
        http_status=400,
        data={"new_task_id": new_task_id, "start_error": start_error},
    )


@task_api_bp.route('/tasks/<task_id>/system-logs', methods=['GET'])
@login_required
def get_task_system_logs(task_id):
    """获取任务相关的系统日志"""
    task_manager.get_required_task(task_id)

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
                    except Exception:
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

    return success(data={
        "logs": task_logs,
        "task_id": task_id,
        "total_found": len(task_logs),
    })

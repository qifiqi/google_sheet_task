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
from app.schemas.task import TaskCreateSchema, TasksBatchCreateSchema, TaskRestartSchema, TaskListQuery
from app.services.task import TaskRuntimeViewService, task_manager
from app.utils.api_response import error, success
from app.utils.request_parsing import parse_body, parse_query
from app.utils.auth import login_required
from app.services.log_query_service import query_task_system_logs
from app.utils.logger import get_logger

logger = get_logger(__name__)

task_api_bp = Blueprint('task_api', __name__)
runtime_view_service = TaskRuntimeViewService(task_manager)


@task_api_bp.route('/tasks', methods=['GET', 'POST'])
@login_required
def tasks():
    """获取任务列表 / 创建任务"""
    if request.method == 'GET':
        query = parse_query(TaskListQuery)
        allowed_task_types = None

        if not query.task_type:
            allowed_task_types = task_manager.get_distinct_task_types()

        if not query.task_type and not allowed_task_types:
            return success(data=task_manager.get_empty_tasks_page(
                query.page, query.per_page
            ))

        data = task_manager.get_tasks_paginated(
            page=query.page,
            per_page=query.per_page,
            task_type=query.task_type,
            task_types=allowed_task_types if not query.task_type else None,
            status=query.status,
            keyword=query.keyword,
        )
        return success(data=data)

    data = parse_body(TaskCreateSchema)
    current_user = getattr(g, "current_user", None)
    result = task_manager.create_and_start_task(
        data.name,
        data.description,
        data.task_type,
        data.config,
        created_by_user_id=getattr(current_user, "id", None),
    )
    message = (
        result["message"] if result.get("queued") else "任务创建并启动成功"
    )
    return success(data={"task_id": result["task_id"], "queued": result.get("queued", False)}, message=message)


@task_api_bp.route('/tasks/batch-create', methods=['POST'])
@login_required
def batch_create_tasks():
    """C31 批量创建接口"""
    data = parse_body(TasksBatchCreateSchema).root
    logger.info("C31 batch create request: %s", json.dumps(data, ensure_ascii=False, default=str))

    # 服务层抛 ValidationError（400）/NotFoundError，由全局处理器渲染信封。
    result = task_manager.batch_create_and_start_task(
        data,
        created_by_user_id=getattr(getattr(g, "current_user", None), "id", None),
    )
    return success(
        data={
            "task_id": result["task_id"],
            "task_ids": result["task_ids"],
            "started_task_ids": result["started_task_ids"],
            "failed_to_start": result["failed_to_start"],
            "total_created": result["total_created"],
            "total_started": result["total_started"],
            "children": result["children"],
        },
        message=result["message"],
    )


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

    logger.info("请求删除任务: task_id=%s", task_id)
    deleted = task_manager.delete_task(task_id)
    if deleted:
        logger.info("任务已删除: task_id=%s", task_id)
        return success(message="任务已删除")
    raise BadRequestError("删除任务失败")


@task_api_bp.route('/tasks/<task_id>/config', methods=['PUT'])
@login_required
def update_task_config(task_id):
    """更新任务配置"""
    task_manager.get_required_task(task_id)

    data = parse_body(TaskConfigUpdateSchema)
    result = task_manager.update_task_config(
        task_id,
        data.config,
        data.name,
        data.description,
        data.status,
    )
    return success(data=result, message="任务更新成功")


@task_api_bp.route('/tasks/<task_id>/cancel', methods=['POST'])
@login_required
def cancel_task(task_id):
    """取消任务"""
    task_manager.get_required_task(task_id)
    logger.info("请求取消任务: task_id=%s", task_id)

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
    logger.info(
        "请求重启任务: task_id=%s resume_from_checkpoint=%s",
        task_id,
        data.resume_from_checkpoint,
    )

    result = task_manager.restart_task(task_id, data.resume_from_checkpoint)
    return success(data=result, message=result.get("message", "任务重启成功"))


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

    task_logs = query_task_system_logs(
        task_id,
        limit=request.args.get('limit', 200, type=int),
        level_filter=request.args.get('level', ''),
    )

    return success(data={
        "logs": task_logs,
        "task_id": task_id,
        "total_found": len(task_logs),
    })

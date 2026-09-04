"""定时任务调度 API（数据层：scheduled_task_repository）。

- 5 处 get_or_404 → get_required + NotFoundError（全局处理器映射 404，URL 与
  状态码语义不变）；
- 调度器（scheduler_service）消费 ORM 实体，实体访问经 repository.get_entity；
- 响应切统一信封：原 {success, ...} 顶层业务键移入 data（前端同批更新）。
"""
from datetime import datetime

import json
from croniter import croniter
from flask import Blueprint, request

from app.exceptions import BadRequestError
from app.repositories import scheduled_task_repository
from app.services.scheduler_service import scheduler_service
from app.utils.api_response import success
from app.utils.auth import login_required
from app.utils.logger import get_logger

logger = get_logger(__name__)

scheduler_api_bp = Blueprint('scheduler_api', __name__)


def _validate_cron(expression):
    try:
        croniter(expression)
    except Exception as e:
        raise BadRequestError(f"无效的cron表达式: {e}")


def _validate_task_params(task_params):
    if task_params:
        try:
            json.loads(task_params)
        except Exception as e:
            raise BadRequestError(f"任务参数必须是有效的JSON格式: {e}")


@scheduler_api_bp.route('/api/admin/scheduler/stats', methods=['GET'])
@login_required
def get_scheduler_stats():
    """获取调度器统计信息"""
    stats = scheduled_task_repository.stats()
    full_stats = {
        'total_tasks': stats["total"],
        'active_tasks': stats["active"],
        'inactive_tasks': stats["total"] - stats["active"],
        'scheduler_running': scheduler_service.is_running,
    }
    return success(data={'stats': full_stats})


@scheduler_api_bp.route('/api/admin/scheduler/tasks', methods=['GET'])
@login_required
def get_scheduled_tasks():
    """获取定时任务列表"""
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 50, type=int)

    page_data = scheduled_task_repository.list_paginated(page, per_page)
    return success(data={
        'tasks': page_data["items"],
        'pagination': {
            'page': page_data["current_page"],
            'per_page': page_data["per_page"],
            'total': page_data["total"],
            'pages': page_data["pages"],
        },
    })


@scheduler_api_bp.route('/api/admin/scheduler/tasks', methods=['POST'])
@login_required
def create_scheduled_task():
    """创建定时任务"""
    data = request.get_json() or {}

    required_fields = ['name', 'cron_expression', 'task_type', 'task_function']
    for field in required_fields:
        if not data.get(field):
            raise BadRequestError(f'缺少必填字段: {field}')

    _validate_cron(data['cron_expression'])

    task_params = data.get('task_params', '{}')
    _validate_task_params(task_params)

    task = scheduled_task_repository.create({
        'name': data['name'],
        'description': data.get('description', ''),
        'cron_expression': data['cron_expression'],
        'task_type': data['task_type'],
        'task_function': data['task_function'],
        'task_params': task_params,
        'is_active': data.get('is_active', True),
    })

    # 如果任务是活跃的，添加到调度器
    if task["is_active"] and scheduler_service.is_running:
        scheduler_service.add_job(scheduled_task_repository.get_entity(task["id"]))

    logger.info(f"创建定时任务成功: {task['name']}")

    return success(
        data={'task': task},
        message='定时任务创建成功',
    )


@scheduler_api_bp.route('/api/admin/scheduler/tasks/<int:task_id>', methods=['PUT'])
@login_required
def update_scheduled_task(task_id):
    """更新定时任务"""
    task = scheduled_task_repository.get_required(task_id)
    data = request.get_json() or {}

    if 'cron_expression' in data:
        _validate_cron(data['cron_expression'])

    if 'task_params' in data and data['task_params']:
        _validate_task_params(data['task_params'])

    fields = {
        field: data[field]
        for field in ['name', 'description', 'cron_expression', 'task_type', 'task_function', 'task_params', 'is_active']
        if field in data
    }
    fields['updated_at'] = datetime.now()
    updated = scheduled_task_repository.update(task_id, fields)

    # 更新调度器中的任务（调度器消费实体）
    if scheduler_service.is_running:
        scheduler_service.remove_job(task_id)
        entity = scheduled_task_repository.get_entity(task_id)
        if entity.is_active:
            scheduler_service.add_job(entity)

    logger.info(f"更新定时任务成功: {updated['name']}")

    return success(
        data={'task': updated},
        message='定时任务更新成功',
    )


@scheduler_api_bp.route('/api/admin/scheduler/tasks/<int:task_id>', methods=['DELETE'])
@login_required
def delete_scheduled_task(task_id):
    """删除定时任务"""
    task = scheduled_task_repository.get_required(task_id)
    task_name = task["name"]

    # 从调度器中移除任务
    if scheduler_service.is_running:
        scheduler_service.remove_job(task_id)

    # 删除数据库记录
    scheduled_task_repository.delete(task_id)

    logger.info(f"删除定时任务成功: {task_name}")

    return success(message='定时任务删除成功')


@scheduler_api_bp.route('/api/admin/scheduler/tasks/<int:task_id>/toggle', methods=['POST'])
@login_required
def toggle_scheduled_task(task_id):
    """切换定时任务状态"""
    task = scheduled_task_repository.get_required(task_id)
    data = request.get_json() or {}

    is_active = data.get('is_active', not task["is_active"])
    updated = scheduled_task_repository.update(task_id, {
        'is_active': is_active,
        'updated_at': datetime.now(),
    })

    # 更新调度器中的任务
    if scheduler_service.is_running:
        scheduler_service.remove_job(task_id)
        if is_active:
            scheduler_service.add_job(scheduled_task_repository.get_entity(task_id))

    status_text = '启用' if is_active else '禁用'
    logger.info(f"{status_text}定时任务: {updated['name']}")

    return success(
        data={'task': updated},
        message=f'定时任务已{status_text}',
    )


@scheduler_api_bp.route('/api/admin/scheduler/tasks/<int:task_id>/run', methods=['POST'])
@login_required
def run_scheduled_task_now(task_id):
    """立即执行定时任务"""
    task = scheduled_task_repository.get_required(task_id)

    if not scheduler_service.is_running:
        raise BadRequestError('调度器未运行')

    # 检查任务是否已在运行中
    current_status = scheduler_service.get_async_task_status(task_id)
    if current_status and current_status['status'] == 'running':
        raise BadRequestError('任务正在执行中，请稍后再试')

    # 立即执行任务（使用异步方式）
    run_ok = scheduler_service.run_job_once(task_id)
    if not run_ok:
        from app.exceptions import ServiceError
        raise ServiceError('任务提交执行失败')

    logger.info(f"立即执行定时任务: {task['name']}")

    return success(
        data={'task_id': task_id},
        message='任务已提交到后台异步执行',
    )


@scheduler_api_bp.route('/api/admin/scheduler/tasks/<int:task_id>/status', methods=['GET'])
@login_required
def get_task_execution_status(task_id):
    """获取任务执行状态"""
    task = scheduled_task_repository.get_required(task_id)

    # 获取异步执行状态
    async_status = scheduler_service.get_async_task_status(task_id)

    # 获取调度器中的任务状态
    job_status = scheduler_service.get_job_status(task_id)

    return success(data={
        'task': {
            'id': task["id"],
            'name': task["name"],
            'is_active': task["is_active"],
            'last_run_time': task["last_run_time"],
            'next_run_time': task["next_run_time"],
            'run_count': task["run_count"],
        },
        'async_status': async_status,
        'job_status': job_status,
    })


@scheduler_api_bp.route('/api/admin/scheduler/status', methods=['GET'])
@login_required
def get_scheduler_status():
    """获取调度器状态"""
    return success(data={
        'status': {
            'running': scheduler_service.is_running,
            'jobs_count': len(scheduler_service.scheduler.get_jobs()) if scheduler_service.scheduler else 0,
        }
    })

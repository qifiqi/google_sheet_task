"""定时任务调度 API。

定时任务 CRUD 与调度器同步编排经 scheduler_service；
路由层只做 HTTP 解析与统一信封，异常交 app/errors.py 全局处理器。
"""
from flask import Blueprint, request

from app.services.scheduler_service import scheduler_service
from app.utils.api_response import success
from app.schemas.scheduler import ScheduledTaskCreateSchema, ScheduledTaskUpdateSchema
from app.utils.auth import login_required
from app.utils.request_parsing import parse_body

scheduler_api_bp = Blueprint('scheduler_api', __name__, url_prefix='/api')


@scheduler_api_bp.route('/admin/scheduler/stats', methods=['GET'])
@login_required
def get_scheduler_stats():
    """获取调度器统计信息"""
    return success(data={'stats': scheduler_service.get_scheduler_stats()})


@scheduler_api_bp.route('/admin/scheduler/tasks', methods=['GET'])
@login_required
def get_scheduled_tasks():
    """获取定时任务列表"""
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 50, type=int)
    return success(data=scheduler_service.list_tasks_page(page, per_page))


@scheduler_api_bp.route('/admin/scheduler/tasks', methods=['POST'])
@login_required
def create_scheduled_task():
    """创建定时任务"""
    data = parse_body(ScheduledTaskCreateSchema)
    task = scheduler_service.create_task({
        'name': data.name,
        'description': data.description,
        'cron_expression': data.cron_expression,
        'task_type': data.task_type,
        'task_function': data.task_function,
        'task_params': data.task_params,
        'is_active': data.is_active,
    })
    return success(data={'task': task}, message='定时任务创建成功')


@scheduler_api_bp.route('/admin/scheduler/tasks/<int:task_id>', methods=['PUT'])
@login_required
def update_scheduled_task(task_id):
    """更新定时任务"""
    # 存在性检查先行：任务不存在时无论请求体如何都返回 404（保持原顺序语义）
    scheduler_service.get_required_task(task_id)
    data = parse_body(ScheduledTaskUpdateSchema).model_dump(exclude_unset=True)
    updated = scheduler_service.update_task(task_id, data)
    return success(data={'task': updated}, message='定时任务更新成功')


@scheduler_api_bp.route('/admin/scheduler/tasks/<int:task_id>', methods=['DELETE'])
@login_required
def delete_scheduled_task(task_id):
    """删除定时任务"""
    scheduler_service.delete_task(task_id)
    return success(message='定时任务删除成功')


@scheduler_api_bp.route('/admin/scheduler/tasks/<int:task_id>/toggle', methods=['POST'])
@login_required
def toggle_scheduled_task(task_id):
    """切换定时任务状态"""
    updated, status_text = scheduler_service.toggle_task(task_id, request.get_json() or {})
    return success(data={'task': updated}, message=f'定时任务已{status_text}')


@scheduler_api_bp.route('/admin/scheduler/tasks/<int:task_id>/run', methods=['POST'])
@login_required
def run_scheduled_task_now(task_id):
    """立即执行定时任务"""
    scheduler_service.run_task_now(task_id)
    return success(data={'task_id': task_id}, message='任务已提交到后台异步执行')


@scheduler_api_bp.route('/admin/scheduler/tasks/<int:task_id>/status', methods=['GET'])
@login_required
def get_task_execution_status(task_id):
    """获取任务执行状态"""
    return success(data=scheduler_service.get_task_execution_status(task_id))


@scheduler_api_bp.route('/admin/scheduler/status', methods=['GET'])
@login_required
def get_scheduler_status():
    """获取调度器状态"""
    return success(data={
        'status': {
            'running': scheduler_service.is_running,
            'jobs_count': len(scheduler_service.scheduler.get_jobs()) if scheduler_service.scheduler else 0,
        }
    })

"""管理后台 API（自 admin.py 页面蓝图归位，URL 不变）。

- dashboard/overview 与 model-summary 查询为服务层契约 payload，保持透传；
- rebuild 端点挂保护性限流（api-model-query-audit/06 §3，rate_limit_rebuild）。
"""

from urllib.parse import quote

from flask import Blueprint, Response, current_app, g, jsonify, request

from app.exceptions import NotFoundError
from app.repositories import task_repository
from app.services.model_summary_service import model_summary_service
from app.services.scheduler_service import scheduler_service
from app.services.task import TaskRuntimeViewService, task_manager
from app.extensions import limiter
from app.utils.api_response import success
from app.utils.auth import login_required

admin_api_bp = Blueprint('admin_api', __name__, url_prefix='/admin')
runtime_view_service = TaskRuntimeViewService(task_manager)


def get_config_value(key, default):
    """限流阈值经 config_manager 运行时可调（零重启）。"""
    from app.services.config_manager import get_config_manager

    return get_config_manager().get_config(key, default)


@admin_api_bp.route('/api/scheduler/status')
@login_required
def scheduler_status():
    """获取异步任务执行状态API"""
    # 获取所有异步任务状态
    async_tasks = scheduler_service.get_async_task_status()

    # 获取调度器状态
    scheduler_info = {
        'is_running': scheduler_service.is_running,
        'total_async_tasks': len(async_tasks),
        'running_tasks': len([t for t in async_tasks.values() if t['status'] == 'running']),
        'completed_tasks': len([t for t in async_tasks.values() if t['status'] == 'completed']),
        'failed_tasks': len([t for t in async_tasks.values() if t['status'] == 'failed'])
    }

    # 格式化任务信息
    formatted_tasks = {}
    for task_id, task_info in async_tasks.items():
        formatted_tasks[task_id] = {
            'status': task_info['status'],
            'start_time': task_info['start_time'].isoformat() if task_info['start_time'] else None,
            'end_time': task_info.get('end_time').isoformat() if task_info.get('end_time') else None,
            'error': task_info.get('error'),
            'duration': None
        }

        # 计算执行时长
        if task_info.get('end_time') and task_info['start_time']:
            duration = task_info['end_time'] - task_info['start_time']
            formatted_tasks[task_id]['duration'] = duration.total_seconds()

    return success(data={
        'scheduler': scheduler_info,
        'async_tasks': formatted_tasks,
    })


@admin_api_bp.route('/api/dashboard/overview')
@login_required
def dashboard_overview():
    """管理后台仪表盘总览数据

    响应契约由 runtime_view 服务定义（task/runtime_view.py），本路由保持透传。
    """
    return jsonify(
        runtime_view_service.build_dashboard_overview(
            getattr(g, "current_user", None),
        )
    )


@admin_api_bp.route('/api/model-summary')
@login_required
def model_summary_api():
    """单模型汇总数据查询。

    响应契约由 model_summary_service 定义，本路由保持透传。
    """
    payload = model_summary_service.query(getattr(g, "current_user", None), request.args.to_dict())
    return jsonify(payload)


@admin_api_bp.route('/api/model-summary/rebuild', methods=['POST'])
@login_required
@limiter.limit(
    lambda: f"{get_config_value('rate_limit_rebuild', 2) or 2}/minute",
    key_func=lambda: f"user:{getattr(getattr(g, 'current_user', None), 'id', 'anon')}",
)
def rebuild_model_summary_api():
    """重建单模型汇总索引。"""
    data = request.get_json(silent=True) or {}
    job = model_summary_service.start_rebuild_job(
        current_app._get_current_object(),
        task_type=data.get('task_type') or None,
        task_id=data.get('task_id') or None,
        batch_size=int(data.get('batch_size') or 20),
        reset=bool(data.get('reset', False)),
        created_by_user_id=getattr(getattr(g, "current_user", None), "id", None),
    )
    return success(data={'job': job})


@admin_api_bp.route('/api/model-summary/rebuild/status')
@login_required
def model_summary_rebuild_status_api():
    """查询单模型汇总索引后台重建状态。"""
    job_id = request.args.get('job_id')
    job = model_summary_service.get_rebuild_job(job_id) if job_id else model_summary_service.latest_rebuild_job()
    return success(data={'job': job})


@admin_api_bp.route('/api/tasks/<task_id>/runtime-detail')
@login_required
def task_runtime_detail(task_id):
    """管理后台任务运行细节"""
    task = task_repository.get_entity(task_id)
    if not task:
        raise NotFoundError('task not found')

    return success(data={
        'task': runtime_view_service.serialize_task_runtime(task),
    })


@admin_api_bp.route('/api/scheduler/cleanup', methods=['POST'])
@login_required
def cleanup_completed_tasks():
    """清理已完成的异步任务记录"""
    max_age_hours = request.json.get('max_age_hours', 24) if request.is_json else 24

    # 清理已完成的任务
    scheduler_service.cleanup_completed_tasks(max_age_hours)

    return success(message=f'已清理超过 {max_age_hours} 小时的已完成任务记录')

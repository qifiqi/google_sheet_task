from flask import Blueprint, current_app, g, jsonify, render_template, request

from app.extensions import db
from app.services.model_summary_service import model_summary_service
from app.services.scheduler_service import scheduler_service
from app.services.task import TaskRuntimeViewService, task_manager
from app.models import Task, GoogleSheetTableType, TaskStatus, TaskType
from app.utils.logger import get_logger
from app.utils.auth import login_required, permission_required
from app.utils.task_authorization import authorize_task_type_action

logger = get_logger(__name__)

admin_bp = Blueprint('admin', __name__)
runtime_view_service = TaskRuntimeViewService(task_manager)

TASK_ACTION_LABELS = {
    "view": "查看",
}


def _task_permission_denied(action: str, task_type: str | None, decision: dict, task_id: str | None = None):
    action_label = TASK_ACTION_LABELS.get(action, action)
    normalized_type = decision.get("task_type") or str(task_type or "unknown")
    missing_permissions = decision.get("missing_permissions") or []
    missing_text = "、".join(missing_permissions) if missing_permissions else "未知"
    message = f"权限不足，无法{action_label}{normalized_type}任务；当前缺少: {missing_text}"

    return jsonify({
        "success": False,
        "error": message,
        "task_id": task_id,
        "task_type": normalized_type,
        "action": action,
        "required_permissions": decision.get("required_permissions") or [],
        "missing_permissions": missing_permissions,
    }), 403


@admin_bp.route('/')
def dashboard():
    """管理面板首页"""
    # 获取任务统计
    total_tasks = Task.query.count()
    completed_tasks = Task.query.filter_by(status='completed').count()
    running_tasks = Task.query.filter_by(status='running').count()
    error_tasks = Task.query.filter_by(status='error').count()
    
    # 获取最近的任务
    recent_tasks = Task.query.order_by(Task.created_at.desc()).limit(10).all()
    
    return render_template('admin/dashboard.html', 
                         total_tasks=total_tasks,
                         completed_tasks=completed_tasks,
                         running_tasks=running_tasks,
                         error_tasks=error_tasks,
                         recent_tasks=recent_tasks)

@admin_bp.route('/tasks')
def tasks():
    """任务管理页面"""
    return render_template(
        'admin/tasks.html',
        task_status_options=TaskStatus.choices(),
        task_status_editable_options=TaskStatus.editable_choices(),
        task_type_options=TaskType.choices(),
        task_type_filter_options=TaskType.choices(include_system=True),
    )

@admin_bp.route('/config')
def config():
    """配置管理页面"""
    return render_template('admin/config.html')

@admin_bp.route('/navigation')
def navigation():
    """路由表管理页面"""
    return render_template('admin/navigation.html')

@admin_bp.route('/logs')
def logs():
    """日志管理页面"""
    return render_template('admin/logs.html')

@admin_bp.route('/templates')
def templates():
    """任务模板管理页面"""
    return render_template('admin/templates.html')

@admin_bp.route('/results')
def results():
    """任务结果管理页面"""
    return render_template('admin/results.html')

@admin_bp.route('/model-summary')
def model_summary():
    """单模型汇总数据看板"""
    return render_template('admin/model_summary.html')

@admin_bp.route('/google-sheets')
def google_sheets():
    return render_template('admin/google_sheets.html', google_sheet_table_type_options=GoogleSheetTableType.choices())

@admin_bp.route('/scheduler')
def scheduler():
    """定时任务管理页面"""
    return render_template('admin/scheduler.html')

@admin_bp.route('/users')
def users():
    """用户管理页面"""
    return render_template('admin/users.html')

@admin_bp.route('/roles')
def roles():
    """角色管理页面"""
    return render_template('admin/roles.html')

@admin_bp.route('/api/scheduler/status')
@login_required
@permission_required('scheduler:view')
def scheduler_status():
    """获取异步任务执行状态API"""
    try:
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
        
        return jsonify({
            'success': True,
            'scheduler': scheduler_info,
            'async_tasks': formatted_tasks
        })
        
    except Exception as e:
        logger.error(f"获取调度器状态失败: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@admin_bp.route('/api/dashboard/overview')
@login_required
@permission_required('task:view')
def dashboard_overview():
    """管理后台仪表盘总览数据"""
    try:
        return jsonify(
            runtime_view_service.build_dashboard_overview(
                getattr(g, "current_user", None),
            )
        )
    except Exception as e:
        logger.error(f"获取仪表盘数据失败: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@admin_bp.route('/api/model-summary')
@login_required
@permission_required('task:view')
def model_summary_api():
    """单模型汇总数据查询。"""
    try:
        payload = model_summary_service.query(getattr(g, "current_user", None), request.args.to_dict())
        return jsonify(payload)
    except Exception as e:
        logger.error(f"获取单模型汇总失败: {e}", exc_info=True)
        return jsonify({'status': 'error', 'message': str(e)}), 500


@admin_bp.route('/api/model-summary/rebuild', methods=['POST'])
@login_required
@permission_required('database:model_summary', 'database:manage')
def rebuild_model_summary_api():
    """重建单模型汇总索引。"""
    try:
        data = request.get_json(silent=True) or {}
        job = model_summary_service.start_rebuild_job(
            current_app._get_current_object(),
            task_type=data.get('task_type') or None,
            task_id=data.get('task_id') or None,
            batch_size=int(data.get('batch_size') or 20),
            reset=bool(data.get('reset', False)),
            created_by_user_id=getattr(getattr(g, "current_user", None), "id", None),
        )
        return jsonify({'status': 'success', 'job': job})
    except Exception as e:
        db.session.rollback()
        logger.error(f"重建单模型汇总索引失败: {e}", exc_info=True)
        return jsonify({'status': 'error', 'message': str(e)}), 500


@admin_bp.route('/api/model-summary/rebuild/status')
@login_required
@permission_required('database:model_summary', 'database:manage')
def model_summary_rebuild_status_api():
    """查询单模型汇总索引后台重建状态。"""
    job_id = request.args.get('job_id')
    job = model_summary_service.get_rebuild_job(job_id) if job_id else model_summary_service.latest_rebuild_job()
    if not job:
        return jsonify({'status': 'success', 'job': None})
    return jsonify({'status': 'success', 'job': job})


@admin_bp.route('/api/tasks/<task_id>/runtime-detail')
@login_required
@permission_required('task:view')
def task_runtime_detail(task_id):
    """管理后台任务运行细节"""
    try:
        task = db.session.get(Task, task_id)
        if not task:
            return jsonify({'success': False, 'error': 'task not found'}), 404

        decision = authorize_task_type_action(getattr(g, "current_user", None), "view", task.task_type)
        if not decision["allowed"]:
            return _task_permission_denied("view", task.task_type, decision, task_id=task_id)

        return jsonify({
            'success': True,
            'task': runtime_view_service.serialize_task_runtime(task),
        })
    except Exception as e:
        logger.error(f"获取任务运行细节失败: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500

@admin_bp.route('/api/scheduler/cleanup', methods=['POST'])
@login_required
@permission_required('scheduler:manage')
def cleanup_completed_tasks():
    """清理已完成的异步任务记录"""
    try:
        max_age_hours = request.json.get('max_age_hours', 24) if request.is_json else 24
        
        # 清理已完成的任务
        scheduler_service.cleanup_completed_tasks(max_age_hours)
        
        return jsonify({
            'success': True,
            'message': f'已清理超过 {max_age_hours} 小时的已完成任务记录'
        })
        
    except Exception as e:
        logger.error(f"清理任务记录失败: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

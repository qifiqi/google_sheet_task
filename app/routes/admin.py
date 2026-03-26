import json
from collections import Counter
from datetime import datetime, timedelta

from flask import Blueprint, render_template, request, jsonify, redirect, url_for
from app.services.task_manager import task_manager
from app.services.config_manager import get_config_manager
from app.services.scheduler_service import scheduler_service
from app.models import Task, TaskLog, TaskResult, TaskResultReturn, ScheduledTask, db
from app.utils.logger import get_logger

logger = get_logger(__name__)

admin_bp = Blueprint('admin', __name__)


def _safe_json_loads(raw_value, default=None):
    if default is None:
        default = {}
    if not raw_value:
        return default
    if isinstance(raw_value, (dict, list)):
        return raw_value
    try:
        return json.loads(raw_value)
    except Exception:
        return default


def _as_dict(value):
    return value if isinstance(value, dict) else {}


def _extract_parameter_label(parameters_payload, step_index: int):
    if isinstance(parameters_payload, dict):
        return (
            parameters_payload.get('stock_code')
            or parameters_payload.get('stock_no')
            or parameters_payload.get('code')
            or parameters_payload.get('symbol')
            or f"step-{step_index + 1}"
        )

    if isinstance(parameters_payload, list):
        for item in parameters_payload:
            if isinstance(item, dict):
                label = (
                    item.get('stock_code')
                    or item.get('stock_no')
                    or item.get('code')
                    or item.get('symbol')
                )
                if label:
                    return label
            elif item not in (None, ''):
                return str(item)

    if parameters_payload not in (None, '', {}):
        return str(parameters_payload)

    return f"step-{step_index + 1}"


def _build_config_summary(task: Task):
    config = _safe_json_loads(task.config, {})
    parameters = config.get('parameters') if isinstance(config, dict) else None
    parameter_groups = len(parameters) if isinstance(parameters, list) else 0
    parameter_sizes = []
    parameter_preview = []
    if isinstance(parameters, list):
        for idx, param_group in enumerate(parameters[:4], start=1):
            if isinstance(param_group, list):
                parameter_sizes.append(len(param_group))
                parameter_preview.append({
                    'group': idx,
                    'size': len(param_group),
                    'sample': param_group[:3],
                })
            else:
                parameter_preview.append({
                    'group': idx,
                    'size': 1,
                    'sample': [param_group],
                })

    return {
        'sheet_name': config.get('sheet_name') if isinstance(config, dict) else None,
        'spreadsheet_id': config.get('spreadsheet_id') if isinstance(config, dict) else None,
        'token_id': config.get('token_id') if isinstance(config, dict) else None,
        'parameter_groups': parameter_groups,
        'parameter_sizes': parameter_sizes,
        'parameter_preview': parameter_preview,
        'config_keys': sorted(list(config.keys()))[:12] if isinstance(config, dict) else [],
    }


def _build_stop_confirmation(task_id: str):
    status_check = task_manager.check_local_task_status(task_id)
    thread = task_manager.running_tasks.get(task_id)
    stop_event = task_manager.task_stop_events.get(task_id)
    task = Task.query.get(task_id)

    thread_alive = bool(thread and thread.is_alive())
    stop_requested = bool(stop_event and stop_event.is_set())
    db_status = task.status if task else status_check.get('db_status')
    stop_confirmed = (db_status != 'running') and (not thread_alive)

    return {
        'task_id': task_id,
        'db_status': db_status,
        'thread_alive': thread_alive,
        'memory_running': status_check.get('memory_running', thread_alive),
        'stop_requested': stop_requested,
        'stop_confirmed': stop_confirmed,
        'current_step': task.current_step if task else None,
        'total_steps': task.total_steps if task else None,
        'checked_at': datetime.now().isoformat(),
        'status_check': status_check,
    }


def _build_result_summary(task_id: str):
    results = TaskResult.query.filter_by(task_id=task_id).order_by(TaskResult.step_index.asc()).all()
    total = len(results)
    success_count = sum(1 for item in results if item.success)
    failed_count = total - success_count

    metric_points = []
    for result in results[-30:]:
        result_payload = _as_dict(_safe_json_loads(result.result, {}))
        parameters_payload = _safe_json_loads(result.parameters, {})
        annualized = result_payload.get('I16') or result_payload.get('annualized_rate') or result_payload.get('annualized')
        maxdd = result_payload.get('I17') or result_payload.get('maxdd')
        return_rate = result_payload.get('I15') or result_payload.get('return_rate')
        metric_points.append({
            'step': result.step_index + 1,
            'success': bool(result.success),
            'annualized_rate': annualized,
            'max_drawdown': maxdd,
            'return_rate': return_rate,
            'parameter_label': _extract_parameter_label(parameters_payload, result.step_index),
        })

    returns = TaskResultReturn.query.filter_by(task_id=task_id).order_by(TaskResultReturn.stock_date.asc()).all()
    return_chart = [
        {
            'date': item.stock_date,
            'index_return': item.index_return,
            'strategy_return': item.start_return,
        }
        for item in returns[-120:]
    ]

    return {
        'total_results': total,
        'success_count': success_count,
        'failed_count': failed_count,
        'success_rate': round((success_count / total) * 100, 2) if total else 0,
        'latest_metric_points': metric_points,
        'return_chart': return_chart,
    }


def _serialize_task_runtime(task: Task):
    config_summary = _build_config_summary(task)
    stop_confirmation = _build_stop_confirmation(task.id)
    result_summary = _build_result_summary(task.id)
    recent_logs = TaskLog.query.filter_by(task_id=task.id).order_by(TaskLog.timestamp.desc()).limit(20).all()
    recent_logs.reverse()

    duration_seconds = None
    if task.start_time:
        end_at = task.end_time or datetime.now()
        duration_seconds = max(0, int((end_at - task.start_time).total_seconds()))

    data = task.to_dict()
    data.update({
        'progress_percentage': task.get_progress_percentage(),
        'duration_seconds': duration_seconds,
        'config_summary': config_summary,
        'stop_confirmation': stop_confirmation,
        'result_summary': result_summary,
        'recent_logs': [log.to_dict() for log in recent_logs],
    })
    return data

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
    return render_template('admin/tasks.html')

@admin_bp.route('/config')
def config():
    """配置管理页面"""
    return render_template('admin/config.html')

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

@admin_bp.route('/google-sheets')
def google_sheets():
    return render_template('admin/google_sheets.html')

@admin_bp.route('/scheduler')
def scheduler():
    """定时任务管理页面"""
    return render_template('admin/scheduler.html')

@admin_bp.route('/api/scheduler/status')
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
def dashboard_overview():
    """管理后台仪表盘总览数据"""
    try:
        tasks = Task.query.order_by(Task.created_at.desc()).all()
        now = datetime.now()
        last_7_days = [(now - timedelta(days=offset)).date() for offset in range(6, -1, -1)]
        daily_map = {day.isoformat(): {'created': 0, 'completed': 0} for day in last_7_days}

        status_counter = Counter(task.status for task in tasks)
        task_type_counter = Counter(task.task_type for task in tasks)

        for task in tasks:
            created_key = task.created_at.date().isoformat() if task.created_at else None
            if created_key in daily_map:
                daily_map[created_key]['created'] += 1
            if task.end_time and task.status == 'completed':
                completed_key = task.end_time.date().isoformat()
                if completed_key in daily_map:
                    daily_map[completed_key]['completed'] += 1

        recent_tasks = [_serialize_task_runtime(task) for task in tasks[:10]]
        active_tasks = [_serialize_task_runtime(task) for task in tasks if task.status == 'running'][:6]

        return jsonify({
            'success': True,
            'summary': {
                'total_tasks': len(tasks),
                'completed_tasks': status_counter.get('completed', 0),
                'running_tasks': status_counter.get('running', 0),
                'error_tasks': status_counter.get('error', 0),
                'cancelled_tasks': status_counter.get('cancelled', 0),
                'pending_tasks': status_counter.get('pending', 0),
            },
            'status_distribution': dict(status_counter),
            'task_type_distribution': dict(task_type_counter),
            'daily_trend': [
                {
                    'date': date_key,
                    'created': values['created'],
                    'completed': values['completed'],
                }
                for date_key, values in daily_map.items()
            ],
            'recent_tasks': recent_tasks,
            'active_tasks': active_tasks,
            'checked_at': now.isoformat(),
        })
    except Exception as e:
        logger.error(f"获取仪表盘数据失败: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@admin_bp.route('/api/tasks/<task_id>/runtime-detail')
def task_runtime_detail(task_id):
    """管理后台任务运行细节"""
    try:
        task = Task.query.get(task_id)
        if not task:
            return jsonify({'success': False, 'error': 'task not found'}), 404

        return jsonify({
            'success': True,
            'task': _serialize_task_runtime(task),
        })
    except Exception as e:
        logger.error(f"获取任务运行细节失败: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500

@admin_bp.route('/api/scheduler/cleanup', methods=['POST'])
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

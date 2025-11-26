from flask import Blueprint, request, jsonify
from datetime import datetime
import json
from croniter import croniter
from app.extensions import db
from app.models import ScheduledTask
from app.services.scheduler_service import scheduler_service
from app.utils.logger import get_logger

logger = get_logger(__name__)

scheduler_api_bp = Blueprint('scheduler_api', __name__)

@scheduler_api_bp.route('/api/admin/scheduler/stats', methods=['GET'])
def get_scheduler_stats():
    """获取调度器统计信息"""
    try:
        total_tasks = ScheduledTask.query.count()
        active_tasks = ScheduledTask.query.filter_by(is_active=True).count()
        inactive_tasks = total_tasks - active_tasks
        
        stats = {
            'total_tasks': total_tasks,
            'active_tasks': active_tasks,
            'inactive_tasks': inactive_tasks,
            'scheduler_running': scheduler_service.is_running
        }
        
        return jsonify({
            'success': True,
            'stats': stats
        })
        
    except Exception as e:
        logger.error(f"获取调度器统计信息失败: {e}")
        return jsonify({
            'success': False,
            'message': str(e)
        }), 500

@scheduler_api_bp.route('/api/admin/scheduler/tasks', methods=['GET'])
def get_scheduled_tasks():
    """获取定时任务列表"""
    try:
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 50, type=int)
        
        tasks_query = ScheduledTask.query.order_by(ScheduledTask.created_at.desc())
        tasks_pagination = tasks_query.paginate(page=page, per_page=per_page, error_out=False)
        
        tasks = []
        for task in tasks_pagination.items:
            tasks.append(task.to_dict())
        
        return jsonify({
            'success': True,
            'tasks': tasks,
            'pagination': {
                'page': page,
                'per_page': per_page,
                'total': tasks_pagination.total,
                'pages': tasks_pagination.pages
            }
        })
        
    except Exception as e:
        logger.error(f"获取定时任务列表失败: {e}")
        return jsonify({
            'success': False,
            'message': str(e)
        }), 500

@scheduler_api_bp.route('/api/admin/scheduler/tasks', methods=['POST'])
def create_scheduled_task():
    """创建定时任务"""
    try:
        data = request.get_json()
        
        # 验证必填字段
        required_fields = ['name', 'cron_expression', 'task_type', 'task_function']
        for field in required_fields:
            if not data.get(field):
                return jsonify({
                    'success': False,
                    'message': f'缺少必填字段: {field}'
                }), 400
        
        # 验证cron表达式
        try:
            croniter(data['cron_expression'])
        except Exception as e:
            return jsonify({
                'success': False,
                'message': f'无效的cron表达式: {e}'
            }), 400
        
        # 验证任务参数JSON格式
        task_params = data.get('task_params', '{}')
        if task_params:
            try:
                json.loads(task_params)
            except Exception as e:
                return jsonify({
                    'success': False,
                    'message': f'任务参数必须是有效的JSON格式: {e}'
                }), 400
        
        # 创建任务
        task = ScheduledTask(
            name=data['name'],
            description=data.get('description', ''),
            cron_expression=data['cron_expression'],
            task_type=data['task_type'],
            task_function=data['task_function'],
            task_params=task_params,
            is_active=data.get('is_active', True)
        )
        
        db.session.add(task)
        db.session.commit()
        
        # 如果任务是活跃的，添加到调度器
        if task.is_active and scheduler_service.is_running:
            scheduler_service.add_job(task)
        
        logger.info(f"创建定时任务成功: {task.name}")
        
        return jsonify({
            'success': True,
            'message': '定时任务创建成功',
            'task': task.to_dict()
        })
        
    except Exception as e:
        logger.error(f"创建定时任务失败: {e}")
        db.session.rollback()
        return jsonify({
            'success': False,
            'message': str(e)
        }), 500

@scheduler_api_bp.route('/api/admin/scheduler/tasks/<int:task_id>', methods=['PUT'])
def update_scheduled_task(task_id):
    """更新定时任务"""
    try:
        task = ScheduledTask.query.get_or_404(task_id)
        data = request.get_json()
        
        # 验证cron表达式
        if 'cron_expression' in data:
            try:
                croniter(data['cron_expression'])
            except Exception as e:
                return jsonify({
                    'success': False,
                    'message': f'无效的cron表达式: {e}'
                }), 400
        
        # 验证任务参数JSON格式
        if 'task_params' in data and data['task_params']:
            try:
                json.loads(data['task_params'])
            except Exception as e:
                return jsonify({
                    'success': False,
                    'message': f'任务参数必须是有效的JSON格式: {e}'
                }), 400
        
        # 更新任务字段
        for field in ['name', 'description', 'cron_expression', 'task_type', 'task_function', 'task_params', 'is_active']:
            if field in data:
                setattr(task, field, data[field])
        
        task.updated_at = datetime.now()
        db.session.commit()
        
        # 更新调度器中的任务
        if scheduler_service.is_running:
            scheduler_service.remove_job(task_id)
            if task.is_active:
                scheduler_service.add_job(task)
        
        logger.info(f"更新定时任务成功: {task.name}")
        
        return jsonify({
            'success': True,
            'message': '定时任务更新成功',
            'task': task.to_dict()
        })
        
    except Exception as e:
        logger.error(f"更新定时任务失败: {e}")
        db.session.rollback()
        return jsonify({
            'success': False,
            'message': str(e)
        }), 500

@scheduler_api_bp.route('/api/admin/scheduler/tasks/<int:task_id>', methods=['DELETE'])
def delete_scheduled_task(task_id):
    """删除定时任务"""
    try:
        task = ScheduledTask.query.get_or_404(task_id)
        task_name = task.name
        
        # 从调度器中移除任务
        if scheduler_service.is_running:
            scheduler_service.remove_job(task_id)
        
        # 删除数据库记录
        db.session.delete(task)
        db.session.commit()
        
        logger.info(f"删除定时任务成功: {task_name}")
        
        return jsonify({
            'success': True,
            'message': '定时任务删除成功'
        })
        
    except Exception as e:
        logger.error(f"删除定时任务失败: {e}")
        db.session.rollback()
        return jsonify({
            'success': False,
            'message': str(e)
        }), 500

@scheduler_api_bp.route('/api/admin/scheduler/tasks/<int:task_id>/toggle', methods=['POST'])
def toggle_scheduled_task(task_id):
    """切换定时任务状态"""
    try:
        task = ScheduledTask.query.get_or_404(task_id)
        data = request.get_json()
        
        is_active = data.get('is_active', not task.is_active)
        task.is_active = is_active
        task.updated_at = datetime.now()
        
        db.session.commit()
        
        # 更新调度器中的任务
        if scheduler_service.is_running:
            scheduler_service.remove_job(task_id)
            if task.is_active:
                scheduler_service.add_job(task)
        
        status_text = '启用' if is_active else '禁用'
        logger.info(f"{status_text}定时任务: {task.name}")
        
        return jsonify({
            'success': True,
            'message': f'定时任务已{status_text}',
            'task': task.to_dict()
        })
        
    except Exception as e:
        logger.error(f"切换定时任务状态失败: {e}")
        db.session.rollback()
        return jsonify({
            'success': False,
            'message': str(e)
        }), 500

@scheduler_api_bp.route('/api/admin/scheduler/tasks/<int:task_id>/run', methods=['POST'])
def run_scheduled_task_now(task_id):
    """立即执行定时任务"""
    try:
        task = ScheduledTask.query.get_or_404(task_id)
        
        if not scheduler_service.is_running:
            return jsonify({
                'success': False,
                'message': '调度器未运行'
            }), 400
        
        # 检查任务是否已在运行中
        current_status = scheduler_service.get_async_task_status(task_id)
        if current_status and current_status['status'] == 'running':
            return jsonify({
                'success': False,
                'message': '任务正在执行中，请稍后再试'
            }), 400
        
        # 立即执行任务（使用异步方式）
        scheduler_service._execute_task_async(task_id)
        
        logger.info(f"立即执行定时任务: {task.name}")
        
        return jsonify({
            'success': True,
            'message': '任务已提交到后台异步执行',
            'task_id': task_id
        })
        
    except Exception as e:
        logger.error(f"立即执行定时任务失败: {e}")
        return jsonify({
            'success': False,
            'message': str(e)
        }), 500

@scheduler_api_bp.route('/api/admin/scheduler/tasks/<int:task_id>/status', methods=['GET'])
def get_task_execution_status(task_id):
    """获取任务执行状态"""
    try:
        task = ScheduledTask.query.get_or_404(task_id)
        
        # 获取异步执行状态
        async_status = scheduler_service.get_async_task_status(task_id)
        
        # 获取调度器中的任务状态
        job_status = scheduler_service.get_job_status(task_id)
        
        return jsonify({
            'success': True,
            'task': {
                'id': task.id,
                'name': task.name,
                'is_active': task.is_active,
                'last_run_time': task.last_run_time.isoformat() if task.last_run_time else None,
                'next_run_time': task.next_run_time.isoformat() if task.next_run_time else None,
                'run_count': task.run_count
            },
            'async_status': async_status,
            'job_status': job_status
        })
        
    except Exception as e:
        logger.error(f"获取任务执行状态失败: {e}")
        return jsonify({
            'success': False,
            'message': str(e)
        }), 500

@scheduler_api_bp.route('/api/admin/scheduler/status', methods=['GET'])
def get_scheduler_status():
    """获取调度器状态"""
    try:
        return jsonify({
            'success': True,
            'status': {
                'running': scheduler_service.is_running,
                'jobs_count': len(scheduler_service.scheduler.get_jobs()) if scheduler_service.scheduler else 0
            }
        })
        
    except Exception as e:
        logger.error(f"获取调度器状态失败: {e}")
        return jsonify({
            'success': False,
            'message': str(e)
        }), 500

from flask import Blueprint, request, jsonify
from datetime import datetime
import json
from croniter import croniter
from app.repositories.scheduled_task_repository import ScheduledTaskRepository
from app.services.scheduler_service import scheduler_service
from app.utils.logger import get_logger
from app.utils.auth import login_required, permission_required

logger = get_logger(__name__)

scheduler_api_bp = Blueprint('scheduler_api', __name__)


def _scheduled_task_repository():
    """创建定时任务远程 CRUD 仓储，供只读接口使用。"""
    return ScheduledTaskRepository()

@scheduler_api_bp.route('/api/admin/scheduler/stats', methods=['GET'])
@login_required
@permission_required('scheduler:view')
def get_scheduler_stats():
    """获取调度器统计信息"""
    try:
        # 标准分页 CRUD 可支持小规模调度任务统计，无需本地 ORM 聚合。
        tasks = _scheduled_task_repository().list_all()
        total_tasks = len(tasks)
        active_tasks = sum(1 for task in tasks if task.get("is_active"))
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
@login_required
@permission_required('scheduler:view')
def get_scheduled_tasks():
    """获取定时任务列表"""
    try:
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 50, type=int)
        
        # 列表读取走 SDK；创建、调度和运行态更新仍由本地调度器维护。
        result = _scheduled_task_repository().list_page(
            page_index=page,
            page_size=per_page,
            order_field="created_at",
            order_type="desc",
        )
        tasks = result["items"]
        total = result["total"]
        
        return jsonify({
            'success': True,
            'tasks': tasks,
            'pagination': {
                'page': page,
                'per_page': per_page,
                'total': total,
                'pages': (total + per_page - 1) // per_page
            }
        })
        
    except Exception as e:
        logger.error(f"获取定时任务列表失败: {e}")
        return jsonify({
            'success': False,
            'message': str(e)
        }), 500

@scheduler_api_bp.route('/api/admin/scheduler/tasks', methods=['POST'])
@login_required
@permission_required('scheduler:manage')
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
        
        task = _scheduled_task_repository().save({
            'name': data['name'],
            'description': data.get('description', ''),
            'cron_expression': data['cron_expression'],
            'task_type': data['task_type'],
            'task_function': data['task_function'],
            'task_params': task_params,
            'is_active': data.get('is_active', True),
        })
        
        # 如果任务是活跃的，添加到调度器
        if task.get('is_active') and scheduler_service.is_running:
            scheduler_service.add_job(task)
        
        logger.info("创建定时任务成功: %s", task.get('name'))
        
        return jsonify({
            'success': True,
            'message': '定时任务创建成功',
            'task': task
        })
        
    except Exception as e:
        logger.error(f"创建定时任务失败: {e}")
        return jsonify({
            'success': False,
            'message': str(e)
        }), 500

@scheduler_api_bp.route('/api/admin/scheduler/tasks/<int:task_id>', methods=['PUT'])
@login_required
@permission_required('scheduler:manage')
def update_scheduled_task(task_id):
    """更新定时任务"""
    try:
        repository = _scheduled_task_repository()
        task = repository.get(task_id)
        if not task:
            return jsonify({'success': False, 'message': '定时任务不存在'}), 404
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
        
        # 合并允许更新的字段并使用同一远程记录主键保存。
        updated = dict(task)
        for field in ['name', 'description', 'cron_expression', 'task_type', 'task_function', 'task_params', 'is_active']:
            if field in data:
                updated[field] = data[field]
        updated['updated_at'] = datetime.now().isoformat()
        task = repository.save(updated)
        
        # 更新调度器中的任务
        if scheduler_service.is_running:
            scheduler_service.remove_job(task_id)
            if task.get('is_active'):
                scheduler_service.add_job(task)
        
        logger.info("更新定时任务成功: %s", task.get('name'))
        
        return jsonify({
            'success': True,
            'message': '定时任务更新成功',
            'task': task
        })
        
    except Exception as e:
        logger.error(f"更新定时任务失败: {e}")
        return jsonify({
            'success': False,
            'message': str(e)
        }), 500

@scheduler_api_bp.route('/api/admin/scheduler/tasks/<int:task_id>', methods=['DELETE'])
@login_required
@permission_required('scheduler:manage')
def delete_scheduled_task(task_id):
    """删除定时任务"""
    try:
        repository = _scheduled_task_repository()
        task = repository.get(task_id)
        if not task:
            return jsonify({'success': False, 'message': '定时任务不存在'}), 404
        task_name = task.get('name')
        
        # 从调度器中移除任务
        if scheduler_service.is_running:
            scheduler_service.remove_job(task_id)
        
        repository.delete(task_id)
        
        logger.info(f"删除定时任务成功: {task_name}")
        
        return jsonify({
            'success': True,
            'message': '定时任务删除成功'
        })
        
    except Exception as e:
        logger.error(f"删除定时任务失败: {e}")
        return jsonify({
            'success': False,
            'message': str(e)
        }), 500

@scheduler_api_bp.route('/api/admin/scheduler/tasks/<int:task_id>/toggle', methods=['POST'])
@login_required
@permission_required('scheduler:manage')
def toggle_scheduled_task(task_id):
    """切换定时任务状态"""
    try:
        repository = _scheduled_task_repository()
        task = repository.get(task_id)
        if not task:
            return jsonify({'success': False, 'message': '定时任务不存在'}), 404
        data = request.get_json()
        
        is_active = data.get('is_active', not task.get('is_active'))
        task = repository.save({
            **task,
            'is_active': is_active,
            'updated_at': datetime.now().isoformat(),
        })
        
        # 更新调度器中的任务
        if scheduler_service.is_running:
            scheduler_service.remove_job(task_id)
            if task.get('is_active'):
                scheduler_service.add_job(task)
        
        status_text = '启用' if is_active else '禁用'
        logger.info("%s定时任务: %s", status_text, task.get('name'))
        
        return jsonify({
            'success': True,
            'message': f'定时任务已{status_text}',
            'task': task
        })
        
    except Exception as e:
        logger.error(f"切换定时任务状态失败: {e}")
        return jsonify({
            'success': False,
            'message': str(e)
        }), 500

@scheduler_api_bp.route('/api/admin/scheduler/tasks/<int:task_id>/run', methods=['POST'])
@login_required
@permission_required('scheduler:manage')
def run_scheduled_task_now(task_id):
    """立即执行定时任务"""
    try:
        task = _scheduled_task_repository().get(task_id)
        if not task:
            return jsonify({'success': False, 'message': '定时任务不存在'}), 404
        
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
        run_ok = scheduler_service.run_job_once(task_id)
        if not run_ok:
            return jsonify({
                'success': False,
                'message': '任务提交执行失败'
            }), 500
        
        logger.info("立即执行定时任务: %s", task.get('name'))
        
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
@login_required
@permission_required('scheduler:view')
def get_task_execution_status(task_id):
    """获取任务执行状态"""
    try:
        # 详情字段从 SDK 获取，异步状态和调度器状态仍来自本地运行态。
        task = _scheduled_task_repository().get(task_id)
        if not task:
            return jsonify({
                'success': False,
                'message': '定时任务不存在',
            }), 404
        
        # 获取异步执行状态
        async_status = scheduler_service.get_async_task_status(task_id)
        
        # 获取调度器中的任务状态
        job_status = scheduler_service.get_job_status(task_id)
        
        return jsonify({
            'success': True,
            'task': {
                'id': task.get('id'),
                'name': task.get('name'),
                'is_active': task.get('is_active'),
                'last_run_time': task.get('last_run_time'),
                'next_run_time': task.get('next_run_time'),
                'run_count': task.get('run_count'),
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
@login_required
@permission_required('scheduler:view')
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

import json
import subprocess
import sys
import threading
import time
from datetime import datetime, timedelta

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from croniter import croniter
from flask import current_app

from app.exceptions import BadRequestError, ServiceError, ValidationError
from app.repositories import (
    scheduled_task_repository,
    task_log_repository,
    task_result_repository,
)
from app.services.task.data_cleanup import delete_task_result_dependencies
from app.utils.logger import get_logger

logger = get_logger(__name__)


class SchedulerService:
    """定时任务调度服务。

    主进程只负责调度触发、数据库抢锁和启动子进程。
    实际清理任务在 ``scheduled_task_worker.py`` 中执行，并由子进程负责释放锁。
    """

    def __init__(self):
        # APScheduler 调度器实例
        self.scheduler = None
        self.is_running = False
        self._lock = threading.Lock()
        self._tasks_lock = threading.Lock()
        self.app = None
        # 跟踪正在运行的异步任务（仅用于手动”立即执行”时的状态查询）
        self.running_tasks = {}
        # 实例ID，用于分布式锁
        import uuid
        self.instance_id = str(uuid.uuid4())[:8]
    
    def start(self, delay_seconds=30, app=None):
        """启动调度器（延时启动）"""
        if self.is_running:
            logger.warning("调度器已经在运行中")
            return
        
        # 保存应用实例
        if app:
            self.app = app
        else:
            try:
                self.app = current_app._get_current_object()
            except RuntimeError:
                logger.error("无法获取Flask应用实例")
                return
        
        def delayed_start():
            logger.info(f"定时任务调度器将在 {delay_seconds} 秒后启动...")
            time.sleep(delay_seconds)
            self._start_scheduler()
        
        # 在后台线程中延时启动
        thread = threading.Thread(target=delayed_start, daemon=True)
        thread.start()
    
    def _start_scheduler(self):
        """内部启动调度器"""
        with self._lock:
            if self.is_running:
                return
            
            try:
                self.scheduler = BackgroundScheduler()
                self.scheduler.start()
                self.is_running = True
                logger.info("定时任务调度器已启动")
                
                # 加载数据库中的定时任务
                self.load_tasks_from_database()
                
            except Exception as e:
                logger.error(f"启动定时任务调度器失败: {e}")
    
    def stop(self):
        """停止调度器"""
        with self._lock:
            if self.scheduler and self.is_running:
                self.scheduler.shutdown()
                self.is_running = False
                logger.info("定时任务调度器已停止")
    
    def load_tasks_from_database(self):
        """从数据库加载定时任务"""
        if not self.app:
            logger.error("Flask应用实例未设置，无法加载定时任务")
            return
            
        try:
            with self.app.app_context():
                active_tasks = scheduled_task_repository.list_active_entities()
                logger.info(f"从数据库加载了 {len(active_tasks)} 个活跃的定时任务")
                
                for task in active_tasks:
                    self.add_job(task)
                    
        except Exception as e:
            logger.error(f"从数据库加载定时任务失败: {e}")
    
    def add_job(self, scheduled_task):
        """添加定时任务到调度器"""
        if not self.is_running or not self.scheduler:
            logger.warning("调度器未运行，无法添加任务")
            return False
        
        try:
            job_id = f"scheduled_task_{scheduled_task.id}"
            
            # 移除已存在的任务
            if self.scheduler.get_job(job_id):
                self.scheduler.remove_job(job_id)
            
            # 创建cron触发器
            trigger = CronTrigger.from_crontab(scheduled_task.cron_expression)
            
            # 添加任务，直接由 APScheduler 在线程池中调用 _execute_task
            self.scheduler.add_job(
                func=self._execute_task,
                trigger=trigger,
                id=job_id,
                args=[scheduled_task.id],
                name=scheduled_task.name,
                replace_existing=True
            )
            
            # 更新下次执行时间
            self._update_task_next_run(scheduled_task)
            
            logger.info(f"已添加定时任务: {scheduled_task.name} ({scheduled_task.cron_expression})")
            return True
            
        except Exception as e:
            logger.error(f"添加定时任务失败: {e}")
            return False
    
    def remove_job(self, task_id):
        """从调度器中移除任务"""
        if not self.is_running or not self.scheduler:
            return False
        
        try:
            job_id = f"scheduled_task_{task_id}"
            if self.scheduler.get_job(job_id):
                self.scheduler.remove_job(job_id)
                logger.info(f"已移除定时任务: {job_id}")
                return True
        except Exception as e:
            logger.error(f"移除定时任务失败: {e}")
        
        return False
    
    def run_job_once(self, task_id):
        """公开方法：异步立即执行指定的定时任务"""
        if not self.is_running:
            logger.warning("调度器未运行，无法立即执行任务")
            return False
        try:
            self._execute_task_async(task_id)
            return True
        except Exception as e:
            logger.error(f"立即执行定时任务失败: {e}")
            return False
    
    def _execute_task_async(self, task_id):
        """异步执行定时任务的包装器"""
        if not self.app:
            logger.error("Flask应用实例未设置，无法执行定时任务")
            return
        
        try:
            # 使用线程异步执行单次任务（用于“立即执行”接口），避免阻塞请求线程
            start_time = datetime.now()
            with self._tasks_lock:
                self.running_tasks[task_id] = {
                    'start_time': start_time,
                    'status': 'running'
                }

            def _run():
                try:
                    self._execute_task(task_id)
                    status = 'completed'
                    error = None
                except Exception as e:  # noqa: B902, E722 - 需要捕获所有异常以更新状态
                    status = 'failed'
                    error = str(e)
                    logger.error(f"定时任务 {task_id} 异步执行失败: {e}")
                finally:
                    # 更新运行状态
                    with self._tasks_lock:
                        task_info = self.running_tasks.get(task_id) or {}
                        task_info['status'] = status
                        task_info['end_time'] = datetime.now()
                        if error is not None:
                            task_info['error'] = error
                        self.running_tasks[task_id] = task_info
                    if status == 'completed':
                        logger.info(f"定时任务 {task_id} 异步执行完成")

            thread = threading.Thread(target=_run, name=f"scheduled_task_{task_id}", daemon=True)
            thread.start()
            
        except Exception as e:
            logger.error(f"提交定时任务到线程池失败: {e}")
    
    def _execute_task(self, task_id):
        """执行定时任务（独立进程，带分布式锁）"""
        if not self.app:
            logger.error("Flask应用实例未设置，无法执行定时任务")
            return

        try:
            with self.app.app_context():
                # 获取任务信息
                scheduled_task = scheduled_task_repository.get_entity(task_id)
                if not scheduled_task or not scheduled_task.is_active:
                    logger.warning(f"定时任务 {task_id} 不存在或已禁用")
                    return

                # 尝试获取分布式锁
                if scheduled_task.is_running:
                    logger.warning(f"定时任务 {scheduled_task.name} 正在被实例 {scheduled_task.running_instance_id} 执行，跳过")
                    return

                # 使用乐观锁获取执行权
                rows_updated = scheduled_task_repository.acquire_run_lock(
                    task_id,
                    self.instance_id,
                    datetime.now(),
                )

                if rows_updated == 0:
                    logger.warning(f"定时任务 {scheduled_task.name} 已被其他实例获取，跳过")
                    return

                scheduled_task_repository.refresh_entity(scheduled_task)
                logger.info(f"[实例 {self.instance_id}] 开始执行定时任务: {scheduled_task.name}")

                # 更新执行次数和下次执行时间
                self._record_task_run(scheduled_task)

                # 使用独立进程执行任务
                self._run_task_in_subprocess(scheduled_task)

        except Exception as e:
            logger.error(f"执行定时任务异常: {e}")
            self._release_task_lock(task_id)
    
    def _run_task_in_subprocess(self, scheduled_task):
        """在独立进程中执行任务"""
        try:
            # 构建子进程命令
            script_path = 'app/services/scheduled_task_worker.py'
            cmd = [sys.executable, script_path, str(scheduled_task.id), self.instance_id]

            # 启动子进程（非阻塞）
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd='.',
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0
            )

            logger.info(f"定时任务 {scheduled_task.name} 已在独立进程 {process.pid} 中启动")

        except Exception as e:
            logger.error(f"启动独立进程失败: {e}")
            self._release_task_lock(scheduled_task.id)

    def _release_task_lock(self, task_id):
        """释放任务锁"""
        try:
            with self.app.app_context():
                scheduled_task_repository.release_run_lock(task_id, self.instance_id)
        except Exception as e:
            logger.error(f"释放任务锁失败: {e}")
    
    def _cleanup_old_logs(self, params):
        """清理旧日志（批量处理优化）"""
        try:
            days = params.get('days', 10)
            batch_size = params.get('batch_size', 200)  # 减小批次大小
            delay = params.get('delay', 2)  # 增加批次间延迟（秒）
            cutoff_date = datetime.now() - timedelta(days=days)

            total_deleted = 0
            while True:
                # 分批删除，避免长时间锁定数据库
                batch_ids = task_log_repository.list_ids_older_than(cutoff_date, batch_size)

                if not batch_ids:
                    break

                # 删除当前批次
                deleted_count = task_log_repository.delete_by_ids(batch_ids)

                total_deleted += deleted_count
                logger.info(f"已清理 {deleted_count} 条日志记录，总计: {total_deleted}")

                # 如果删除的记录少于批次大小，说明已经清理完毕
                if deleted_count < batch_size:
                    break

                # 延长休息时间，降低系统负载
                time.sleep(delay)

            logger.info(f"清理完成，共删除 {total_deleted} 条超过 {days} 天的任务日志")
            return True

        except Exception as e:
            logger.error(f"清理旧日志失败: {e}")
            return False
    
    def _cleanup_old_results(self, params):
        """清理旧结果（批量处理优化）"""
        try:
            days = params.get('days', 10)
            batch_size = params.get('batch_size', 200)  # 减小批次大小
            delay = params.get('delay', 2)  # 增加批次间延迟（秒）
            cutoff_date = datetime.now() - timedelta(days=days)

            total_deleted = 0
            while True:
                # 分批删除，避免长时间锁定数据库
                batch_ids = task_result_repository.list_ids_older_than(cutoff_date, batch_size)

                if not batch_ids:
                    break

                delete_task_result_dependencies(batch_ids)
                deleted_count = task_result_repository.delete_by_ids(batch_ids)

                total_deleted += deleted_count
                logger.info(f"已清理 {deleted_count} 条结果记录，总计: {total_deleted}")

                # 如果删除的记录少于批次大小，说明已经清理完毕
                if deleted_count < batch_size:
                    break

                # 延长休息时间，降低系统负载
                time.sleep(delay)

            logger.info(f"清理完成，共删除 {total_deleted} 条超过 {days} 天的任务结果")
            return True

        except Exception as e:
            logger.error(f"清理旧结果失败: {e}")
            return False
    
    def _cleanup_old_data(self, params):
        """清理旧数据（日志和结果）"""
        try:
            log_success = self._cleanup_old_logs(params)
            return log_success
            # result_success = self._cleanup_old_results(params)
            # return log_success and result_success
            
        except Exception as e:
            logger.error(f"清理旧数据失败: {e}")
            return False
    
    def _record_task_run(self, scheduled_task):
        """累计执行次数并更新下次执行时间"""
        next_time = self._compute_next_run(scheduled_task)
        if next_time is not None:
            scheduled_task_repository.record_run(scheduled_task.id, next_time)
            scheduled_task.next_run_time = next_time

    def _update_task_next_run(self, scheduled_task):
        """仅更新下次执行时间（add_job，不计执行次数）"""
        next_time = self._compute_next_run(scheduled_task)
        if next_time is not None:
            scheduled_task_repository.update_next_run(scheduled_task.id, next_time)
            scheduled_task.next_run_time = next_time

    def _compute_next_run(self, scheduled_task):
        try:
            cron = croniter(scheduled_task.cron_expression, datetime.now())
            return cron.get_next(datetime)
        except Exception as e:
            logger.error(f"计算下次执行时间失败: {e}")
            return None
    
    def get_job_status(self, task_id):
        """获取任务状态"""
        if not self.is_running or not self.scheduler:
            return None
        
        job_id = f"scheduled_task_{task_id}"
        job = self.scheduler.get_job(job_id)
        
        if job:
            return {
                'id': job.id,
                'name': job.name,
                'next_run_time': job.next_run_time.isoformat() if job.next_run_time else None
            }
        return None
    
    def get_async_task_status(self, task_id=None):
        """获取异步任务执行状态"""
        with self._tasks_lock:
            if task_id:
                # 获取特定任务状态
                return self.running_tasks.get(task_id)
            else:
                # 获取所有任务状态
                return dict(self.running_tasks)
    
    def cleanup_completed_tasks(self, max_age_hours=24):
        """清理已完成的任务记录"""
        current_time = datetime.now()
        to_remove = []
        
        with self._tasks_lock:
            for task_id, task_info in self.running_tasks.items():
                if task_info['status'] in ['completed', 'failed']:
                    end_time = task_info.get('end_time', current_time)
                    age = current_time - end_time
                    
                    if age.total_seconds() > max_age_hours * 3600:
                        to_remove.append(task_id)
        
        with self._tasks_lock:
            for task_id in to_remove:
                if task_id in self.running_tasks:
                    del self.running_tasks[task_id]
            
        if to_remove:
            logger.info(f"清理了 {len(to_remove)} 个已完成的任务记录")

    # ── 定时任务 CRUD 编排（/admin/scheduler* 端点，R4 自路由下沉） ──

    # 管理端可更新字段白名单（与 ScheduledTaskUpdateSchema 对齐）
    SCHEDULER_TASK_FIELDS = (
        'name', 'description', 'cron_expression',
        'task_type', 'task_function', 'task_params', 'is_active',
    )

    @staticmethod
    def _validate_cron_expression(expression):
        """cron 表达式校验；无效抛 ValidationError（400 语义）。"""
        try:
            croniter(expression)
        except Exception as e:
            raise ValidationError(f"无效的cron表达式: {e}")

    @staticmethod
    def _validate_task_params_json(task_params):
        """任务参数 JSON 校验；无效抛 ValidationError（400 语义）。"""
        if task_params:
            try:
                json.loads(task_params)
            except Exception as e:
                raise ValidationError(f"任务参数必须是有效的JSON格式: {e}")

    def get_required_task(self, task_id):
        """定时任务 dict 访问；不存在抛 NotFoundError（路由 404 前置检查用）。"""
        return scheduled_task_repository.get_required(task_id)

    def get_scheduler_stats(self) -> dict:
        """调度器统计（/admin/scheduler/stats）。"""
        stats = scheduled_task_repository.get_stats()
        return {
            'total_tasks': stats["total"],
            'active_tasks': stats["active"],
            'inactive_tasks': stats["total"] - stats["active"],
            'scheduler_running': self.is_running,
        }

    def list_tasks_page(self, page: int, per_page: int) -> dict:
        """定时任务分页列表（/admin/scheduler/tasks GET 响应结构）。"""
        page_data = scheduled_task_repository.list_paginated(page, per_page)
        return {
            'tasks': page_data["items"],
            'pagination': {
                'page': page_data["current_page"],
                'per_page': page_data["per_page"],
                'total': page_data["total"],
                'pages': page_data["pages"],
            },
        }

    def create_task(self, payload: dict) -> dict:
        """创建定时任务；活跃且调度器运行中则注册调度。"""
        self._validate_cron_expression(payload["cron_expression"])
        self._validate_task_params_json(payload["task_params"])

        task = scheduled_task_repository.create(payload)
        if task["is_active"] and self.is_running:
            self.add_job(scheduled_task_repository.get_entity(task["id"]))

        logger.info(f"创建定时任务成功: {task['name']}")
        return task

    def update_task(self, task_id: int, data: dict) -> dict:
        """按白名单更新定时任务字段并重新同步调度。"""
        scheduled_task_repository.get_required(task_id)

        if 'cron_expression' in data:
            self._validate_cron_expression(data['cron_expression'])
        if 'task_params' in data and data['task_params']:
            self._validate_task_params_json(data['task_params'])

        fields = {field: data[field] for field in self.SCHEDULER_TASK_FIELDS if field in data}
        fields['updated_at'] = datetime.now()
        updated = scheduled_task_repository.update(task_id, fields)

        # 更新调度器中的任务（调度器消费实体）
        if self.is_running:
            self.remove_job(task_id)
            entity = scheduled_task_repository.get_entity(task_id)
            if entity.is_active:
                self.add_job(entity)

        logger.info(f"更新定时任务成功: {updated['name']}")
        return updated

    def delete_task(self, task_id: int) -> None:
        """删除定时任务并移除调度。"""
        task = scheduled_task_repository.get_required(task_id)

        if self.is_running:
            self.remove_job(task_id)

        scheduled_task_repository.delete(task_id)
        logger.info(f"删除定时任务成功: {task['name']}")

    def toggle_task(self, task_id: int, data: dict) -> tuple:
        """切换定时任务启停（data 未带 is_active 时取反）。返回 (更新后任务, 状态文案)。"""
        task = scheduled_task_repository.get_required(task_id)

        is_active = data.get('is_active', not task["is_active"])
        updated = scheduled_task_repository.update(task_id, {
            'is_active': is_active,
            'updated_at': datetime.now(),
        })

        if self.is_running:
            self.remove_job(task_id)
            if is_active:
                self.add_job(scheduled_task_repository.get_entity(task_id))

        status_text = '启用' if is_active else '禁用'
        logger.info(f"{status_text}定时任务: {updated['name']}")
        return updated, status_text

    def run_task_now(self, task_id: int) -> None:
        """立即执行定时任务（异步提交）；未运行/执行中/提交失败按原语义抛异常。"""
        task = scheduled_task_repository.get_required(task_id)

        if not self.is_running:
            raise BadRequestError('调度器未运行')

        current_status = self.get_async_task_status(task_id)
        if current_status and current_status['status'] == 'running':
            raise BadRequestError('任务正在执行中，请稍后再试')

        if not self.run_job_once(task_id):
            raise ServiceError('任务提交执行失败')

        logger.info(f"立即执行定时任务: {task['name']}")

    def get_task_execution_status(self, task_id: int) -> dict:
        """任务执行状态（任务摘要 + 异步状态 + 调度状态）。"""
        task = scheduled_task_repository.get_required(task_id)
        return {
            'task': {
                'id': task["id"],
                'name': task["name"],
                'is_active': task["is_active"],
                'last_run_time': task["last_run_time"],
                'next_run_time': task["next_run_time"],
                'run_count': task["run_count"],
            },
            'async_status': self.get_async_task_status(task_id),
            'job_status': self.get_job_status(task_id),
        }

    def create_default_tasks(self):
        """创建默认定时任务"""
        if not self.app:
            logger.error("Flask应用实例未设置，无法创建默认定时任务")
            return None
            
        try:
            with self.app.app_context():
                # 检查是否已存在默认任务
                existing_task = scheduled_task_repository.get_by_name_and_function(
                    '每日数据清理', 'cleanup_old_data'
                )
                
                if existing_task:
                    logger.info("默认定时任务已存在")
                    return existing_task
                
                # 创建默认任务：每天0点清理超过10天的日志和结果
                created = scheduled_task_repository.create({
                    'name': '每日数据清理',
                    'description': '每天0点自动清理超过10天的任务日志和任务结果',
                    'cron_expression': '0 0 * * *',  # 每天0点
                    'task_type': 'cleanup',
                    'task_function': 'cleanup_old_data',
                    'task_params': json.dumps({'days': 10}),
                    'is_active': True,
                })
                default_task = scheduled_task_repository.get_entity(created['id'])
                
                # 添加到调度器
                if self.is_running:
                    self.add_job(default_task)
                
                logger.info("已创建默认定时任务：每日数据清理")
                return default_task
                
        except Exception as e:
            logger.error(f"创建默认定时任务失败: {e}")
            return None

# 全局调度器实例
scheduler_service = SchedulerService()

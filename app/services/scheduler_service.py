from datetime import datetime, timedelta
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from croniter import croniter
import json
import threading
import time
import asyncio
from concurrent.futures import ThreadPoolExecutor
from flask import current_app
from app.extensions import db
from app.models import ScheduledTask, TaskLog, TaskResult
from app.utils.logger import get_logger

logger = get_logger(__name__)

class SchedulerService:
    """定时任务调度服务"""
    
    def __init__(self):
        self.scheduler = None
        self.is_running = False
        self._lock = threading.Lock()
        self.app = None
        # 创建线程池用于异步执行任务
        self.executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="scheduler_task")
        # 跟踪正在运行的异步任务
        self.running_tasks = {}
    
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
            
            # 关闭线程池
            if self.executor:
                self.executor.shutdown(wait=True)
                logger.info("任务执行线程池已关闭")
    
    def load_tasks_from_database(self):
        """从数据库加载定时任务"""
        if not self.app:
            logger.error("Flask应用实例未设置，无法加载定时任务")
            return
            
        try:
            with self.app.app_context():
                active_tasks = ScheduledTask.query.filter_by(is_active=True).all()
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
            
            # 添加任务（使用异步执行包装器）
            self.scheduler.add_job(
                func=self._execute_task_async,
                trigger=trigger,
                id=job_id,
                args=[scheduled_task.id],
                name=scheduled_task.name,
                replace_existing=True
            )
            
            # 更新下次执行时间
            self._update_next_run_time(scheduled_task)
            
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
    
    def _execute_task_async(self, task_id):
        """异步执行定时任务的包装器"""
        if not self.app:
            logger.error("Flask应用实例未设置，无法执行定时任务")
            return
        
        try:
            # 在线程池中异步执行任务，避免阻塞主进程
            future = self.executor.submit(self._execute_task, task_id)
            
            # 记录正在运行的任务
            self.running_tasks[task_id] = {
                'future': future,
                'start_time': datetime.now(),
                'status': 'running'
            }
            
            logger.info(f"定时任务 {task_id} 已提交到线程池异步执行")
            
            # 添加回调处理任务完成或失败
            future.add_done_callback(lambda f: self._task_completion_callback(task_id, f))
            
        except Exception as e:
            logger.error(f"提交定时任务到线程池失败: {e}")
    
    def _task_completion_callback(self, task_id, future):
        """任务完成后的回调函数"""
        try:
            result = future.result()  # 获取任务执行结果
            
            # 更新任务状态
            if task_id in self.running_tasks:
                self.running_tasks[task_id]['status'] = 'completed'
                self.running_tasks[task_id]['end_time'] = datetime.now()
                
            logger.info(f"定时任务 {task_id} 异步执行完成")
            
        except Exception as e:
            # 更新任务状态为失败
            if task_id in self.running_tasks:
                self.running_tasks[task_id]['status'] = 'failed'
                self.running_tasks[task_id]['end_time'] = datetime.now()
                self.running_tasks[task_id]['error'] = str(e)
                
            logger.error(f"定时任务 {task_id} 异步执行失败: {e}")
        
        finally:
            # 清理完成的任务记录（可选：保留一段时间用于监控）
            # 这里我们保留任务记录，可以后续添加清理机制
            pass
    
    def _execute_task(self, task_id):
        """执行定时任务"""
        if not self.app:
            logger.error("Flask应用实例未设置，无法执行定时任务")
            return
            
        try:
            with self.app.app_context():
                # 获取任务信息
                scheduled_task = ScheduledTask.query.get(task_id)
                if not scheduled_task or not scheduled_task.is_active:
                    logger.warning(f"定时任务 {task_id} 不存在或已禁用")
                    return
                
                logger.info(f"开始执行定时任务: {scheduled_task.name}")
                
                # 更新执行时间和次数
                scheduled_task.last_run_time = datetime.now()
                scheduled_task.run_count += 1
                self._update_next_run_time(scheduled_task)
                db.session.commit()
                
                # 执行具体任务
                success = self._run_task_function(scheduled_task)
                
                if success:
                    logger.info(f"定时任务执行成功: {scheduled_task.name}")
                else:
                    logger.error(f"定时任务执行失败: {scheduled_task.name}")
                    
        except Exception as e:
            logger.error(f"执行定时任务异常: {e}")
    
    def _run_task_function(self, scheduled_task):
        """运行具体的任务函数"""
        try:
            function_name = scheduled_task.task_function
            params = json.loads(scheduled_task.task_params) if scheduled_task.task_params else {}
            
            # 根据任务类型执行不同的函数
            if function_name == 'cleanup_old_logs':
                return self._cleanup_old_logs(params)
            elif function_name == 'cleanup_old_results':
                return self._cleanup_old_results(params)
            elif function_name == 'cleanup_old_data':
                return self._cleanup_old_data(params)
            else:
                logger.error(f"未知的任务函数: {function_name}")
                return False
                
        except Exception as e:
            logger.error(f"执行任务函数失败: {e}")
            return False
    
    def _cleanup_old_logs(self, params):
        """清理旧日志（批量处理优化）"""
        try:
            days = params.get('days', 10)
            batch_size = params.get('batch_size', 1000)  # 批量处理大小
            cutoff_date = datetime.now() - timedelta(days=days)
            
            total_deleted = 0
            while True:
                # 分批删除，避免长时间锁定数据库
                batch_query = TaskLog.query.filter(TaskLog.timestamp < cutoff_date).limit(batch_size)
                batch_ids = [log.id for log in batch_query.all()]
                
                if not batch_ids:
                    break
                
                # 删除当前批次
                deleted_count = TaskLog.query.filter(TaskLog.id.in_(batch_ids)).delete(synchronize_session=False)
                db.session.commit()
                
                total_deleted += deleted_count
                logger.info(f"已清理 {deleted_count} 条日志记录，总计: {total_deleted}")
                
                # 如果删除的记录少于批次大小，说明已经清理完毕
                if deleted_count < batch_size:
                    break
                
                # 短暂休息，避免过度占用资源
                time.sleep(0.1)
            
            logger.info(f"清理完成，共删除 {total_deleted} 条超过 {days} 天的任务日志")
            return True
            
        except Exception as e:
            logger.error(f"清理旧日志失败: {e}")
            db.session.rollback()
            return False
    
    def _cleanup_old_results(self, params):
        """清理旧结果（批量处理优化）"""
        try:
            days = params.get('days', 10)
            batch_size = params.get('batch_size', 1000)  # 批量处理大小
            cutoff_date = datetime.now() - timedelta(days=days)
            
            total_deleted = 0
            while True:
                # 分批删除，避免长时间锁定数据库
                batch_query = TaskResult.query.filter(TaskResult.timestamp < cutoff_date).limit(batch_size)
                batch_ids = [result.id for result in batch_query.all()]
                
                if not batch_ids:
                    break
                
                # 删除当前批次
                deleted_count = TaskResult.query.filter(TaskResult.id.in_(batch_ids)).delete(synchronize_session=False)
                db.session.commit()
                
                total_deleted += deleted_count
                logger.info(f"已清理 {deleted_count} 条结果记录，总计: {total_deleted}")
                
                # 如果删除的记录少于批次大小，说明已经清理完毕
                if deleted_count < batch_size:
                    break
                
                # 短暂休息，避免过度占用资源
                time.sleep(0.1)
            
            logger.info(f"清理完成，共删除 {total_deleted} 条超过 {days} 天的任务结果")
            return True
            
        except Exception as e:
            logger.error(f"清理旧结果失败: {e}")
            db.session.rollback()
            return False
    
    def _cleanup_old_data(self, params):
        """清理旧数据（日志和结果）"""
        try:
            log_success = self._cleanup_old_logs(params)
            result_success = self._cleanup_old_results(params)
            return log_success and result_success
            
        except Exception as e:
            logger.error(f"清理旧数据失败: {e}")
            return False
    
    def _update_next_run_time(self, scheduled_task):
        """更新下次执行时间"""
        try:
            cron = croniter(scheduled_task.cron_expression, datetime.now())
            next_time = cron.get_next(datetime)
            scheduled_task.next_run_time = next_time
            db.session.commit()
        except Exception as e:
            logger.error(f"更新下次执行时间失败: {e}")
    
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
        
        for task_id, task_info in self.running_tasks.items():
            if task_info['status'] in ['completed', 'failed']:
                end_time = task_info.get('end_time', current_time)
                age = current_time - end_time
                
                if age.total_seconds() > max_age_hours * 3600:
                    to_remove.append(task_id)
        
        for task_id in to_remove:
            del self.running_tasks[task_id]
            
        if to_remove:
            logger.info(f"清理了 {len(to_remove)} 个已完成的任务记录")
    
    def create_default_tasks(self):
        """创建默认定时任务"""
        if not self.app:
            logger.error("Flask应用实例未设置，无法创建默认定时任务")
            return None
            
        try:
            with self.app.app_context():
                # 检查是否已存在默认任务
                existing_task = ScheduledTask.query.filter_by(
                    name='每日数据清理',
                    task_function='cleanup_old_data'
                ).first()
                
                if existing_task:
                    logger.info("默认定时任务已存在")
                    return existing_task
                
                # 创建默认任务：每天0点清理超过10天的日志和结果
                default_task = ScheduledTask(
                    name='每日数据清理',
                    description='每天0点自动清理超过10天的任务日志和任务结果',
                    cron_expression='0 0 * * *',  # 每天0点
                    task_type='cleanup',
                    task_function='cleanup_old_data',
                    task_params=json.dumps({'days': 10}),
                    is_active=True
                )
                
                db.session.add(default_task)
                db.session.commit()
                
                # 添加到调度器
                if self.is_running:
                    self.add_job(default_task)
                
                logger.info("已创建默认定时任务：每日数据清理")
                return default_task
                
        except Exception as e:
            logger.error(f"创建默认定时任务失败: {e}")
            with self.app.app_context():
                db.session.rollback()
            return None

# 全局调度器实例
scheduler_service = SchedulerService()

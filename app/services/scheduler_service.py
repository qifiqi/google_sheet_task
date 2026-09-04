import subprocess
import sys
import threading
import time
from datetime import datetime

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from croniter import croniter
from flask import current_app

from app.repositories.scheduled_task_repository import ScheduledTaskRepository
from app.utils.logger import get_logger

logger = get_logger(__name__)
_scheduled_task_repository = ScheduledTaskRepository()


class SchedulerService:
    """定时任务调度服务。

    主进程只负责调度触发、数据库抢锁和启动子进程。
    实际清理任务在 ``scheduled_task_worker.py`` 中执行，并由子进程负责释放锁。
    """

    def __init__(self):
        """初始化 APScheduler 引用、应用上下文和并发保护锁。"""
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
            """延迟启动调度器，避免应用初始化阶段的资源竞争。"""
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
                active_tasks = [
                    task for task in _scheduled_task_repository.list_all()
                    if task.get("is_active")
                ]
                logger.info(f"从数据库加载了 {len(active_tasks)} 个活跃的定时任务")
                
                for task in active_tasks:
                    if self._is_removed_cleanup_task(task):
                        logger.warning(
                            "跳过已移除的数据清理定时任务: %s (%s)",
                            task.get("name"),
                            task.get("task_function"),
                        )
                        continue
                    self.add_job(task)
                    
        except Exception as e:
            logger.error(f"从数据库加载定时任务失败: {e}")
    
    @staticmethod
    def _is_removed_cleanup_task(scheduled_task):
        """判断任务是否为已移除的按时间清理任务。"""
        function_name = (
            scheduled_task.get("task_function")
            if isinstance(scheduled_task, dict)
            else scheduled_task.task_function
        )
        return function_name in {
            "cleanup_old_logs",
            "cleanup_old_results",
            "cleanup_old_data",
        }

    def add_job(self, scheduled_task):
        """添加定时任务到调度器"""
        if not self.is_running or not self.scheduler:
            logger.warning("调度器未运行，无法添加任务")
            return False
        
        if self._is_removed_cleanup_task(scheduled_task):
            task_name = scheduled_task.get("name") if isinstance(scheduled_task, dict) else scheduled_task.name
            logger.warning("拒绝添加已移除的数据清理定时任务: %s", task_name)
            return False

        try:
            task_id = scheduled_task.get("id") if isinstance(scheduled_task, dict) else scheduled_task.id
            task_name = scheduled_task.get("name") if isinstance(scheduled_task, dict) else scheduled_task.name
            cron_expression = scheduled_task.get("cron_expression") if isinstance(scheduled_task, dict) else scheduled_task.cron_expression
            job_id = f"scheduled_task_{task_id}"
            
            # 移除已存在的任务
            if self.scheduler.get_job(job_id):
                self.scheduler.remove_job(job_id)
            
            # 创建cron触发器
            trigger = CronTrigger.from_crontab(cron_expression)
            
            # 添加任务，直接由 APScheduler 在线程池中调用 _execute_task
            self.scheduler.add_job(
                func=self._execute_task,
                trigger=trigger,
                id=job_id,
                args=[task_id],
                name=task_name,
                replace_existing=True
            )
            
            # 更新下次执行时间
            self._update_next_run_time(scheduled_task)
            
            logger.info("已添加定时任务: %s (%s)", task_name, cron_expression)
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
                """在线程中执行指定定时任务，并记录未捕获异常。"""
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
                scheduled_task = _scheduled_task_repository.get(task_id)
                if not scheduled_task or not scheduled_task.get("is_active"):
                    logger.warning(f"定时任务 {task_id} 不存在或已禁用")
                    return

                if self._is_removed_cleanup_task(scheduled_task):
                    logger.warning(
                        "跳过已移除的数据清理定时任务执行: %s (%s)",
                        scheduled_task.get("name"),
                        scheduled_task.get("task_function"),
                    )
                    return

                # 尝试获取分布式锁
                if scheduled_task.get("is_running"):
                    logger.warning("定时任务 %s 正在被实例 %s 执行，跳过", scheduled_task.get("name"), scheduled_task.get("running_instance_id"))
                    return

                # 当前部署为单调度实例，进程内锁足以串行化；多实例需 ClaimRun 接口。
                scheduled_task = _scheduled_task_repository.save({
                    **scheduled_task,
                    'is_running': True,
                    'running_instance_id': self.instance_id,
                    'last_run_time': datetime.now(),
                    'run_count': int(scheduled_task.get('run_count') or 0) + 1,
                })
                logger.info("[实例 %s] 开始执行定时任务: %s", self.instance_id, scheduled_task.get("name"))

                # 更新执行次数和下次执行时间
                self._update_next_run_time(scheduled_task)

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
            task_id = scheduled_task.get("id") if isinstance(scheduled_task, dict) else scheduled_task.id
            task_name = scheduled_task.get("name") if isinstance(scheduled_task, dict) else scheduled_task.name
            cmd = [sys.executable, script_path, str(task_id), self.instance_id]

            # 启动子进程（非阻塞）
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd='.',
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0
            )

            logger.info("定时任务 %s 已在独立进程 %s 中启动", task_name, process.pid)

        except Exception as e:
            logger.error(f"启动独立进程失败: {e}")
            self._release_task_lock(task_id)

    def _release_task_lock(self, task_id):
        """释放任务锁"""
        try:
            with self.app.app_context():
                task = _scheduled_task_repository.get(task_id)
                if task and task.get("running_instance_id") == self.instance_id:
                    _scheduled_task_repository.save({
                        **task,
                        "is_running": False,
                        "running_instance_id": None,
                    })
        except Exception as e:
            logger.error(f"释放任务锁失败: {e}")
    
    def _update_next_run_time(self, scheduled_task):
        """更新下次执行时间"""
        try:
            if not isinstance(scheduled_task, dict):
                logger.error("定时任务必须由远端 Repository 返回字典记录")
                return None
            cron_expression = scheduled_task.get("cron_expression")
            cron = croniter(cron_expression, datetime.now())
            next_time = cron.get_next(datetime)
            scheduled_task["next_run_time"] = next_time.isoformat()
            return _scheduled_task_repository.save(scheduled_task)
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
    
    def create_default_tasks(self):
        """默认定时任务已移除，不再创建按时间清理任务。"""
        logger.info("默认数据清理定时任务已移除，跳过创建")
        return None

# 全局调度器实例
scheduler_service = SchedulerService()

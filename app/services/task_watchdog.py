import threading
import time
from datetime import datetime

from app.models import Task,TaskLog
from app.services.config_manager import get_config_manager
from app.services.task_manager import task_manager
from app.utils.logger import get_logger

logger = get_logger(__name__)


class TaskWatchdog:
    def __init__(self):
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._lock = threading.Lock()

    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self, app):
        with self._lock:
            if self.is_running():
                return

            self._stop_event.clear()
            self._thread = threading.Thread(target=self._run, args=(app,))
            self._thread.daemon = True
            self._thread.start()

    def stop(self, timeout: float | None = 5.0):
        with self._lock:
            self._stop_event.set()
            t = self._thread

        if t and t.is_alive() and timeout is not None:
            t.join(timeout=timeout)

    def _get_config(self, app, key: str, default):
        with app.app_context():
            return get_config_manager().get_config(key, default)

    def _run(self, app):
        while not self._stop_event.is_set():
            try:
                enabled = bool(self._get_config(app, 'watchdog_enabled', True))
                interval_seconds = int(self._get_config(app, 'watchdog_interval_seconds', 60))
                # 获取日志超时阈值（分钟），默认30分钟无日志更新则认为任务卡死
                log_timeout_minutes = int(self._get_config(app, 'watchdog_log_timeout_minutes', 60))

                if not enabled:
                    time.sleep(max(interval_seconds, 1))
                    continue

                with app.app_context():
                    running_tasks = Task.query.filter_by(status='running').all()

                    for task in running_tasks:
                        if self._stop_event.is_set():
                            break

                        # 检查任务管理器状态
                        status_check = task_manager.check_local_task_status(task.id)
                        if status_check.get('can_restart'):
                            logger.info(f"watchdog detected stuck task: {task.id}")
                            reason = status_check.get('restart_reason')
                            logger.warning(f"watchdog detected stuck task: {task.id}, reason: {reason}")
                            result = task_manager.restart_task(task.id, resume_from_checkpoint=True)
                            logger.warning(f"watchdog restart result: {task.id}, {result}")
                            continue

                        # 检查任务日志更新时间
                        latest_log = TaskLog.query.filter_by(task_id=task.id).order_by(TaskLog.timestamp.desc()).first()
                        
                        if latest_log:
                            # 计算距离最后一条日志的时间差
                            time_since_last_log = datetime.now() - latest_log.timestamp
                            minutes_since_last_log = time_since_last_log.total_seconds() / 60
                            
                            if minutes_since_last_log > log_timeout_minutes:
                                logger.warning(
                                    f"watchdog detected task with no log updates: task_id={task.id}, "
                                    f"last_log_time={latest_log.timestamp}, "
                                    f"minutes_since_last_log={minutes_since_last_log:.2f}"
                                )
                                # 强制取消任务后重启
                                try:
                                    logger.info(f"watchdog force cancelling task: {task.id}")
                                    task_manager.cancel_task(task.id)
                                    logger.info(f"watchdog cancelled task: {task.id}, now restarting...")
                                    result = task_manager.restart_task(task.id, resume_from_checkpoint=True)
                                    logger.warning(f"watchdog restart result: {task.id}, {result}")
                                except Exception as restart_error:
                                    logger.error(f"watchdog restart error: {task.id}, {str(restart_error)}", exc_info=True)
                        else:
                            # 如果任务没有任何日志记录，检查任务开始时间
                            if task.start_time:
                                time_since_start = datetime.now() - task.start_time
                                minutes_since_start = time_since_start.total_seconds() / 60
                                
                                if minutes_since_start > log_timeout_minutes:
                                    logger.warning(
                                        f"watchdog detected running task with no logs: task_id={task.id}, "
                                        f"start_time={task.start_time}, "
                                        f"minutes_since_start={minutes_since_start:.2f}"
                                    )
                                    # 强制取消任务后重启
                                    try:
                                        logger.info(f"watchdog force cancelling task: {task.id}")
                                        task_manager.cancel_task(task.id)
                                        logger.info(f"watchdog cancelled task: {task.id}, now restarting...")
                                        result = task_manager.restart_task(task.id, resume_from_checkpoint=True)
                                        logger.warning(f"watchdog restart result: {task.id}, {result}")
                                    except Exception as restart_error:
                                        logger.error(f"watchdog restart error: {task.id}, {str(restart_error)}", exc_info=True)

                time.sleep(max(interval_seconds, 1))

            except Exception as e:
                logger.error(f"watchdog loop error: {str(e)}", exc_info=True)
                time.sleep(5)


task_watchdog = TaskWatchdog()

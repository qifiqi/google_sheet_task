import threading
import time
from datetime import datetime, timedelta

from sqlalchemy import and_, or_

from app.models import Task, TaskLog
from app.services.config_manager import get_config_manager
from app.services.task import task_manager
from app.utils.logger import get_logger
from app.utils.task_error_utils import NETWORK_ERROR_PREFIX

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

    def _load_runtime_config(self, app) -> tuple[bool, int, int, int]:
        enabled = bool(self._get_config(app, 'watchdog_enabled', True))
        interval_seconds = int(self._get_config(app, 'watchdog_interval_seconds', 60))
        log_timeout_minutes = int(
            self._get_config(app, 'watchdog_log_timeout_minutes', 30)
        )
        effective_sleep_seconds = max(interval_seconds, 5)
        return (
            enabled,
            interval_seconds,
            log_timeout_minutes,
            effective_sleep_seconds,
        )

    def _log_config_snapshot(
        self,
        last_logged_config,
        config_snapshot: tuple[bool, int, int, int],
    ):
        if config_snapshot != last_logged_config:
            enabled, interval_seconds, log_timeout_minutes, effective_sleep_seconds = (
                config_snapshot
            )
            logger.info(
                "watchdog config applied: enabled=%s, interval_seconds=%s, "
                "log_timeout_minutes=%s, effective_sleep_seconds=%s",
                enabled,
                interval_seconds,
                log_timeout_minutes,
                effective_sleep_seconds,
            )
            return config_snapshot
        return last_logged_config

    def _restart_task_with_reason(self, task_id: str, reason: str) -> None:
        try:
            logger.warning(
                "watchdog restarting task: task_id=%s, reason=%s",
                task_id,
                reason,
            )
            task_manager.cancel_task(task_id)

            time.sleep(10)

            result = task_manager.restart_task(task_id, resume_from_checkpoint=True)
            logger.warning(
                "watchdog restart result: task_id=%s, reason=%s, result=%s",
                task_id,
                reason,
                result,
            )
        except Exception as restart_error:
            logger.error(
                "watchdog restart error: task_id=%s, reason=%s, err=%s",
                task_id,
                reason,
                str(restart_error),
                exc_info=True,
            )

    def _restart_retryable_network_task(self, task: Task) -> None:
        error_message = str(task.error_message or "")
        try:
            logger.warning(
                "watchdog detected retryable network error task: task_id=%s, error=%s",
                task.id,
                error_message,
            )
            result = task_manager.restart_task(task.id, resume_from_checkpoint=True)
            logger.warning(
                "watchdog network restart result: task_id=%s, result=%s",
                task.id,
                result,
            )
        except Exception as restart_error:
            logger.error(
                "watchdog network restart error: task_id=%s, err=%s",
                task.id,
                str(restart_error),
                exc_info=True,
            )

    def _has_task_exceeded_log_timeout(
        self,
        task: Task,
        latest_log: TaskLog | None,
        log_timeout_minutes: int,
        now: datetime,
    ) -> tuple[bool, str | None]:
        if latest_log:
            minutes_since_last_log = (now - latest_log.timestamp).total_seconds() / 60
            if minutes_since_last_log > log_timeout_minutes:
                logger.warning(
                    "watchdog detected task with no log updates: task_id=%s, "
                    "last_log_time=%s, minutes_since_last_log=%.2f",
                    task.id,
                    latest_log.timestamp,
                    minutes_since_last_log,
                )
                return True, "log_timeout"
            return False, None

        if task.start_time:
            minutes_since_start = (now - task.start_time).total_seconds() / 60
            if minutes_since_start > log_timeout_minutes:
                logger.warning(
                    "watchdog detected running task with no logs: task_id=%s, "
                    "start_time=%s, minutes_since_start=%.2f",
                    task.id,
                    task.start_time,
                    minutes_since_start,
                )
                return True, "missing_initial_log"
        return False, None

    def _process_watched_task(self, task: Task, log_timeout_minutes: int) -> None:
        if task.status == 'error':
            self._restart_retryable_network_task(task)
            return

        latest_log = (
            TaskLog.query.filter_by(task_id=task.id)
            .order_by(TaskLog.timestamp.desc())
            .first()
        )
        should_restart, reason = self._has_task_exceeded_log_timeout(
            task,
            latest_log,
            log_timeout_minutes,
            datetime.now(),
        )
        if should_restart and reason:
            self._restart_task_with_reason(task.id, reason)

    def _run(self, app):
        last_logged_config = None

        while not self._stop_event.is_set():
            try:
                config_snapshot = self._load_runtime_config(app)
                enabled, _, log_timeout_minutes, effective_sleep_seconds = config_snapshot
                last_logged_config = self._log_config_snapshot(
                    last_logged_config,
                    config_snapshot,
                )

                if not enabled:
                    time.sleep(effective_sleep_seconds)
                    continue

                with app.app_context():
                    from app.models import Task as TaskModel
                    created_cutoff = datetime.now() - timedelta(days=5)
                    watched_tasks = TaskModel.query.filter(
                        TaskModel.created_at >= created_cutoff,
                        or_(
                            TaskModel.status == 'running',
                            and_(
                                TaskModel.status == 'error',
                                TaskModel.error_message.isnot(None),
                                TaskModel.error_message.startswith(NETWORK_ERROR_PREFIX)
                            )
                        )
                    ).all()

                    for task in watched_tasks:
                        if self._stop_event.is_set():
                            break
                        self._process_watched_task(task, log_timeout_minutes)

                time.sleep(effective_sleep_seconds)

            except Exception as e:
                logger.error(f"watchdog loop error: {str(e)}", exc_info=True)
                time.sleep(5)


task_watchdog = TaskWatchdog()

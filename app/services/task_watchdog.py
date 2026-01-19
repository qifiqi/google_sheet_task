import threading
import time
from datetime import datetime

from app.models import Task
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

                if not enabled:
                    time.sleep(max(interval_seconds, 1))
                    continue

                with app.app_context():
                    running_tasks = Task.query.filter_by(status='running').all()

                    for task in running_tasks:
                        if self._stop_event.is_set():
                            break

                        status_check = task_manager.check_local_task_status(task.id)
                        if status_check.get('can_restart'):
                            reason = status_check.get('restart_reason')
                            logger.warning(f"watchdog detected stuck task: {task.id}, reason: {reason}")
                            result = task_manager.restart_task(task.id, resume_from_checkpoint=True)
                            logger.warning(f"watchdog restart result: {task.id}, {result}")

                time.sleep(max(interval_seconds, 1))

            except Exception as e:
                logger.error(f"watchdog loop error: {str(e)}")
                time.sleep(5)


task_watchdog = TaskWatchdog()

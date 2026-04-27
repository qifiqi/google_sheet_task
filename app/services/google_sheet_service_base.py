from datetime import datetime
from typing import Any, Dict

from flask import current_app

from app.models import Task, TaskLog, db
from app.utils.db_retry import safe_db_operation
from app.utils.logger import get_logger


logger = get_logger(__name__)


def should_alert_execute_task_result(result):
    return result == 'error'


def build_execute_task_alert(target, func_name, phase, exc, result):
    if exc is not None:
        return f"{func_name} 执行异常: {type(exc).__name__}: {exc}"

    task = getattr(target, 'task', None)
    task_error = getattr(task, 'error', None)
    if task_error:
        return f"{func_name} 返回失败状态: {result}, 错误信息: {task_error}"
    return f"{func_name} 返回失败状态: {result}"


class BaseGoogleSheetService:
    def __init__(self, config: Dict[str, Any], task_id: str, app=None, stop_event=None):
        self.config = config
        self.task_id = task_id
        self.app = app
        self.stop_event = stop_event
        self.task_name = ''
        self.task = None
        self.task_logger = get_logger(f"{self.__module__}.{task_id}")

    def _is_cancel_requested(self) -> bool:
        if self.stop_event and self.stop_event.is_set():
            return True
        try:
            task = Task.query.get(self.task_id)
            return bool(task and task.status == 'cancelled')
        except Exception:
            return False

    def _interruptible_sleep(self, seconds: float) -> bool:
        if seconds <= 0:
            return not self._is_cancel_requested()
        if self.stop_event:
            return not self.stop_event.wait(seconds)
        import time
        time.sleep(seconds)
        return not self._is_cancel_requested()

    def _task_display_name(self) -> str:
        return self.task_name or self.task_id

    def _task_detail_url(self) -> str:
        return f"{current_app.config.get('BASE_URL')}/google-sheet/detail?task_id={self.task_id}"

    def error_dd(self, error_msg):
        result = self.app.notifier.send_task_notification(
            self.task_id,
            notify_type="error",
            summary=error_msg,
            detail_url=self._task_detail_url(),
        )
        return result

    def task_ok_to_dd(self, result):
        payload_result = self.app.notifier.send_task_notification(
            self.task_id,
            notify_type="success",
            summary=result,
            detail_url=self._task_detail_url(),
        )
        return payload_result

    def _log(self, level: str, message: str, log_type: str = 'general', **kwargs):
        try:
            formatted_message = self._format_log_message(message, log_type, **kwargs)
            prefixed_message = f"[Task-{self.task_id[:8]}] {formatted_message}"

            if level == 'error':
                self.task_logger.error(prefixed_message)
            elif level == 'warning':
                self.task_logger.warning(prefixed_message)
            else:
                self.task_logger.info(prefixed_message)

            self._save_to_database(level, formatted_message)
        except Exception:
            pass

    def _format_log_message(self, message: str, log_type: str, **kwargs) -> str:
        if log_type == 'step':
            step = kwargs.get('step', 0)
            total = kwargs.get('total', 0)
            return f"[Step {step}/{total}] {message}"
        if log_type == 'progress':
            percentage = kwargs.get('percentage', 0)
            return f"[Progress {percentage:.1f}%] {message}"
        if log_type == 'api':
            action = kwargs.get('action', '')
            details = kwargs.get('details', '')
            base_msg = f"[API] {action}"
            return f"{base_msg} - {details}" if details else base_msg
        if log_type == 'api_error':
            action = kwargs.get('action', '')
            error = kwargs.get('error', '')
            return f"[API_ERROR] {action} - {error}"
        return message

    def _save_to_database(self, level: str, message: str):
        def save_log_operation():
            log = TaskLog(task_id=self.task_id, level=level, message=message)
            db.session.add(log)
            db.session.commit()

        try:
            if self.app:
                with self.app.app_context():
                    safe_db_operation(save_log_operation)
            else:
                with current_app.app_context():
                    safe_db_operation(save_log_operation)
        except Exception:
            pass

    def _log_info(self, message: str, log_type: str = 'general', **kwargs):
        self._log('info', message, log_type, **kwargs)

    def _log_warning(self, message: str, log_type: str = 'general', **kwargs):
        self._log('warning', message, log_type, **kwargs)

    def _log_error(self, message: str, log_type: str = 'general', **kwargs):
        self._log('error', message, log_type, **kwargs)

    def _log_step(self, step: int, total: int, message: str):
        self._log('info', message, 'step', step=step, total=total)

    def _log_progress(self, percentage: float, message: str):
        self._log('info', message, 'progress', percentage=percentage)

    def _log_api(self, action: str, details: str = ''):
        self._log('info', '', 'api', action=action, details=details)

    def _log_api_error(self, action: str, error: str):
        self._log('error', '', 'api_error', action=action, error=error)

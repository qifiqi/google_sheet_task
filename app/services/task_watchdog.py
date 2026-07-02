"""任务挂死检测与强制重启看门狗。

逻辑要点:

- 周期扫描最近 ``WATCHED_TASK_CREATED_WITHIN_DAYS`` 天的任务，只关注三类:
    1. ``status == 'running'`` 但日志静默超过阈值 (真正的挂死目标);
    2. ``status == 'error'`` 的异常任务;
    3. ``status == 'cancelled'`` 且带 ``[WATCHDOG_FORCE_RESTART]`` 前缀
       (上一轮 watchdog 强制重启失败的兜底)。
- 强制重启绕开 ``cancel_task`` / ``restart_task`` 的状态机短路, 直接 evict
  挂死线程引用、释放占用、置 pending 再调 ``start_task``。
- 通过把 ``attempt=N/MAX`` 写入 ``error_message``, 防止失败任务被无限重启。
- 对已经落成 ``error`` 的异常，使用 watchdog 本地缓存记录重启次数。
"""

from __future__ import annotations

import logging
import logging.handlers
import re
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from flask import has_app_context
from sqlalchemy import and_, inspect, not_, or_

from app.config import Config
from app.extensions import db
from app.models import Task, TaskLog
from app.services.config_manager import get_config_manager
from app.services.task import task_manager
from app.utils.task_error_utils import (
    GOOGLE_SHEET_EXECUTION_ERROR_PREFIX,
    NETWORK_ERROR_PREFIX,
    WATCHDOG_RESTART_PREFIX,
)


def _get_watchdog_logger() -> logging.Logger:
    logger = logging.getLogger("task_watchdog")
    if logger.handlers:
        return logger

    logger.setLevel(getattr(logging, Config.LOG_LEVEL.upper(), logging.INFO))
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    log_path = Path(Config.LOGS_DIR) / "task_watchdog.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)

    file_handler = logging.handlers.RotatingFileHandler(
        filename=log_path,
        mode="a",
        maxBytes=10 * 1024 * 1024,
        backupCount=10,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    logger.propagate = False
    return logger


logger = _get_watchdog_logger()

REASON_LOG_TIMEOUT = "log_timeout"
REASON_MISSING_INITIAL_LOG = "missing_initial_log"
REASON_PREVIOUS_RESTART_FAILED = "previous_watchdog_force_restart_failed"
REASON_RETRYABLE_NETWORK_ERROR = "retryable_network_error"
REASON_RETRYABLE_GOOGLE_SHEET_EXECUTION_ERROR = "retryable_google_sheet_execution_error"
REASON_TASK_ERROR = "task_error"

WATCHED_TASK_CREATED_WITHIN_DAYS = 5
DEFAULT_INTERVAL_SECONDS = 60
DEFAULT_LOG_TIMEOUT_MINUTES = 30
DEFAULT_FORCE_RESTART_WAIT_SECONDS = 45
DEFAULT_MAX_RESTART_ATTEMPTS = 3
MIN_SLEEP_SECONDS = 5
THREAD_JOIN_POLL_SECONDS = 2.0
WATCHDOG_ABANDON_PREFIX = "watchdog 已放弃自动重启"

_ATTEMPT_PATTERN = re.compile(r"attempt=(\d+)/\d+")


@dataclass(frozen=True)
class _WatchdogConfig:
    enabled: bool
    interval_seconds: int
    log_timeout_minutes: int
    force_restart_wait_seconds: int
    max_restart_attempts: int

    @property
    def effective_sleep_seconds(self) -> int:
        return max(self.interval_seconds, MIN_SLEEP_SECONDS)


class TaskWatchdog:
    def __init__(self):
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._lock = threading.Lock()
        self._retry_restart_attempts: dict[str, int] = {}
        self._retry_restart_lock = threading.Lock()

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

    def _load_runtime_config(self, app) -> _WatchdogConfig:
        return _WatchdogConfig(
            enabled=bool(self._get_config(app, "watchdog_enabled", True)),
            interval_seconds=int(
                self._get_config(
                    app, "watchdog_interval_seconds", DEFAULT_INTERVAL_SECONDS
                )
            ),
            log_timeout_minutes=int(
                self._get_config(
                    app,
                    "watchdog_log_timeout_minutes",
                    DEFAULT_LOG_TIMEOUT_MINUTES,
                )
            ),
            force_restart_wait_seconds=max(
                int(
                    self._get_config(
                        app,
                        "watchdog_force_restart_wait_seconds",
                        DEFAULT_FORCE_RESTART_WAIT_SECONDS,
                    )
                ),
                0,
            ),
            max_restart_attempts=max(
                int(
                    self._get_config(
                        app,
                        "watchdog_max_restart_attempts",
                        DEFAULT_MAX_RESTART_ATTEMPTS,
                    )
                ),
                1,
            ),
        )

    def _log_config_snapshot(
        self,
        last_logged_config: _WatchdogConfig | None,
        config: _WatchdogConfig,
    ) -> _WatchdogConfig:
        if config != last_logged_config:
            logger.info(
                "watchdog config applied: enabled=%s, interval_seconds=%s, "
                "log_timeout_minutes=%s, effective_sleep_seconds=%s, "
                "force_restart_wait_seconds=%s, max_restart_attempts=%s",
                config.enabled,
                config.interval_seconds,
                config.log_timeout_minutes,
                config.effective_sleep_seconds,
                config.force_restart_wait_seconds,
                config.max_restart_attempts,
            )
            return config
        return last_logged_config

    def _wait_for_task_thread_stop(self, task_id: str, wait_seconds: int) -> bool:
        """轮询等待挂死线程退出，期间响应 watchdog 自身的 stop_event。"""
        thread = task_manager.running_tasks.get(task_id)
        if not thread or not thread.is_alive():
            return True

        deadline = time.monotonic() + max(wait_seconds, 0)
        while True:
            if self._stop_event.is_set():
                break
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            thread.join(timeout=min(THREAD_JOIN_POLL_SECONDS, remaining))
            if not thread.is_alive():
                break

        return not thread.is_alive()

    def _read_prior_attempt_count(self, error_message: str | None) -> int:
        match = _ATTEMPT_PATTERN.search(str(error_message or ""))
        return int(match.group(1)) if match else 0

    def _abandon_task(
        self,
        task_id: str,
        reason: str,
        attempts: int,
        last_error: str,
    ) -> None:
        """重启次数耗尽: 把任务彻底标成 error 退出自动重试循环。"""
        task = db.session.get(Task, task_id)
        if task:
            task.status = "error"
            task.error_message = (
                f"{WATCHDOG_ABANDON_PREFIX} (尝试 {attempts} 次, reason={reason}): "
                f"{last_error}"
            )
            task.end_time = datetime.now()
            db.session.commit()
        message = (
            f"watchdog 已停止自动重启 (达到上限 {attempts} 次, reason={reason}), "
            "等待人工介入"
        )
        logger.error(
            "watchdog abandoning task after %s failed restarts: task_id=%s, "
            "reason=%s, last_error=%s",
            attempts,
            task_id,
            reason,
            last_error,
        )
        task_manager.add_task_log(task_id, "error", message)
        self._clear_cached_retry_attempts(task_id)

    def _read_cached_retry_attempts(self, task_id: str) -> int:
        with self._retry_restart_lock:
            return self._retry_restart_attempts.get(task_id, 0)

    def _increment_cached_retry_attempts(self, task_id: str) -> int:
        with self._retry_restart_lock:
            attempt = self._retry_restart_attempts.get(task_id, 0) + 1
            self._retry_restart_attempts[task_id] = attempt
            return attempt

    def _set_cached_retry_attempts(self, task_id: str, attempts: int) -> None:
        with self._retry_restart_lock:
            self._retry_restart_attempts[task_id] = max(attempts, 0)

    def _clear_cached_retry_attempts(self, task_id: str) -> None:
        with self._retry_restart_lock:
            self._retry_restart_attempts.pop(task_id, None)

    def _next_restart_attempt(
        self,
        task_id: str,
        max_attempts: int,
        *,
        persisted_attempts: int = 0,
    ) -> tuple[int | None, int]:
        prior_attempts = max(
            self._read_cached_retry_attempts(task_id),
            persisted_attempts,
        )
        if prior_attempts >= max_attempts:
            return None, prior_attempts

        attempt = prior_attempts + 1
        self._set_cached_retry_attempts(task_id, attempt)
        return attempt, prior_attempts

    def _prepare_task_for_force_restart(
        self, task_id: str, reason: str
    ) -> Task | None:
        task = db.session.get(Task, task_id)
        if not task:
            logger.warning("watchdog force restart skipped, task missing: %s", task_id)
            return None

        task_manager.release_backtest_sheet_locks(task_id)
        task_manager.release_task_token_occupancy(task_id)
        task_manager.release_google_sheet_occupancy(task_id)

        task.status = "pending"
        task.error_message = None
        task.end_time = None
        db.session.commit()

        task_manager.add_task_log(
            task_id,
            "warning",
            f"watchdog 已释放任务占用并重置状态, 准备重新启动: {reason}",
        )
        return task

    def _mark_force_restart_failed(
        self,
        task_id: str,
        reason: str,
        attempt: int,
        max_attempts: int,
        message: str,
    ) -> None:
        task = db.session.get(Task, task_id)
        if task:
            task.status = "cancelled"
            task.error_message = (
                f"{WATCHDOG_RESTART_PREFIX} attempt={attempt}/{max_attempts} "
                f"reason={reason}: {message}"
            )
            task.end_time = datetime.now()
            db.session.commit()
        task_manager.add_task_log(task_id, "error", message)

    def _restart_task_with_reason(
        self,
        task_id: str,
        reason: str,
        wait_seconds: int = DEFAULT_FORCE_RESTART_WAIT_SECONDS,
        max_attempts: int = DEFAULT_MAX_RESTART_ATTEMPTS,
    ) -> None:
        if not has_app_context():
            task_manager.cancel_task(task_id)
            task_manager.restart_task(task_id, resume_from_checkpoint=True)
            return

        try:
            task = db.session.get(Task, task_id)
            if not task:
                return
            attempt, prior_attempts = self._next_restart_attempt(
                task_id,
                max_attempts,
                persisted_attempts=self._read_prior_attempt_count(task.error_message),
            )
            if attempt is None:
                self._abandon_task(
                    task_id,
                    reason,
                    attempts=prior_attempts,
                    last_error=str(task.error_message or ""),
                )
                return

            logger.warning(
                "watchdog force restarting task: task_id=%s, reason=%s, "
                "attempt=%s/%s, wait_seconds=%s",
                task_id,
                reason,
                attempt,
                max_attempts,
                wait_seconds,
            )
            task_manager.add_task_log(
                task_id,
                "warning",
                f"watchdog 检测到任务挂死, 准备停止原任务线程 "
                f"(尝试 {attempt}/{max_attempts}): {reason}",
            )

            stop_event = task_manager.task_stop_events.get(task_id)
            if stop_event:
                stop_event.set()

            stopped = self._wait_for_task_thread_stop(task_id, wait_seconds)
            if stopped:
                task_manager.running_tasks.pop(task_id, None)
                task_manager.add_task_log(
                    task_id,
                    "warning",
                    f"watchdog 已停止原任务线程: {reason}",
                )
            else:
                stale_thread = task_manager.running_tasks.pop(task_id, None)
                logger.warning(
                    "watchdog detached hung task thread: task_id=%s, thread=%s",
                    task_id,
                    stale_thread,
                )
                task_manager.add_task_log(
                    task_id,
                    "warning",
                    f"watchdog 等待 {wait_seconds}s 后原任务线程仍未退出, "
                    f"已强制 detach: {reason}",
                )
            task_manager.task_stop_events.pop(task_id, None)

            task = self._prepare_task_for_force_restart(task_id, reason)
            if not task:
                return

            success = task_manager.start_task(task_id)
            if success:
                task_manager.add_task_log(
                    task_id,
                    "info",
                    f"watchdog 已触发任务重启 "
                    f"(从第 {task.current_step} 步继续, 尝试 {attempt}/{max_attempts}): "
                    f"{reason}",
                )
                logger.warning(
                    "watchdog force restart success: task_id=%s, reason=%s, "
                    "attempt=%s/%s, restart_from_step=%s",
                    task_id,
                    reason,
                    attempt,
                    max_attempts,
                    task.current_step,
                )
            else:
                start_error = task_manager.get_start_error(task_id)
                self._mark_force_restart_failed(
                    task_id,
                    reason,
                    attempt,
                    max_attempts,
                    f"watchdog force restart failed: {start_error}",
                )
                logger.warning(
                    "watchdog force restart failed: task_id=%s, reason=%s, "
                    "attempt=%s/%s, start_error=%s",
                    task_id,
                    reason,
                    attempt,
                    max_attempts,
                    start_error,
                )
        except Exception as restart_error:
            db.session.rollback()
            logger.error(
                "watchdog force restart error: task_id=%s, reason=%s, err=%s",
                task_id,
                reason,
                str(restart_error),
                exc_info=True,
            )

    def _classify_error_restart_reason(self, error_message: str) -> str:
        if error_message.startswith(NETWORK_ERROR_PREFIX):
            return REASON_RETRYABLE_NETWORK_ERROR
        if error_message.startswith(
            (GOOGLE_SHEET_EXECUTION_ERROR_PREFIX, "[C3_RETRYABLE]")
        ):
            return REASON_RETRYABLE_GOOGLE_SHEET_EXECUTION_ERROR
        return REASON_TASK_ERROR

    def _prefix_for_restart_failure_reason(self, reason: str) -> str:
        if reason == REASON_RETRYABLE_NETWORK_ERROR:
            return NETWORK_ERROR_PREFIX
        if reason == REASON_RETRYABLE_GOOGLE_SHEET_EXECUTION_ERROR:
            return GOOGLE_SHEET_EXECUTION_ERROR_PREFIX
        return WATCHDOG_RESTART_PREFIX

    def _mark_error_restart_failed(
        self,
        task_id: str,
        reason: str,
        attempt: int,
        max_attempts: int,
        original_error: str,
        message: str,
    ) -> None:
        task = db.session.get(Task, task_id)
        prefix = self._prefix_for_restart_failure_reason(reason)
        if task:
            task.status = "error"
            task.error_message = (
                f"{prefix} watchdog_restart_failed attempt={attempt}/{max_attempts} "
                f"reason={reason}: {message}; original_error={original_error}"
            )
            task.end_time = datetime.now()
            db.session.commit()
        task_manager.add_task_log(task_id, "error", message)

    def _restart_error_task(
        self,
        task: Task,
        reason: str,
        max_attempts: int,
    ) -> None:
        inspected = inspect(task)
        task_id = inspected.identity[0] if inspected.identity else task.id
        current_task = db.session.get(Task, task_id)
        if not current_task:
            logger.warning("watchdog error restart skipped, task missing: %s", task_id)
            return

        error_message = str(current_task.error_message or "")
        persisted_attempts = self._read_prior_attempt_count(error_message)
        attempt, prior_attempts = self._next_restart_attempt(
            task_id,
            max_attempts,
            persisted_attempts=persisted_attempts,
        )
        if attempt is None:
            self._abandon_task(
                task_id,
                reason,
                attempts=prior_attempts,
                last_error=error_message,
            )
            return

        try:
            logger.warning(
                "watchdog detected error task: task_id=%s, "
                "reason=%s, attempt=%s/%s, error=%s",
                task_id,
                reason,
                attempt,
                max_attempts,
                error_message,
            )
            task_manager.add_task_log(
                task_id,
                "warning",
                f"watchdog 检测到异常任务，准备自动断点重启 "
                f"(尝试 {attempt}/{max_attempts}, reason={reason})",
            )
            result = task_manager.restart_task(task_id, resume_from_checkpoint=True)
            logger.warning(
                "watchdog error restart result: task_id=%s, "
                "reason=%s, attempt=%s/%s, result=%s",
                task_id,
                reason,
                attempt,
                max_attempts,
                result,
            )
            if result.get("status") != "success":
                self._mark_error_restart_failed(
                    task_id,
                    reason,
                    attempt,
                    max_attempts,
                    error_message,
                    f"watchdog 自动重启失败 "
                    f"(尝试 {attempt}/{max_attempts}, reason={reason}): "
                    f"{result.get('message') or result}",
                )
        except Exception as restart_error:
            db.session.rollback()
            logger.error(
                "watchdog error restart error: task_id=%s, "
                "reason=%s, err=%s",
                task_id,
                reason,
                str(restart_error),
                exc_info=True,
            )
            self._mark_error_restart_failed(
                task_id,
                reason,
                attempt,
                max_attempts,
                error_message,
                f"watchdog 自动重启异常 "
                f"(尝试 {attempt}/{max_attempts}, reason={reason}): {restart_error}",
            )

    def _restart_retryable_error_task(
        self,
        task: Task,
        reason: str,
        max_attempts: int,
    ) -> None:
        self._restart_error_task(task, reason, max_attempts)

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
                return True, REASON_LOG_TIMEOUT
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
                return True, REASON_MISSING_INITIAL_LOG
        return False, None

    def _process_watched_task(self, task: Task, config: _WatchdogConfig) -> None:
        error_message = str(task.error_message or "")

        if task.status == "cancelled":
            # 防御性兜底: 即使 SQL filter 之外的代码路径把任务带进来,
            # 也只处理 watchdog 自己留下的标记任务。
            if not error_message.startswith(WATCHDOG_RESTART_PREFIX):
                logger.warning(
                    "watchdog skipping non-watchdog cancelled task: task_id=%s, "
                    "error_message=%s",
                    task.id,
                    error_message,
                )
                return
            logger.warning(
                "watchdog retrying previously failed force restart: task_id=%s, "
                "error=%s",
                task.id,
                error_message,
            )
            self._restart_task_with_reason(
                task.id,
                REASON_PREVIOUS_RESTART_FAILED,
                config.force_restart_wait_seconds,
                config.max_restart_attempts,
            )
            return

        if task.status == "error":
            if error_message.startswith(WATCHDOG_ABANDON_PREFIX):
                logger.warning(
                    "watchdog skipping abandoned error task: task_id=%s, "
                    "error_message=%s",
                    task.id,
                    error_message,
                )
                return
            reason = self._classify_error_restart_reason(error_message)
            self._restart_error_task(
                task,
                reason,
                config.max_restart_attempts,
            )
            return

        latest_log = (
            TaskLog.query.filter_by(task_id=task.id)
            .order_by(TaskLog.timestamp.desc())
            .first()
        )
        should_restart, reason = self._has_task_exceeded_log_timeout(
            task,
            latest_log,
            config.log_timeout_minutes,
            datetime.now(),
        )
        if should_restart and reason:
            self._restart_task_with_reason(
                task.id,
                reason,
                config.force_restart_wait_seconds,
                config.max_restart_attempts,
            )

    def _fetch_watched_tasks(self) -> list[Task]:
        created_cutoff = datetime.now() - timedelta(
            days=WATCHED_TASK_CREATED_WITHIN_DAYS
        )
        return Task.query.filter(
            Task.created_at >= created_cutoff,
            or_(
                Task.status == "running",
                and_(
                    Task.status == "error",
                    or_(
                        Task.error_message.is_(None),
                        not_(Task.error_message.startswith(WATCHDOG_ABANDON_PREFIX)),
                    ),
                ),
                and_(
                    Task.status == "cancelled",
                    Task.error_message.isnot(None),
                    Task.error_message.startswith(WATCHDOG_RESTART_PREFIX),
                ),
            ),
        ).all()

    def _prune_retry_attempt_cache(self) -> None:
        created_cutoff = datetime.now() - timedelta(
            days=WATCHED_TASK_CREATED_WITHIN_DAYS
        )
        active_ids = {
            task_id
            for (task_id,) in db.session.query(Task.id)
            .filter(
                Task.created_at >= created_cutoff,
                Task.status.in_(["pending", "running", "error", "cancelled"]),
            )
            .all()
        }
        with self._retry_restart_lock:
            stale_ids = set(self._retry_restart_attempts) - active_ids
            for task_id in stale_ids:
                self._retry_restart_attempts.pop(task_id, None)

    def _run(self, app):
        last_logged_config: _WatchdogConfig | None = None

        while not self._stop_event.is_set():
            try:
                config = self._load_runtime_config(app)
                last_logged_config = self._log_config_snapshot(
                    last_logged_config, config
                )

                if not config.enabled:
                    time.sleep(config.effective_sleep_seconds)
                    continue

                with app.app_context():
                    for task in self._fetch_watched_tasks():
                        if self._stop_event.is_set():
                            break
                        self._process_watched_task(task, config)
                    self._prune_retry_attempt_cache()

                time.sleep(config.effective_sleep_seconds)

            except Exception as exc:
                logger.error("watchdog loop error: %s", exc, exc_info=True)
                time.sleep(MIN_SLEEP_SECONDS)


task_watchdog = TaskWatchdog()

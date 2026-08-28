from __future__ import annotations

from datetime import datetime

from app.extensions import db
from app.models import Task, TaskLog
from app.services.task_watchdog import (
    DEFAULT_MAX_RESTART_ATTEMPTS,
    REASON_RETRYABLE_GOOGLE_SHEET_EXECUTION_ERROR,
    task_watchdog,
)
from app.utils.task_error_utils import GOOGLE_SHEET_EXECUTION_ERROR_PREFIX


def _create_retryable_google_sheet_task(task_id: str = "sheet-retryable-task") -> Task:
    task = Task(
        id=task_id,
        name="sheet retryable task",
        status="error",
        task_type="google_sheet_C4",
        config="{}",
        current_step=515,
        total_steps=600,
        error_message=(
            f"{GOOGLE_SHEET_EXECUTION_ERROR_PREFIX} RuntimeError: "
            "执行超时，未在规定时间内完成"
        ),
        created_at=datetime.now(),
    )
    db.session.add(task)
    db.session.commit()
    return task


def test_watchdog_limits_retryable_google_sheet_restarts(app_factory, monkeypatch):
    with app_factory.app_context():
        task = _create_retryable_google_sheet_task()
        task_id = task.id
        restart_calls = []

        def fake_restart(task_id, resume_from_checkpoint=True):
            restart_calls.append((task_id, resume_from_checkpoint))
            return {
                "status": "success",
                "message": "任务重启成功",
                "restart_from_step": 515,
            }

        monkeypatch.setattr(
            "app.services.task_watchdog.task_manager.restart_task",
            fake_restart,
        )
        task_watchdog._clear_cached_retry_attempts(task_id)

        for _ in range(DEFAULT_MAX_RESTART_ATTEMPTS):
            task_watchdog._restart_retryable_error_task(
                task,
                REASON_RETRYABLE_GOOGLE_SHEET_EXECUTION_ERROR,
                DEFAULT_MAX_RESTART_ATTEMPTS,
            )

        assert len(restart_calls) == DEFAULT_MAX_RESTART_ATTEMPTS

        task_watchdog._restart_retryable_error_task(
            task,
            REASON_RETRYABLE_GOOGLE_SHEET_EXECUTION_ERROR,
            DEFAULT_MAX_RESTART_ATTEMPTS,
        )

        assert len(restart_calls) == DEFAULT_MAX_RESTART_ATTEMPTS
        refreshed = db.session.get(Task, task_id)
        assert refreshed.status == "error"
        assert "watchdog 已放弃自动重启" in refreshed.error_message

        abandon_log = (
            TaskLog.query.filter_by(task_id=task_id, level="error")
            .order_by(TaskLog.timestamp.desc())
            .first()
        )
        assert abandon_log is not None
        assert "达到上限 3 次" in abandon_log.message

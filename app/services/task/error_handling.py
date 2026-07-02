"""Shared task exception recording helpers."""

from __future__ import annotations

import logging
import re
import traceback
import uuid
from dataclasses import dataclass
from datetime import datetime

from flask import current_app, has_app_context

from app.extensions import db
from app.models import Task, TaskLog
from app.utils.task_error_utils import unwrap_exception

logger = logging.getLogger(__name__)

TASK_ERROR_MESSAGE_MAX_LENGTH = 500
_TASK_ERROR_RECORD_ATTR = "_task_error_record"
_TASK_ERROR_LOGGED_ATTR = "_task_error_logged"


@dataclass(frozen=True)
class TaskErrorRecord:
    trace_id: str
    task_id: str
    phase: str
    exception_type: str
    message: str
    traceback_text: str


def _normalize_error_message(message: str) -> str:
    normalized = re.sub(r"\s+", " ", str(message or "")).strip()
    if len(normalized) <= TASK_ERROR_MESSAGE_MAX_LENGTH:
        return normalized
    return f"{normalized[:TASK_ERROR_MESSAGE_MAX_LENGTH - 3]}..."


def _get_attached_error_record(exc: BaseException) -> TaskErrorRecord | None:
    record = getattr(exc, _TASK_ERROR_RECORD_ATTR, None)
    return record if isinstance(record, TaskErrorRecord) else None


def _attach_error_record(exc: BaseException, record: TaskErrorRecord) -> None:
    try:
        setattr(exc, _TASK_ERROR_RECORD_ATTR, record)
    except Exception:
        pass


def _is_record_logged(exc: BaseException) -> bool:
    return bool(getattr(exc, _TASK_ERROR_LOGGED_ATTR, False))


def _mark_record_logged(exc: BaseException) -> None:
    try:
        setattr(exc, _TASK_ERROR_LOGGED_ATTR, True)
    except Exception:
        pass


def build_task_error_record(exc: BaseException, phase: str, task_id: str) -> TaskErrorRecord:
    existing_record = _get_attached_error_record(exc)
    if existing_record is not None:
        return existing_record

    root = unwrap_exception(exc) or exc
    record = TaskErrorRecord(
        trace_id=uuid.uuid4().hex[:12],
        task_id=task_id,
        phase=phase,
        exception_type=root.__class__.__name__,
        message=_normalize_error_message(str(root)),
        traceback_text="".join(traceback.format_exception(type(exc), exc, exc.__traceback__)),
    )
    _attach_error_record(exc, record)
    return record


def format_task_error_message(record: TaskErrorRecord) -> str:
    return f"trace_id={record.trace_id} {record.exception_type}: {record.message}"


def format_task_error_log(record: TaskErrorRecord) -> str:
    return (
        f"任务异常 trace_id={record.trace_id} phase={record.phase} "
        f"{record.exception_type}: {record.message}\n{record.traceback_text}"
    )


def record_task_exception(
    task_id: str,
    exc: BaseException,
    phase: str,
    app=None,
    *,
    mark_error: bool = True,
) -> TaskErrorRecord:
    record = build_task_error_record(exc, phase, task_id)
    error_message = format_task_error_message(record)
    log_message = format_task_error_log(record)
    should_write_log = not _is_record_logged(exc)

    def write_record() -> None:
        task = db.session.get(Task, task_id)
        if task and mark_error:
            task.status = "error"
            task.error_message = error_message
            task.end_time = datetime.now()
        if should_write_log:
            db.session.add(TaskLog(task_id=task_id, level="error", message=log_message))
        db.session.commit()
        if should_write_log:
            _mark_record_logged(exc)

    try:
        if has_app_context():
            write_record()
        elif app is not None:
            with app.app_context():
                write_record()
        else:
            with current_app.app_context():
                write_record()
    except Exception:
        try:
            db.session.rollback()
        except Exception:
            pass
        logger.exception(
            "记录任务异常失败: task_id=%s phase=%s trace_id=%s",
            task_id,
            phase,
            record.trace_id,
        )

    logger.error(log_message)
    return record

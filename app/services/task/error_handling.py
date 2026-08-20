"""任务异常记录的共享工具。"""

from __future__ import annotations

import logging
import re
import traceback
import uuid
from dataclasses import dataclass
from datetime import datetime

from flask import current_app, has_app_context

from app.repositories.task_log_repository import TaskLogRepository
from app.repositories.task_repository import TaskRepository
from app.utils.task_error_utils import (
    NETWORK_ERROR_PREFIX,
    is_retryable_network_error,
    unwrap_exception,
)

logger = logging.getLogger(__name__)
_task_repository = TaskRepository()
_task_log_repository = TaskLogRepository()

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
    """压缩异常摘要空白字符并限制写入任务字段的长度。"""
    normalized = re.sub(r"\s+", " ", str(message or "")).strip()
    if len(normalized) <= TASK_ERROR_MESSAGE_MAX_LENGTH:
        return normalized
    return f"{normalized[:TASK_ERROR_MESSAGE_MAX_LENGTH - 3]}..."


def _get_attached_error_record(exc: BaseException) -> TaskErrorRecord | None:
    """读取已附着在异常对象上的任务错误追踪记录。"""
    record = getattr(exc, _TASK_ERROR_RECORD_ATTR, None)
    return record if isinstance(record, TaskErrorRecord) else None


def _attach_error_record(exc: BaseException, record: TaskErrorRecord) -> None:
    """将任务错误追踪记录附着到异常对象，避免跨层重复创建。"""
    try:
        setattr(exc, _TASK_ERROR_RECORD_ATTR, record)
    except Exception:
        pass


def _is_record_logged(exc: BaseException) -> bool:
    """判断该异常是否已写入任务错误日志。"""
    return bool(getattr(exc, _TASK_ERROR_LOGGED_ATTR, False))


def _mark_record_logged(exc: BaseException) -> None:
    """标记该异常已完成任务错误日志写入。"""
    try:
        setattr(exc, _TASK_ERROR_LOGGED_ATTR, True)
    except Exception:
        pass


def build_task_error_record(exc: BaseException, phase: str, task_id: str) -> TaskErrorRecord:
    """为同一异常创建可复用的追踪记录，防止跨层重复生成追踪号。"""
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
    """生成可安全写入任务状态字段的简短异常摘要。"""
    return f"trace_id={record.trace_id} {record.exception_type}: {record.message}"


def format_task_error_log(record: TaskErrorRecord) -> str:
    """生成包含执行阶段和调用栈的内部诊断日志内容。"""
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
    """持久化任务异常状态和日志，并保留原异常对应的唯一追踪号。"""
    record = build_task_error_record(exc, phase, task_id)
    error_message = format_task_error_message(record)
    if is_retryable_network_error(exc):
        error_message = f"{NETWORK_ERROR_PREFIX} {error_message}"
    log_message = format_task_error_log(record)
    should_write_log = not _is_record_logged(exc)

    def write_record() -> None:
        """在已建立的应用上下文内完成远端状态与日志写入。"""
        task = _task_repository.get(task_id)
        if task and mark_error:
            _task_repository.save({
                **task,
                "status": "error",
                "error_message": error_message,
                "end_time": datetime.now(),
            })
        if should_write_log:
            _task_log_repository.save({"task_id": task_id, "level": "error", "message": log_message})
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
        # 远端调用没有可回滚的本地会话；保留异常日志用于后续恢复。
        logger.exception(
            "记录任务异常失败: task_id=%s phase=%s trace_id=%s",
            task_id,
            phase,
            record.trace_id,
        )

    logger.error(log_message)
    return record

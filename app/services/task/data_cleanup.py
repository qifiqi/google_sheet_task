"""显式清理任务关联数据，避免依赖数据库外键级联。"""

from __future__ import annotations

from sqlalchemy import inspect, text

from app.extensions import db
from app.models import BacktestSheetRunLock, TaskLog, TaskResult, TaskResultReturn, TaskResultSummaryIndex


def _delete_xpl_analysis_jobs(*, task_id: str | None = None, result_ids: list[int] | None = None, return_series_ids: list[int] | None = None) -> None:
    """Delete XPL rows when the legacy table exists in the target database."""
    if not inspect(db.engine).has_table("xpl_analysis_jobs"):
        return

    clauses = []
    params = {}
    if task_id:
        clauses.append("task_id = :task_id")
        params["task_id"] = task_id
    if result_ids:
        placeholders = []
        for index, result_id in enumerate(result_ids):
            key = f"result_id_{index}"
            placeholders.append(f":{key}")
            params[key] = result_id
        clauses.append(f"task_result_id IN ({', '.join(placeholders)})")
    if return_series_ids:
        placeholders = []
        for index, return_series_id in enumerate(return_series_ids):
            key = f"return_series_id_{index}"
            placeholders.append(f":{key}")
            params[key] = return_series_id
        clauses.append(f"return_series_id IN ({', '.join(placeholders)})")
    if clauses:
        db.session.execute(text(f"DELETE FROM xpl_analysis_jobs WHERE {' OR '.join(clauses)}"), params)


def delete_task_result_dependencies(result_ids: list[int]) -> None:
    """Remove records that previously depended on task_results via foreign keys."""
    if not result_ids:
        return
    _delete_xpl_analysis_jobs(result_ids=result_ids)
    TaskResultSummaryIndex.query.filter(
        TaskResultSummaryIndex.task_result_id.in_(result_ids)
    ).delete(synchronize_session=False)


def clear_task_execution_data(task_id: str, *, include_logs: bool = False) -> None:
    """Remove all execution records owned by one task using business identifiers."""
    result_ids = [
        result_id
        for result_id, in db.session.query(TaskResult.id).filter_by(task_id=task_id).all()
    ]
    return_series_ids = [
        return_series_id
        for return_series_id, in db.session.query(TaskResultReturn.id).filter_by(task_id=task_id).all()
    ]

    _delete_xpl_analysis_jobs(
        task_id=task_id,
        result_ids=result_ids,
        return_series_ids=return_series_ids,
    )
    TaskResultSummaryIndex.query.filter(
        (TaskResultSummaryIndex.task_id == task_id)
        | TaskResultSummaryIndex.task_result_id.in_(result_ids)
    ).delete(synchronize_session=False)
    TaskResult.query.filter_by(task_id=task_id).delete(synchronize_session=False)
    TaskResultReturn.query.filter_by(task_id=task_id).delete(synchronize_session=False)
    BacktestSheetRunLock.query.filter_by(task_id=task_id).delete(synchronize_session=False)
    if include_logs:
        TaskLog.query.filter_by(task_id=task_id).delete(synchronize_session=False)

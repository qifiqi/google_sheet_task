"""显式清理任务关联数据，避免依赖数据库外键级联。"""

from __future__ import annotations

from sqlalchemy import MetaData, Table, inspect, or_

from app.extensions import db
from app.models import BacktestSheetRunLock, TaskLog, TaskResult, TaskResultReturn, TaskResultSummaryIndex


def _delete_xpl_analysis_jobs(*, task_id: str | None = None, result_ids: list[int] | None = None, return_series_ids: list[int] | None = None) -> None:
    """Delete XPL rows when the legacy table exists in the target database."""
    if not inspect(db.engine).has_table("xpl_analysis_jobs"):
        return

    jobs_table = Table(
        "xpl_analysis_jobs",
        MetaData(),
        autoload_with=db.engine,
    )
    clauses = []
    if task_id:
        clauses.append(jobs_table.c.task_id == task_id)
    if result_ids:
        clauses.append(jobs_table.c.task_result_id.in_(result_ids))
    if return_series_ids:
        clauses.append(jobs_table.c.return_series_id.in_(return_series_ids))
    if clauses:
        db.session.execute(jobs_table.delete().where(or_(*clauses)))


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

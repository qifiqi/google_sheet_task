"""显式清理任务关联数据，避免依赖数据库外键级联。"""

from __future__ import annotations

from sqlalchemy import MetaData, Table, inspect, or_

from app.extensions import db
from app.models import BacktestSheetRunLock, TaskLog, TaskResult, TaskResultReturn, TaskResultSummaryIndex
from app.repositories.backtest_sheet_run_lock_repository import BacktestSheetRunLockRepository
from app.repositories.task_log_repository import TaskLogRepository
from app.repositories.task_result_repository import TaskResultRepository
from app.repositories.task_result_return_repository import TaskResultReturnRepository
from app.repositories.task_result_summary_index_repository import TaskResultSummaryIndexRepository


_task_log_repository = TaskLogRepository()
_task_result_repository = TaskResultRepository()
_task_result_return_repository = TaskResultReturnRepository()
_summary_index_repository = TaskResultSummaryIndexRepository()
_sheet_run_lock_repository = BacktestSheetRunLockRepository()


def _delete_xpl_analysis_jobs(*, task_id: str | None = None, result_ids: list[int] | None = None, return_series_ids: list[int] | None = None) -> None:
    """目标数据库仍存在旧表时，删除关联任务数据的 XPL 分析记录。"""
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
    """删除历史上通过外键依赖任务结果的关联执行记录。"""
    if not result_ids:
        return
    _delete_xpl_analysis_jobs(result_ids=result_ids)
    # TODO: 按 task_result_id 查询索引 ID 等待汇总索引 Query；禁止 SDK 全表筛选。
    index_ids = [
        item.id
        for item in TaskResultSummaryIndex.query.filter(
            TaskResultSummaryIndex.task_result_id.in_(result_ids)
        ).all()
    ]
    for index_id in index_ids:
        _summary_index_repository.delete(index_id)


def clear_task_execution_data(task_id: str, *, include_logs: bool = False) -> None:
    """按业务标识删除一个任务拥有的全部执行记录。"""
    # TODO: 按 task_id 枚举结果、收益、日志和索引 ID 必须等待对应 Query 接口。
    # 在接口到位前保留本地清理，禁止调用 SDK 分页后再在进程内筛选。
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
    index_ids = [
        item.id
        for item in TaskResultSummaryIndex.query.filter(
            (TaskResultSummaryIndex.task_id == task_id)
            | TaskResultSummaryIndex.task_result_id.in_(result_ids)
        ).all()
    ]
    lock_ids = [
        item.id
        for item in BacktestSheetRunLock.query.filter_by(task_id=task_id).all()
    ]
    for index_id in index_ids:
        _summary_index_repository.delete(index_id)
    for result_id in result_ids:
        _task_result_repository.delete(result_id)
    for return_series_id in return_series_ids:
        _task_result_return_repository.delete(return_series_id)
    for lock_id in lock_ids:
        _sheet_run_lock_repository.delete(lock_id)
    if include_logs:
        log_ids = [item.id for item in TaskLog.query.filter_by(task_id=task_id).all()]
        for log_id in log_ids:
            _task_log_repository.delete(log_id)

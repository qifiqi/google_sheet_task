"""显式清理任务关联数据，避免依赖数据库外键级联（数据访问见仓储）。"""

from __future__ import annotations

from app.repositories import (
    backtest_repository,
    task_log_repository,
    task_result_repository,
)


def _delete_xpl_analysis_jobs(*, task_id: str | None = None, result_ids: list[int] | None = None, return_series_ids: list[int] | None = None) -> None:
    backtest_repository.delete_xpl_analysis_jobs(
        task_id=task_id,
        result_ids=result_ids,
        return_series_ids=return_series_ids,
    )


def delete_task_result_dependencies(result_ids: list[int]) -> None:
    """Remove records that previously depended on task_results via foreign keys."""
    if not result_ids:
        return
    _delete_xpl_analysis_jobs(result_ids=result_ids)
    backtest_repository.delete_summary_index_by_result_ids(result_ids, commit=False)


def clear_task_execution_data(task_id: str, *, include_logs: bool = False) -> None:
    """Remove all execution records owned by one task using business identifiers."""
    result_ids = task_result_repository.list_ids_by_task(task_id)
    return_series_ids = task_result_repository.list_return_ids_by_task(task_id)

    _delete_xpl_analysis_jobs(
        task_id=task_id,
        result_ids=result_ids,
        return_series_ids=return_series_ids,
    )
    backtest_repository.delete_summary_index_by_task_or_results(task_id, result_ids, commit=False)
    task_result_repository.delete_by_task(task_id, commit=False)
    task_result_repository.delete_returns_by_task(task_id, commit=False)
    backtest_repository.release_locks_by_task(task_id, commit=False)
    if include_logs:
        task_log_repository.delete_by_task(task_id, commit=False)

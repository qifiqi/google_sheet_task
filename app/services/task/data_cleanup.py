"""显式清理任务关联数据，避免依赖数据库外键级联。"""

from __future__ import annotations

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


def delete_task_result_dependencies(result_ids: list[int]) -> None:
    """删除历史上通过外键依赖任务结果的关联执行记录。"""
    if not result_ids:
        return
    index_ids: set[int] = set()
    for result_id in result_ids:
        page_index = 1
        while True:
            page = _summary_index_repository.list_indexes(
                page_index=page_index,
                page_size=200,
                task_result_id=int(result_id),
            )
            index_ids.update(int(item["id"]) for item in page["items"] if item.get("id") is not None)
            if not page["items"] or page_index * 200 >= page["total"]:
                break
            page_index += 1
    for index_id in index_ids:
        _summary_index_repository.delete(index_id)


def clear_task_execution_data(task_id: str, *, include_logs: bool = False) -> None:
    """按业务标识删除一个任务拥有的全部执行记录。"""
    # 先完整收集远程记录 ID，再开始删除，避免分页数据因删除发生偏移而遗漏。
    result_ids: list[int] = []
    page_index = 1
    while True:
        result_page = _task_result_repository.list_results(
            page_index=page_index,
            page_size=200,
            task_ids=[task_id],
            order_field="timestamp",
            order_type="desc",
        )
        result_ids.extend(
            int(item["id"])
            for item in result_page["items"]
            if item.get("id") is not None
        )
        if not result_page["items"] or len(result_ids) >= result_page["total"]:
            break
        page_index += 1

    index_ids: set[int] = set()
    index_filters = [{"task_id": task_id}]
    index_filters.extend({"task_result_id": result_id} for result_id in result_ids)
    for index_filter in index_filters:
        index_page_index = 1
        while True:
            index_page = _summary_index_repository.list_indexes(
                page_index=index_page_index,
                page_size=200,
                **index_filter,
            )
            index_ids.update(
                int(item["id"]) for item in index_page["items"] if item.get("id") is not None
            )
            if not index_page["items"] or index_page_index * 200 >= index_page["total"]:
                break
            index_page_index += 1

    return_series_ids: list[int] = []
    page_index = 1
    while True:
        return_page = _task_result_return_repository.list_return_series(
            page_index=page_index,
            page_size=200,
            task_id=task_id,
        )
        return_series_ids.extend(
            int(item["id"])
            for item in return_page["items"]
            if item.get("id") is not None
        )
        if not return_page["items"] or len(return_series_ids) >= return_page["total"]:
            break
        page_index += 1

    lock_ids: list[int] = []
    page_index = 1
    while True:
        lock_page = _sheet_run_lock_repository.list_locks(
            page_index=page_index,
            page_size=200,
            task_id=task_id,
        )
        lock_ids.extend(
            int(item["id"])
            for item in lock_page["items"]
            if item.get("id") is not None
        )
        if not lock_page["items"] or len(lock_ids) >= lock_page["total"]:
            break
        page_index += 1

    log_ids: list[int] = []
    if include_logs:
        page_index = 1
        while True:
            log_page = _task_log_repository.list_logs(
                page_index=page_index,
                page_size=200,
                task_id=task_id,
            )
            log_ids.extend(
                int(item["id"])
                for item in log_page["items"]
                if item.get("id") is not None
            )
            if not log_page["items"] or len(log_ids) >= log_page["total"]:
                break
            page_index += 1

    for index_id in index_ids:
        _summary_index_repository.delete(index_id)
    for result_id in result_ids:
        _task_result_repository.delete(result_id)
    for return_series_id in return_series_ids:
        _task_result_return_repository.delete(return_series_id)
    for lock_id in lock_ids:
        _sheet_run_lock_repository.delete(lock_id)
    for log_id in log_ids:
        _task_log_repository.delete(log_id)

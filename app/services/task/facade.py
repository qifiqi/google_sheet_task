"""任务系统统一门面。"""

from __future__ import annotations

import threading
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Any

from app.services.task.registry import GLOBAL_MAX_DEFAULT, GLOBAL_MAX_KEY

from app.services.task.creation import TaskCreationMixin
from app.services.task.logs import TaskLogMixin
from app.services.task.occupancy import TaskOccupancyMixin
from app.services.task.query import TaskQueryMixin
from app.services.task.restart import TaskRestartMixin
from app.services.task.results import TaskResultMixin
from app.services.task.runtime import TaskRuntimeMixin


class TaskManager(
    TaskCreationMixin,
    TaskRuntimeMixin,
    TaskRestartMixin,
    TaskResultMixin,
    TaskQueryMixin,
    TaskLogMixin,
    TaskOccupancyMixin,
):
    """任务系统统一门面。

    对外只暴露这一层，内部能力按职责拆分到不同模块，避免单文件持续膨胀。
    """

    def __init__(self):
        # 值为 _TaskExecution 运行态句柄（包装线程池 Future）。
        self.running_tasks: dict[str, "_TaskExecution"] = {}
        self.task_stop_events: dict[str, threading.Event] = {}
        self.start_errors: dict[str, str] = {}
        self.task_token_occupancy: dict[str, int] = {}
        self.task_execution_types: dict[str, str] = {}
        self.backtest_sheet_start_lock = threading.RLock()
        self._pool: ThreadPoolExecutor | None = None
        self._pool_lock = threading.RLock()
        self._active_worker_ids: dict[str, int] = {}

    def _get_pool(self) -> ThreadPoolExecutor:
        """全局任务线程池；task_max_workers 决定上限（进程生命周期内固定）。"""
        with self._pool_lock:
            if self._pool is None:
                from app.services.config_manager import get_config_manager

                max_workers = int(
                    get_config_manager().get_config(GLOBAL_MAX_KEY, GLOBAL_MAX_DEFAULT)
                    or GLOBAL_MAX_DEFAULT
                )
                self._pool = ThreadPoolExecutor(
                    max_workers=max(max_workers, 1),
                    thread_name_prefix="task_worker",
                )
            return self._pool

    def count_running_executions(self) -> int:
        return sum(1 for handle in self.running_tasks.values() if handle.is_alive())

    def submit_task_execution(self, task_id: str, app, runner) -> Future:
        """把任务执行提交到全局线程池（启动前配额检查由 runtime.start_task 负责）。"""
        pool = self._get_pool()
        handle = _TaskExecution(None)

        def _wrapped():
            handle.thread_id = threading.get_ident()
            self._active_worker_ids[task_id] = handle.thread_id
            try:
                runner(task_id, app)
            finally:
                self._active_worker_ids.pop(task_id, None)

        handle.future = pool.submit(_wrapped)
        return handle

    def get_runtime_snapshot(self) -> dict[str, Any]:
        """返回当前门面维护的核心运行态快照。"""
        return {
            "running_task_ids": list(self.running_tasks.keys()),
            "stop_event_task_ids": list(self.task_stop_events.keys()),
            "start_error_task_ids": list(self.start_errors.keys()),
            "token_occupancy_task_ids": list(self.task_token_occupancy.keys()),
        }

    def get_runtime_snapshot(self) -> dict[str, Any]:
        """返回当前门面维护的核心运行态快照。"""
        return {
            "running_task_ids": list(self.running_tasks.keys()),
            "stop_event_task_ids": list(self.task_stop_events.keys()),
            "start_error_task_ids": list(self.start_errors.keys()),
            "token_occupancy_task_ids": list(self.task_token_occupancy.keys()),
        }


class _TaskExecution:
    """运行态句柄：包装线程池 Future，保持 Thread 兼容的 is_alive/join 语义。"""

    def __init__(self, future: Future | None):
        self.future = future
        self.thread_id: int | None = None

    def is_alive(self) -> bool:
        return self.future is not None and not self.future.done()

    def join(self, timeout: float | None = None) -> None:
        if self.future is None:
            return
        try:
            self.future.result(timeout=timeout)
        except Exception:
            pass


task_manager = TaskManager()

"""任务系统统一门面。"""

from __future__ import annotations

import threading
from typing import Any

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
        self.running_tasks: dict[str, threading.Thread] = {}
        self.task_stop_events: dict[str, threading.Event] = {}
        self.start_errors: dict[str, str] = {}
        self.task_token_occupancy: dict[str, int] = {}
        self.backtest_sheet_start_lock = threading.RLock()

    def get_runtime_snapshot(self) -> dict[str, Any]:
        """返回当前门面维护的核心运行态快照。"""
        return {
            "running_task_ids": list(self.running_tasks.keys()),
            "stop_event_task_ids": list(self.task_stop_events.keys()),
            "start_error_task_ids": list(self.start_errors.keys()),
            "token_occupancy_task_ids": list(self.task_token_occupancy.keys()),
        }


task_manager = TaskManager()

"""任务模块共享类型定义。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable


TaskAppContext = Any
TaskExecutorFactory = Callable[[str, TaskAppContext, Any], Any]


@dataclass(frozen=True)
class TaskExecutorSpec:
    """描述任务类型与执行器的绑定关系。"""

    task_type: str
    logger_suffix: str
    start_message: str
    duplicate_start_message: str
    service_factory: TaskExecutorFactory

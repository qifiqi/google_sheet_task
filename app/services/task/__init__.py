"""任务服务包。

对外统一暴露任务门面与只读服务，减少外部模块感知内部拆分细节。
"""

from app.services.task.facade import TaskManager, task_manager
from app.services.task.dashboard_query import TaskDashboardQueryService
from app.services.task.query import TaskQueryService
from app.services.task.runtime_view import TaskRuntimeViewService

__all__ = [
    "TaskDashboardQueryService",
    "TaskManager",
    "TaskQueryService",
    "TaskRuntimeViewService",
    "task_manager",
]

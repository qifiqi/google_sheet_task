"""任务服务包。

对外统一暴露任务门面与只读服务，减少外部模块感知内部拆分细节。
"""

from __future__ import annotations

__all__ = [
    "TaskDashboardQueryService",
    "TaskManager",
    "TaskQueryService",
    "TaskRuntimeViewService",
    "task_manager",
]


def __getattr__(name: str):
    """按需导入任务门面和只读服务，避免包初始化时产生循环依赖。"""
    if name in {"TaskManager", "task_manager"}:
        from app.services.task.facade import TaskManager, task_manager

        return {"TaskManager": TaskManager, "task_manager": task_manager}[name]

    if name == "TaskDashboardQueryService":
        from app.services.task.dashboard_query import TaskDashboardQueryService

        return TaskDashboardQueryService

    if name == "TaskQueryService":
        from app.services.task.query import TaskQueryService

        return TaskQueryService

    if name == "TaskRuntimeViewService":
        from app.services.task.runtime_view import TaskRuntimeViewService

        return TaskRuntimeViewService

    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

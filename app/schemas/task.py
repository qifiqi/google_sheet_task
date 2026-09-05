"""任务域请求 Schema。"""

from typing import Any

from pydantic import RootModel

from app.schemas.common import APIModel, PageQuery


class TaskListQuery(PageQuery):
    """GET /api/tasks 查询参数。"""

    task_type: str | None = None
    status: str | None = None
    keyword: str = ""


class TaskResultListQuery(PageQuery):
    """GET /api/results 查询参数。"""

    task_id: str | None = None


class TaskCreateSchema(APIModel):
    name: str = "未命名任务"
    description: str = ""
    task_type: str = "google_sheet"
    config: dict[str, Any]


class TasksBatchCreateSchema(RootModel[dict[str, Any]]):
    """C31 批量创建：body 边界仅约束为 JSON 对象（与 service 的
    "批量任务请求体必须是 JSON 对象" 语义对齐）；
    字段级校验由 task_manager.batch_create_and_start_task 服务负责。"""


class TaskRestartSchema(APIModel):
    resume_from_checkpoint: bool = True

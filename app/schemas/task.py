"""任务域请求 Schema。"""

from typing import Any

from pydantic import Field

from app.schemas.common import APIModel


class TaskCreateSchema(APIModel):
    name: str = "未命名任务"
    description: str = ""
    task_type: str = "google_sheet"
    config: dict[str, Any]


class TasksBatchCreateSchema(APIModel):
    """C31 批量创建：body 边界仅约束为 JSON 对象；
    字段级校验由 task_manager.batch_create_and_start_task 服务负责。"""


class TaskRestartSchema(APIModel):
    resume_from_checkpoint: bool = True

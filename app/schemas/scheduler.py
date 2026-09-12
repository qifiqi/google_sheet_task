"""定时任务域请求 Schema。"""

from pydantic import Field

from app.schemas.common import PageQuery, APIModel


class ScheduledTaskCreateSchema(APIModel):
    name: str = Field(min_length=1)
    description: str = ""
    cron_expression: str = Field(min_length=1)
    task_type: str = Field(min_length=1)
    task_function: str = Field(min_length=1)
    task_params: str = "{}"
    is_active: bool = True


class ScheduledTaskUpdateSchema(APIModel):
    name: str | None = None
    description: str | None = None
    cron_expression: str | None = None
    task_type: str | None = None
    task_function: str | None = None
    task_params: str | None = None
    is_active: bool | None = None


class SchedulerTaskListQuery(PageQuery):
    """GET /api/admin/scheduler/tasks 查询参数（per_page 默认 50）。"""

    per_page: int = Field(default=50, ge=1, le=100)


class ToggleTaskSchema(APIModel):
    """POST /api/admin/scheduler/tasks/<id>/toggle；缺省 is_active 表示取反。"""

    is_active: bool | None = None

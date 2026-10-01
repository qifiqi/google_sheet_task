"""任务域请求 Schema。"""

from typing import Any

from pydantic import RootModel, field_validator

from app.schemas.common import APIModel, PageQuery

# GET /api/tasks/<task_id>/results 的 fields 白名单；return_date_range 为计算字段
# （收益序列首末日期，批量从 return_series 取），不在存储列映射里。
TASK_RESULT_FIELD_WHITELIST = frozenset({
    "id", "task_id", "step_index", "parameters", "result", "return_series_id",
    "success", "error_message", "timestamp", "return_date_range",
})


class TaskListQuery(PageQuery):
    """GET /api/tasks 查询参数。"""

    task_type: str | None = None
    status: str | None = None
    keyword: str = ""
    stock_code: str = ""


class TaskResultListQuery(PageQuery):
    """GET /api/results 查询参数。"""

    task_id: str | None = None
    success: bool | None = None
    keyword: str = ""


class TaskConfigUpdateSchema(APIModel):
    """PUT /api/tasks/<id>/config。"""

    config: dict[str, Any]
    name: str | None = None
    description: str | None = None
    status: str | None = None


class TaskIdsBatchSchema(APIModel):
    """POST /api/exports/tasks/batch-export 等批量导出请求体。"""

    task_ids: list[Any]


class TaskResultsQuerySchema(APIModel):
    """GET /api/tasks/<task_id>/results 的 fields 投影查询参数。

    缺省（不带 fields）= 历史全量 to_dict，CSV/详情消费方不受影响；
    下拉/索引类消费方用 fields 裁剪响应，避开 result 大 JSON。
    """

    fields: str = ""

    @field_validator("fields")
    @classmethod
    def _validate_fields(cls, value: str) -> list[str]:
        """逗号分隔字段白名单校验；未知字段直接 400（支持列表随消息下发）。"""
        requested = [part.strip() for part in value.split(",") if part.strip()]
        unknown = [part for part in requested if part not in TASK_RESULT_FIELD_WHITELIST]
        if unknown:
            raise ValueError(
                f"fields 含不支持的字段: {','.join(unknown)}"
                f"（支持: {','.join(sorted(TASK_RESULT_FIELD_WHITELIST))}）"
            )
        return list(dict.fromkeys(requested))


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

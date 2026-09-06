"""管理后台域请求 Schema。"""

from app.schemas.common import APIModel


class RebuildSchema(APIModel):
    """POST /admin/api/model-summary/rebuild。"""

    task_type: str | None = None
    task_id: str | None = None
    batch_size: int = 20
    reset: bool = False

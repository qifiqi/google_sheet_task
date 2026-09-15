"""管理后台域请求 Schema。"""

from app.schemas.common import APIModel


class RebuildSchema(APIModel):
    """POST /admin/api/model-summary/rebuild。"""

    task_type: str | None = None
    task_id: str | None = None
    batch_size: int = 20
    reset: bool = False


class WordExportCacheClearSchema(APIModel):
    """POST /admin/api/word-export-cache/clear。

    默认全清；task_id 定向清理该任务的报告缓存；only_expired 仅清过期条目。
    """

    task_id: str | None = None
    only_expired: bool = False

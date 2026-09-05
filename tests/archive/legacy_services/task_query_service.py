"""历史兼容文件留档。

此文件保留原 app/services/task_query_service.py 的最后兼容形态，
仅用于测试目录下的迁移留痕，不参与正式运行路径。
"""

from app.services.task.query import TaskQueryService

__all__ = ["TaskQueryService"]

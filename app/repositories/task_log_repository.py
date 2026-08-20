"""任务日志的远程 CRUD 访问。"""

from app.repositories.base import RemoteRecord, SdkCrudRepository


class TaskLogRepository(SdkCrudRepository):
    """仅提供标准 CRUD；按 task_id 查询等待 ParamTaskLogs/Query。"""

    group_name = "param_task_logs"

    def normalize_record(self, record):
        """日志 DTO 保留属性访问，便于兼容旧运行态逻辑。"""
        return RemoteRecord(record)

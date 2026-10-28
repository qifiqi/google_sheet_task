"""Sheet 执行锁统一服务（唯一互斥权威）。

语义（全任务类型通用，见 docs 内"统一 Sheet 执行锁"约定）：
- 唯一键为 spreadsheet_id（trim 后精确匹配），与任务类型无关、不依赖注册状态；
- 同一 spreadsheet 同时只能被一个执行中的任务持有；
- pending 排队任务不持锁；锁只在 start_task 成功路径获取、线程收尾/看门狗释放；
- registry 的 is_in_use 仅作展示镜像，不参与互斥判定。
"""

from __future__ import annotations

from app.repositories import sheet_lock_repository
from app.utils.logger import get_logger

logger = get_logger(__name__)


def normalize_spreadsheet_id(value) -> str:
    """锁键规范化：仅 trim；Google spreadsheet ID 区分大小写。"""
    return str(value or "").strip()


class SheetExecutionLockService:
    """acquire/release/conflict 判定的唯一出口。"""

    def acquire_for_task(
        self,
        task_id: str,
        task_type: str,
        spreadsheet_ids: list[str],
    ) -> tuple[bool, str | None, list[str]]:
        """原子获取任务的全部 sheet 锁（全拿全放）。

        返回 (acquired_all, holder_task_id, acquired_ids)。
        """
        normalized = self.normalize_ids(spreadsheet_ids)
        if not normalized:
            return True, None, []
        return sheet_lock_repository.acquire_all(normalized, task_id, task_type)

    def release_for_task(self, task_id: str) -> int:
        """释放任务持有的全部锁；返回删除行数（仅持锁者可释放由仓储保证）。"""
        return sheet_lock_repository.release_all_by_task(task_id)

    def list_held_spreadsheet_ids(self, task_id: str) -> list[str]:
        """任务当前持有的全部锁键（收尾接力集合依据，与释放动作同源）。"""
        return sheet_lock_repository.list_spreadsheet_ids_by_task(task_id)

    def release_sheets(self, spreadsheet_ids: list[str], task_id: str) -> None:
        """逐把释放（仅清理指定 sheet；他人锁被仓储拒绝并告警）。"""
        for spreadsheet_id in self.normalize_ids(spreadsheet_ids):
            released = sheet_lock_repository.release(spreadsheet_id, task_id)
            if not released:
                lock = sheet_lock_repository.get(spreadsheet_id)
                if lock:
                    logger.warning(
                        "跳过释放 Sheet 执行锁: sheet=%s, task_id=%s, holder=%s",
                        spreadsheet_id,
                        task_id,
                        lock.get("task_id"),
                    )

    def find_conflict(
        self,
        spreadsheet_ids: list[str],
        exclude_task_id: str | None = None,
    ) -> str | None:
        """任一 sheet 被其他任务持锁时返回持锁任务 id，否则 None。"""
        normalized = self.normalize_ids(spreadsheet_ids)
        if not normalized:
            return None
        return sheet_lock_repository.find_conflict(normalized, exclude_task_id)

    @staticmethod
    def normalize_ids(spreadsheet_ids) -> list[str]:
        return sorted(
            {
                normalized
                for normalized in (
                    normalize_spreadsheet_id(value) for value in (spreadsheet_ids or [])
                )
                if normalized
            }
        )


sheet_execution_lock_service = SheetExecutionLockService()


def get_sheet_execution_lock_service() -> SheetExecutionLockService:
    return sheet_execution_lock_service

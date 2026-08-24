"""回测 Google Sheet 运行锁的远程 CRUD 访问。"""

from app.repositories.base import SdkCrudRepository
from typing import Any


class BacktestSheetRunLockRepository(SdkCrudRepository):
    """锁的互斥依赖远端 spreadsheet_id 唯一约束与重复键错误。"""

    group_name = "param_backtest_sheet_run_locks"

    def list_locks(
        self,
        *,
        page_index: int = 1,
        page_size: int = 100,
        spreadsheet_id: str | None = None,
        task_id: str | None = None,
        order_field: str = "created_at",
        order_type: str = "desc",
    ) -> dict[str, Any]:
        """按 spreadsheet_id、task_id 查询回测 Sheet 锁。"""
        payload: dict[str, Any] = {
            "page_index": max(1, int(page_index)),
            "page_size": max(1, int(page_size)),
            "order_field": order_field,
            "order_type": order_type,
        }
        if spreadsheet_id:
            payload["spreadsheet_id"] = str(spreadsheet_id)
        if task_id:
            payload["task_id"] = str(task_id)
        raw = self.client.call(self.group_name, "get_data_by_page_list", payload)
        return self._normalize_page(raw)

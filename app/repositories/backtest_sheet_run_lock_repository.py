"""回测 Google Sheet 运行锁的远程 CRUD 访问。"""

from app.repositories.base import SdkCrudRepository


class BacktestSheetRunLockRepository(SdkCrudRepository):
    """锁的互斥依赖远端 spreadsheet_id 唯一约束与重复键错误。"""

    group_name = "param_backtest_sheet_run_locks"

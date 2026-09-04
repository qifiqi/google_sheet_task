"""数据访问层（repositories）。

分层方向：routes → services → repositories → models。
本包独占 ORM 操作；调用方统一 `from app.repositories import xxx_repository`。
模块级单例，见 docs/design/data-layer-refactor/02 §3。
"""
from app.repositories.backtest_repository import BacktestRepository
from app.repositories.base import BaseRepository
from app.repositories.google_sheet_repository import GoogleSheetRepository
from app.repositories.google_sheet_token_repository import GoogleSheetTokenRepository
from app.repositories.navigation_repository import NavigationRepository
from app.repositories.rbac_repository import RbacRepository
from app.repositories.scheduled_task_repository import ScheduledTaskRepository
from app.repositories.stock_metadata_repository import StockMetadataRepository
from app.repositories.system_config_repository import SystemConfigRepository
from app.repositories.task_log_repository import TaskLogRepository
from app.repositories.task_repository import TaskRepository
from app.repositories.task_result_repository import TaskResultRepository
from app.repositories.task_template_repository import TaskTemplateRepository

__all__ = [
    "BaseRepository",
    "backtest_repository",
    "google_sheet_repository",
    "google_sheet_token_repository",
    "navigation_repository",
    "rbac_repository",
    "scheduled_task_repository",
    "stock_metadata_repository",
    "system_config_repository",
    "task_log_repository",
    "task_repository",
    "task_result_repository",
    "task_template_repository",
]

backtest_repository = BacktestRepository()
google_sheet_repository = GoogleSheetRepository()
google_sheet_token_repository = GoogleSheetTokenRepository()
navigation_repository = NavigationRepository()
rbac_repository = RbacRepository()
scheduled_task_repository = ScheduledTaskRepository()
stock_metadata_repository = StockMetadataRepository()
system_config_repository = SystemConfigRepository()
task_log_repository = TaskLogRepository()
task_repository = TaskRepository()
task_result_repository = TaskResultRepository()
task_template_repository = TaskTemplateRepository()

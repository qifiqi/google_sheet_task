"""数据层 HTTP 后端（db-to-http 迁移，见 docs/design/db-to-http-migration/）。

每个模块与 app/repositories/ 下的本地 ORM 仓储同名同签名，由
app/repositories/__init__.py 按 ``DATA_ACCESS_MODE``（env，默认 http）
绑定其中一个；service/routes 调用点零改动。
"""
from app.repositories.http_backend.backtest_repository import BacktestHttpRepository
from app.repositories.http_backend.base import HttpRepositoryBase, RemoteRecord
from app.repositories.http_backend.google_sheet_repository import GoogleSheetHttpRepository
from app.repositories.http_backend.google_sheet_token_repository import GoogleSheetTokenHttpRepository
from app.repositories.http_backend.scheduled_task_repository import ScheduledTaskHttpRepository
from app.repositories.http_backend.stock_metadata_repository import StockMetadataHttpRepository
from app.repositories.http_backend.system_config_repository import SystemConfigHttpRepository
from app.repositories.http_backend.task_log_repository import TaskLogHttpRepository
from app.repositories.http_backend.task_repository import TaskHttpRepository
from app.repositories.http_backend.task_result_repository import TaskResultHttpRepository
from app.repositories.http_backend.task_template_repository import TaskTemplateHttpRepository

__all__ = [
    "BacktestHttpRepository",
    "GoogleSheetHttpRepository",
    "GoogleSheetTokenHttpRepository",
    "HttpRepositoryBase",
    "RemoteRecord",
    "ScheduledTaskHttpRepository",
    "StockMetadataHttpRepository",
    "SystemConfigHttpRepository",
    "TaskHttpRepository",
    "TaskLogHttpRepository",
    "TaskResultHttpRepository",
    "TaskTemplateHttpRepository",
]

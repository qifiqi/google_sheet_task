"""数据访问层（repositories）。

分层方向：routes → services → repositories → models。
本包独占 ORM 操作；调用方统一 `from app.repositories import xxx_repository`。
模块级单例，见 docs/design/data-layer-refactor/02 §3。

db-to-http 迁移（docs/design/db-to-http-migration/）：``DATA_ACCESS_MODE``
环境变量决定单例绑定本地 ORM 仓储还是 HTTP 孪生仓储（app/repositories/
http_backend/，同签名）。默认 http（全量走远程 DY.Stock.Api）；db 为暂时
保留的本地回退。启动期读取，不做运行时热切换。

无法迁移、固定绑定本地 DB 的仓储：
- navigation_repository：远端无导航菜单表（迁移文档《无法接入清单》）；
- auth_repository：用户/角色/权限管理已上收主 Web（单 Token 子服务模式），
  本地实现仅保留供 db 模式与历史脚手架使用。
"""
import os

from app.repositories.backtest_repository import BacktestRepository
from app.repositories.base import BaseRepository
from app.repositories.google_sheet_repository import GoogleSheetRepository
from app.repositories.google_sheet_token_repository import GoogleSheetTokenRepository
from app.repositories.navigation_repository import NavigationRepository
from app.repositories.auth_repository import AuthRepository
from app.repositories.scheduled_task_repository import ScheduledTaskRepository
from app.repositories.stock_metadata_repository import StockMetadataRepository
from app.repositories.system_config_repository import SystemConfigRepository
from app.repositories.task_log_repository import TaskLogRepository
from app.repositories.task_repository import TaskRepository
from app.repositories.task_result_repository import TaskResultRepository
from app.repositories.task_template_repository import TaskTemplateRepository
from app.repositories.http_backend import (
    BacktestHttpRepository,
    GoogleSheetHttpRepository,
    GoogleSheetTokenHttpRepository,
    ScheduledTaskHttpRepository,
    StockMetadataHttpRepository,
    SystemConfigHttpRepository,
    TaskHttpRepository,
    TaskLogHttpRepository,
    TaskResultHttpRepository,
    TaskTemplateHttpRepository,
)

__all__ = [
    "BaseRepository",
    "backtest_repository",
    "google_sheet_repository",
    "google_sheet_token_repository",
    "navigation_repository",
    "auth_repository",
    "scheduled_task_repository",
    "stock_metadata_repository",
    "system_config_repository",
    "task_log_repository",
    "task_repository",
    "task_result_repository",
    "task_template_repository",
]

# 仅启动期读取一次；与 app/config.py 的 DATA_ACCESS_MODE 同源同默认。
_DATA_ACCESS_MODE = os.environ.get('DATA_ACCESS_MODE', 'http').strip().lower()
_USE_HTTP_BACKEND = _DATA_ACCESS_MODE == 'http'

backtest_repository = (
    BacktestHttpRepository() if _USE_HTTP_BACKEND else BacktestRepository()
)
google_sheet_repository = (
    GoogleSheetHttpRepository() if _USE_HTTP_BACKEND else GoogleSheetRepository()
)
google_sheet_token_repository = (
    GoogleSheetTokenHttpRepository() if _USE_HTTP_BACKEND else GoogleSheetTokenRepository()
)
# 导航菜单远端无对应表，固定本地。
navigation_repository = NavigationRepository()
auth_repository = AuthRepository()
scheduled_task_repository = (
    ScheduledTaskHttpRepository() if _USE_HTTP_BACKEND else ScheduledTaskRepository()
)
stock_metadata_repository = (
    StockMetadataHttpRepository() if _USE_HTTP_BACKEND else StockMetadataRepository()
)
system_config_repository = (
    SystemConfigHttpRepository() if _USE_HTTP_BACKEND else SystemConfigRepository()
)
task_log_repository = (
    TaskLogHttpRepository() if _USE_HTTP_BACKEND else TaskLogRepository()
)
task_repository = TaskHttpRepository() if _USE_HTTP_BACKEND else TaskRepository()
task_result_repository = (
    TaskResultHttpRepository() if _USE_HTTP_BACKEND else TaskResultRepository()
)
task_template_repository = (
    TaskTemplateHttpRepository() if _USE_HTTP_BACKEND else TaskTemplateRepository()
)

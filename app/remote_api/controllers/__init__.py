"""DY.Stock.Api 控制器分组：按 URL 中段（Swagger 控制器）一控制器一文件。"""

from __future__ import annotations

from typing import Any

from app.remote_api.controllers.param_backtest_product_result_cache import ParamBacktestProductResultCacheApi
from app.remote_api.controllers.param_backtest_sheet_run_locks import ParamBacktestSheetRunLocksApi
from app.remote_api.controllers.param_google_sheet import ParamGoogleSheetApi
from app.remote_api.controllers.param_google_sheet_tokens import ParamGoogleSheetTokensApi
from app.remote_api.controllers.param_scheduled_tasks import ParamScheduledTasksApi
from app.remote_api.controllers.param_stock_metadata import ParamStockMetadataApi
from app.remote_api.controllers.param_system_configs import ParamSystemConfigsApi
from app.remote_api.controllers.param_task_logs import ParamTaskLogsApi
from app.remote_api.controllers.param_task_result_summary_index import ParamTaskResultSummaryIndexApi
from app.remote_api.controllers.param_task_results import ParamTaskResultsApi
from app.remote_api.controllers.param_task_results_return import ParamTaskResultsReturnApi
from app.remote_api.controllers.param_task_templates import ParamTaskTemplatesApi
from app.remote_api.controllers.param_tasks import ParamTasksApi
from app.remote_api.controllers.param_xpl_analysis_jobs import ParamXplAnalysisJobsApi
from app.remote_api.controllers.stock_data import StockDataApi
from app.remote_api.controllers.stock_data_us import StockDataUsApi
from app.remote_api.controllers.sys_model import SysModelApi
from app.remote_api.controllers.sys_role import SysRoleApi
from app.remote_api.controllers.sys_user import SysUserApi

__all__ = [
    "ParamBacktestProductResultCacheApi",
    "ParamBacktestSheetRunLocksApi",
    "ParamGoogleSheetApi",
    "ParamGoogleSheetTokensApi",
    "ParamScheduledTasksApi",
    "ParamStockMetadataApi",
    "ParamSystemConfigsApi",
    "ParamTaskLogsApi",
    "ParamTaskResultSummaryIndexApi",
    "ParamTaskResultsApi",
    "ParamTaskResultsReturnApi",
    "ParamTaskTemplatesApi",
    "ParamTasksApi",
    "ParamXplAnalysisJobsApi",
    "StockDataApi",
    "StockDataUsApi",
    "SysModelApi",
    "SysRoleApi",
    "SysUserApi",
    "bind_controllers",
]


def bind_controllers(client: Any) -> None:
    """把全部控制器挂到统一调用器实例（属性名与仓储层 group_name 一致）。"""
    client.param_backtest_product_result_cache = ParamBacktestProductResultCacheApi(client)
    client.param_backtest_sheet_run_locks = ParamBacktestSheetRunLocksApi(client)
    client.param_google_sheet = ParamGoogleSheetApi(client)
    client.param_google_sheet_tokens = ParamGoogleSheetTokensApi(client)
    client.param_scheduled_tasks = ParamScheduledTasksApi(client)
    client.param_stock_metadata = ParamStockMetadataApi(client)
    client.param_system_configs = ParamSystemConfigsApi(client)
    client.param_task_logs = ParamTaskLogsApi(client)
    client.param_task_result_summary_index = ParamTaskResultSummaryIndexApi(client)
    client.param_task_results = ParamTaskResultsApi(client)
    client.param_task_results_return = ParamTaskResultsReturnApi(client)
    client.param_task_templates = ParamTaskTemplatesApi(client)
    client.param_tasks = ParamTasksApi(client)
    client.param_xpl_analysis_jobs = ParamXplAnalysisJobsApi(client)
    client.stock_data = StockDataApi(client)
    client.stock_data_us = StockDataUsApi(client)
    client.sys_model = SysModelApi(client)
    client.sys_role = SysRoleApi(client)
    client.sys_user = SysUserApi(client)

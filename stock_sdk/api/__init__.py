"""All generated endpoint groups, grouped by Swagger controller."""

from __future__ import annotations

from typing import Any

from ._metadata import collect_operations

from .east_money_stock_quote import EastmoneystockquoteApi
from .param_backtest_product_result_cache import ParambacktestproductresultcacheApi
from .param_backtest_sheet_run_locks import ParambacktestsheetrunlocksApi
from .param_google_sheet import ParamgooglesheetApi
from .param_google_sheet_tokens import ParamgooglesheettokensApi
from .param_scheduled_tasks import ParamscheduledtasksApi
from .param_stock_metadata import ParamstockmetadataApi
from .param_system_configs import ParamsystemconfigsApi
from .param_task_logs import ParamtasklogsApi
from .param_task_results import ParamtaskresultsApi
from .param_task_results_return import ParamtaskresultsreturnApi
from .param_task_result_summary_index import ParamtaskresultsummaryindexApi
from .param_tasks import ParamtasksApi
from .param_task_templates import ParamtasktemplatesApi
from .param_xpl_analysis_jobs import ParamxplanalysisjobsApi
from .stock_atarget import StockatargetApi
from .stock_atarget_cond import StockatargetcondApi
from .stock_atarget_log import StockatargetlogApi
from .stock_cn_order import StockcnorderApi
from .stock_data import StockdataApi
from .stock_data_area import StockdataareaApi
from .stock_data_concept import StockdataconceptApi
from .stock_data_index import StockdataindexApi
from .stock_data_industry import StockdataindustryApi
from .stock_data_us import StockdatausApi
from .stock_data_volume import StockdatavolumeApi
from .stock_date import StockdateApi
from .stock_dic import StockdicApi
from .stock_financial_data import StockfinancialdataApi
from .stock_industry import StockindustryApi
from .stock_minute_tick import StockminutetickApi
from .stock_param_data import StockparamdataApi
from .stock_param_result import StockparamresultApi
from .stock_param_template import StockparamtemplateApi
from .stock_param_tuning import StockparamtuningApi
from .stock_sms_msg import StocksmsmsgApi
from .stock_top10_circulating import Stocktop10circulatingApi
from .stock_trs_account import StocktrsaccountApi
from .stock_trs_child_order import StocktrschildorderApi
from .stock_trs_deal_records import StocktrsdealrecordsApi
from .stock_trs_events_log import StocktrseventslogApi
from .stock_trs_order import StocktrsorderApi
from .stock_trs_pool import StocktrspoolApi
from .stock_trs_position_snapshot import StocktrspositionsnapshotApi
from .stock_ws import StockwsApi
from .stock_xt_credit_detail import StockxtcreditdetailApi
from .stock_xt_data import StockxtdataApi
from .stock_xt_data_trading import StockxtdatatradingApi
from .stock_xt_order import StockxtorderApi
from .stock_xt_position import StockxtpositionApi
from .stock_xt_trade import StockxttradeApi
from .sys_log import SyslogApi
from .sys_model import SysmodelApi
from .sys_role import SysroleApi
from .sys_user import SysuserApi

def bind_api_groups(client: Any) -> None:
    """Attach every controller group to a client instance."""
    client.east_money_stock_quote = EastmoneystockquoteApi(client)
    client.param_backtest_product_result_cache = ParambacktestproductresultcacheApi(client)
    client.param_backtest_sheet_run_locks = ParambacktestsheetrunlocksApi(client)
    client.param_google_sheet = ParamgooglesheetApi(client)
    client.param_google_sheet_tokens = ParamgooglesheettokensApi(client)
    client.param_scheduled_tasks = ParamscheduledtasksApi(client)
    client.param_stock_metadata = ParamstockmetadataApi(client)
    client.param_system_configs = ParamsystemconfigsApi(client)
    client.param_task_logs = ParamtasklogsApi(client)
    client.param_task_results = ParamtaskresultsApi(client)
    client.param_task_results_return = ParamtaskresultsreturnApi(client)
    client.param_task_result_summary_index = ParamtaskresultsummaryindexApi(client)
    client.param_tasks = ParamtasksApi(client)
    client.param_task_templates = ParamtasktemplatesApi(client)
    client.param_xpl_analysis_jobs = ParamxplanalysisjobsApi(client)
    client.stock_atarget = StockatargetApi(client)
    client.stock_atarget_cond = StockatargetcondApi(client)
    client.stock_atarget_log = StockatargetlogApi(client)
    client.stock_cn_order = StockcnorderApi(client)
    client.stock_data = StockdataApi(client)
    client.stock_data_area = StockdataareaApi(client)
    client.stock_data_concept = StockdataconceptApi(client)
    client.stock_data_index = StockdataindexApi(client)
    client.stock_data_industry = StockdataindustryApi(client)
    client.stock_data_us = StockdatausApi(client)
    client.stock_data_volume = StockdatavolumeApi(client)
    client.stock_date = StockdateApi(client)
    client.stock_dic = StockdicApi(client)
    client.stock_financial_data = StockfinancialdataApi(client)
    client.stock_industry = StockindustryApi(client)
    client.stock_minute_tick = StockminutetickApi(client)
    client.stock_param_data = StockparamdataApi(client)
    client.stock_param_result = StockparamresultApi(client)
    client.stock_param_template = StockparamtemplateApi(client)
    client.stock_param_tuning = StockparamtuningApi(client)
    client.stock_sms_msg = StocksmsmsgApi(client)
    client.stock_top10_circulating = Stocktop10circulatingApi(client)
    client.stock_trs_account = StocktrsaccountApi(client)
    client.stock_trs_child_order = StocktrschildorderApi(client)
    client.stock_trs_deal_records = StocktrsdealrecordsApi(client)
    client.stock_trs_events_log = StocktrseventslogApi(client)
    client.stock_trs_order = StocktrsorderApi(client)
    client.stock_trs_pool = StocktrspoolApi(client)
    client.stock_trs_position_snapshot = StocktrspositionsnapshotApi(client)
    client.stock_ws = StockwsApi(client)
    client.stock_xt_credit_detail = StockxtcreditdetailApi(client)
    client.stock_xt_data = StockxtdataApi(client)
    client.stock_xt_data_trading = StockxtdatatradingApi(client)
    client.stock_xt_order = StockxtorderApi(client)
    client.stock_xt_position = StockxtpositionApi(client)
    client.stock_xt_trade = StockxttradeApi(client)
    client.sys_log = SyslogApi(client)
    client.sys_model = SysmodelApi(client)
    client.sys_role = SysroleApi(client)
    client.sys_user = SysuserApi(client)

API_OPERATIONS = collect_operations(
    ('east_money_stock_quote', EastmoneystockquoteApi),
    ('param_backtest_product_result_cache', ParambacktestproductresultcacheApi),
    ('param_backtest_sheet_run_locks', ParambacktestsheetrunlocksApi),
    ('param_google_sheet', ParamgooglesheetApi),
    ('param_google_sheet_tokens', ParamgooglesheettokensApi),
    ('param_scheduled_tasks', ParamscheduledtasksApi),
    ('param_stock_metadata', ParamstockmetadataApi),
    ('param_system_configs', ParamsystemconfigsApi),
    ('param_task_logs', ParamtasklogsApi),
    ('param_task_results', ParamtaskresultsApi),
    ('param_task_results_return', ParamtaskresultsreturnApi),
    ('param_task_result_summary_index', ParamtaskresultsummaryindexApi),
    ('param_tasks', ParamtasksApi),
    ('param_task_templates', ParamtasktemplatesApi),
    ('param_xpl_analysis_jobs', ParamxplanalysisjobsApi),
    ('stock_atarget', StockatargetApi),
    ('stock_atarget_cond', StockatargetcondApi),
    ('stock_atarget_log', StockatargetlogApi),
    ('stock_cn_order', StockcnorderApi),
    ('stock_data', StockdataApi),
    ('stock_data_area', StockdataareaApi),
    ('stock_data_concept', StockdataconceptApi),
    ('stock_data_index', StockdataindexApi),
    ('stock_data_industry', StockdataindustryApi),
    ('stock_data_us', StockdatausApi),
    ('stock_data_volume', StockdatavolumeApi),
    ('stock_date', StockdateApi),
    ('stock_dic', StockdicApi),
    ('stock_financial_data', StockfinancialdataApi),
    ('stock_industry', StockindustryApi),
    ('stock_minute_tick', StockminutetickApi),
    ('stock_param_data', StockparamdataApi),
    ('stock_param_result', StockparamresultApi),
    ('stock_param_template', StockparamtemplateApi),
    ('stock_param_tuning', StockparamtuningApi),
    ('stock_sms_msg', StocksmsmsgApi),
    ('stock_top10_circulating', Stocktop10circulatingApi),
    ('stock_trs_account', StocktrsaccountApi),
    ('stock_trs_child_order', StocktrschildorderApi),
    ('stock_trs_deal_records', StocktrsdealrecordsApi),
    ('stock_trs_events_log', StocktrseventslogApi),
    ('stock_trs_order', StocktrsorderApi),
    ('stock_trs_pool', StocktrspoolApi),
    ('stock_trs_position_snapshot', StocktrspositionsnapshotApi),
    ('stock_ws', StockwsApi),
    ('stock_xt_credit_detail', StockxtcreditdetailApi),
    ('stock_xt_data', StockxtdataApi),
    ('stock_xt_data_trading', StockxtdatatradingApi),
    ('stock_xt_order', StockxtorderApi),
    ('stock_xt_position', StockxtpositionApi),
    ('stock_xt_trade', StockxttradeApi),
    ('sys_log', SyslogApi),
    ('sys_model', SysmodelApi),
    ('sys_role', SysroleApi),
    ('sys_user', SysuserApi),
)

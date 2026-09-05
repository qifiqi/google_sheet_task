"""All generated OpenAPI models, grouped by controller."""

from .stock_param_result import DeleteStockParamResultRequestDto, GetSingleStockTemplateRequestDto, GetStockParamResultListRequestDto, t_stock_param_result
from .stock_data_area import GetAreaListRequestDto, t_stock_data_area
from .stock_xt_order import GetDataByPageListForWindowsRequestDto, GetStockXtOrderListRequestDto, t_stock_xt_order
from .stock_data_concept import GetDataConceptListRequestDto, t_stock_data_concept
from .stock_data_index import GetDataIndexListRequestDto, t_stock_data_index
from .stock_data_industry import GetDataIndustryListRequestDto, t_stock_data_industry
from .stock_xt_data import GetDataStateListRequestDto, GetStockXtDataListRequestDto, UpdateStateRequestDto, UpdateUserRequestDto, t_stock_xt_data
from .stock_dic import GetDicListForSelectRequestDto
from .east_money_stock_quote import GetEastMoneyStockQuoteRequestDto, GetEastMoneyStockTrendsRequestDto
from .stock_data import GetListHisPageRequestDto, GetStockDataAllListRequestDto, GetStockDataListPageRequestDto, GetStockDataListRequestDto, GetStockDataRequestDto, GetStockListByCodeRequestDto, t_stock_data
from .sys_model import GetModelListRequestDto, sys_model
from .stock_atarget_cond import GetStockATargetCondListRequestDto, GetStockATargetCondSearchRequestDto, t_stock_a_target_cond
from .stock_atarget import GetStockATargetListRequestDto, t_stock_a_target
from .stock_atarget_log import GetStockATargetLogListRequestDto, t_stock_a_target_log
from .stock_cn_order import GetStockCnOrderListRequestDto, t_stock_cn_order
from .stock_data_volume import GetStockDataVolumeHisListRequestDto, GetStockDataVolumeListRequestDto, GetStockDataVolumeRequestDto, t_stock_data_volume, t_stock_data_volume_his
from .stock_financial_data import GetStockFinancialDataRequestDto, t_stock_financial_data
from .stock_minute_tick import GetStockMinuteTickListRequestDto, LongIdRequestDto, t_stock_minute_tick
from .stock_param_data import GetStockParamDataListRequestDto, t_stock_param_data
from .stock_param_template import GetStockParamTemplateListRequestDto, t_stock_param_template
from .stock_param_tuning import GetStockParamTuningListRequestDto, t_stock_param_tuning
from .stock_top10_circulating import GetStockTop10CirculatingListRequestDto, t_stock_top10_circulating
from .stock_trs_child_order import GetStockTrsChildOrderListRequestDto, t_stock_trs_child_orders
from .stock_trs_deal_records import GetStockTrsDealRecordsListRequestDto, t_stock_trs_deal_records
from .stock_trs_events_log import GetStockTrsEventsLogListRequestDto, t_stock_trs_events_log
from .stock_trs_order import GetStockTrsOrderListRequestDto, GetStockTrsOrderStatusRequestDto, t_stock_trs_order
from .stock_trs_pool import GetStockTrsPoolListRequestDto, t_stock_trs_pool
from .stock_trs_position_snapshot import GetStockTrsPositionSnapshottRequestDto, t_stock_trs_position_snapshot
from .stock_xt_credit_detail import GetStockXtCreditDetailListRequestDto, t_stock_xt_credit_detail
from .stock_xt_data_trading import GetStockXtDataTradingListRequestDto, t_stock_xt_data_trading
from .stock_xt_position import GetStockXtPositionListForWindowsRequestDto, GetStockXtPositionListRequestDto, t_stock_xt_position
from .stock_xt_trade import GetStockXtTradeListForWindowsRequestDto, GetStockXtTradeListRequestDto, t_stock_xt_trade
from .sys_log import GetSysLogListRequestDto
from .sys_role import GetSysRoleListRequestDto, IsRoleRequestDto, sys_role
from .sys_user import GetSysUserListRequestDto, GetUserListForSelectRequestDto, RegisterRequestDto, UpdatePwdRequestDto, UserEnableOrUnEnableRequestDto, sys_user
from .param_backtest_product_result_cache import IdRequestDto, RequsetPageDto, t_param_backtest_product_result_cache
from .common import ModelTypeEnum, ResponseDto, UserStatusEnum
from .param_tasks import ParamStringIdRequestDto, t_param_tasks
from .param_backtest_sheet_run_locks import t_param_backtest_sheet_run_locks
from .param_google_sheet import t_param_google_sheet
from .param_google_sheet_tokens import t_param_google_sheet_tokens
from .param_scheduled_tasks import t_param_scheduled_tasks
from .param_stock_metadata import t_param_stock_metadata
from .param_system_configs import t_param_system_configs
from .param_task_logs import t_param_task_logs
from .param_task_result_summary_index import t_param_task_result_summary_index
from .param_task_results import t_param_task_results
from .param_task_results_return import t_param_task_results_return
from .param_task_templates import t_param_task_templates
from .param_xpl_analysis_jobs import t_param_xpl_analysis_jobs
from .stock_data_us import t_stock_data_us
from .stock_date import t_stock_date
from .stock_sms_msg import t_stock_smsmsg
from .stock_trs_account import t_stock_trs_account

__all__ = ['DeleteStockParamResultRequestDto',
 'GetSingleStockTemplateRequestDto',
 'GetStockParamResultListRequestDto',
 't_stock_param_result',
 'GetAreaListRequestDto',
 't_stock_data_area',
 'GetDataByPageListForWindowsRequestDto',
 'GetStockXtOrderListRequestDto',
 't_stock_xt_order',
 'GetDataConceptListRequestDto',
 't_stock_data_concept',
 'GetDataIndexListRequestDto',
 't_stock_data_index',
 'GetDataIndustryListRequestDto',
 't_stock_data_industry',
 'GetDataStateListRequestDto',
 'GetStockXtDataListRequestDto',
 'UpdateStateRequestDto',
 'UpdateUserRequestDto',
 't_stock_xt_data',
 'GetDicListForSelectRequestDto',
 'GetEastMoneyStockQuoteRequestDto',
 'GetEastMoneyStockTrendsRequestDto',
 'GetListHisPageRequestDto',
 'GetStockDataAllListRequestDto',
 'GetStockDataListPageRequestDto',
 'GetStockDataListRequestDto',
 'GetStockDataRequestDto',
 'GetStockListByCodeRequestDto',
 't_stock_data',
 'GetModelListRequestDto',
 'sys_model',
 'GetStockATargetCondListRequestDto',
 'GetStockATargetCondSearchRequestDto',
 't_stock_a_target_cond',
 'GetStockATargetListRequestDto',
 't_stock_a_target',
 'GetStockATargetLogListRequestDto',
 't_stock_a_target_log',
 'GetStockCnOrderListRequestDto',
 't_stock_cn_order',
 'GetStockDataVolumeHisListRequestDto',
 'GetStockDataVolumeListRequestDto',
 'GetStockDataVolumeRequestDto',
 't_stock_data_volume',
 't_stock_data_volume_his',
 'GetStockFinancialDataRequestDto',
 't_stock_financial_data',
 'GetStockMinuteTickListRequestDto',
 'LongIdRequestDto',
 't_stock_minute_tick',
 'GetStockParamDataListRequestDto',
 't_stock_param_data',
 'GetStockParamTemplateListRequestDto',
 't_stock_param_template',
 'GetStockParamTuningListRequestDto',
 't_stock_param_tuning',
 'GetStockTop10CirculatingListRequestDto',
 't_stock_top10_circulating',
 'GetStockTrsChildOrderListRequestDto',
 't_stock_trs_child_orders',
 'GetStockTrsDealRecordsListRequestDto',
 't_stock_trs_deal_records',
 'GetStockTrsEventsLogListRequestDto',
 't_stock_trs_events_log',
 'GetStockTrsOrderListRequestDto',
 'GetStockTrsOrderStatusRequestDto',
 't_stock_trs_order',
 'GetStockTrsPoolListRequestDto',
 't_stock_trs_pool',
 'GetStockTrsPositionSnapshottRequestDto',
 't_stock_trs_position_snapshot',
 'GetStockXtCreditDetailListRequestDto',
 't_stock_xt_credit_detail',
 'GetStockXtDataTradingListRequestDto',
 't_stock_xt_data_trading',
 'GetStockXtPositionListForWindowsRequestDto',
 'GetStockXtPositionListRequestDto',
 't_stock_xt_position',
 'GetStockXtTradeListForWindowsRequestDto',
 'GetStockXtTradeListRequestDto',
 't_stock_xt_trade',
 'GetSysLogListRequestDto',
 'GetSysRoleListRequestDto',
 'IsRoleRequestDto',
 'sys_role',
 'GetSysUserListRequestDto',
 'GetUserListForSelectRequestDto',
 'RegisterRequestDto',
 'UpdatePwdRequestDto',
 'UserEnableOrUnEnableRequestDto',
 'sys_user',
 'IdRequestDto',
 'RequsetPageDto',
 't_param_backtest_product_result_cache',
 'ModelTypeEnum',
 'ResponseDto',
 'UserStatusEnum',
 'ParamStringIdRequestDto',
 't_param_tasks',
 't_param_backtest_sheet_run_locks',
 't_param_google_sheet',
 't_param_google_sheet_tokens',
 't_param_scheduled_tasks',
 't_param_stock_metadata',
 't_param_system_configs',
 't_param_task_logs',
 't_param_task_result_summary_index',
 't_param_task_results',
 't_param_task_results_return',
 't_param_task_templates',
 't_param_xpl_analysis_jobs',
 't_stock_data_us',
 't_stock_date',
 't_stock_smsmsg',
 't_stock_trs_account']

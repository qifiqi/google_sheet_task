"""SystemConfig 默认配置种子（自 app/config.py 原位迁出，键/值/描述逐条等价）。

唯一消费方：app/config.py::init_config()（启动期幂等补种，缺键才写、不覆盖已有值）。
"""


def build_default_configs():
    """构建 SystemConfig 种子字典。

    全局与分类型并发键由任务注册表提供（app/services/task/registry.py），
    新增任务类型自动补种；此处保持调用期导入，与拆分前 init_config() 的导入时机一致。
    """
    from app.services.task.registry import CONCURRENCY_CONFIG_DEFAULTS, CONCURRENCY_LABELS

    default_configs = {
        'spreadsheet_id': {
            'value': '1MGRmNA6SFJKLMPwO31FWLsOwmOkfzCYR6rQ4Yoe-IYU',
            'description': '默认 Google Spreadsheet ID（C1.1 共享模板），为空时需在任务或页面配置中指定。',
        },
        'sheet_name': {
            'value': 'control',
            'description': '默认工作表名称（C1.1 模板控制页）。',
        },
        'token_file': {
            'value': 'data/token.json',
            'description': '默认单 token 文件路径；启用 token 池后可被任务级 token_file 覆盖。',
        },
        'google_sheet_token_global_max_usage': {
            'value': 0,
            'description': 'Google token 全局总占用上限，0 表示不限制。',
        },
        'google_sheet_http_timeout': {
            'value': 30,
            'description': 'Google Sheet 请求默认 HTTP 超时，单位秒。',
        },
        'backtest_training_token_id': {
            'value': '',
            'description': 'Backtest training task token_id from google_sheet_tokens table.',
        },
        'proxy_url': {
            'value': None,
            'description': 'Google Sheet 请求默认代理地址，为空表示直连。',
        },
        'dfcf_kline_proxy_enabled': {
            'value': False,
            'description': '是否为东方财富 K 线接口启用 proxy_manager 代理。true 启用，false 直连。',
        },
        'min_kline_rows': {
            'value': '',
            'description': '统一K线最小数据量下限（C3/C4/C5/C7、单品回测、多品回测共用）；留空时 C3/多品回测默认100条，其余默认30条。',
        },
        # 全局并发上限为 task_max_workers（registry 派生种子，见下方并发键块）；
        # 旧 max_concurrent_tasks 双轨已废弃（2026-10 常量收敛 P2），存量库中的
        # 历史配置行无消费方，可留在库中但不再生效。
        # 全局与分类型并发上限：key/默认值由任务注册表提供
        # （app/services/task/registry.py），新增任务类型自动补种。改值即时生效，无需重启。
        **{
            key: {
                'value': value,
                'description': (
                    f'{CONCURRENCY_LABELS[key]} 并发上限（达到上限时任务启动被拒绝并保持待执行，'
                    '等待下次手动或调度启动）。'
                ),
            }
            for key, value in CONCURRENCY_CONFIG_DEFAULTS.items()
        },
        'task_timeout': {
            'value': 36000,
            'description': '单个任务执行超时时间，单位秒。',
        },
        'task_status_check_timeout': {
            'value': 600,
            'description': '任务状态检查超时时间，单位秒。',
        },
        'rate_limit_analyze': {
            'value': 10,
            'description': '绩效分析接口限流：每分钟每用户次数（0=不限）。',
        },
        'rate_limit_heavy': {
            'value': 6,
            'description': '重计算端点（Excel 导入/比例计算）限流：每分钟每用户次数（0=不限）。',
        },
        'rate_limit_rebuild': {
            'value': 2,
            'description': '模型汇总重建端点限流：每分钟每用户次数（0=不限）。',
        },
        'rate_limit_export': {
            'value': 10,
            'description': '导出端点限流：每分钟每用户次数（0=不限）。',
        },
        'word_export_cache_ttl_minutes': {
            'value': 10,
            'description': 'Word 报告导出缓存时长（分钟）：相同查询条件在期内直接回放缓存文件，调大可延长缓存；0 或负数关闭缓存。',
        },
        'watchdog_enabled': {
            'value': True,
            'description': '是否启用任务看门狗线程。',
        },
        'watchdog_interval_seconds': {
            'value': 1800,
            'description': '看门狗巡检间隔，单位秒。',
        },
        'watchdog_log_timeout_minutes': {
            'value': 30,
            'description': '任务日志超过多少分钟未更新时，判定为可能卡死。',
        },
        'execution_delay_min': {
            'value': 20,
            'description': '批量执行时每步最小延迟，单位秒。',
        },
        'execution_delay_max': {
            'value': 30,
            'description': '批量执行时每步最大延迟，单位秒。',
        },
        'sheet_settle_seconds': {
            'value': 20,
            'description': 'Google Sheet 清空/重写输入后等待模型响应的时长，单位秒（0-300）。',
        },
        'sheet_refresh_attempts': {
            'value': [5, 15, 25, 35],
            'description': 'C3/C4/C5/C7/回测轮询中额外触发参数刷新的检查轮次（JSON 数组，0 为第一次检查）。',
        },
        'sheet_refresh_interval_attempts': {
            'value': 10,
            'description': 'C3/C4/C5/C7/回测轮询中每隔多少次检查刷新一次参数（0=关闭周期刷新）。',
        },
        'api_retry_max_attempts': {
            'value': 10,
            'description': '外部 API 最大重试次数。',
        },
        'api_retry_delay': {
            'value': 30,
            'description': '外部 API 重试间隔，单位秒。',
        },
        'frontend_polling_interval': {
            'value': 15000,
            'description': '前端任务轮询间隔，单位毫秒。',
        },
        'dashboard_refresh_interval': {
            'value': 30000,
            'description': '仪表盘自动刷新间隔，单位毫秒。',
        },
        'detail_refresh_interval': {
            'value': 60000,
            'description': '详情页自动刷新间隔，单位毫秒。',
        },
        'log_polling_interval': {
            'value': 3000,
            'description': '日志轮询间隔，单位毫秒。',
        },
        'log_realtime_interval': {
            'value': 3000,
            'description': '日志实时刷新间隔，单位毫秒。',
        },
        'tasks_admin_refresh_interval': {
            'value': 30000,
            'description': '管理页任务列表刷新间隔，单位毫秒。',
        },
        'parameter_positions': {
            'value': ['B6', 'B7', 'B9', 'B10', 'B11', 'B12'],
            'description': 'Google Sheet 主流程参数输入单元格位置列表。',
        },
        'check_positions': {
            'value': ['I6', 'I7', 'I9', 'I10', 'I11', 'I12'],
            'description': 'Google Sheet 主流程勾选/触发单元格位置列表。',
        },
        'result_positions': {
            'value': ['I15', 'I16', 'I17', 'I18', 'I19', 'I20', 'I21', 'I22', 'I23'],
            'description': 'Google Sheet 主流程结果读取单元格位置列表。',
        },

        "C3_commission_cell": {
            "value": "B5",
            "description": "C3 模板佣金单元格位置。",
        },

        'c3_parameter_positions': {
            'value': ['B5','B6', 'B7', 'B8','B9', 'B10', 'B11', 'B12'],
            'description': 'C3 模板参数输入单元格位置列表。',
        },
        'c3_check_positions': {
            'value': ["I15","I16"],
            'description': 'C3 模板勾选/触发单元格位置列表。',
        },
        'c3_input_column_d': {
            'value': 'D',
            'description': 'C3 模板输入列 D 的列标识。',
        },
        'c3_input_column_e': {
            'value': 'E',
            'description': 'C3 模板输入列 E 的列标识。',
        },
        'c3_output_range_1': {
            'value': 'I2:I23',
            'description': 'C3 模板第一段结果读取区域。',
        },
        'c3_output_range_2': {
            'value': 'I15:I23',
            'description': 'C3 模板第二段结果读取区域。',
        },
        'c3_output_column_K': {
            'value': 'K',
            'description': 'C3 模板输出列 K 的列标识。',
        },
        'c3_output_column_O': {
            'value': 'O',
            'description': 'C3 模板输出列 O 的列标识。',
        },


        'c4_input_column_a': {
            'value': 'A',
            'description': 'C4 模板输入列 A 的列标识。',
        },
        'c4_input_column_b': {
            'value': 'B',
            'description': 'C4 模板输入列 B 的列标识。',
        },
        'c4_output_range_1': {
            'value': 'D2:D20',
            'description': 'C4 模板第一段结果读取区域。',
        },
        'c4_output_range_2': {
            'value': 'D22:F25',
            'description': 'C4 模板第二段结果读取区域。',
        },
        'c4_output_column_j': {
            'value': 'J',
            'description': 'C4 模板输出列 J 的列标识。',
        },
        'c4_output_column_l': {
            'value': 'L',
            'description': 'C4 模板输出列 L 的列标识。',
        },

        'c5_parameter_positions': {
            'value': ['A1', 'B1'],
            'description': 'C5 模板参数输入单元格位置列表。',
        },
        'c5_check_positions': {
            'value': ['G1', 'H1'],
            'description': 'C5 模板勾选/触发单元格位置列表。',
        },
        'c5_input_column_a': {
            'value': 'A',
            'description': 'C5 模板输入列 A 的列标识。',
        },
        'c5_input_column_b': {
            'value': 'B',
            'description': 'C5 模板输入列 B 的列标识。',
        },
        'c5_output_range_1': {
            'value': 'D2:D20',
            'description': 'C5 模板第一段结果读取区域。',
        },
        'c5_output_range_2': {
            'value': 'D22:F25',
            'description': 'C5 模板第二段结果读取区域。',
        },
        'c5_output_column_j': {
            'value': 'J',
            'description': 'C5 模板输出列 J 的列标识。',
        },
        'c5_output_column_l': {
            'value': 'L',
            'description': 'C5 模板输出列 L 的列标识。',
        },

        'c7_parameter_positions': {
            'value': ['A1', 'B1'],
            'description': 'C5 模板参数输入单元格位置列表。',
        },
        'c7_check_positions': {
            'value': ['G1', 'H1'],
            'description': 'C5 模板勾选/触发单元格位置列表。',
        },
        'c7_input_column_a': {
            'value': 'A',
            'description': 'C5 模板输入列 A 的列标识。',
        },
        'c7_input_column_b': {
            'value': 'B',
            'description': 'C5 模板输入列 B 的列标识。',
        },
        'c7_0_3_kline_start_row': {
            'value': 2,
            'description': 'C7.0.3 OHLC K线输入起始行。',
        },
        'c7_0_3_kline_date_column': {
            'value': 'CC',
            'description': 'C7.0.3 OHLC K线日期列。',
        },
        'c7_0_3_kline_open_column': {
            'value': 'CD',
            'description': 'C7.0.3 OHLC K线开盘价列。',
        },
        'c7_0_3_kline_high_column': {
            'value': 'CE',
            'description': 'C7.0.3 OHLC K线最高价列。',
        },
        'c7_0_3_kline_low_column': {
            'value': 'CF',
            'description': 'C7.0.3 OHLC K线最低价列。',
        },
        'c7_0_3_kline_close_column': {
            'value': 'CG',
            'description': 'C7.0.3 OHLC K线收盘价列。',
        },
        'c7_0_3_output_range_1': {
            'value': 'D2:D20',
            'description': 'C7.0.3 第一段结果读取区域，与 C5 一致。',
        },
        'c7_0_3_output_range_2': {
            'value': 'D22:F25',
            'description': 'C7.0.3 第二段结果读取区域，与 C5 一致。',
        },
        'c7_0_3_output_column_j': {
            'value': 'J',
            'description': 'C7.0.3 指数收益输出列，与 C5 一致。',
        },
        'c7_0_3_output_column_l': {
            'value': 'L',
            'description': 'C7.0.3 起始收益输出列，与 C5 一致。',
        },
        # 'c7_output_range_1': {
        #     'value': 'D2:F4',
        #     'description': 'C5 模板第一段结果读取区域。',
        # },
        'c7_output_range_1': {
            'value': 'D8:D26',
            'description': 'C5 模板第一段结果读取区域。',
        },
        'c7_output_range_2': {
            'value': 'D28:F31',
            'description': 'C5 模板第二段结果读取区域。',
        },
        'c7_output_column_j': {
            'value': 'J',
            'description': 'C5 模板输出列 J 的列标识。',
        },
        'c7_output_column_l': {
            'value': 'L',
            'description': 'C5 模板输出列 L 的列标识。',
        },

    }
    return default_configs

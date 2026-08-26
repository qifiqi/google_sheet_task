"""CSV report rendering for performance-analysis results."""

import math
from datetime import datetime
from io import BytesIO

import pandas as pd


class PerformanceReportExporterMixin:
    @staticmethod
    def _resolve_export_model_name(data, analyze_result):
        """从导出数据、文件标题和 Sheet 名中识别对应模型版本。"""
        sheet_result = analyze_result.get('sheet_result', {}) if isinstance(analyze_result, dict) else {}
        sources = [
            data.get('model_name', ''),
            data.get('filename_title', ''),
            *(sheet_result.keys() if isinstance(sheet_result, dict) else []),
        ]
        for source in sources:
            source = str(source).upper()
            for model_name in ('C7', 'C5', 'C4', 'C3'):
                if model_name in source:
                    return model_name
        return 'C3'

    @staticmethod
    def _format_export_metric(value, format_spec):
        """按给定格式输出指标，缺失值统一展示为占位符。"""
        return '--' if value is None else f"{value:{format_spec}}"

    @staticmethod
    def _max_yearly_repair_days(yearly_repair_days):
        """返回年度最大修复天数中的最大值。"""
        if not isinstance(yearly_repair_days, dict):
            return None
        values = [
            value for value in yearly_repair_days.values()
            if isinstance(value, (int, float)) and not isinstance(value, bool)
            and math.isfinite(value)
        ]
        return max(values) if values else None

    def format_export_file_data(self, data):
        """将分析结果整理为 XPL 导出文件需要的二维数据。"""
        analyze_result = data.get('analyze_result')
        model_name = self._resolve_export_model_name(data, analyze_result)

        excess_returns = analyze_result.get('excess_returns')
        excess_return = [i for i in excess_returns if i['year'] == 'all'][0]
        start_end_date = excess_return.get('start_end_date')
        # 拆分为起始和结束时间
        start_str, end_str = start_end_date.split('/')

        _start_date = datetime.strptime(start_str, "%Y-%m-%d %H:%M:%S")
        _end_date = datetime.strptime(end_str, "%Y-%m-%d %H:%M:%S")

        start_date = _start_date.strftime("%Y/%m/%d")
        end_date = _end_date.strftime("%Y/%m/%d")

        # 年化收益
        index_annualized_return = excess_return.get('index_annualized_return')
        start_annualized_return = excess_return.get('start_annualized_return')
        # 盈利年份百分比
        index_profit_annual = analyze_result.get('index_profit_annual')
        start_profit_annual = analyze_result.get('start_profit_annual')
        # 月盈利百分比

        index_profit_monthly = analyze_result.get('index_profit_monthly')
        index_profit_monthly_all = [i for i in index_profit_monthly if i['year'] == 'all'][0]
        index_profit_monthly_percentage = index_profit_monthly_all.get('profit_monthly_percentage')
        start_profit_monthly = analyze_result.get('start_profit_monthly')
        start_profit_monthly_all = [i for i in start_profit_monthly if i['year'] == 'all'][0]
        start_profit_monthly_percentage = start_profit_monthly_all.get('profit_monthly_percentage')

        index_sharpe_ratios_all = analyze_result.get('index_sharpe_ratios').get('all')
        start_sharpe_ratios_all = analyze_result.get('start_sharpe_ratios').get('all')
        # 平均月收益率
        index_avg_monthly_return = index_sharpe_ratios_all.get("avg_monthly_return")
        start_avg_monthly_return = start_sharpe_ratios_all.get("avg_monthly_return")
        # 月收益率波动率
        index_monthly_return_volatility = analyze_result.get('index_monthly_return_volatility')
        start_monthly_return_volatility = analyze_result.get('start_monthly_return_volatility')
        # 年化超额收益
        annualized_return_diff = excess_return.get('annualized_return_diff')
        # 跑赢年份(百分比）
        outperform_year = analyze_result.get('outperform_year')
        # 月超额收益胜率
        monthly_excess_return_percentage = analyze_result.get('monthly_excess_return_percentage')
        monthly_excess_return_percentage_last = [i for i in monthly_excess_return_percentage if i['year'] == 'all'][0]
        monthly_excess_return_percentage_last_return = monthly_excess_return_percentage_last.get('excess_return')
        # 平均月超额
        monthly_excess_returns = analyze_result.get('monthly_excess_returns')
        avg_monthly_excess_returns = sum(i['monthly_excess_return_diff'] for i in monthly_excess_returns) / len(
            monthly_excess_returns)
        # 月超额波动率
        monthly_excess_volatility = analyze_result.get('monthly_excess_volatility')
        # 年最大超额回撤
        index_maximum_drawdown = analyze_result.get('index_maximum_drawdown')
        start_maximum_drawdown = analyze_result.get('start_maximum_drawdown')
        year_excess_returns = [int(i['year']) for i in excess_returns if
                               i['annualized_return_diff'] > 0 and i['year'] != 'all']
        index_year_maximum_drawdown = {i['year']: i for i in index_maximum_drawdown['year_maximum_drawdown'] if
                                       i['year'] in year_excess_returns}
        start_year_maximum_drawdown = {i['year']: i for i in start_maximum_drawdown['year_maximum_drawdown'] if
                                       i['year'] in year_excess_returns}
        max_drawdown_list = []
        for k, v in index_year_maximum_drawdown.items():
            index_drawdown = v['drawdown']
            start_drawdown = start_year_maximum_drawdown.get(k).get('drawdown')
            max_drawdown_list.append(
                start_drawdown - index_drawdown
            )

        max_drawdown = max(max_drawdown_list) if max_drawdown_list else 0

        # excess_drawdown_winning_rate = analyze_result.get('excess_drawdown_winning_rate')
        # 超额回撤胜率
        excess_drawdown_winning_rate = analyze_result.get('excess_drawdown_winning_rate')
        # 年最大回撤
        start_maximum_drawdown = analyze_result.get('start_maximum_drawdown')
        total_maximum_drawdown = start_maximum_drawdown.get('total_maximum_drawdown')
        start_drawdown = total_maximum_drawdown.get('drawdown')

        # 夏普比率
        index_sharpe_ratio = index_sharpe_ratios_all.get('sharpe_ratio')
        start_sharpe_ratio = start_sharpe_ratios_all.get('sharpe_ratio')
        # 卡玛比率
        index_kama_ratios = analyze_result.get('index_kama_ratio')
        index_kama_ratio_all = [i for i in index_kama_ratios if i['year'] == 'all'][0]
        index_kama_ratio = index_kama_ratio_all.get('kama_ratio')
        start_kama_ratios = analyze_result.get('start_kama_ratio')
        start_kama_ratio_all = [i for i in start_kama_ratios if i['year'] == 'all'][0]
        start_kama_ratio = start_kama_ratio_all.get('kama_ratio')

        # 索提诺比率
        index_sotino_ratios = analyze_result.get('index_sotino_ratio')
        index_sotino_ratio_all = [i for i in index_sotino_ratios if i['year'] == 'all'][0]
        index_sotino_ratio = index_sotino_ratio_all.get('sotino_ratio')
        start_sotino_ratios = analyze_result.get('start_sotino_ratio')
        start_sotino_ratio_all = [i for i in start_sotino_ratios if i['year'] == 'all'][0]
        start_sotino_ratio = start_sotino_ratio_all.get('sotino_ratio')

        excess_sharp = analyze_result.get('excess_sharp')
        excess_of_promissory_note = analyze_result.get('excess_of_promissory_note')
        # 最大回测修复天数
        start_maximum_number_of_backtest_repair_days = analyze_result.get(
            'start_maximum_number_of_backtest_repair_days')
        excess_maximum_number_of_backtest_repair_days = analyze_result.get(
            'excess_maximum_number_of_backtest_repair_days')
        year_index_max_repair_days = self._max_yearly_repair_days(
            analyze_result.get('year_index_yearly_max_repair_days')
        )
        year_start_max_repair_days = self._max_yearly_repair_days(
            analyze_result.get('year_start_yearly_max_repair_days')
        )

        data_1_2d = [
            ["标的", "", "", ""],
            ["回测区间", f"{start_date}-{end_date}", "", ""],
            ["指标类型", "指标", "指数", model_name],
            ["绝对收益", "年化收益", f"{index_annualized_return:.2%}", f"{start_annualized_return:.2%}"],
            ["绝对收益", "盈利年份百分比", f"{index_profit_annual:.2%}", f"{start_profit_annual:.2%}"],
            ["绝对收益", "月盈利百分比", f"{index_profit_monthly_percentage:.2%}",
             f"{start_profit_monthly_percentage:.2%}"],
            ["绝对收益", "平均月收益率", f"{index_avg_monthly_return:.2%}", f"{start_avg_monthly_return:.2%}"],
            ["绝对收益", "月收益率波动率", f"{index_monthly_return_volatility:.2%}",
             f"{start_monthly_return_volatility:.2%}"],
            ["相对收益", "年化超额收益", "", f"{annualized_return_diff:.2%}"],  # 注意：第二列是空
            ["相对收益", "跑赢年份(百分比）", "", f"{outperform_year:.2%}"],
            ["相对收益", "月超额收益胜率", "", f"{monthly_excess_return_percentage_last_return:.2%}"],
            ["相对收益", "平均月超额", "", f"{avg_monthly_excess_returns:.2%}"],
            ["相对收益", "月超额波动率", "", f"{monthly_excess_volatility:.2%}"],
            ["回撤", "年最大超额回撤", "", f"{max_drawdown:.2%}"],
            ["回撤", "超额回撤胜率", "", f"{excess_drawdown_winning_rate:.2%}"],
            ["回撤", "年最大回撤", "", f"-{start_drawdown:.2%}"],
            ["回撤", "最大修复天数", "", f"{start_maximum_number_of_backtest_repair_days}"],
            ["回撤", "超额最大修复天数", "", f"{excess_maximum_number_of_backtest_repair_days}"],
            ["回撤", "年最大回测修复天数", self._format_export_metric(year_index_max_repair_days, '.0f'),
             self._format_export_metric(year_start_max_repair_days, '.0f')],
            ["比率", "夏普比率", self._format_export_metric(index_sharpe_ratio, '.2'),
             self._format_export_metric(start_sharpe_ratio, '.2')],  # 注意：数字后面有空格
            ["比率", "卡玛比率", self._format_export_metric(index_kama_ratio, '.2'),
             self._format_export_metric(start_kama_ratio, '.2')],
            ["比率", "索提诺比率", self._format_export_metric(index_sotino_ratio, '.2'),
             self._format_export_metric(start_sotino_ratio, '.2')],
            ["夏普", "超额夏普", f"", self._format_export_metric(excess_sharp, '.2')],
            ["索提诺", "超额索提诺比率", f"", self._format_export_metric(excess_of_promissory_note, '.2')]
        ]

        data_2_2d = [
            ["收益率明细"],
            ["年份"],
            ["指数"],
            ["策略"],
            ["超额"]
        ]
        for excess_return in excess_returns:
            if excess_return['year'] == 'all':
                continue
            data_2_2d[0].append("")
            data_2_2d[1].append(excess_return['year'])
            data_2_2d[2].append(f"{excess_return['index_annualized_return']:.2%}")
            data_2_2d[3].append(f"{excess_return['start_annualized_return']:.2%}")
            data_2_2d[4].append(f"{excess_return['annualized_return_diff']:.2%}")

        data_3_2d = [
            ["回撤明细"],
            ["年份"],
            ["指数"],
            ["策略"],
            ["超额回撤"],
        ]
        index_year_maximum_drawdown = index_maximum_drawdown['year_maximum_drawdown']
        for index_drawdown, start_drawdown in zip(index_year_maximum_drawdown,
                                                  start_maximum_drawdown['year_maximum_drawdown']):
            data_3_2d[0].append("")
            data_3_2d[1].append(str(index_drawdown['year']))
            data_3_2d[2].append(f"-{index_drawdown['drawdown']:.2%}")
            data_3_2d[3].append(f"-{start_drawdown['drawdown']:.2%}")
            excessive_backtesting = f"{start_drawdown['drawdown'] - index_drawdown['drawdown']:.2%}"
            excessive_backtesting = excessive_backtesting.replace('-',
                                                                  '') if '-' in excessive_backtesting else '-' + excessive_backtesting
            data_3_2d[4].append(excessive_backtesting)

        data_4_2d = [
            ['', "策略收益率", "月超额"]
        ]
        for monthly_excess in monthly_excess_returns:
            data_4_2d.append(
                [
                    monthly_excess['date'],
                    f"{monthly_excess['start_monthly_return']:.2%}",
                    f"{monthly_excess['monthly_excess_return_diff']:.2%}"
                ]
            )

        target_df = pd.DataFrame('', index=range(200), columns=range(20))

        data_2_col_num = len(data_2_2d[0])
        data3_col_num = len(data_3_2d[0])
        # 计算需要赋值的行数
        data_4_start_row = 3
        data_4_end_row = data_4_start_row + len(data_4_2d)

        target_df.iloc[0:len(data_1_2d), 0:4] = data_1_2d
        target_df.iloc[24:29, 0:data_2_col_num] = data_2_2d
        target_df.iloc[30:35, 0:data3_col_num] = data_3_2d
        target_df.iloc[data_4_start_row:data_4_end_row, 9:12] = data_4_2d

        return target_df

    def export_file(self, data):
        """根据分析结果生成可下载的 XPL Excel 文件。"""
        if not data:
            raise ValueError("data不能为空")

        file_data = self.format_export_file_data(data)
        csv_buffer = BytesIO()

        # 将DataFrame写入CSV（注意编码）
        file_data.to_csv(csv_buffer, index=False, header=False, encoding='utf-8')

        # 重置指针到文件开头
        csv_buffer.seek(0)

        return csv_buffer, 'text/csv'

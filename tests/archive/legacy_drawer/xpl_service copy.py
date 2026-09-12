import json
import logging
import math
import re
from datetime import datetime
from io import BytesIO
from typing import List, Dict, Any, Tuple

import numpy as np
import pandas as pd

from app.services.config_manager import get_config_manager
from app.services.google_sheet_client import GoogleSheet
from app.utils.logger import get_logger

logger = get_logger(__name__)


class XPLAnalyzer:
    """
    Excel数据收益率分析器
    负责处理Excel数据并计算相关指标
    """

    def __init__(self):
        self.data = []
        self.metrics = {}

    @staticmethod
    def calculate_max_drawdown_by_year_and_total(df):
        """
        计算按年份和总计的最大回撤
        Calculate maximum drawdown by year and total

        Args:
            df: 包含'year'、'date'、'net_value'列的DataFrame
                 Contains 'year', 'date', 'net_value' columns

        Returns:
            dict: 包含年度最大回撤和总计最大回撤的数据
                  Contains annual and total maximum drawdown data
                - year_maximum_drawdown: 每年最大回撤记录列表
                                        List of annual maximum drawdown records
                - total_maximum_drawdown: 总计最大回撤记录
                                        Total maximum drawdown record
        """
        if df.empty:
            return {"year_maximum_drawdown": [], 'total_maximum_drawdown': {}}

        result = {"year_maximum_drawdown": [], 'total_maximum_drawdown': {}}
        ordered_df = df.sort_values('date').reset_index(drop=True).copy()

        # 按年计算最大回撤，使用 cummax 避免逐行切片导致的 O(n²) 开销。
        yearly_df = ordered_df.copy()
        yearly_df['running_max'] = yearly_df.groupby('year', sort=False)['net_value'].cummax()
        yearly_df['drawdown'] = np.where(
            yearly_df['running_max'] > 0,
            (yearly_df['running_max'] - yearly_df['net_value']) / yearly_df['running_max'],
            0.0,
        )
        yearly_df['drawdown'] = yearly_df['drawdown'].fillna(0.0)

        yearly_idx = yearly_df.groupby('year', sort=False)['drawdown'].idxmax()
        yearly_rows = yearly_df.loc[yearly_idx].sort_values('year')
        for _, row in yearly_rows.iterrows():
            row_dict = row.drop(labels=['running_max']).to_dict()
            row_dict['date'] = row_dict['date'].strftime('%Y-%m-%d')
            result['year_maximum_drawdown'].append(row_dict)

        # 计算总计最大回撤
        total_df = ordered_df.copy()
        total_df['running_max'] = total_df['net_value'].cummax()
        total_df['drawdown'] = np.where(
            total_df['running_max'] > 0,
            (total_df['running_max'] - total_df['net_value']) / total_df['running_max'],
            0.0,
        )
        total_df['drawdown'] = total_df['drawdown'].fillna(0.0)

        max_drawdown_row = total_df.loc[total_df['drawdown'].idxmax()].drop(labels=['running_max']).to_dict()
        max_drawdown_row['date'] = max_drawdown_row['date'].strftime('%Y-%m-%d')
        result['total_maximum_drawdown'].update(max_drawdown_row)

        return result

    @staticmethod
    def calculate_year_returns(df):
        """
        计算基金的年度收益率（按年分组计算）
        Calculate monthly returns of the fund (grouped by year)

        参数/Args:
            df: DataFrame，包含净值数据的DataFrame，必须有['year', 'net_value', 'date']列
                DataFrame containing net value data, must have ['year', 'net_value', 'date'] columns

        返回/Returns:
            list: 包含年度收益率信息的字典列表，每个字典包含:
                  List of dictionaries containing monthly return information, each dictionary contains:
                - 'year_month': 年月标识 Year and month identifier
                - 'annual_return': 年度收益率（小数形式） annual_return (in decimal)
                - 'year': 年份 Year
                - 'date': 时间戳 Timestamp
        """
        if df.empty:
            return []

        ordered_df = df.sort_values('date').reset_index(drop=True)
        yearly_summary = ordered_df.groupby('year', sort=False).agg(
            start_net_value=('net_value', 'first'),
            end_net_value=('net_value', 'last'),
            end_date=('date', 'last'),
        ).reset_index()

        yearly_summary['comparison_net_value'] = yearly_summary['end_net_value'].shift(1)
        yearly_summary.loc[0, 'comparison_net_value'] = yearly_summary.loc[0, 'start_net_value']
        yearly_summary['annual_return'] = (
            yearly_summary['end_net_value'] / yearly_summary['comparison_net_value'] - 1
        ).round(4)

        annual_returns = []
        for _, row in yearly_summary.iterrows():
            annual_returns.append({
                'year_month': str(row['year']),
                'annual_return': float(row['annual_return']),
                'year': str(row['year']),
                'net_value': row['end_net_value'],
                'date': row['end_date'].strftime('%Y-%m-%d'),
            })

        return annual_returns

    @staticmethod
    def calculate_sharpe_for_period(monthly_subset, period_name, annualization_factor=12):
        """
        # 定义计算指定时间段夏普比率的内部函数
        # Define inner function to calculate Sharpe ratio for a specific period
        计算指定时间段的夏普比率
        Calculate Sharpe ratio for a specific time period

        参数/Args:
            monthly_subset: DataFrame，月度收益率数据子集
                           Subset of monthly return data
            period_name: str，时间段名称标识
                        Period name identifier
            annualization_factor: int，年化因子（默认12，用于月度数据）
                                Annualization factor (default 12 for monthly data)

        返回/Returns:
            float or None: 夏普比率值，如果数据不足则返回None
                          Sharpe ratio value, or None if insufficient data
        """
        if len(monthly_subset) < 2:
            return None

        # 获取月度收益率序列
        # Get monthly return series
        monthly_returns = monthly_subset['monthly_return']

        # 计算平均月收益率
        # Calculate average monthly return
        avg_monthly_return = monthly_returns.mean()

        # 计算月度收益率标准差（使用样本标准差）
        # Calculate monthly return standard deviation (population standard deviation)
        monthly_std = monthly_returns.std(ddof=1)

        # 计算年化标准差
        # Calculate annualized standard deviation
        annual_std = monthly_std * math.sqrt(annualization_factor)

        # 计算夏普比率（假设无风险利率为0）
        # Calculate Sharpe ratio (assuming risk-free rate is 0)
        if annual_std != 0:
            sharpe_ratio = avg_monthly_return * annualization_factor / annual_std
        else:
            sharpe_ratio = 0

        return {
            'sharpe_ratio': sharpe_ratio,  # 夏普比率 Sharpe ratio
            'annual_std_dev': annual_std,  # 年化标准差 Annualized standard deviation (%)
            'avg_monthly_return': avg_monthly_return,  # 平均月收益率 Average monthly return (%)
            'monthly_std_dev': monthly_std,  # 月度标准差 Monthly standard deviation (%)
            'month_count': len(monthly_subset),  # 月数 Number of months
            'start_date': monthly_subset['date'].min().strftime('%Y-%m'),  # 开始时间 Start date
            'end_date': monthly_subset['date'].max().strftime('%Y-%m')  # 结束时间 End date
        }

    @staticmethod
    def calculate_monthly_return_data(df):
        """
            计算月度收益率数据
        """
        monthly_df = XPLAnalyzer._build_monthly_return_frame(df)
        return monthly_df.to_dict(orient='records')

    @staticmethod
    def _build_monthly_return_frame(df: pd.DataFrame) -> pd.DataFrame:
        """构建月度收益率 DataFrame，便于多个指标复用。"""
        if df.empty:
            return pd.DataFrame(columns=['year_month', 'monthly_return', 'year', 'date'])

        ordered_df = df.sort_values('date').reset_index(drop=True)
        monthly_summary = ordered_df.groupby('year_month', sort=False).agg(
            month_end_net_value=('net_value', 'last'),
            year=('year', 'last'),
            date=('date', 'last'),
        ).reset_index()

        monthly_summary['comparison_net_value'] = monthly_summary['month_end_net_value'].shift(1).fillna(1.0)
        monthly_summary['monthly_return'] = (
            monthly_summary['month_end_net_value'] / monthly_summary['comparison_net_value'] - 1
        ).round(4)

        return monthly_summary[['year_month', 'monthly_return', 'year', 'date']]

    def calculate_sharpe_ratios_by_periods(self, df):
        """
        计算不同时间段的夏普比率
        Calculate Sharpe ratios for different time periods

        参数/Args:
            df: DataFrame，包含'date'、'net_value'、'year'、'year_month'列的数据框
                DataFrame containing 'date', 'net_value', 'year', 'year_month' columns

        返回/Returns:
            dict: 包含不同时间段夏普比率的字典
                  Dictionary containing Sharpe ratios for different time periods
                - 键为时间段标识（如'all', 'year_1_2023'等）
                  Keys are period identifiers (e.g., 'all', 'year_1_2023', etc.)
                - 值为包含夏普比率、年化标准差、平均月收益率等指标的字典
                  Values are dictionaries containing Sharpe ratio, annualized standard deviation, 
                  average monthly return, etc.
        """
        monthly_df = self._build_monthly_return_frame(df)
        return self._calculate_sharpe_ratios_from_monthly_df(
            monthly_df=monthly_df,
            start_date=df['date'].min(),
            end_date=df['date'].max(),
        )

    def _calculate_sharpe_ratios_from_monthly_df(
            self,
            monthly_df: pd.DataFrame,
            start_date: pd.Timestamp,
            end_date: pd.Timestamp,
    ) -> Dict[str, Any]:
        """基于已计算好的月度收益率复用夏普比率计算。"""
        total_months = len(monthly_df)
        logger.info(f"数据时间范围/Data time range: {start_date.date()} 到/to {end_date.date()}")
        logger.info(f"总数据月份数/Total months of data: {total_months}个月/months")

        results = {
            "all": self.calculate_sharpe_for_period(monthly_df, "all", 12),
        }

        years = sorted(monthly_df['year'].unique()) if not monthly_df.empty else []
        for i, year in enumerate(years):
            year_data = monthly_df[monthly_df['year'] == year]
            if len(year_data) >= 3:
                year_name = f"year_{i + 1}_{year}"
                logger.debug("计算年份/Calculating year %s, 总月数/Total months: %s", year_name, len(year_data))
                results[year_name] = self.calculate_sharpe_for_period(year_data, year_name, 12)

        years_desc = sorted(years, reverse=True)
        for i, year in enumerate(years_desc):
            year_data = monthly_df[monthly_df['year'] >= year]
            if len(year_data) >= 3:
                year_name = f"past_{i + 1}_years_since_{year}"
                logger.debug("计算滚动年份/Calculating rolling year %s, 总月数/Total months: %s", year_name, len(year_data))
                results[year_name] = self.calculate_sharpe_for_period(year_data, year_name, 12)

        return results

    def annualized_rate_return(self, df):
        """
        计算年化收益率
        计算公式：
            年化收益率 = (期末净值 / 期初净值) ^ (365 / 持有天数) - 1
        计算步骤：

            确定期初和期末净值：找到你要计算的那一年的第一个交易日净值（期初）和最后一个交易日净值（期末）。

            计算实际收益率：(期末净值 - 期初净值) / 期初净值。但更直接的是用期末净值/期初净值得到增长率。

            计算持有天数：这一年实际持有的天数（通常扣除非交易日，但用自然日365天标准化更常见）。

            年化处理：由于资金有时间价值，需要将这段期间的收益“放大”到一整年。这就是公式中 ^(365/持有天数) 的作用。
        """

        if df.empty:
            return []

        ordered_df = df.sort_values('date').reset_index(drop=True)
        annualized_rate_returns = []

        yearly_summary = ordered_df.groupby('year', sort=False).agg(
            start_value=('net_value', 'first'),
            end_value=('net_value', 'last'),
            start_date=('date', 'first'),
            end_date=('date', 'last'),
        ).reset_index()
        yearly_summary['holding_days'] = (yearly_summary['end_date'] - yearly_summary['start_date']).dt.days

        valid_years = yearly_summary[yearly_summary['holding_days'] > 0]
        for _, row in valid_years.iterrows():
            total_return = row['end_value'] / row['start_value']
            annualized_return = total_return ** (365 / row['holding_days']) - 1
            annualized_rate_returns.append({
                'year': str(row['year']),
                'annualized_return': annualized_return,
                'date': f"{row['start_date']}/{row['end_date']}",
            })

        if len(ordered_df) >= 2:
            start_value = ordered_df.iloc[0]['net_value']
            end_value = ordered_df.iloc[-1]['net_value']
            start_date = ordered_df.iloc[0]['date']
            end_date = ordered_df.iloc[-1]['date']
            holding_days = (end_date - start_date).days

            if holding_days > 0:
                total_return = end_value / start_value
                overall_annualized_return = total_return ** (365 / holding_days) - 1
                annualized_rate_returns.append({
                    'year': "all",
                    'annualized_return': overall_annualized_return,
                    'date': f"{start_date}/{end_date}",
                })

        return annualized_rate_returns

    def calculate_kama_ratio(self, annualized_rates: list, max_drawdown):
        """
        卡玛比率 年化收益率/区间最大回撤
        """
        max_drawdowns = max_drawdown
        if isinstance(max_drawdown, dict):
            max_drawdowns = {str(i['year']): i for i in max_drawdown['year_maximum_drawdown']}

            _max_drowdowns = [i['drawdown'] for i in max_drawdown['year_maximum_drawdown']]
            max_drawdowns['all'] = {**max_drawdown['total_maximum_drawdown']}
            max_drawdowns['all']['drawdown'] = max(_max_drowdowns)

        kama_ratios = []
        for item in annualized_rates:
            year = item['year']
            drawdown_item = max_drawdowns.get(year)
            drawdown = drawdown_item['drawdown']
            kama_ratio = item['annualized_return'] / drawdown

            kama_ratios.append({
                "year": year,
                "kama_ratio": kama_ratio,
                "annualized_return": item['annualized_return'],
                "drawdown": drawdown
            })

        return kama_ratios

    def calculate_sotino_ratio(self, monthly_data: pd.DataFrame):
        """
            所提诺比例
            月均年化收益率/下行标准差	
                # 下行边准差	所有月低于0的收益率的标准差*√12
                下行边准差	所有月的收益率的标准差*√12 （大于0的设置成0）
               月均年化收益率	月均收益率*12（所有月）
        """
        sotino_ratios = []
        # 计算月度收益率数据
        monthly_data_df = monthly_data.copy()
        monthly_groups = monthly_data_df.groupby('year')
        for year, year_df in monthly_groups:
            average_monthly_annualized_return = year_df['monthly_return'].mean() * 12
            # monthly_return_0 = year_df[year_df['monthly_return'] < 0]['monthly_return']
            monthly_return_0 = year_df['monthly_return'].mask(
                year_df['monthly_return'] > 0, 0
            )

            downside_standard_deviation = 0
            sotino_ratio = 0

            if len(monthly_return_0) > 1:
                downside_standard_deviation = monthly_return_0.std() * np.sqrt(12)
                sotino_ratio = average_monthly_annualized_return / downside_standard_deviation

            sotino_ratios.append({
                "year": year,
                "sotino_ratio": sotino_ratio,
                "average_monthly_annualized_return": average_monthly_annualized_return,
                "downside_standard_deviation": downside_standard_deviation
            })

        average_monthly_annualized_return = monthly_data_df['monthly_return'].mean() * 12
        # downside_standard_deviation = monthly_data_df[monthly_data_df['monthly_return'] < 0][
        #                                   'monthly_return'].std() * np.sqrt(12)
        downside_standard_deviation_monthly_return = monthly_data_df['monthly_return'].mask(
            monthly_data_df['monthly_return'] > 0, 0
        )
        downside_standard_deviation = downside_standard_deviation_monthly_return.std() * np.sqrt(12)
        sotino_ratio = average_monthly_annualized_return / downside_standard_deviation
        sotino_ratios.append({
            "year": "all",
            "sotino_ratio": sotino_ratio,
            "average_monthly_annualized_return": average_monthly_annualized_return,
            "downside_standard_deviation": downside_standard_deviation
        })
        return sotino_ratios

    def calculate_profit_annual_percentage(self, returns_rate):
        """
            盈利年百分比 = 年收益率大于0/区间总年份
            returns_rate 年度收益率列表 回报率
            
        """

        annual_return = [i for i in returns_rate if i['annual_return'] > 0]
        return len(annual_return) / len(returns_rate)

    def calculate_profit_monthly_percentage(self, returns_rate: pd.DataFrame):
        """
            盈利月百分比	月收益率大于0/区间总月份
            returns_rate 月度回报率列表 (每年)
        """

        profit_monthly_percentages = []
        year_groups = returns_rate.groupby('year')
        for year, year_df in year_groups:
            profit_monthly_percentages.append({
                "year": year,
                "profit_monthly_percentage": len(year_df[year_df['monthly_return'] > 0]) / len(
                    year_df['monthly_return'])
            })

        profit_monthly_percentages.append({
            "year": 'all',
            "profit_monthly_percentage": len(returns_rate[returns_rate['monthly_return'] > 0]) / len(
                returns_rate['monthly_return'])
        })
        return profit_monthly_percentages

    def calculate_monthly_return_volatility(self, returns_rate):
        """
            月收益率波动率 月收益率的标准差（夏普标准差） * *√12
        """
        return returns_rate['monthly_return'].std() * np.sqrt(12)

    def calculate_excess_return(self, index_annualized_rates, start_annualized_rates) -> pd.DataFrame:
        """
            超额收益	模型的年化收益-指数收益率
        """
        index_annualized_rates = pd.DataFrame(index_annualized_rates)
        start_annualized_rates = pd.DataFrame(start_annualized_rates)

        index_annualized_rates = index_annualized_rates.rename(
            columns={'annualized_return': 'index_annualized_return', 'date': "start_end_date"})
        start_annualized_rates = start_annualized_rates.rename(
            columns={'annualized_return': 'start_annualized_return'})

        excess_return = pd.merge(index_annualized_rates, start_annualized_rates, on='year')

        excess_return['annualized_return_diff'] = (
                excess_return['start_annualized_return'] -
                excess_return['index_annualized_return']
        )
        return excess_return

    def calculate_outperform_year(self, excess_return):
        """
            跑赢年份 超额大于0的年份/总年份
        """
        _excess_return = excess_return[excess_return['year'] != 'all']
        excess_greater_0 = _excess_return[_excess_return['annualized_return_diff'] > 0]
        return len(excess_greater_0) / len(_excess_return['annualized_return_diff'])

    def calculate_monthly_excess_return(self, index_monthly_returns_rate, start_monthly_returns_rate):
        """
            月超额收益
        """
        index_monthly_returns_rate = index_monthly_returns_rate.copy()
        start_monthly_returns_rate = start_monthly_returns_rate.copy()
        index_monthly_returns_rate = index_monthly_returns_rate.rename(
            columns={'monthly_return': 'index_monthly_return', 'year': "index_year", "date": "index_date"})
        start_monthly_returns_rate = start_monthly_returns_rate.rename(
            columns={'monthly_return': 'start_monthly_return'})

        excess_return = pd.merge(index_monthly_returns_rate, start_monthly_returns_rate, on='year_month')

        excess_return['monthly_excess_return_diff'] = round(
            (
                    excess_return['start_monthly_return'] -
                    excess_return['index_monthly_return']
            ),4
        )
        excess_return['date'] = excess_return['date'].dt.strftime("%Y/%m/%d")
        excess_return['index_date'] = excess_return['index_date'].dt.strftime("%Y/%m/%d")
        return excess_return

    def calculate_monthly_excess_return_percentage(self, excess_return):
        """
            月超额收益百分比	月超额大于0/区间总月份 (计算每年，和总)
        """
        year_excess_return = []
        year_groups = excess_return.groupby('year')

        for year, year_df in year_groups:
            excess_return_0 = year_df[year_df['monthly_excess_return_diff'] > 0]
            _excess_return = len(excess_return_0) / len(year_df['monthly_excess_return_diff'])
            year_excess_return.append({
                "year": year,
                "excess_return": _excess_return,
            })

        excess_return_0 = excess_return[excess_return['monthly_excess_return_diff'] > 0]
        _excess_return = len(excess_return_0) / len(excess_return['monthly_excess_return_diff'])
        year_excess_return.append({
            "year": 'all',
            "excess_return": _excess_return,
        })

        return year_excess_return

    def calculate_monthly_excess_volatility(self, excess_return: pd.DataFrame):
        """
            月超额波动率 月超额收益率的标准差（夏普标准差） * 根号12

        """
        return excess_return['monthly_excess_return_diff'].std() * np.sqrt(12)

    def calculate_excess_drawdown_winning_rate(self, index_maximum_drawdown, start_maximum_drawdown):
        """
            超额回撤胜率 年回撤小于指数的年份/总年份
        """
        index_year_maximum_drawdown = pd.DataFrame(index_maximum_drawdown['year_maximum_drawdown'])
        start_year_maximum_drawdown = pd.DataFrame(start_maximum_drawdown['year_maximum_drawdown'])

        index_year_maximum_drawdown = index_year_maximum_drawdown.rename(
            columns={'drawdown': 'index_drawdown'})
        start_year_maximum_drawdown = start_year_maximum_drawdown.rename(
            columns={'drawdown': 'start_drawdown'})

        maximum_drawdown = pd.merge(index_year_maximum_drawdown, start_year_maximum_drawdown, on='year')
        start_index = maximum_drawdown[maximum_drawdown['start_drawdown'] < maximum_drawdown['index_drawdown']]
        return len(start_index['start_drawdown']) / len(maximum_drawdown['start_drawdown'])

    def maximum_number_of_backtest_repair_days(self, data_df):
        """
            # 最大回测修复天数 = （出现最大净值最多次数的天数）（每年）(index，start)
        """

        data_df['previous_max'] = data_df['net_value'].expanding().max().shift(1)
        #
        # # 按年份分组处理
        # yearly_groups = data_df.groupby('year')
        #
        # max_net_value_count = {}
        #
        # for year, year_df in yearly_groups:
        #     if len(year_df) == 0:
        #         continue
        #     # mode_values = year_df['previous_max'].mode()
        #     mode_freq = year_df['previous_max'].value_counts().max()
        #
        #     max_net_value_count[year] = int(mode_freq)
        #
        # return max_net_value_count

        return int(data_df['previous_max'].value_counts().max())
        # d_max = data_df['previous_max'].max()
        # return data_df[data_df['previous_max'] == d_max]['previous_max'].count()

    def exceeding_maximum_number_of_backtest_repair_days(self, index_data, start_data):
        """
            # 最大回测修复天数 = （出现最大净值最多次数的天数）（每年）(index，start)
        """

        # start_index_data = {}
        #
        # for k,v in start_data.items():
        #     start_index_data[k] = v - index_data[k]
        # return start_index_data

        return start_data - index_data

    def get_xpl(self, data: List[Dict[str, Any]], date='date', val='daily_return'):
        if not data:
            return {}

        try:
            # 转换为DataFrame便于计算
            # Convert to DataFrame for calculation
            df = pd.DataFrame(data)
            df['date'] = pd.to_datetime(df[date])
            df = df.sort_values('date')

            # 1. 计算净值
            # Calculate net value
            df['net_value'] = 1 * (1 + df[val])

            # 2. 提取年份信息
            # Extract year and month information
            df['year'] = df['date'].dt.year
            df['month'] = df['date'].dt.month
            df['year_month'] = df['date'].dt.strftime('%Y-%m')

            # 计算月度收益率数据
            # Calculate monthly return data
            monthly_data = self.calculate_monthly_return_data(df)

            # 创建月度收益率DataFrame
            # Create monthly return DataFrame
            monthly_df = pd.DataFrame(monthly_data)

            # 记录数据范围信息
            # Record data range information
            start_date = df['date'].min()
            end_date = df['date'].max()
            total_months = len(monthly_df)

            logger.info(f"数据时间范围/Data time range: {start_date.date()} 到/to {end_date.date()}")
            logger.info(f"总数据月份数/Total months of data: {total_months}个月/months")
            # 计算全部数据的夏普比率
            # Calculate Sharpe ratio for all data
            res = self.calculate_sharpe_for_period(monthly_df, "all", 12)
            return res

        except Exception as e:
            logger.error(f"计算指标时出错: {str(e)}", exc_info=True)
            return {}

    def analyze(self, data, time_format: str = 'auto') -> Dict[str, Any]:
        """
        分析输入的Excel数据并返回结果和指标

        Args:
            data: 输入的文本数据
            time_format: 时间格式，默认为'auto'自动检测
            return_col: 收益率所在列（从1开始）

        Returns:
            Dict[str, Any]: 包含分析结果和指标的字典
        """
        try:
            parsed_data = None
            # 解析原始数据
            if isinstance(data, str):
                parsed_data = self._parse_input_data(data)
            elif isinstance(data, list):
                parsed_data = data
            if not parsed_data:
                raise ValueError("无法解析输入数据")

            # 计算指标
            metrics = self._calculate_metrics(parsed_data)

            # 准备返回结果
            return {
                'status': 'success',
                'results': metrics,
                # 'metrics': metrics
            }

        except Exception as e:
            logger.error(f"分析数据时出错: {str(e)}", exc_info=True)
            return {
                'status': 'error',
                'message': f"分析数据时出错: {str(e)}"
            }

    def _parse_input_data(self, data: str) -> List[Dict[str, Any]]:
        """
        解析输入的文本数据
        Parse input text data

        Args:
            data: 输入的文本数据 Input text data
            return_col: 收益率所在列（从1开始） Return column index (1-based)

        Returns:
            List[Dict[str, Any]]: 解析后的数据列表 Parsed data list
        """
        results = []
        lines = [line.strip() for line in data.split('\n') if line.strip()]

        for i, line in enumerate(lines):
            try:
                # 使用正则表达式分割，支持空格、制表符、逗号分隔
                # Split by whitespace, tabs, or commas using regex
                parts = re.split(r'[\s,]+', line.strip())
                if len(parts) < 2:
                    continue

                # 解析日期和收益率
                # Parse date and return value
                date_str = parts[0]
                val = parts[1]
                if '%' in val:
                    val = float(val.replace('%', '')) / 100
                index_return = float(val) if isinstance(val, str) else val
                index_return = round(index_return, 4)

                if len(parts) == 2:
                    results.append({
                        'date': date_str,  # 日期 Date
                        'daily_return': index_return,  # 每天收益率 Daily return
                    })
                    continue

                val = parts[2]
                if '%' in val:
                    val = float(val.replace('%', '')) / 100
                start_return = float(val) if isinstance(val, str) else val
                start_return = round(start_return, 4)

                # 添加到结果
                # Add to results
                results.append({
                    'date': date_str,  # 日期 Date
                    'index_return': index_return,  # 指数收益率 Index return
                    "start_return": start_return,  # 模型收益率 Start return
                })

            except (ValueError, IndexError) as e:
                logger.warning(f"解析行 {i + 1} 时出错: {line}")
                continue

        return results

    def _calculate_metrics(self, data: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        计算各项指标
        Calculate various metrics

        Args:
            data: 输入数据，包含日期和每日收益率
                  Input data containing date and daily returns

        Returns:
            Dict[str, Any]: 包含计算结果的字典
                          Dictionary containing calculation results
        """
        if not data:
            return {}

        try:
            # 转换为DataFrame便于计算
            # Convert to DataFrame for calculation
            df = pd.DataFrame(data)
            df['date'] = pd.to_datetime(df['date'])
            df = df.sort_values('date')

            # 1. 计算净值
            # Calculate net value
            df['net_value'] = 1 * (1 + df['daily_return'])

            # 2. 提取年份信息
            # Extract year and month information
            df['year'] = df['date'].dt.year
            df['month'] = df['date'].dt.month
            df['year_month'] = df['date'].dt.strftime('%Y-%m')

            # 3. 计算各项指标
            # Calculate various metrics
            maximum_drawdown = self.calculate_max_drawdown_by_year_and_total(df)
            returns_rate = self.calculate_year_returns(df)
            sharpe_ratios = self.calculate_sharpe_ratios_by_periods(df)

            # 4. 构建返回结果
            # Build return results
            result = {
                "maximum_drawdown": maximum_drawdown,  # 最大回撤
                "returns_rate": returns_rate,  # 收益率
                "sharpe_ratios": sharpe_ratios  # 夏普比率
            }

            # 打印调试信息
            # Print debug information
            logger.debug("Maximum Drawdown: %s", json.dumps(maximum_drawdown, indent=4, default=str))
            logger.debug("Monthly Returns: %s", json.dumps(returns_rate, indent=4, default=str))
            logger.debug("Sharpe Ratios: %s", json.dumps(sharpe_ratios, indent=4, default=str))

            return result

        except Exception as e:
            logger.error(f"计算指标时出错: {str(e)}", exc_info=True)
            return {}

    def analyze_v1(self, spreadsheet_id: str, google_sheet_name: str) -> Dict[str, Any]:
        """
        分析输入的Excel数据并返回结果和指标

        """
        try:
            # from app.services.da import data
            # parsed_data = self._parse_input_data(data)
            _data, _data_result, sheet_df = self.get_google_sheet_data(spreadsheet_id, google_sheet_name)
            # 计算指标
            metrics = self._calculate_metrics_v1(_data)

            metrics['sheet_result'] = _data_result
            # 准备返回结果
            return {
                'status': 'success',
                'results': metrics,
                # 'metrics': metrics
            }

        except Exception as e:
            logger.error(f"分析数据时出错: {str(e)}", exc_info=True)
            return {
                'status': 'error',
                'message': f"分析数据时出错: {str(e)}"
            }

    def _init_google_sheet(self, spreadsheet_id, sheet_name):
        """初始化Google Sheet连接"""
        try:
            config_data = get_config_manager().get_all_configs()
            token_file = config_data.get('token_file',
                                         r'D:\Users\Administrator\Desktop\谷歌参数批量校验\data\token.json')
            proxy_url = config_data.get('proxy_url', None)

            google_sheet = GoogleSheet(spreadsheet_id, sheet_name, token_file, proxy_url)
            if not google_sheet.worksheet:
                raise Exception("请先选择工作表")
            return google_sheet
        except Exception as e:
            error_msg = f"初始化Google Sheet连接失败: {str(e)}"
            raise error_msg

    @staticmethod
    def _parse_google_sheet_dates(date_series: pd.Series) -> pd.Series:
        """兼容 Google Sheet 中混合的序列日期和字符串日期。"""
        excel_base = pd.Timestamp('1899-12-30')
        text_series = date_series.astype(str).str.strip()
        numeric_values = pd.to_numeric(text_series, errors='coerce')
        parsed_dates = pd.Series(pd.NaT, index=date_series.index, dtype='datetime64[ns]')

        numeric_mask = numeric_values.notna()
        if numeric_mask.any():
            parsed_dates.loc[numeric_mask] = pd.to_timedelta(
                numeric_values.loc[numeric_mask],
                unit='d'
            ) + excel_base

        text_mask = (~numeric_mask) & text_series.ne('') & text_series.ne('nan') & text_series.ne('None')
        if text_mask.any():
            parsed_dates.loc[text_mask] = pd.to_datetime(
                text_series.loc[text_mask],
                errors='coerce'
            )

        return parsed_dates

    def get_google_sheet_data(self, spreadsheet_id: str, google_sheet_name: str) -> tuple[Any, dict[
        Any, Any], pd.DataFrame] | None:
        google_sheet = self._init_google_sheet(spreadsheet_id, google_sheet_name)
        title = google_sheet.title.upper()

        if 'C5' in title:
            last_now_num = google_sheet.get_last_row("A")
            if last_now_num < 10:
                last_now_num = 30
            sheet_data = google_sheet.get_range_2d(f'A2:N{last_now_num}', 'UNFORMATTED_VALUE')
            sheet_df = pd.DataFrame(sheet_data, columns=[
                'date', 'values_B', 'result_key_C', 'result_values_D', 'year_start_E',
                'year_beats_F', 'model_date_G', 'model_values_H', 'net_value_I', 'index_return', "index_DD_K",
                "start_return", "index_beats_M", "start_DD_N"])

            # Excel/Google Sheets 的基准日期是 1899-12-30
            sheet_df["date"] = self._parse_google_sheet_dates(sheet_df["date"])

            _data = sheet_df[['date', 'index_return', 'start_return']]

            _data = _data.to_dict(orient='records')

            _data_result = {}

            for item in sheet_df[['result_key_C', 'result_values_D']].to_dict(orient='records'):
                if item['result_key_C'] in ['', 'year#']:
                    continue

                _data_result[item['result_key_C']] = item['result_values_D']

            return _data, _data_result, sheet_df

        elif 'C4' in title:
            last_now_num = google_sheet.get_last_row("A")
            if last_now_num < 10:
                last_now_num = 30
            sheet_data = google_sheet.get_range_2d(f'A2:N{last_now_num}', 'UNFORMATTED_VALUE')
            sheet_df = pd.DataFrame(sheet_data, columns=[
                'date', 'values_B', 'result_key_C', 'result_values_D', 'year_start_E',
                'year_beats_F', 'model_date_G', 'model_values_H', 'net_value_I', 'index_return', "index_DD_K",
                "start_return", "index_beats_M", "start_DD_N"])
            # Excel/Google Sheets 的基准日期是 1899-12-30
            sheet_df["date"] = self._parse_google_sheet_dates(sheet_df["date"])

            _data = sheet_df[['date', 'index_return', 'start_return']]

            _data = _data.to_dict(orient='records')

            _data_result = {}

            for item in sheet_df[['result_key_C', 'result_values_D']].to_dict(orient='records'):
                if item['result_key_C'] in ['', 'year#']:
                    continue

                _data_result[item['result_key_C']] = item['result_values_D']

            return _data, _data_result, sheet_df


        elif 'C3' in title or 'Charting:3'.upper() in title:
            last_now_num = google_sheet.get_last_row("D")
            if last_now_num < 10:
                last_now_num = 30
            sheet_data = google_sheet.get_range_2d(f'A2:Q{last_now_num}', 'UNFORMATTED_VALUE')
            sheet_df = pd.DataFrame(sheet_data, columns=[
                'Parameter_A', 'Value_A', '_C', 'date', 'data_E',
                '_F', '_G', 'Parameter_H', 'Value_I', 'net_value_J', "index_return", 'index_DD_K', '_M', "_N",
                "start_return", "_P", "start_DD_Q"])

            # Excel/Google Sheets 的基准日期是 1899-12-30
            sheet_df["date"] = self._parse_google_sheet_dates(sheet_df["date"])

            _data = sheet_df[['date', 'index_return', 'start_return']].to_dict(orient='records')
            _data_result = {}
            _subset_df = sheet_df.iloc[14:23]  # 第15行到第23行

            for item in _subset_df[['Parameter_H', 'Value_I']].to_dict(orient='records'):
                if item['Parameter_H'] == '':
                    continue
                _data_result[item['Parameter_H']] = item['Value_I']

            return _data, _data_result, sheet_df

    def get_return_analysis_v1(self, data: List[Dict[str, Any]]) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        """
        基于与 get_calculate_metrics_v1 相同的 return 列表结构，
        返回扁平化结构结果。

        入参示例:
        [
            {
                "date": "2026-01-02",
                "index_return": 0.0123,
                "start_return": 0.0156,
            }
        ]
        """
        if not data:
            return {}, {}

        analyze_result = self._calculate_metrics_v1(data)
        if not analyze_result:
            return {}, {}

        result = {
            "index_annualized_return": 0,
            "start_annualized_return": 0,
            "index_profit_annual": 0,
            "start_profit_annual": 0,
            "index_profit_monthly_percentage": 0,
            "start_profit_monthly_percentage": 0,
            "index_avg_monthly_return": 0,
            "start_avg_monthly_return": 0,
            "index_avg_monthly_return_common": 0,
            "start_avg_monthly_return_common": 0,
            "index_monthly_std_dev": 0,
            "start_monthly_std_dev": 0,
            "index_annual_std_dev": 0,
            "start_annual_std_dev": 0,
            "index_monthly_return_volatility": 0,
            "start_monthly_return_volatility": 0,
            "annualized_return_diff": 0,
            "outperform_year": 0,
            "monthly_excess_return_percentage_last_return": 0,
            "avg_monthly_excess_returns": 0,
            "monthly_excess_volatility": 0,
            "max_drawdown": 0,
            "excess_drawdown_winning_rate": 0,
            "start_drawdown": 0,
            "start_maximum_number_of_backtest_repair_days": 0,
            "excess_maximum_number_of_backtest_repair_days": 0,
            "index_sharpe_ratio": 0,
            "start_sharpe_ratio": 0,
            "index_kama_ratio": 0,
            "start_kama_ratio": 0,
            "index_sotino_ratio": 0,
            "start_sotino_ratio": 0,
            "excess_sharp": 0,
            "excess_of_promissory_note": 0,
        }

        def pick_all(items, key="year", value="all"):
            if not isinstance(items, list):
                return {}
            for item in items:
                if isinstance(item, dict) and item.get(key) == value:
                    return item
            return {}

        def safe_value(value):
            if value is None:
                return 0
            if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
                return 0
            return value

        excess_returns = analyze_result.get("excess_returns") or []
        excess_return_all = pick_all(excess_returns)
        result["index_annualized_return"] = safe_value(excess_return_all.get("index_annualized_return"))
        result["start_annualized_return"] = safe_value(excess_return_all.get("start_annualized_return"))
        result["annualized_return_diff"] = safe_value(excess_return_all.get("annualized_return_diff"))

        result["index_profit_annual"] = safe_value(analyze_result.get("index_profit_annual"))
        result["start_profit_annual"] = safe_value(analyze_result.get("start_profit_annual"))
        result["outperform_year"] = safe_value(analyze_result.get("outperform_year"))
        result["monthly_excess_volatility"] = safe_value(analyze_result.get("monthly_excess_volatility"))
        result["excess_drawdown_winning_rate"] = safe_value(analyze_result.get("excess_drawdown_winning_rate"))
        result["start_maximum_number_of_backtest_repair_days"] = safe_value(
            analyze_result.get("start_maximum_number_of_backtest_repair_days")
        )
        result["excess_maximum_number_of_backtest_repair_days"] = safe_value(
            analyze_result.get("excess_maximum_number_of_backtest_repair_days")
        )
        result["excess_sharp"] = safe_value(analyze_result.get("excess_sharp"))
        result["excess_of_promissory_note"] = safe_value(analyze_result.get("excess_of_promissory_note"))

        index_profit_monthly_all = pick_all(analyze_result.get("index_profit_monthly"))
        start_profit_monthly_all = pick_all(analyze_result.get("start_profit_monthly"))
        result["index_profit_monthly_percentage"] = safe_value(
            index_profit_monthly_all.get("profit_monthly_percentage")
        )
        result["start_profit_monthly_percentage"] = safe_value(
            start_profit_monthly_all.get("profit_monthly_percentage")
        )

        monthly_excess_return_percentage_all = pick_all(analyze_result.get("monthly_excess_return_percentage"))
        result["monthly_excess_return_percentage_last_return"] = safe_value(
            monthly_excess_return_percentage_all.get("excess_return")
        )

        index_sharpe_ratios_all = (analyze_result.get("index_sharpe_ratios") or {}).get("all") or {}
        start_sharpe_ratios_all = (analyze_result.get("start_sharpe_ratios") or {}).get("all") or {}
        result["index_avg_monthly_return"] = safe_value(index_sharpe_ratios_all.get("avg_monthly_return"))
        result["start_avg_monthly_return"] = safe_value(start_sharpe_ratios_all.get("avg_monthly_return"))
        result["index_avg_monthly_return_common"] = result["index_avg_monthly_return"]
        result["start_avg_monthly_return_common"] = result["start_avg_monthly_return"]
        result["index_monthly_std_dev"] = safe_value(index_sharpe_ratios_all.get("monthly_std_dev"))
        result["start_monthly_std_dev"] = safe_value(start_sharpe_ratios_all.get("monthly_std_dev"))
        result["index_annual_std_dev"] = safe_value(index_sharpe_ratios_all.get("annual_std_dev"))
        result["start_annual_std_dev"] = safe_value(start_sharpe_ratios_all.get("annual_std_dev"))
        result["index_monthly_return_volatility"] = safe_value(analyze_result.get("index_monthly_return_volatility"))
        result["start_monthly_return_volatility"] = safe_value(analyze_result.get("start_monthly_return_volatility"))
        result["index_sharpe_ratio"] = safe_value(index_sharpe_ratios_all.get("sharpe_ratio"))
        result["start_sharpe_ratio"] = safe_value(start_sharpe_ratios_all.get("sharpe_ratio"))

        monthly_excess_returns = analyze_result.get("monthly_excess_returns") or []
        if monthly_excess_returns:
            avg_monthly_excess_returns = sum(
                safe_value(item.get("monthly_excess_return_diff"))
                for item in monthly_excess_returns
                if isinstance(item, dict)
            ) / len(monthly_excess_returns)
            result["avg_monthly_excess_returns"] = safe_value(avg_monthly_excess_returns)

        index_maximum_drawdown = analyze_result.get("index_maximum_drawdown") or {}
        start_maximum_drawdown = analyze_result.get("start_maximum_drawdown") or {}
        year_excess_returns = [
            int(item["year"])
            for item in excess_returns
            if isinstance(item, dict)
               and item.get("year") != "all"
               and safe_value(item.get("annualized_return_diff")) > 0
        ]
        index_year_maximum_drawdown = {
            item["year"]: item
            for item in index_maximum_drawdown.get("year_maximum_drawdown", [])
            if isinstance(item, dict) and item.get("year") in year_excess_returns
        }
        start_year_maximum_drawdown = {
            item["year"]: item
            for item in start_maximum_drawdown.get("year_maximum_drawdown", [])
            if isinstance(item, dict) and item.get("year") in year_excess_returns
        }
        max_drawdown_list = []
        for year, index_item in index_year_maximum_drawdown.items():
            start_item = start_year_maximum_drawdown.get(year)
            if not start_item:
                continue
            max_drawdown_list.append(
                safe_value(start_item.get("drawdown")) - safe_value(index_item.get("drawdown"))
            )
        if max_drawdown_list:
            result["max_drawdown"] = safe_value(max(max_drawdown_list))

        total_maximum_drawdown = start_maximum_drawdown.get("total_maximum_drawdown") or {}
        result["start_drawdown"] = safe_value(total_maximum_drawdown.get("drawdown"))

        index_kama_ratio_all = pick_all(analyze_result.get("index_kama_ratio"))
        start_kama_ratio_all = pick_all(analyze_result.get("start_kama_ratio"))
        result["index_kama_ratio"] = safe_value(index_kama_ratio_all.get("kama_ratio"))
        result["start_kama_ratio"] = safe_value(start_kama_ratio_all.get("kama_ratio"))

        index_sotino_ratio_all = pick_all(analyze_result.get("index_sotino_ratio"))
        start_sotino_ratio_all = pick_all(analyze_result.get("start_sotino_ratio"))
        result["index_sotino_ratio"] = safe_value(index_sotino_ratio_all.get("sotino_ratio"))
        result["start_sotino_ratio"] = safe_value(start_sotino_ratio_all.get("sotino_ratio"))

        return result, analyze_result

    def _calculate_metrics_v1(self, data) -> Dict[str, Any]:
        """
        计算各项指标
        Calculate various metrics

        Args:
            data:

        Returns:
            Dict[str, Any]: 包含计算结果的字典
                          Dictionary containing calculation results
        """
        if not data:
            return {}

        try:
            # 转换为DataFrame便于计算
            # Convert to DataFrame for calculation
            df = pd.DataFrame(data)
            df['date'] = pd.to_datetime(df['date'])
            df['index_return'] = pd.to_numeric(df['index_return'], errors='coerce')
            df['start_return'] = pd.to_numeric(df['start_return'], errors='coerce')
            df = df.sort_values('date').reset_index(drop=True)

            # 提取年份信息
            # Extract year and month information
            df['year'] = df['date'].dt.year
            df['month'] = df['date'].dt.month
            df['year_month'] = df['date'].dt.strftime('%Y-%m')

            # 计算净值
            # Calculate net value
            index_df = df.copy()
            index_df['net_value'] = 1 + index_df['index_return']
            start_df = df.copy()
            start_df['net_value'] = 1 + start_df['start_return']

            # 3. 计算各项指标
            # Calculate various metrics
            index_maximum_drawdown = self.calculate_max_drawdown_by_year_and_total(index_df)
            index_returns_rate = self.calculate_year_returns(index_df)
            index_monthly_returns_rate = self._build_monthly_return_frame(index_df)
            index_sharpe_ratios = self._calculate_sharpe_ratios_from_monthly_df(
                monthly_df=index_monthly_returns_rate,
                start_date=index_df['date'].min(),
                end_date=index_df['date'].max(),
            )

            start_maximum_drawdown = self.calculate_max_drawdown_by_year_and_total(start_df)
            start_returns_rate = self.calculate_year_returns(start_df)
            start_monthly_returns_rate = self._build_monthly_return_frame(start_df)
            start_sharpe_ratios = self._calculate_sharpe_ratios_from_monthly_df(
                monthly_df=start_monthly_returns_rate,
                start_date=start_df['date'].min(),
                end_date=start_df['date'].max(),
            )

            # 卡玛比率
            index_annualized_rates = self.annualized_rate_return(index_df)
            index_kama_ratio = self.calculate_kama_ratio(index_annualized_rates, index_maximum_drawdown)

            start_annualized_rates = self.annualized_rate_return(start_df)
            start_kama_ratio = self.calculate_kama_ratio(start_annualized_rates, start_maximum_drawdown)

            # 所提诺比例
            index_sotino_ratio = self.calculate_sotino_ratio(index_monthly_returns_rate)
            start_sotino_ratio = self.calculate_sotino_ratio(start_monthly_returns_rate)

            # 盈利年百分比（不需要每年）
            index_profit_annual = self.calculate_profit_annual_percentage(index_returns_rate)
            start_profit_annual = self.calculate_profit_annual_percentage(start_returns_rate)

            # 盈利月百分比
            index_profit_monthly = self.calculate_profit_monthly_percentage(index_monthly_returns_rate)
            start_profit_monthly = self.calculate_profit_monthly_percentage(start_monthly_returns_rate)

            # 月收益率波动率
            index_monthly_return_volatility = self.calculate_monthly_return_volatility(index_monthly_returns_rate)
            start_monthly_return_volatility = self.calculate_monthly_return_volatility(start_monthly_returns_rate)

            # 年超额收益
            excess_returns_df = self.calculate_excess_return(index_annualized_rates, start_annualized_rates)
            excess_returns = excess_returns_df[
                ['year', 'annualized_return_diff', 'start_annualized_return', 'index_annualized_return',
                 'start_end_date']
            ].to_dict(orient='records')
            # 跑赢年份
            outperform_year = self.calculate_outperform_year(excess_returns_df)

            # 月超额收益
            monthly_excess_returns = self.calculate_monthly_excess_return(index_monthly_returns_rate,
                                                                          start_monthly_returns_rate)
            monthly_excess_returns_dict = monthly_excess_returns[
                ['year_month', 'date', 'monthly_excess_return_diff', 'start_monthly_return', 'index_monthly_return', ]
            ].to_dict(orient='records')
            # 月超额收益百分比
            monthly_excess_return_percentage = self.calculate_monthly_excess_return_percentage(monthly_excess_returns)
            # 月超额波动率
            monthly_excess_volatility = self.calculate_monthly_excess_volatility(monthly_excess_returns)

            # 超额回撤胜率
            excess_drawdown_winning_rate = self.calculate_excess_drawdown_winning_rate(index_maximum_drawdown,
                                                                                       start_maximum_drawdown)

            # 超额夏普= 月超额收益（均值） * 12 / (月超额收益率标准差 * 根号12)
            monthly_excess_return_diff_mean = monthly_excess_returns['monthly_excess_return_diff'].mean()
            monthly_excess_return_standard_deviation = monthly_excess_returns['monthly_excess_return_diff'].std()
            excess_sharp = (monthly_excess_return_diff_mean * 12) / (
                    monthly_excess_return_standard_deviation * np.sqrt(12))

            # 超额所提诺 = 月超额收益（均值） * 12 / (下行月超额收益率标准差 * 根号12) (老版本移除)
            # 超额所提诺 = 月超额收益（均值） * 12 / (月超额收益率标准差 * 根号12)(大于0的设置0)
            monthly_excess_returns_diff = monthly_excess_returns['monthly_excess_return_diff'].mask(
                monthly_excess_returns['monthly_excess_return_diff'] > 0, 0
            )
            excess_of_promissory_note = (monthly_excess_return_diff_mean * 12) / (monthly_excess_returns_diff.std() * np.sqrt(12))


            # 最大回测修复天数 = （出现净值最多次数的天数）（每年）(index，start)
            index_maximum_number_of_backtest_repair_days = self.maximum_number_of_backtest_repair_days(index_df)
            start_maximum_number_of_backtest_repair_days = self.maximum_number_of_backtest_repair_days(start_df)

            # 超额最大回测修复天数 = start - index
            data_df_2 = pd.DataFrame({
                'net_value': start_df['net_value'] - index_df['net_value'],
            })
            excess_maximum_number_of_backtest_repair_days = self.maximum_number_of_backtest_repair_days(data_df_2)

            # # 超额最大回测修复天数 = start - index
            # excess_maximum_number_of_backtest_repair_days = self.exceeding_maximum_number_of_backtest_repair_days(
            #     index_maximum_number_of_backtest_repair_days, start_maximum_number_of_backtest_repair_days
            # )

            # 构建返回结果
            # Build return results
            result = {
                "index_maximum_drawdown": index_maximum_drawdown,  # 指数最大回撤
                "index_returns_rate": index_returns_rate,  # 指数收益率
                "index_sharpe_ratios": index_sharpe_ratios,  # 指数夏普比率
                "start_maximum_drawdown": start_maximum_drawdown,  # 模型最大回撤
                "start_returns_rate": start_returns_rate,  # 模型收益率
                "start_sharpe_ratios": start_sharpe_ratios,  # 模型夏普比率

                "index_kama_ratio": index_kama_ratio,  # 卡玛比率
                "index_sotino_ratio": index_sotino_ratio,  # 所提诺比例
                "index_profit_annual": index_profit_annual,  # 盈利年百分比（不需要每年）
                "index_profit_monthly": index_profit_monthly,  # 盈利月百分比
                "index_monthly_return_volatility": index_monthly_return_volatility,

                "start_kama_ratio": start_kama_ratio,
                "start_sotino_ratio": start_sotino_ratio,
                "start_profit_annual": start_profit_annual,
                "start_profit_monthly": start_profit_monthly,
                "start_monthly_return_volatility": start_monthly_return_volatility,

                "excess_returns": excess_returns,  # 年超额收益
                "outperform_year": outperform_year,  # 跑赢年份
                "monthly_excess_returns": monthly_excess_returns_dict,  # 月超额收益
                "monthly_excess_return_percentage": monthly_excess_return_percentage,  # 月超额收益百分比
                "monthly_excess_volatility": monthly_excess_volatility,  # 月超额波动率
                "excess_drawdown_winning_rate": excess_drawdown_winning_rate,  # 超额回撤胜率
                "excess_sharp": excess_sharp,  # 超额夏普
                "excess_of_promissory_note": excess_of_promissory_note,  # 超额所提诺
                "index_maximum_number_of_backtest_repair_days": index_maximum_number_of_backtest_repair_days,
                # 最大回测修复天数 index
                "start_maximum_number_of_backtest_repair_days": start_maximum_number_of_backtest_repair_days,
                # 最大回测修复天数 start
                "excess_maximum_number_of_backtest_repair_days": excess_maximum_number_of_backtest_repair_days,
                # 超额最大回测修复天数
            }

            # 打印调试信息
            # Print debug information
            if logger.isEnabledFor(logging.DEBUG):
                logger.debug("指数最大回撤: %s", json.dumps(index_maximum_drawdown, indent=4, default=str))
                logger.debug("指数月度收益率: %s", json.dumps(index_returns_rate, indent=4, default=str))
                logger.debug("指数夏普比率: %s", json.dumps(index_sharpe_ratios, indent=4, default=str))
                logger.debug("模型最大回撤: %s", json.dumps(start_maximum_drawdown, indent=4, default=str))
                logger.debug("模型月度收益率: %s", json.dumps(start_returns_rate, indent=4, default=str))
                logger.debug("模型夏普比率: %s", json.dumps(start_sharpe_ratios, indent=4, default=str))
                logger.debug("指数卡玛比率: %s", json.dumps(index_kama_ratio, indent=4, default=str))
                logger.debug("模型所提诺比例: %s", json.dumps(index_sotino_ratio, indent=4, default=str))
                logger.debug("指数盈利年百分比（不需要每年）: %s", json.dumps(index_profit_annual, indent=4, default=str))
                logger.debug("模型盈利月百分比: %s", json.dumps(index_profit_monthly, indent=4, default=str))
                logger.debug("指数月度收益率波动率: %s", json.dumps(index_monthly_return_volatility, indent=4, default=str))
                logger.debug("模型卡玛比率: %s", json.dumps(start_kama_ratio, indent=4, default=str))
                logger.debug("模型所提诺比例: %s", json.dumps(start_sotino_ratio, indent=4, default=str))
                logger.debug("模型盈利年百分比（不需要每年）: %s", json.dumps(start_profit_annual, indent=4, default=str))
                logger.debug("模型盈利月百分比: %s", json.dumps(start_profit_monthly, indent=4, default=str))
                logger.debug("模型月度收益率波动率: %s", json.dumps(start_monthly_return_volatility, indent=4, default=str))
                logger.debug("年超额收益: %s", json.dumps(excess_returns, indent=4, default=str))
                logger.debug("跑赢年份: %s", json.dumps(outperform_year, indent=4, default=str))
                logger.debug("月超额收益百分比: %s", json.dumps(monthly_excess_return_percentage, indent=4, default=str))
                logger.debug("月超额波动率: %s", json.dumps(monthly_excess_volatility, indent=4, default=str))
                logger.debug("超额回撤胜率: %s", json.dumps(excess_drawdown_winning_rate, indent=4, default=str))
            return result

        except Exception as e:
            logger.error(f"计算指标时出错: {str(e)}", exc_info=True)
            return {}

    def format_export_file_data(self, data):
        analyze_result = data.get('analyze_result')
        filename_title = data.get('filename_title', "").upper()

        model_name = ''
        if "C5" in filename_title:
            model_name = "C5"
        elif "C4" in filename_title:
            model_name = "C4"
        else:
            model_name = "C3"

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

        # 所提诺比率
        index_sotino_ratios = analyze_result.get('index_sotino_ratio')
        index_sotino_ratio_all = [i for i in index_sotino_ratios if i['year'] == 'all'][0]
        index_sotino_ratio = index_sotino_ratio_all.get('sotino_ratio')
        start_sotino_ratios = analyze_result.get('start_sotino_ratio')
        start_sotino_ratio_all = [i for i in start_sotino_ratios if i['year'] == 'all'][0]
        start_sotino_ratio = start_sotino_ratio_all.get('sotino_ratio')

        excess_sharp = analyze_result.get('excess_sharp')
        excess_of_promissory_note = analyze_result.get('excess_of_promissory_note')
        start_maximum_number_of_backtest_repair_days = analyze_result.get(
            'start_maximum_number_of_backtest_repair_days')
        excess_maximum_number_of_backtest_repair_days = analyze_result.get(
            'excess_maximum_number_of_backtest_repair_days')

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
            ["回撤", "年最大超额回撤", "", f"-{max_drawdown:.2%}"],
            ["回撤", "超额回撤胜率", "", f"-{excess_drawdown_winning_rate:.2%}"],
            ["回撤", "年最大回撤", "", f"-{start_drawdown:.2%}"],
            ["回撤", "最大修复天数", "", f"{start_maximum_number_of_backtest_repair_days}"],
            ["回撤", "超额最大修复天数", "", f"{excess_maximum_number_of_backtest_repair_days}"],
            ["比率", "夏普比率", f"{index_sharpe_ratio:.2}", f"{start_sharpe_ratio:.2}"],  # 注意：数字后面有空格
            ["比率", "卡玛比率", f"{index_kama_ratio:.2}", f"{start_kama_ratio:.2}"],
            ["比率", "所提诺比率", f"{index_sotino_ratio:.2}", f"{start_sotino_ratio:.2}"],
            ["夏普", "超额夏普", f"", f"{excess_sharp:.2}"],
            ["所提诺", "超额所提诺比率", f"", f"{excess_of_promissory_note:.2}"]
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

        target_df.iloc[0:23, 0:4] = data_1_2d
        target_df.iloc[24:29, 0:data_2_col_num] = data_2_2d
        target_df.iloc[30:35, 0:data3_col_num] = data_3_2d
        target_df.iloc[data_4_start_row:data_4_end_row, 9:12] = data_4_2d

        return target_df

    def export_file(self, data):
        if not data:
            raise ValueError("data不能为空")

        file_data = self.format_export_file_data(data)
        csv_buffer = BytesIO()

        # 将DataFrame写入CSV（注意编码）
        file_data.to_csv(csv_buffer, index=False, header=False, encoding='utf-8')

        # 重置指针到文件开头
        csv_buffer.seek(0)

        return csv_buffer, 'text/csv'


# 创建全局实例
xpl_analyzer = XPLAnalyzer()

if __name__ == "__main__":
    xpl_analyzer = XPLAnalyzer()
    from d import data

    parsed_data = xpl_analyzer._parse_input_data(data)

    print(json.dumps(xpl_analyzer._calculate_metrics_v1(parsed_data),ensure_ascii=False))
    # xpl_analyzer._calculate_metrics(parsed_data)
    # xpl_analyzer.analyze_v1('1jTXxqMzQXu52_eWt8_5qnnZB0EfRwjH9bfC79TpPcwM','data7y')
    # xpl_analyzer.get_google_sheet_data('1jTXxqMzQXu52_eWt8_5qnnZB0EfRwjH9bfC79TpPcwM','data7y')
    # xpl_analyzer.get_google_sheet_data('1BxinniyEdRwSx-tPi_3qMi_WjhYbEQVTyX3Mg_sQr5U','control')

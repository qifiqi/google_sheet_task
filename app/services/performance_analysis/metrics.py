"""Metric calculations for return and backtest performance analysis."""

import json
import math
from typing import Any, Dict, List

import numpy as np
import pandas as pd

from app.utils.logger import get_logger

logger = get_logger(__name__)


class PerformanceMetricsMixin:
    # Metric methods are kept in their original order to preserve implementation behavior.
    @staticmethod
    def monthly_maximum_drawdown(df):
        """

        每年每月最好的那个
        """
        all_years = df['year_month'].unique()
        result = {"year_maximum_drawdown": []}

        # 计算每年的最大回撤
        # Calculate maximum drawdown for each year
        df_yearly = df.copy()

        for year in all_years:
            yearly_data = df_yearly[df_yearly['year_month'] == year]

            # 按时间排序，确保计算正确
            # Sort by date to ensure correct calculation
            yearly_data = yearly_data.sort_values('date').reset_index(drop=True)

            # 计算每个时间点的回撤
            # Calculate drawdown for each time point
            for index in range(len(yearly_data)):
                current_row = yearly_data.iloc[index]

                # 获取当前时间及之前的所有数据
                # Get all data up to the current time
                historical_data = yearly_data.iloc[:index + 1]

                # 计算到当前时间的最高净值
                # Calculate maximum net value up to current time
                historical_max = historical_data['net_value'].max()

                # 计算回撤：(历史最高净值 - 当前净值) / 历史最高净值
                if historical_max > 0:
                    drawdown = (historical_max - current_row['net_value']) / historical_max
                else:
                    drawdown = 0

                yearly_data.at[index, 'drawdown'] = drawdown  # 回撤值 Drawdown value

            # 找到该年度的最大回撤
            max_drawdown_row = yearly_data.loc[yearly_data['drawdown'].idxmax()]
            _ = max_drawdown_row.to_dict()
            _['date'] = _['date'].strftime('%Y-%m-%d')
            result['year_maximum_drawdown'].append(_)

        return result

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
        all_years = df['year'].unique()
        result = {"year_maximum_drawdown": [], 'total_maximum_drawdown': {}}

        # 计算每年的最大回撤
        # Calculate maximum drawdown for each year
        df_yearly = df.copy()

        for year in all_years:
            yearly_data = df_yearly[df_yearly['year'] == year]

            # 按时间排序，确保计算正确
            # Sort by date to ensure correct calculation
            yearly_data = yearly_data.sort_values('date').reset_index(drop=True)

            # 计算每个时间点的回撤
            # Calculate drawdown for each time point
            for index in range(len(yearly_data)):
                current_row = yearly_data.iloc[index]

                # 获取当前时间及之前的所有数据
                # Get all data up to the current time
                historical_data = yearly_data.iloc[:index + 1]

                # 计算到当前时间的最高净值
                # Calculate maximum net value up to current time
                historical_max = historical_data['net_value'].max()

                # 计算回撤：(历史最高净值 - 当前净值) / 历史最高净值
                if historical_max > 0:
                    drawdown = (historical_max - current_row['net_value']) / historical_max
                else:
                    drawdown = 0

                yearly_data.at[index, 'drawdown'] = drawdown  # 回撤值 Drawdown value

            # 找到该年度的最大回撤
            max_drawdown_row = yearly_data.loc[yearly_data['drawdown'].idxmax()]
            _ = max_drawdown_row.to_dict()
            _['date'] = _['date'].strftime('%Y-%m-%d')
            result['year_maximum_drawdown'].append(_)

        # 计算总计最大回撤
        # Calculate total maximum drawdown
        df_total = df.copy()

        # 确保数据按时间排序
        # Ensure data is sorted by date
        df_total = df_total.sort_values('date').reset_index(drop=True)

        # 计算每个时间点的回撤
        # Calculate drawdown for each time point
        for index in range(len(df_total)):
            current_row = df_total.iloc[index]

            # 获取从开始到当前时间的所有数据
            # Get all data from start to current time
            historical_data = df_total.iloc[:index + 1]

            # 计算到当前时间的最高净值
            # Calculate maximum net value up to current time
            historical_max = historical_data['net_value'].max()

            # 计算回撤：(历史最高净值 - 当前净值) / 历史最高净值
            # Calculate drawdown: (historical max - current) / historical max
            if historical_max > 0:
                drawdown = (historical_max - current_row['net_value']) / historical_max
            else:
                drawdown = 0

            # 检查NaN值
            # Check for NaN values
            if pd.isna(drawdown):
                drawdown = 0

            df_total.at[index, 'drawdown'] = drawdown

        # 找到总计的最大回撤
        # Find the total maximum drawdown
        max_drawdown_row = df_total.loc[df_total['drawdown'].idxmax()]
        max_drawdown_row = max_drawdown_row.to_dict()
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
        annual_returns = []

        # 按年份分组处理
        # Group by year for processing
        yearly_groups = df.groupby('year')
        previous_year_data = None  # 保存上一年份的数据 Store data from previous year

        for year_month, month_df in yearly_groups:
            if len(month_df) == 0:
                continue

            # 获取当前年份最后一天的数据（假设数据已按日期排序）
            # Get the last day's data of the current year (assuming data is sorted by date)
            current_month_last_day = month_df.iloc[-1]

            # 确定对比基准日
            # Determine comparison base day
            if previous_year_data is None:
                # 如果是第一个月，使用当前月份第一天作为基准
                # If it's the first month, use the first day of the current month as base
                comparison_day = month_df.iloc[0]
            else:
                # 否则使用去年最后一天作为基准
                # Otherwise, use the last day of the previous month as base
                comparison_day = previous_year_data.iloc[-1]

            # 计算年度收益率：(本年最后一天净值 / 基准日净值 - 1)
            # Calculate annual return: (end of month value / base day value - 1)
            annual_return = current_month_last_day['net_value'] / comparison_day['net_value'] - 1

            # 记录年度收益数据
            # Record monthly return data
            annual_returns.append({
                'year_month': str(year_month),  # 年月 Year and month
                'annual_return': float(annual_return.__round__(6)),  # 收益率 Monthly return
                'year': str(current_month_last_day['year']),  # 年份 Year
                'net_value': current_month_last_day['net_value'],  # 净值
                'date': current_month_last_day['date'].strftime('%Y-%m-%d')  # 日期 Date
            })

            # 保存当前年份数据供下一年使用
            # Save current year's data for next year's comparison
            previous_year_data = month_df

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

        # TODO
        # 计算月度收益率标准差（使用样本标准差）（月收益率标准差）
        # Calculate monthly return standard deviation (population standard deviation)
        monthly_std = monthly_returns.std(ddof=1)

        # 计算年化标准差(年化波动率)
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
            'monthly_std_dev': monthly_std,  # 月收益率标准差 Monthly standard deviation (%)
            'month_count': len(monthly_subset),  # 月数 Number of months
            'start_date': monthly_subset['date'].min().strftime('%Y-%m'),  # 开始时间 Start date
            'end_date': monthly_subset['date'].max().strftime('%Y-%m')  # 结束时间 End date
        }

    @staticmethod
    def calculate_monthly_return_data(df):
        """
            计算月度收益率数据
                周均年化收益率 = (周末净值 / 上周末 - 1)
        """
        # 计算月度收益率数据
        # Calculate monthly return data
        monthly_data = []
        monthly_groups = df.groupby('year_month')
        previous_month_data = None

        for month, month_df in monthly_groups:
            if len(month_df) > 0:
                # 取当月最后一个数据点
                # Take the last data point of the month
                current_month_end = month_df.iloc[-1]

                # 确定比较基准（上个月末或当月初）
                # Determine comparison base (end of previous month or start of current month)
                if previous_month_data is None:
                    # 如果是第一个月，使用当月第一个数据点作为基准
                    # If it's the first month, use the first data point of the month as base
                    # comparison_point = month_df.iloc[0]
                    # comparison_point = comparison_point['net_value']
                    comparison_point = 1
                else:
                    # 否则使用上个月最后一个数据点作为基准
                    # Otherwise, use the last data point of the previous month as base
                    comparison_point = previous_month_data.iloc[-1]
                    comparison_point = comparison_point['net_value']

                # 计算月度收益率：(月末净值 / 基准日净值 - 1)
                # Calculate monthly return: (end of month value / base day value - 1)
                monthly_return = (current_month_end['net_value'] / comparison_point - 1)

                # 记录月度数据
                # Record monthly data
                monthly_data.append({
                    'year_month': month,  # 年月 Year and month
                    'monthly_return': round(monthly_return, 4),  # 月收益率 Monthly return
                    'year': current_month_end['year'],  # 年份 Year
                    'date': current_month_end['date']  # 日期 Date
                })

                previous_month_data = month_df

        return monthly_data
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
        # 保存结果
        # Save results
        results = {}

        # 计算全部数据的夏普比率
        # Calculate Sharpe ratio for all data
        results["all"] = res

        # 计算每年的夏普比率
        # Calculate Sharpe ratio for each year
        years = sorted(monthly_df['year'].unique())
        for i, year in enumerate(years):
            year_data = monthly_df[monthly_df['year'] == year]
            if len(year_data) >= 3:  # 至少需要3个月的数据 Need at least 3 months of data
                year_name = f"year_{i + 1}_{year}"  # 例如: year_1_2023
                logger.debug(f"计算年份/Calculating year {year_name}, 总月数/Total months: {len(year_data)}")
                res = self.calculate_sharpe_for_period(year_data, year_name, 12)
                results[year_name] = res

        # 计算滚动年份的夏普比率（前1年、前2年等）
        # Calculate rolling year Sharpe ratios (past 1 year, past 2 years, etc.)
        years = sorted(monthly_df['year'].unique(), reverse=True)
        for i, year in enumerate(years):
            year_data = monthly_df[monthly_df['year'] >= year]
            if len(year_data) >= 3:  # 至少需要3个月的数据 Need at least 3 months of data
                year_name = f"past_{i + 1}_years_since_{year}"  # 例如: past_1_years_since_2023
                logger.debug(
                    f"计算滚动年份/Calculating rolling year {year_name}, 总月数/Total months: {len(year_data)}")
                res = self.calculate_sharpe_for_period(year_data, year_name, 12)
                results[year_name] = res

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

        annualized_rate_returns = []

        # 按年份分组处理
        yearly_groups = df.groupby('year')

        for year, year_df in yearly_groups:
            if len(year_df) == 0:
                continue

            # 获取期初和期末净值
            start_value = year_df.iloc[0]['net_value']
            end_value = year_df.iloc[-1]['net_value']

            # 计算持有天数
            start_date = year_df.iloc[0]['date']
            end_date = year_df.iloc[-1]['date']
            holding_days = (end_date - start_date).days

            if holding_days == 0:
                continue

            # 计算年化收益率
            # 注意：期末净值 / 期初净值
            total_return = end_value / start_value
            annualized_return = total_return ** (365 / holding_days) - 1

            annualized_rate_returns.append({
                'year': str(year),
                'annualized_return': annualized_return,  # 收益率 Monthly return
                'date': f"{start_date}/{end_date}"
            })

        # 计算整体年化收益率
        if len(df) >= 2:
            start_value = df.iloc[0]['net_value']
            end_value = df.iloc[-1]['net_value']
            start_date = df.iloc[0]['date']
            end_date = df.iloc[-1]['date']
            holding_days = (end_date - start_date).days

            if holding_days > 0:
                total_return = end_value / start_value
                overall_annualized_return = total_return ** (365 / holding_days) - 1

                # 记录年度收益数据
                annualized_rate_returns.append({
                    'year': "all",
                    'annualized_return': overall_annualized_return,  # 收益率 Monthly return
                    'date': f"{start_date}/{end_date}"
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
            TODO 下行边准差  月 =SQRT (SUMSQ (D2:D36)/COUNT (D2:D36))*SQRT (12)
                            周 =SQRT (SUMSQ (D2:D36)/COUNT (D2:D36))*SQRT (52)
                                周均年化收益率	周均收益率*52（所有周）

            索提诺比例
            月均年化收益率/下行标准差（
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
            ), 4
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
        logger.debug(maximum_drawdown[['year', 'start_drawdown', 'index_drawdown']])
        start_index = maximum_drawdown[maximum_drawdown['start_drawdown'] < maximum_drawdown['index_drawdown']]
        return len(start_index['start_drawdown']) / len(maximum_drawdown['start_drawdown'])

    # def maximum_number_of_backtest_repair_days(self, data_df):
    #     """
    #         # 最大回测修复天数 = （出现最大净值最多次数的天数）（每年）(index，start)
    #     """
    #
    #     data_df['previous_max'] = data_df['net_value'].expanding().max().shift(1)
    #     #
    #     # # 按年份分组处理
    #     # yearly_groups = data_df.groupby('year')
    #     #
    #     # max_net_value_count = {}
    #     #
    #     # for year, year_df in yearly_groups:
    #     #     if len(year_df) == 0:
    #     #         continue
    #     #     # mode_values = year_df['previous_max'].mode()
    #     #     mode_freq = year_df['previous_max'].value_counts().max()
    #     #
    #     #     max_net_value_count[year] = int(mode_freq)
    #     #
    #     # return max_net_value_count
    #
    #     return int(data_df['previous_max'].value_counts().max())
    #     # d_max = data_df['previous_max'].max()
    #     # return data_df[data_df['previous_max'] == d_max]['previous_max'].count()

    def maximum_number_of_backtest_repair_days(self, data_df):
        """
        最大回测修复天数（整体区间）

        含义：
            在完整的考察区间内，基金净值从某一个峰值下跌后，重新回到该峰值水平
            所需要的【最长】天数。

        通俗理解：
            "从山顶跌到谷底再爬回山顶，最久的一次花了多少天？"

        为什么重要：
            - 衡量基金的"抗跌修复能力"
            - 修复天数越短，说明基金越能快速从下跌中恢复
            - 对于投资者来说，修复天数过长意味着资金可能被长期套牢

        计算逻辑：
            1. 记录当前遇到过的最高净值（peak）
            2. 逐日遍历净值序列：
               a. 如果当日净值 >= peak（创新高或回到前高）：
                  - 说明修复完成！记录本轮修复天数
                  - 更新peak为当日净值（新的历史最高）
                  - 重置修复天数计数器为0
               b. 如果当日净值 < peak（仍在回撤中）：
                  - 修复天数 +1（多跌了一天）
            3. 返回所有修复周期中的最大天数

        注意：
            - 只统计【已完成】的修复周期
            - 如果区间结束时仍未修复，不纳入统计
            - 回撤修复天数从【跌破前高后的第一个交易日】开始计算

        参数：
            data_df: pandas.DataFrame，必须包含 'net_value' 列（净值数据）

        返回：
            int: 最大回测修复天数（已完成修复周期中的最大值）

        示例：
            净值序列: [1.00, 1.50, 1.40, 1.30, 1.20, 1.50, 1.60]
            修复周期1: 1.50 → 1.20 → 1.50，耗时 3天（索引2,3,4）
            修复周期2: 1.60 未完成修复，不计入
            返回: 3
        """
        net_values = data_df['net_value'].values
        if len(net_values) < 2:
            return 0

        # peak: 当前历史最高净值（记录"山顶"的位置）
        peak = net_values[0]

        # repair_days: 当前回撤已经持续的天数（正在"爬山"的天数）
        repair_days = 0

        # max_repair_days: 历史所有修复周期中的最大天数（最终答案）
        max_repair_days = 0

        # 从第二个交易日开始遍历（第一天没有历史参照）
        for i in range(1, len(net_values)):
            if net_values[i] >= peak:
                # 情况1：净值回到前高或创新高 → 修复完成！
                # 判断本次修复是否刷新了最长记录
                if repair_days > max_repair_days:
                    max_repair_days = repair_days

                # 更新历史最高净值（新的"山顶"）
                peak = net_values[i]

                # 重置修复天数计数器（开始新的回撤周期）
                repair_days = 0
            else:
                # 情况2：净值低于历史最高 → 仍在回撤中
                # 修复天数+1（又跌了一天，离山顶更远了）
                repair_days += 1

        return max_repair_days

    def yearly_max_repair_days(self, data_df):
        """
        按年计算最大回测修复天数

        含义：
            将完整的考察区间按【自然年份】拆分，分别计算每一年的最大回测修复天数。

        使用场景：
            - 评估基金在不同年份的修复能力变化
            - 比较基金在牛市、熊市中的表现差异
            - 识别基金在某些年份是否存在异常（修复天数突然变长）

        核心逻辑（重要！）：
            1. 年份拆分：按'date'列将数据分为2020年、2021年、2022年...
            2. 【跨年累积】：上一年未修复的回撤，会累积到下一年的数据中继续计算
            3. 每一年统计该年度内【完成修复】的周期中，最大的修复天数

        为什么要跨年累积？
            - 假设2020年12月31日净值1.50，2021年1月跌到1.30
            - 如果2021年6月才回到1.50，修复天数应跨年计算
            - 如果每年重置peak，会低估修复天数

        参数：
            data_df: pandas.DataFrame，必须包含 'date' 列（日期）和 'net_value' 列（净值）

        返回：
            dict: {年份: 该年最大修复天数}

        示例：
            2019年: 最大回测修复天数 = 0天（无完成修复）
            2020年: 最大回测修复天数 = 10天
            2021年: 最大回测修复天数 = 5天

        输出格式：
            {2019: 0, 2020: 10, 2021: 5}
        """
        # 步骤1：按日期排序，确保时间顺序正确
        data_df = data_df.sort_values('date')

        # 步骤2：提取年份，用于分组
        data_df['year'] = data_df['date'].dt.year

        yearly_result = {}

        # peak: 跨年维护的历史最高净值（不因年份切换而重置！）
        peak = None

        # repair_days: 跨年维护的当前回撤天数（不因年份切换而重置！）
        repair_days = 0

        # 步骤3：按年份分组遍历（年份从小到大）
        for year, year_df in data_df.groupby('year', sort=True):
            net_values = year_df['net_value'].values

            # 判断是否为第一年
            if peak is None:
                # 第一年：用该年第一天的净值初始化peak
                peak = net_values[0]
                # 从该年第二天开始遍历（第一天没有历史参照）
                start_idx = 1
            else:
                # 非第一年：peak保持上一年末的历史最高值
                # 从该年第一天开始遍历（要继承上年的修复状态）
                start_idx = 0

            # 该年度的最大修复天数（初始为0）
            max_repair_days = 0

            # 步骤4：遍历该年每一天的净值
            for i in range(start_idx, len(net_values)):
                if net_values[i] >= peak:
                    # 修复完成！
                    if repair_days > max_repair_days:
                        max_repair_days = repair_days

                    # 更新历史最高峰值
                    peak = net_values[i]

                    # 重置回撤计数器
                    repair_days = 0
                else:
                    # 仍在回撤中，回撤天数+1
                    repair_days += 1

            # 步骤5：记录该年的最大修复天数
            yearly_result[year] = max_repair_days

        return yearly_result

    def exceeding_maximum_number_of_backtest_repair_days(self, index_data, start_data):
        """
        """

        # start_index_data = {}
        #
        # for k,v in start_data.items():
        #     start_index_data[k] = v - index_data[k]
        # return start_index_data

        return start_data - index_data


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
            df = df.sort_values('date')

            # 提取年份信息
            # Extract year and month information
            df['year'] = df['date'].dt.year
            df['month'] = df['date'].dt.month
            df['year_month'] = df['date'].dt.strftime('%Y-%m')

            # 计算净值
            # Calculate net value
            index_df = df.copy()
            index_df['net_value'] = 1 * (1 + index_df['index_return'])
            start_df = df.copy()
            start_df['net_value'] = 1 * (1 + start_df['start_return'])

            # 当天收益率
            # 当天收益率 = (当天净值 / 前一天净值) - 1
            index_df['daily_return'] = (index_df['net_value'] / index_df['net_value'].shift(1)) - 1
            start_df['daily_return'] = (start_df['net_value'] / start_df['net_value'].shift(1)) - 1
            # # 回撤
            # index_df['drawdown'] = index_df['net_value'] / index_df['net_value'].cummax() - 1
            # start_df['drawdown'] = start_df['net_value'] / start_df['net_value'].cummax() - 1

            # 3. 计算各项指标
            # Calculate various metrics
            index_maximum_drawdown = self.calculate_max_drawdown_by_year_and_total(index_df)
            index_returns_rate = self.calculate_year_returns(index_df)
            index_sharpe_ratios = self.calculate_sharpe_ratios_by_periods(index_df)

            start_maximum_drawdown = self.calculate_max_drawdown_by_year_and_total(start_df)
            start_returns_rate = self.calculate_year_returns(start_df)
            start_sharpe_ratios = self.calculate_sharpe_ratios_by_periods(start_df)

            # 卡玛比率
            index_annualized_rates = self.annualized_rate_return(index_df)
            index_kama_ratio = self.calculate_kama_ratio(index_annualized_rates, index_maximum_drawdown)

            start_annualized_rates = self.annualized_rate_return(start_df)
            start_kama_ratio = self.calculate_kama_ratio(start_annualized_rates, start_maximum_drawdown)

            # 计算月度收益率
            index_monthly_returns_rate = self.calculate_monthly_return_data(index_df)
            index_monthly_returns_rate = pd.DataFrame(index_monthly_returns_rate)

            start_monthly_returns_rate = self.calculate_monthly_return_data(start_df)
            start_monthly_returns_rate = pd.DataFrame(start_monthly_returns_rate)

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

            # 索提诺比例
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

            # 超额回撤胜率
            excess_drawdown_winning_rate = self.calculate_excess_drawdown_winning_rate(index_maximum_drawdown,
                                                                                       start_maximum_drawdown)

            # 超额夏普= 月超额收益（均值） * 12 / (月超额收益率标准差 * 根号12)
            monthly_excess_return_diff_mean = monthly_excess_returns['monthly_excess_return_diff'].mean()
            monthly_excess_return_standard_deviation = monthly_excess_returns['monthly_excess_return_diff'].std()
            excess_sharp = (monthly_excess_return_diff_mean * 12) / (
                    monthly_excess_return_standard_deviation * np.sqrt(12))

            # 超额索提诺 = 月超额收益（均值） * 12 / (下行月超额收益率标准差 * 根号12) (老版本移除)
            # 超额索提诺 = 月超额收益（均值） * 12 / (月超额收益率标准差 * 根号12)(大于0的设置0)
            monthly_excess_returns_diff = monthly_excess_returns['monthly_excess_return_diff'].mask(
                monthly_excess_returns['monthly_excess_return_diff'] > 0, 0
            )
            excess_of_promissory_note = (monthly_excess_return_diff_mean * 12) / (
                        monthly_excess_returns_diff.std() * np.sqrt(12))

            # 在完整的考察区间内，基金净值从某一个峰值下跌后，重新回到该峰值水平 所需要的【最长】天数。
            index_maximum_number_of_backtest_repair_days = self.maximum_number_of_backtest_repair_days(index_df)
            start_maximum_number_of_backtest_repair_days = self.maximum_number_of_backtest_repair_days(start_df)

            # 将完整的考察区间按【自然年份】拆分，分别计算每一年的最大回测修复天数。 取最大值
            year_index_yearly_max_repair_days = self.yearly_max_repair_days(index_df)
            year_start_yearly_max_repair_days = self.yearly_max_repair_days(start_df)

            # 超额最大回测修复天数 = start - index
            data_df_2 = pd.DataFrame()
            data_df_2['net_value'] = start_df['net_value'] - index_df['net_value']
            excess_maximum_number_of_backtest_repair_days = self.maximum_number_of_backtest_repair_days(data_df_2)

            # # 超额最大回测修复天数 = start - index
            # excess_maximum_number_of_backtest_repair_days = self.exceeding_maximum_number_of_backtest_repair_days(
            #     index_maximum_number_of_backtest_repair_days, start_maximum_number_of_backtest_repair_days
            # )

            # 累计回报率
            index_cumulative_return = index_df['index_return'].iloc[-1]
            start_cumulative_return = start_df['start_return'].iloc[-1]

            # 1.3 滚动收益（月度窗口）
            # 3个月滚动
            index_rolling_return_3 = self.calculate_rolling_return(index_monthly_returns_rate,3)
            start_rolling_return_3 = self.calculate_rolling_return(start_monthly_returns_rate,3)
            # 6个月滚动
            index_rolling_return_6 = self.calculate_rolling_return(index_monthly_returns_rate,6)
            start_rolling_return_6 = self.calculate_rolling_return(start_monthly_returns_rate,6)
            # 12个月滚动
            index_rolling_return_12 = self.calculate_rolling_return(index_monthly_returns_rate,12)
            start_rolling_return_12 = self.calculate_rolling_return(start_monthly_returns_rate,12)


            # 四、月度收益分布
            # 总月数
            total_months = len(index_monthly_returns_rate)
            # 盈利月数（绝对收益率）
            index_profit_months = len(index_monthly_returns_rate[index_monthly_returns_rate['monthly_return'] > 0])
            start_profit_months = len(start_monthly_returns_rate[start_monthly_returns_rate['monthly_return'] > 0])
            # 亏损月数（绝对收益率）
            index_loss_months = len(index_monthly_returns_rate[index_monthly_returns_rate['monthly_return'] < 0])
            start_loss_months = len(start_monthly_returns_rate[start_monthly_returns_rate['monthly_return'] < 0])
            # 月盈利百分比
            index_profit_percentage = index_profit_months / total_months
            start_profit_percentage = start_profit_months / total_months
            # 平均月收益率
            # 月收益率标准差
            # 这两个在index_sharpe_ratios[all] 内
            # 'avg_monthly_return': avg_monthly_return,  # 平均月收益率 Average monthly return (%)
            # 'monthly_std_dev': monthly_std,  # 月收益率标准差 Monthly standard deviation (%)

            # 最大单月收益 （收益率最高月份）
            index_max_monthly_return = index_monthly_returns_rate['monthly_return'].max()
            start_max_monthly_return = start_monthly_returns_rate['monthly_return'].max()
            # 最大单月亏损 （收益率最低月份）
            index_max_monthly_loss = index_monthly_returns_rate['monthly_return'].min()
            start_max_monthly_loss = start_monthly_returns_rate['monthly_return'].min()


            # 4.2 月度收益区间分布
            # 收益区间
            # < -5%
            # -5%~-2%
            # -2%~0%
            # 0%~2%
            # 2%~5%
            # 5%~10%
            # >10%
            monthly_bins = [-1, -0.05, -0.02, 0, 0.02, 0.05, 0.10, 1]
            monthly_labels = ['<-5%', '-5%~-2%', '-2%~0%', '0%~2%', '2%~5%', '5%~10%', '>10%']
            index_monthly_distribution, index_monthly_distribution_pct, total = self.calculate_distribution(
                index_monthly_returns_rate, "monthly_return",bins=monthly_bins,labels=monthly_labels
            )
            start_monthly_distribution, start_monthly_distribution_pct, total = self.calculate_distribution(
                start_monthly_returns_rate,"monthly_return",bins=monthly_bins, labels=monthly_labels
            )

            # 日度收益分布
            # 总交易日
            total_trading_days = len(index_df['daily_return'])
            # 盈利天数
            index_profit_days = len(index_df[index_df['daily_return'] > 0])
            start_profit_days = len(start_df[start_df['daily_return'] > 0])
            # 亏损天数
            index_loss_days = len(index_df[index_df['daily_return'] < 0])
            start_loss_days = len(start_df[start_df['daily_return'] < 0])
            # 日盈利百分比
            index_profit_percentage = index_profit_days / total_trading_days
            start_profit_percentage = start_profit_days / total_trading_days
            # 日均收益率
            index_mean_daily_return = index_df['daily_return'].mean()
            start_mean_daily_return = start_df['daily_return'].mean()
            # 日收益率峰度
            index_mean_daily_kurtosis = index_df['daily_return'].kurt()
            start_mean_daily_kurtosis = start_df['daily_return'].kurt()
            # 日收益率偏度
            index_mean_daily_skewness = index_df['daily_return'].skew()
            start_mean_daily_skewness = start_df['daily_return'].skew()
            # 日收益率标准差
            index_daily_return_std = index_df['daily_return'].std()
            start_daily_return_std = start_df['daily_return'].std()

            # 5.2 盈亏比分析（日收益率）
            # 平均盈利日收益（盈利天数 avg） / 盈利天数
            index_avg_profit_day_return = index_df['daily_return'][index_df['daily_return'] > 0].mean()
            start_avg_profit_day_return = start_df['daily_return'][start_df['daily_return'] > 0].mean()
            # 平均亏损日收益
            index_avg_loss_day_return = index_df['daily_return'][index_df['daily_return'] < 0].mean()
            start_avg_loss_day_return = start_df['daily_return'][start_df['daily_return'] < 0].mean()
            # 盈亏比(平均盈利/平均亏损)
            index_profit_loss_ratio = index_avg_profit_day_return / index_avg_loss_day_return
            start_profit_loss_ratio = start_avg_profit_day_return / start_avg_loss_day_return
            # 单笔最大盈利/最大亏损 最大盈利天数据/最大亏损天
            index_max_profit_day = index_df['daily_return'][index_df['daily_return'] > 0].max()
            start_max_profit_day = start_df['daily_return'][start_df['daily_return'] > 0].max()
            index_max_loss_day = index_df['daily_return'][index_df['daily_return'] < 0].min()
            start_max_loss_day = start_df['daily_return'][start_df['daily_return'] < 0].min()




            # 5.3 日度收益区间分布（当日收益率列）
            # 收益区间
            # <-2%
            # -2%~-1%
            # -1%~-0.2%
            # -0.2%~0.2%
            # 0.2%~1%
            # 1%~2%
            # >2%
            # index_df['return_range'] = pd.cut(index_df['daily_return'], bins=bins, labels=labels)
            # start_df['return_range'] = pd.cut(start_df['daily_return'], bins=bins, labels=labels)
            days_bins = [-1, -0.05, -0.03, -0.01, 0, 0.01, 0.03, 0.05, 1]
            days_labels = ['<-5%', '-5%~-3%', '-3%~-1%', '-1%~0%', '0%~1%', '1%~3%', '3%~5%', '>5%']
            index_days_distribution, index_days_distribution_pct, days_total = self.calculate_distribution(
                index_monthly_returns_rate, "daily_return",bins=days_bins,labels=days_labels
            )
            start_days_distribution, start_days_distribution_pct, days_total = self.calculate_distribution(
                start_monthly_returns_rate,"daily_return",bins=days_bins, labels=days_labels
            )


            # 1. 单日跌幅 > 5% 的次数
            index_dd_count = (index_df['daily_return'] < -0.05).sum()
            start_dd_count = (start_df['daily_return'] < -0.05).sum()

            # 2. 单日跌幅 > 5% 的频率
            index_dd_freq = (index_df['daily_return'] < -0.05).mean()
            start_dd_freq = (start_df['daily_return'] < -0.05).mean()

            # 3. 最大单日跌幅
            index_max_daily_loss = index_df['daily_return'].min()
            start_max_daily_loss = start_df['daily_return'].min()



            # 5. 跌幅分布统计
            index_return_dist = index_df['return_range'].value_counts().sort_index()
            start_return_dist = start_df['return_range'].value_counts().sort_index()

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
                "index_sotino_ratio": index_sotino_ratio,  # 索提诺比例
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
                "excess_of_promissory_note": excess_of_promissory_note,  # 超额索提诺
                "index_maximum_number_of_backtest_repair_days": index_maximum_number_of_backtest_repair_days,
                # 最大回测修复天数 index
                "start_maximum_number_of_backtest_repair_days": start_maximum_number_of_backtest_repair_days,
                # 最大回测修复天数 start
                "excess_maximum_number_of_backtest_repair_days": excess_maximum_number_of_backtest_repair_days,
                "year_index_yearly_max_repair_days": year_index_yearly_max_repair_days,
                "year_start_yearly_max_repair_days": year_start_yearly_max_repair_days,
                "index_cumulative_return": index_cumulative_return,
                "start_cumulative_return": start_cumulative_return,
                "index_annualized_rates":index_annualized_rates,
                "start_annualized_rates": start_annualized_rates,
                "index_rolling_return_3": index_rolling_return_3,
                "start_rolling_return_3": start_rolling_return_3,
                "index_rolling_return_6": index_rolling_return_6,
                "start_rolling_return_6": start_rolling_return_6,
                "index_rolling_return_12": index_rolling_return_12,
                "start_rolling_return_12": start_rolling_return_12,
                "index_loss_days": index_loss_days,
                "start_loss_days": start_loss_days,
                "index_profit_days": index_profit_days,
                "start_profit_days": start_profit_days,
                "index_mean_daily_return": index_mean_daily_return,
                "start_mean_daily_return": start_mean_daily_return,
                "index_daily_return_std": index_daily_return_std,
                "start_daily_return_std": start_daily_return_std,
                "index_mean_daily_kurtosis": index_mean_daily_kurtosis,
                "start_mean_daily_kurtosis": start_mean_daily_kurtosis,
                "index_mean_daily_skewness": index_mean_daily_skewness,
                "start_mean_daily_skewness": start_mean_daily_skewness,
                "index_profit_percentage":index_profit_percentage,
                "start_profit_percentage": start_profit_percentage,
            }

            # 打印调试信息
            # Print debug information
            logger.debug("指数最大回撤: %s", json.dumps(index_maximum_drawdown, indent=4, default=str))
            logger.debug("指数月度收益率: %s", json.dumps(index_returns_rate, indent=4, default=str))
            logger.debug("指数夏普比率: %s", json.dumps(index_sharpe_ratios, indent=4, default=str))
            logger.debug("模型最大回撤: %s", json.dumps(start_maximum_drawdown, indent=4, default=str))
            logger.debug("模型月度收益率: %s", json.dumps(start_returns_rate, indent=4, default=str))
            logger.debug("模型夏普比率: %s", json.dumps(start_sharpe_ratios, indent=4, default=str))
            logger.debug("指数卡玛比率: %s", json.dumps(index_kama_ratio, indent=4, default=str))
            logger.debug("模型索提诺比例: %s", json.dumps(index_sotino_ratio, indent=4, default=str))
            logger.debug("指数盈利年百分比（不需要每年）: %s", json.dumps(index_profit_annual, indent=4, default=str))
            logger.debug("模型盈利月百分比: %s", json.dumps(index_profit_monthly, indent=4, default=str))
            logger.debug("指数月度收益率波动率: %s", json.dumps(index_monthly_return_volatility, indent=4, default=str))
            logger.debug("模型卡玛比率: %s", json.dumps(start_kama_ratio, indent=4, default=str))
            logger.debug("模型索提诺比例: %s", json.dumps(start_sotino_ratio, indent=4, default=str))
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

    def calculate_rolling_return(self, df, months=3):
        """
        按月份计算滚动平均收益率

        Args:
            df: 包含 'date' 和 'monthly_return' 列的DataFrame
            months: 滚动月份，如 3、6、12（默认3）

        Returns:
            dict: 包含滚动平均收益率及统计信息
        """

        total_months = len(df)
        total_years = total_months / 12

        if total_months < 60:
            return {
                'status': 'failed',
                'reason': f'数据不足5年，当前仅{total_years:.1f}年',
                'total_months': total_months,
                'total_years': total_years,
            }

        roll_col = f'roll_{months}m'
        df[roll_col] = df['monthly_return'].rolling(window=months).mean()

        return df.dropna(subset=[roll_col]).reset_index(drop=True)


    def calculate_distribution(self, returns_df, col='monthly_return', bins=None,labels=None):
        """
        收益区间分布

        参数：
            monthly_returns_df: 包含 'monthly_return' 列的DataFrame

        返回：
            dict: 各区间统计
        """
        # 定义区间边界和标签
        if bins is None:
            bins = [-1, -0.05, -0.02, 0, 0.02, 0.05, 0.10, 1]

        if labels is None:
            labels = ['<-5%', '-5%~-2%', '-2%~0%', '0%~2%', '2%~5%', '5%~10%', '>10%']

        # 切割数据
        returns_df['return_range'] = pd.cut(
            returns_df[col],
            bins=bins,
            labels=labels
        )

        # 统计各区间频次
        distribution = returns_df['return_range'].value_counts().sort_index()

        # 计算占比
        total = len(returns_df)
        distribution_pct = (distribution / total * 100).round(2)

        return distribution, distribution_pct, total

    pass

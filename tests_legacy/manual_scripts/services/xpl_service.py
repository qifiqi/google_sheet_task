import json
import math
from datetime import datetime
from typing import List, Dict, Any, Tuple, Optional
import re
import numpy as np
import pandas as pd
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
    
    def analyze(self, data: str, time_format: str = 'auto', return_col: int = 2) -> Dict[str, Any]:
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
            # 解析原始数据
            parsed_data = self._parse_input_data(data, return_col)
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
    
    def _parse_input_data(self, data: str, return_col: int) -> List[Dict[str, Any]]:
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
                if len(parts) < return_col:
                    continue
                    
                # 解析日期和收益率
                # Parse date and return value
                date_str = parts[0]
                val = parts[return_col - 1]
                if '%' in val:
                    val = float(val.replace('%', '')) / 100
                return_val = float(val) if isinstance(val, str) else val
                return_val = round(return_val, 4)
                
                # 添加到结果
                # Add to results
                results.append({
                    'date': date_str,           # 日期 Date
                    'daily_return': return_val,  # 每天收益率 Daily return
                })
                
            except (ValueError, IndexError) as e:
                logger.warning(f"解析行 {i+1} 时出错: {line}")
                continue
                
        return results


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
                # Calculate drawdown: (historical max - current) / historical max
                if historical_max > 0:
                    drawdown = (historical_max - current_row['net_value']) / historical_max
                else:
                    drawdown = 0

                yearly_data.at[index, 'drawdown'] = drawdown  # 回撤值 Drawdown value

            # 找到该年度的最大回撤
            # Find the maximum drawdown for the year
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
    def calculate_monthly_returns(df):
        """
        计算基金的月度收益率（按年分组计算）
        Calculate monthly returns of the fund (grouped by year)

        参数/Args:
            df: DataFrame，包含净值数据的DataFrame，必须有['year', 'net_value', 'date']列
                DataFrame containing net value data, must have ['year', 'net_value', 'date'] columns

        返回/Returns:
            list: 包含月度收益率信息的字典列表，每个字典包含:
                  List of dictionaries containing monthly return information, each dictionary contains:
                - 'year_month': 年月标识 Year and month identifier
                - 'monthly_return': 月度收益率（小数形式） Monthly return (in decimal)
                - 'year': 年份 Year
                - 'date': 时间戳 Timestamp
        """
        monthly_returns = []

        # 按年份分组处理
        # Group by year for processing
        yearly_groups = df.groupby('year')
        previous_month_data = None  # 保存上一个月份的数据 Store data from previous month

        for year_month, month_df in yearly_groups:
            if len(month_df) == 0:
                continue

            # 获取当前月份最后一天的数据（假设数据已按日期排序）
            # Get the last day's data of the current month (assuming data is sorted by date)
            current_month_last_day = month_df.iloc[-1]

            # 确定对比基准日
            # Determine comparison base day
            if previous_month_data is None:
                # 如果是第一个月，使用当前月份第一天作为基准
                # If it's the first month, use the first day of the current month as base
                comparison_day = month_df.iloc[0]
            else:
                # 否则使用上个月最后一天作为基准
                # Otherwise, use the last day of the previous month as base
                comparison_day = previous_month_data.iloc[-1]

            # 计算月度收益率：(本月最后一天净值 / 基准日净值 - 1)
            # Calculate monthly return: (end of month value / base day value - 1)
            monthly_return = current_month_last_day['net_value'] / comparison_day['net_value'] - 1

            # 记录月度收益数据
            # Record monthly return data
            monthly_returns.append({
                'year_month': str(year_month),  # 年月 Year and month
                'monthly_return': float(monthly_return.__round__(4)),  # 月收益率 Monthly return
                'year': str(current_month_last_day['year']),  # 年份 Year
                'net_value': current_month_last_day['net_value'],  # 净值
                'date': current_month_last_day['date'].strftime('%Y-%m-%d')  # 日期 Date
            })

            # 保存当前月份数据供下个月使用
            # Save current month's data for next month's comparison
            previous_month_data = month_df

        return monthly_returns

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
                    comparison_point = month_df.iloc[0]
                else:
                    # 否则使用上个月最后一个数据点作为基准
                    # Otherwise, use the last data point of the previous month as base
                    comparison_point = previous_month_data.iloc[-1]

                # 计算月度收益率：(月末净值 / 基准日净值 - 1)
                # Calculate monthly return: (end of month value / base day value - 1)
                monthly_return = (current_month_end['net_value'] / comparison_point['net_value'] - 1)

                # 记录月度数据
                # Record monthly data
                monthly_data.append({
                    'year_month': month,  # 年月 Year and month
                    'monthly_return': monthly_return,  # 月收益率 Monthly return
                    'year': current_month_end['year'],  # 年份 Year
                    'date': current_month_end['date']  # 日期 Date
                })

                previous_month_data = month_df

        return monthly_data

    def calculate_sharpe_ratios_by_periods(self,df):
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

        results = {}

        # 计算全部数据的夏普比率
        # Calculate Sharpe ratio for all data
        res = self.calculate_sharpe_for_period(monthly_df, "all", 12)
        # 保存结果
        # Save results
        results["all"] = res

        # 计算每年的夏普比率
        # Calculate Sharpe ratio for each year
        years = sorted(monthly_df['year'].unique())
        for i, year in enumerate(years):
            year_data = monthly_df[monthly_df['year'] == year]
            if len(year_data) >= 3:  # 至少需要3个月的数据 Need at least 3 months of data
                year_name = f"year_{i+1}_{year}"  # 例如: year_1_2023
                logger.info(f"计算年份/Calculating year {year_name}, 总月数/Total months: {len(year_data)}")
                res = self.calculate_sharpe_for_period(year_data, year_name, 12)
                results[year_name] = res


        # 计算滚动年份的夏普比率（前1年、前2年等）
        # Calculate rolling year Sharpe ratios (past 1 year, past 2 years, etc.)
        years = sorted(monthly_df['year'].unique(), reverse=True)
        for i, year in enumerate(years):
            year_data = monthly_df[monthly_df['year'] >= year]
            if len(year_data) >= 3:  # 至少需要3个月的数据 Need at least 3 months of data
                year_name = f"past_{i+1}_years_since_{year}"  # 例如: past_1_years_since_2023
                logger.info(f"计算滚动年份/Calculating rolling year {year_name}, 总月数/Total months: {len(year_data)}")
                res = self.calculate_sharpe_for_period(year_data, year_name, 12)
                results[year_name] = res

        return results

    def get_xpl(self, data: List[Dict[str, Any]],date='date',val = 'daily_return'):
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
            returns_rate = self.calculate_monthly_returns(df)
            sharpe_ratios = self.calculate_sharpe_ratios_by_periods(df)

            # 4. 构建返回结果
            # Build return results
            result = {
                "maximum_drawdown": maximum_drawdown,  # 最大回撤
                "returns_rate": returns_rate,    # 收益率
                "sharpe_ratios": sharpe_ratios         # 夏普比率
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

# 创建全局实例
xpl_analyzer = XPLAnalyzer()
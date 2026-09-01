"""文本或内存收益序列的绩效分析适配组件。

负责将调用方传入的日期与收益率记录转换为 DataFrame，并组织 XPL 等
分析入口所需的数据；具体绩效指标仍复用本包的计算组件。
"""

import json
import math
import re
from typing import Any, Dict, List

import numpy as np
import pandas as pd

from app.utils.logger import get_logger
from app.utils.value_parser import _convert_pandas_to_native

logger = get_logger(__name__)


class TextReturnAnalysisMixin:
    def get_xpl(self, data: List[Dict[str, Any]], date='date', val='daily_return'):
        """根据日期和日收益数据计算 XPL 指标。"""
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
            if self._has_dual_return_columns(parsed_data):
                metrics = self._calculate_metrics_v1(parsed_data)
                metrics["analysis_mode"] = "dual"
            else:
                metrics = self._calculate_metrics(parsed_data)
                metrics["analysis_mode"] = "single"
            metrics = self._sanitize_for_json(_convert_pandas_to_native(metrics))

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

                if len(parts) == 2:
                    results.append({
                        'date': date_str,  # 日期 Date
                        'daily_return': self._parse_return_value(parts[1]),  # 每天收益率 Daily return
                    })
                    continue

                index_return = self._parse_return_value(parts[1])
                start_return = self._parse_return_value(parts[2])

                # 添加到结果
                # Add to results
                results.append({
                    'date': date_str,  # 日期 Date
                    # 'daily_return': start_return,  # 每天收益率 Daily return
                    'index_return': index_return,  # 指数收益率 Index return
                    "start_return": start_return,  # 模型收益率 Start return
                })

            except (ValueError, IndexError) as e:
                logger.warning(f"解析行 {i + 1} 时出错: {line}")
                continue

        return results

    @staticmethod
    def _has_dual_return_columns(data: List[Dict[str, Any]]) -> bool:
        """判断输入记录是否同时包含指数和策略两列收益率。"""
        return any(
            "index_return" in row and "start_return" in row
            for row in data
            if isinstance(row, dict)
        )

    @staticmethod
    def _parse_return_value(value: Any) -> float:
        """解析数值或百分号文本形式的单期收益率。"""
        if isinstance(value, str):
            value = value.strip()
            if '%' in value:
                value = float(value.replace('%', '')) / 100
            else:
                value = float(value)
        return round(float(value), 4)

    @classmethod
    def _sanitize_for_json(cls, value: Any) -> Any:
        """递归清理 NaN、时间对象和 NumPy 标量，使分析结果可 JSON 编码。"""
        if isinstance(value, dict):
            return {key: cls._sanitize_for_json(item) for key, item in value.items()}
        if isinstance(value, list):
            return [cls._sanitize_for_json(item) for item in value]
        if isinstance(value, tuple):
            return [cls._sanitize_for_json(item) for item in value]
        if isinstance(value, np.generic):
            value = value.item()
        if isinstance(value, float):
            return value if math.isfinite(value) else None
        return value

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

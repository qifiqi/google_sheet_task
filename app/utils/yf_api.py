import pandas as pd
import yfinance as yf
import hashlib
import logging
import time
from datetime import datetime

import requests
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from app.utils.kline_adjustment import yahoo_adjust_flags



class YFApi:
    """
    """

    def __init__(self):
        self.kline_data = []
        self.logger = logging.getLogger(self.__class__.__name__)

    def get_kline_data(self, stock_code='BTC', period='max', interval='1d', proxy=None, adjust_type=None):
        # 3. 下载数据
        adjust_flags = yahoo_adjust_flags(adjust_type)
        data = yf.download(
            stock_code,
            period=period,
            interval=interval,
            progress=False,
            **adjust_flags,
        )
        data = self.parse_multiple_tickers(data)
        return data

    def parse_multiple_tickers(self,df):
        """
        处理包含多只股票的数据，转换为标准格式

        参数:
            df: 雅虎财经下载的多级索引DataFrame

        返回:
            list: 包含所有股票K线数据的字典列表，格式与您的规范一致
        """
        try:
            result = []

            # 获取所有唯一的股票代码
            if isinstance(df.columns, pd.MultiIndex):
                # 从多级索引中提取股票代码
                if 'Ticker' in df.columns.names:
                    tickers = df.columns.get_level_values('Ticker').unique()
                else:
                    # 尝试从第三层获取股票代码
                    tickers = df.columns.get_level_values(2).unique()
            else:
                # 如果只有单只股票，直接处理
                tickers = [df.columns[0]] if len(df.columns) > 0 else []

            self.logger.info(f"发现 {len(tickers)} 只股票: {list(tickers)}")

            for ticker in tickers:
                try:
                    # 提取该股票的数据
                    if isinstance(df.columns, pd.MultiIndex):
                        ticker_data = df.xs(ticker, level='Ticker', axis=1)
                        # 如果还有Price层级，去掉它
                        if isinstance(ticker_data.columns, pd.MultiIndex):
                            if 'Price' in ticker_data.columns.names:
                                ticker_data.columns = ticker_data.columns.droplevel('Price')
                    else:
                        ticker_data = df

                    # 遍历每一行数据
                    for date_idx, row in ticker_data.iterrows():
                        try:
                            # 获取基础数据
                            close_price = float(row.get('Close', 0))
                            open_price = float(row.get('Open', 0))
                            high_price = float(row.get('High', 0))
                            low_price = float(row.get('Low', 0))
                            volume = int(row.get('Volume', 0))

                            # 计算衍生指标（避免除零）
                            stock_zde = close_price - open_price  # 涨跌额

                            # 涨跌幅%
                            if open_price != 0:
                                stock_zdf = (stock_zde / open_price) * 100
                            else:
                                stock_zdf = 0.0

                            # 振幅%
                            if low_price != 0:
                                stock_zf = ((high_price - low_price) / low_price) * 100
                            else:
                                stock_zf = 0.0

                            # 成交额（如果没有则使用收盘价*成交量估算）
                            stock_cje = float(row.get('Adj Close', close_price)) * volume if volume > 0 else 0

                            # 换手率%（雅虎数据通常没有，设为0）
                            stock_hsl = 0.0

                            # 构建标准格式的记录
                            record = {
                                'stock_code': str(ticker),  # 股票代码
                                'stock_date': date_idx.strftime('%Y-%m-%d'),  # 日期
                                'stock_kp': round(open_price,2),  # 开盘价
                                'stock_sp': round(close_price,2),  # 收盘价
                                'stock_zg': round(high_price,2),  # 最高价
                                'stock_zd': round(low_price,2),  # 最低价
                                'stock_cjl': volume,  # 成交量
                                'stock_cje': round(stock_cje, 2),  # 成交额
                                'stock_zf': round(stock_zf, 2),  # 振幅%
                                'stock_zdf': round(stock_zdf, 2),  # 涨跌幅%
                                'stock_zde': round(stock_zde, 2),  # 涨跌额
                                'stock_hsl': stock_hsl,  # 换手率%
                                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                            }

                            result.append(record)

                        except Exception as row_error:
                            self.logger.warning(
                                f"处理股票 {ticker} 日期 {date_idx} 的数据失败: {str(row_error)}")
                            continue

                    self.logger.info(f"股票 {ticker} 处理完成，共 {ticker_data.shape[0]} 条记录")

                except Exception as ticker_error:
                    self.logger.error(f"处理股票 {ticker} 失败: {str(ticker_error)}")
                    continue

            self.logger.info(f"总共解析了 {len(result)} 条K线数据")
            return result

        except Exception as e:
            self.logger.exception(f"解析多股票数据失败: {str(e)}")
            return []

if __name__ == '__main__':
    api = YFApi()
    df = api.get_kline_data(stock_code=["MCHP"],period='10y')
    print(df)
    # tickers = df.columns.get_level_values('Ticker').unique()
    # print(tickers)
    # ticker_data = df.xs('AAPL', level='Ticker', axis=1)
    # print(api.parse_multiple_tickers(df))

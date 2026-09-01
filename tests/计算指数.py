from datetime import datetime

from app.utils.yf_api import YFApi
from app.services.google_sheet_service_C7 import GoogleSheetService

yf = YFApi()

ser = GoogleSheetService({
    "count_mode": "n_plus_1",
    "date_range_mode": [
        "recent"
    ],
    "end_date": "2026-08-20",
    "exclude_recent_years": [
        2,
        4
    ],
    "kline_adjustment": "forward",
    "kline_source": "auto",
    "market_type": "us",
    "parameters": [
        [
            "SCHD"
        ],
        [
            ""
        ],
        [
            3
        ]
    ],
    "price_mode": "ohlc_price",
    "sheets": [
        {
            "c7_model_version": "c7_0_3",
            "sheet_name": "control",
            "spreadsheet_id": "1eXH5TsJw2EuXmIiCgeqE2fOr2facxGguaXIubLgA7RA",
            "title": "C7.0.3.v20260729-回测-sharable-manual"
        }
    ],
    "start_date": "2021-08-20",
    "token_file": "data/google_sheet_tokens/token_2.json",
    "token_id": 2,
    "token_json": "",
    "token_name": "dwy",
    "token_selection_mode": "__random__",
    "token_task_type": "google_sheet",
    "token_type": "file"
}, "")


def _calculate_c7_0_3_index_returns(kline_rows):
    """以 C7.0.3 OHLC 收盘价计算相对首日的累计指数收益。"""
    base_close = None
    index_returns = []

    for index, row in enumerate(kline_rows, start=1):
        try:
            close_price = float(row["stock_sp"])
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError(f"C7.0.3 K线第 {index} 条收盘价无效") from error
        if close_price <= 0:
            raise ValueError(f"C7.0.3 K线第 {index} 条收盘价必须大于 0")

        if base_close is None:
            base_close = close_price
        index_returns.append(close_price / base_close - 1)

    return index_returns


if __name__ == '__main__':

    kline = yf.get_kline_data('SCHD')

    import pandas as pd

    # 转换为DataFrame
    df = pd.DataFrame(kline)

    # 将 stock_date 转为日期类型，并按日期排序
    df['stock_date'] = pd.to_datetime(df['stock_date'])
    df = df.sort_values('stock_date').reset_index(drop=True)

    # 查看数据结构
    print(df.head())
    print(df.info())

    # 选取并重命名核心列
    kline_df = df[['stock_date', 'stock_kp', 'stock_zg', 'stock_zd', 'stock_sp', 'stock_cjl']].copy()

    # 将日期设为索引（便于后续时间切片）
    kline_df = kline_df.set_index('stock_date')

    # 确保数值列为浮点型
    kline_df = kline_df.astype(float)

    print(kline_df.tail(10))

    # 获取数据中的最新日期作为截止日期
    end_date = pd.to_datetime(ser.config["end_date"])
    print(f"数据最新日期: {end_date}")

    # 定义不同周期
    start_date_1y = end_date - pd.DateOffset(years=1)
    start_date_3y = end_date - pd.DateOffset(years=3)
    start_date_5y = end_date - pd.DateOffset(years=5)
    start_date_6y = end_date - pd.DateOffset(years=6)

    # 筛选数据
    kline_1y = kline_df[kline_df.index >= start_date_1y]
    kline_3y = kline_df[kline_df.index >= start_date_3y]
    kline_5y = kline_df[kline_df.index >= start_date_5y]
    kline_6y = kline_df[kline_df.index >= start_date_6y]

    print(f"近一年数据量: {len(kline_1y)}")
    print(f"近三年数据量: {len(kline_3y)}")
    print(f"近五年数据量: {len(kline_5y)}")
    print(f"近六年数据量: {len(kline_6y)}")

    # 计算各周期的指数收益
    returns_1y = _calculate_c7_0_3_index_returns(kline_1y.to_dict(orient='records'))
    returns_3y = _calculate_c7_0_3_index_returns(kline_3y.to_dict(orient='records'))
    returns_5y = _calculate_c7_0_3_index_returns(kline_5y.to_dict(orient='records'))
    returns_6y = _calculate_c7_0_3_index_returns(kline_6y.to_dict(orient='records'))

    # ========== 输出到Excel ==========

    # 1. 准备要输出的数据（修正：周期和长度匹配）
    output_data = {
        '周期': ['近一年', '近三年', '近五年', '近六年'],
        '起始日期': [
            start_date_1y.strftime('%Y-%m-%d'),
            start_date_3y.strftime('%Y-%m-%d'),
            start_date_5y.strftime('%Y-%m-%d'),
            start_date_6y.strftime('%Y-%m-%d')
        ],
        '结束日期': [end_date.strftime('%Y-%m-%d')] * 4,
        '数据条数': [
            len(kline_1y),
            len(kline_3y),
            len(kline_5y),
            len(kline_6y)
        ],
        '累计收益率': [
            returns_1y[-1] if returns_1y else None,
            returns_3y[-1] if returns_3y else None,
            returns_5y[-1] if returns_5y else None,
            returns_6y[-1] if returns_6y else None
        ],
        '年化收益率': [
            (1 + returns_1y[-1]) ** (252 / len(returns_1y)) - 1 if returns_1y and len(returns_1y) > 0 else None,
            (1 + returns_3y[-1]) ** (252 / len(returns_3y)) - 1 if returns_3y and len(returns_3y) > 0 else None,
            (1 + returns_5y[-1]) ** (252 / len(returns_5y)) - 1 if returns_5y and len(returns_5y) > 0 else None,
            (1 + returns_6y[-1]) ** (252 / len(returns_6y)) - 1 if returns_6y and len(returns_6y) > 0 else None
        ]
    }

    summary_df = pd.DataFrame(output_data)

    # 2. 创建Excel文件
    filename = f'SCHD_analysis_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx'
    with pd.ExcelWriter(filename, engine='openpyxl') as writer:
        # Sheet 1: 汇总统计
        summary_df.to_excel(writer, sheet_name='汇总统计', index=False)

        # Sheet 2: 完整K线数据（近5年）- 使用中文列名
        kline_5y.to_excel(writer, sheet_name='完整K线数据')

        # Sheet 3: 近一年日收益率明细
        if returns_1y:
            daily_1y = pd.DataFrame({
                '日期': kline_1y.index,
                '开盘价': kline_1y['stock_kp'],
                '最高价': kline_1y['stock_zg'],
                '最低价': kline_1y['stock_zd'],
                '收盘价': kline_1y['stock_sp'],
                '成交量': kline_1y['stock_cjl'],
                '指数收益率': returns_1y
            })
            daily_1y.to_excel(writer, sheet_name='近一年日收益率', index=False)

        # Sheet 4: 近三年日收益率明细
        if returns_3y:
            daily_3y = pd.DataFrame({
                '日期': kline_3y.index,
                '开盘价': kline_3y['stock_kp'],
                '最高价': kline_3y['stock_zg'],
                '最低价': kline_3y['stock_zd'],
                '收盘价': kline_3y['stock_sp'],
                '成交量': kline_3y['stock_cjl'],
                '指数收益率': returns_3y
            })
            daily_3y.to_excel(writer, sheet_name='近三年日收益率', index=False)

        # Sheet 5: 近五年日收益率明细
        if returns_5y:
            daily_5y = pd.DataFrame({
                '日期': kline_5y.index,
                '开盘价': kline_5y['stock_kp'],
                '最高价': kline_5y['stock_zg'],
                '最低价': kline_5y['stock_zd'],
                '收盘价': kline_5y['stock_sp'],
                '成交量': kline_5y['stock_cjl'],
                '指数收益率': returns_5y
            })
            daily_5y.to_excel(writer, sheet_name='近五年日收益率', index=False)

        # Sheet 6: 近六年日收益率明细
        if returns_6y:
            daily_6y = pd.DataFrame({
                '日期': kline_6y.index,
                '开盘价': kline_6y['stock_kp'],
                '最高价': kline_6y['stock_zg'],
                '最低价': kline_6y['stock_zd'],
                '收盘价': kline_6y['stock_sp'],
                '成交量': kline_6y['stock_cjl'],
                '指数收益率': returns_6y
            })
            daily_6y.to_excel(writer, sheet_name='近六年日收益率', index=False)

    print(f"✅ 数据已导出到: {filename}")
    print(f"   - 汇总统计: {len(summary_df)} 行")
    print(f"   - 近一年K线: {len(kline_1y)} 行")
    print(f"   - 近三年K线: {len(kline_3y)} 行")
    print(f"   - 近五年K线: {len(kline_5y)} 行")
    print(f"   - 近六年K线: {len(kline_6y)} 行")
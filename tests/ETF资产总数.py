# import yfinance as yf
#
# symbol = "QQQ"
# t = yf.Ticker(symbol)
# # Net Assets
# ops = t.funds_data.fund_operations
#
# # 列名就是基金代码本身
# total_net_assets_k = ops.loc["Total Net Assets", symbol]
# total_net_assets_usd = float(total_net_assets_k) * 1000  # 千美元 -> 美元
# print(ops)
# print(f"{symbol} 总净资产: {total_net_assets_usd:,.0f} USD")
# SPY 总净资产: 513,975,700,000 USD
#
# import yfinance as yf
#
#
# def get_fund_assets(symbol):
#     t = yf.Ticker(symbol)
#
#     # 用 info 里的 quoteType 判断，不要用 funds_data.quote_type
#     try:
#         info = t.info
#         qtype = info.get('quoteType')
#     except Exception:
#         return None
#
#     if qtype not in ('ETF', 'MUTUALFUND'):
#         return None
#
#     try:
#         ops = t.funds_data.fund_operations
#         if ops is None or ops.empty:
#             return None
#         val_k = ops.loc["Total Net Assets"].iloc[0]
#         return float(val_k) * 1000
#     except Exception:
#         return None
#
#
#
# if __name__ == '__main__':
#     print(get_fund_assets("QQQ"))
#     print(get_fund_assets("AAPL"))

#
# import akshare as ak
# import pandas as pd
# from typing import Optional, Union
#
#
# def get_a_etf_assets(etf_code: str) -> Optional[dict]:
#     """
#     获取A股ETF的资产规模（总资产）。
#
#     参数:
#         etf_code: 6位ETF代码，如 '510300' (沪深300ETF)
#
#     返回:
#         包含代码、名称、最新规模的字典；失败返回 None
#     """
#     try:
#         # fund_etf_spot_em 返回全市场ETF实时行情，包含规模字段
#         df = ak.fund_etf_spot_em()
#
#         # 确保代码格式一致（通常接口返回不带后缀）
#         etf_code = str(etf_code).strip().zfill(6)
#
#         row = df[df['代码'] == etf_code]
#         if row.empty:
#             print(f"未找到 ETF 代码: {etf_code}")
#             return None
#
#         row = row.iloc[0]
#         # 东方财富的ETF行情接口中，规模字段名可能是 '总市值' 或 '流通市值'（单位：元）
#         # 实际字段需根据 ak 版本确认，这里做兼容处理
#         scale_col = None
#         for col in ['总市值', '流通市值', '规模']:
#             if col in row.index:
#                 scale_col = col
#                 break
#
#         result = {
#             '代码': etf_code,
#             '名称': row.get('名称', ''),
#             '最新规模': row[scale_col] if scale_col else None,
#             '单位': '元' if scale_col else '未知',
#         }
#         return result
#
#     except Exception as e:
#         print(f"获取 ETF {etf_code} 规模失败: {e}")
#         return None
#
#
# def batch_get_etf_assets(codes: list) -> pd.DataFrame:
#     """批量获取多只ETF的规模"""
#     results = []
#     for code in codes:
#         info = get_a_etf_assets(code)
#         if info:
#             results.append(info)
#     return pd.DataFrame(results)
#
#
# if __name__ == '__main__':
#     # 测试：沪深300ETF、科创50ETF、创业板ETF
#     codes = ['510300', '588000', '159915']
#     df = batch_get_etf_assets(codes)
#     print(df)
5

# import akshare as ak
#
# df = ak.fund_etf_spot_em()
# etf = df[df['代码'] == '510300']
# print(etf[['代码', '名称', '总市值']])
# df.to_csv("全市场基金规模变动数据.csv",index=False)


import yfinance as yf

t = yf.Ticker("AAPL")
info = t.info
net_assets = info.get('totalAssets')  # 可能为 None

print(dict(info),net_assets)
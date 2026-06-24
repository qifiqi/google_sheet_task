import pandas as pd

from app.services.xpl_service import XPLAnalyzer
from app.services.d import data



xpl = XPLAnalyzer()

# 转换为DataFrame便于计算
# Convert to DataFrame for calculation
parsed_data = xpl._parse_input_data(data)

df = pd.DataFrame(parsed_data)
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

print(xpl.monthly_maximum_drawdown(index_df))
print(xpl.monthly_maximum_drawdown(start_df))

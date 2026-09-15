import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import pandas as pd

# ---------- 1. 读数据 ----------
df = pd.read_csv('excess_df.csv')
df['date'] = pd.to_datetime(df['date'])
df = df.sort_values('date').reset_index(drop=True)

# ---------- 2. 画图 ----------
fig, ax1 = plt.subplots(figsize=(15, 6))

# 左轴：日超额收益（柱状图，红正绿负）
colors = ['#d62728' if x >= 0 else '#2ca02c' for x in df['excess_return']]
ax1.bar(df['date'], df['excess_return'], color=colors, alpha=0.6,
        width=0.8, label='日超额收益')
ax1.axhline(0, color='black', linewidth=0.8, linestyle='--')
ax1.set_ylabel('日超额收益', fontsize=12)

# 右轴：超额累计净值（折线图）
ax2 = ax1.twinx()
ax2.plot(df['date'], df['net_value'], color='#1f77b4',
         linewidth=2, label='超额累计净值')
ax2.axhline(1, color='gray', linewidth=0.8, linestyle=':')
ax2.set_ylabel('超额累计净值', fontsize=12)

# ---------- 3. 日期格式 ----------
ax1.xaxis.set_major_locator(mdates.AutoDateLocator())
ax1.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m'))
fig.autofmt_xdate()

# ---------- 4. 图例合并 ----------
lines1, labels1 = ax1.get_legend_handles_labels()
lines2, labels2 = ax2.get_legend_handles_labels()
ax1.legend(lines1 + lines2, labels1 + labels2, loc='upper left', fontsize=11)

plt.title('日超额收益（柱）与超额累计净值（线）', fontsize=14)
plt.tight_layout()
plt.savefig('excess_return.png', dpi=150)
plt.show()
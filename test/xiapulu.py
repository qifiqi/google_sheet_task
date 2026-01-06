# 求净值:1*1+每天收益率
# 求月收益率：最后一天除以第一天-1

# 月末收益率的边准差  = (每月月收益率)
# 求年化标准差：月末收益率的边准差*根号 12
# 夏普：月末收益率的均值*12 除以月末标准差

# 当天的净值除以之前的最高-1


import json
import math
from datetime import datetime, timedelta
from collections import defaultdict

import numpy as np
import pandas as pd



def calculate_sharpe_ratios_huice(json_file_path, risk_free_rate=0.02):
    """

    """

    # 读取数据
    with open(json_file_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    # 转换为DataFrame便于处理
    df = pd.DataFrame(data)
    df['时间'] = pd.to_datetime(df['时间'])
    df = df.sort_values('时间')

    # 1. 计算净值
    df['净值'] = 1 * (1 + df['每天收益率'])
    # df['净值'] = (1 + df['每天收益率']).cumprod()

    # 2. 提取年份信息
    df['年份'] = df['时间'].dt.year
    df['月份'] = df['时间'].dt.month
    df['年月'] = df['时间'].dt.strftime('%Y-%m')
    #
    # all_year = df['年份'].unique()
    # df_1 = df.copy()
    # for year_name in all_year:
    #     all_year_df = df_1[df_1['年份'] == year_name]
    #     for index in range(len(all_year_df)):
    #         item_df = all_year_df.iloc[index]
    #         # print(item_df)
    #         ddd = all_year_df[all_year_df['时间'] <= item_df['时间']]
    #         day_return =  (ddd['净值'].max()-item_df['净值']) / ddd['净值'].max()
    #         if day_return == np.nan:
    #             day_return = 0
    #         all_year_df.at[index, '最大回测'] = day_return
    #         # day_return =  (1-item_df['净值']) / ddd['净值'].max()
    #         # print(day_return)
    #     print(all_year_df[all_year_df['最大回测'] == all_year_df['最大回测'].max()])
    #     pass
    #
    all_year = df['年份'].unique()
    df_3 = df.copy()

    for year_name in all_year:
        all_year_df = df_3[df_3['年份'] == year_name]

        # 先按时间排序，确保计算正确
        all_year_df = all_year_df.sort_values('时间').copy()
        all_year_df = all_year_df.reset_index(drop=True)

        for index in range(len(all_year_df)):
            item_df = all_year_df.iloc[index]

            # 获取当前时间及之前的所有数据
            ddd = all_year_df.iloc[:index + 1]  # 使用iloc更高效

            # 计算到当前时间的最高净值
            historical_max = ddd['净值'].max()

            # 计算回撤：(历史最高-当前净值)/历史最高
            if historical_max > 0:
                day_return = (historical_max - item_df['净值']) / historical_max
            else:
                day_return = 0

            all_year_df.at[index, '最大回测'] = day_return

        # 找到并输出最大回撤
        max_dd_row = all_year_df.loc[all_year_df['最大回测'].idxmax()]
        print(f"年份: {year_name}")
        print(f"最大回撤: {max_dd_row['最大回测']:.4f} ({max_dd_row['最大回测']:.2%})")
        print(f"发生时间: {max_dd_row['时间']}")
        print(f"当时净值: {max_dd_row['净值']:.4f}")
        print("-" * 50)

        # 将计算后的数据更新回df_1
        df_3.loc[all_year_df.index, '最大回测'] = all_year_df['最大回测']


    #
    # df_2 = df.copy()
    #
    # for index in range(len(df_2)):
    #     item_df = df_2.iloc[index]
    #     # print(item_df)
    #     ddd = df_2[df_2['时间'] <= item_df['时间']]
    #     day_return =  (ddd['净值'].max()-item_df['净值']) / ddd['净值'].max()
    #     if day_return == np.nan:
    #         day_return = 0
    #     df_2.at[index, '最大回测'] = day_return
    #     # day_return =  (1-item_df['净值']) / ddd['净值'].max()
    #     # print(day_return)
    # print(df_2[df_2['最大回测'] == df_2['最大回测'].max()])
    # pass

    df_3 = df.copy()

    # 确保数据按时间排序
    df_3 = df_3.sort_values('时间').reset_index(drop=True)

    for index in range(len(df_3)):
        item_df = df_3.iloc[index]

        # 获取从开始到当前时间的所有数据
        ddd = df_3.iloc[:index + 1]  # 更高效的切片方式

        # 计算到当前时间的最高净值
        historical_max = ddd['净值'].max()

        # 计算回撤：(历史最高 - 当前净值) / 历史最高
        if historical_max > 0:
            day_return = (historical_max - item_df['净值']) / historical_max
        else:
            day_return = 0

        # 正确检查NaN值
        if pd.isna(day_return):
            day_return = 0

        df_3.at[index, '最大回测'] = day_return

    # 找到最大回撤的行
    # max_dd_value = df_3['最大回测'].max()
    # max_dd_rows = df_3[df_3['最大回测'] == max_dd_value]
    max_dd_row = df_3.loc[df_3['最大回测'].idxmax()]
    print(max_dd_row)


def calculate_sharpe_ratios_year(json_file_path, risk_free_rate=0.02):
    """

    """

    # 读取数据
    with open(json_file_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    # 转换为DataFrame便于处理
    df = pd.DataFrame(data)
    df['时间'] = pd.to_datetime(df['时间'])
    df = df.sort_values('时间')

    # 1. 计算净值
    df['净值'] = 1 * (1 + df['每天收益率'])
    # df['净值'] = (1 + df['每天收益率']).cumprod()

    # 2. 提取年份信息
    df['年份'] = df['时间'].dt.year
    df['月份'] = df['时间'].dt.month
    df['年月'] = df['时间'].dt.strftime('%Y-%m')

    # 3. 计算年度收益率
    monthly_data = []
    monthly_groups = df.groupby('年份')
    last_month = None
    for month, month_df in monthly_groups:
        if len(month_df) > 0:
            first_day = month_df.iloc[-1]
            # first_day = month_df.iloc[0]
            if last_month is None:
                last_day = month_df.iloc[0]
            else:
                last_day = last_month.iloc[-1]
            # month_return = (last_day['净值'] / (first_day['净值'] - 1))
            month_return = (first_day['净值'] / last_day['净值']  - 1)
            # month_return = (last_day['净值'] / first_day['净值'] - 1) * 100  # 转换为百分比
            monthly_data.append({
                '年月': month,
                '月收益率': month_return,
                '年份': first_day['年份'],
                '时间': first_day['时间']
            })
            last_month = month_df


def calculate_sharpe_ratios(json_file_path, risk_free_rate=0.02):
    """
    计算不同时间段的夏普比率

    参数:
    json_file_path: JSON文件路径
    risk_free_rate: 无风险年化利率（默认2%）

    返回:
    包含不同时间段夏普比率的字典
    """

    # 读取数据
    with open(json_file_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    # 转换为DataFrame便于处理
    df = pd.DataFrame(data)
    df['时间'] = pd.to_datetime(df['时间'])
    df = df.sort_values('时间')

    # 1. 计算净值
    df['净值'] = 1 * (1 + df['每天收益率'])
    # df['净值'] = (1 + df['每天收益率']).cumprod()

    # 2. 提取年份信息
    df['年份'] = df['时间'].dt.year
    df['月份'] = df['时间'].dt.month
    df['年月'] = df['时间'].dt.strftime('%Y-%m')

    # 3. 计算月度收益率
    # 找到每个月的第一天和最后一天
    monthly_data = []
    monthly_groups = df.groupby('年月')
    last_month = None
    for month, month_df in monthly_groups:
        if len(month_df) > 0:
            first_day = month_df.iloc[-1]
            # first_day = month_df.iloc[0]
            if last_month is None:
                last_day = month_df.iloc[0]
            else:
                last_day = last_month.iloc[-1]
            # month_return = (last_day['净值'] / (first_day['净值'] - 1))
            month_return = (first_day['净值'] / last_day['净值']  - 1)
            # month_return = (last_day['净值'] / first_day['净值'] - 1) * 100  # 转换为百分比
            monthly_data.append({
                '年月': month,
                '月收益率': month_return,
                '年份': first_day['年份'],
                '时间': first_day['时间']
            })
            last_month = month_df
    monthly_df = pd.DataFrame(monthly_data)
    print(monthly_df)
    # 4. 计算整体数据范围
    start_date = df['时间'].min()
    end_date = df['时间'].max()
    total_months = len(monthly_df)

    print(f"数据时间范围: {start_date.date()} 到 {end_date.date()}")
    print(f"总数据月份数: {total_months}个月")
    print("=" * 50)

    results = {}

    # 5. 计算不同时间段的夏普比率

    # 函数：计算给定月度数据的夏普比率
    def calculate_sharpe_for_period(monthly_subset, period_name, annualization_factor=12):
        if len(monthly_subset) < 2:
            return None
        print(monthly_subset.to_string())
        # 转换为小数
        monthly_returns = monthly_subset['月收益率']
        print(monthly_returns.to_string())
        # 平均月收益率
        avg_monthly_return = monthly_returns.mean()

        # 月度标准差
        # monthly_std = monthly_returns.std(ddof=0)  # # 总体标准差
        monthly_std = monthly_returns.std(ddof=1)  # 样本标准差

        # 年化收益率和年化标准差
        annual_return = avg_monthly_return * annualization_factor

        # 年化标准差
        annual_std = monthly_std * math.sqrt(annualization_factor)


        # 夏普比率
        if annual_std != 0:
            sharpe_ratio = avg_monthly_return * annualization_factor / annual_std
            # sharpe_ratio = (annual_return - annual_risk_free) / annual_std
        else:
            sharpe_ratio = 0

        # 计算其他统计指标
        total_return = ((monthly_returns + 1).prod() - 1) * 100  # 总收益率%
        max_return = monthly_returns.max() * 100
        min_return = monthly_returns.min() * 100

        results[period_name] = {
            '夏普比率': sharpe_ratio,
            '年化收益率': annual_return * 100,  # 转换为百分比
            '年化标准差': annual_std * 100,  # 转换为百分比
            '平均月收益率': avg_monthly_return * 100,
            '月度标准差': monthly_std * 100,
            '总收益率': total_return,
            '最大月收益率': max_return,
            '最小月收益率': min_return,
            '月数': len(monthly_subset),
            '开始时间': monthly_subset['时间'].min().strftime('%Y-%m'),
            '结束时间': monthly_subset['时间'].max().strftime('%Y-%m')
        }

        return sharpe_ratio

    calculate_sharpe_for_period(monthly_df, "全部", 12)
    # # 第几年
    # years = sorted(monthly_df['年份'].unique())
    # for i, year in enumerate(years):
    #     year_data = monthly_df[monthly_df['年份'] == year]
    #     if len(year_data) >= 3:  # 至少需要3个月的数据
    #         year_name = f"第{i + 1}年({year})"
    #         calculate_sharpe_for_period(year_data, year_name, 12)
    #
    # # 前几年
    # years = sorted(monthly_df['年份'].unique(), reverse=True)
    # for i, year in enumerate(years):
    #     year_data = monthly_df[monthly_df['年份'] >= year]
    #     if len(year_data) >= 3:  # 至少需要3个月的数据
    #         year_name = f"前{i + 1}年({year})"
    #         # print(year_name,len(year_data))
    #         calculate_sharpe_for_period(year_data, year_name, 12)
    # print(json.dumps(results, indent=4,ensure_ascii=False))
    pass


# 使用示例
if __name__ == "__main__":
    # 使用示例JSON文件路径
    json_file_path = "data.json"

    try:
        # results, summary_df, df, monthly_df = calculate_sharpe_ratios_year(json_file_path)
        # results, summary_df, df, monthly_df = calculate_sharpe_ratios_huice(json_file_path)
        results, summary_df, df, monthly_df = calculate_sharpe_ratios(json_file_path)

        print("\n" + "=" * 50)
        print("详细统计表格:")
        print("=" * 50)
        print(summary_df.round(4).to_string())

        # 保存结果到CSV文件
        summary_df.to_csv('夏普比率分析结果.csv', encoding='utf-8-sig')
        print("\n结果已保存到 '夏普比率分析结果.csv'")

        # # 可选：绘制净值曲线
        # import matplotlib.pyplot as plt
        #
        # plt.figure(figsize=(12, 6))
        # plt.plot(df['时间'], df['净值'])
        # plt.title('净值曲线')
        # plt.xlabel('日期')
        # plt.ylabel('净值')
        # plt.grid(True)
        # plt.savefig('净值曲线.png', dpi=300, bbox_inches='tight')
        # plt.show()

    except FileNotFoundError:
        print(f"错误：找不到文件 {json_file_path}")
    except json.JSONDecodeError:
        print("错误：JSON文件格式不正确")
    except KeyError as e:
        print(f"错误：JSON文件中缺少必要的字段 {e}")
    except Exception as e:
        print(f"发生错误：{str(e)}")
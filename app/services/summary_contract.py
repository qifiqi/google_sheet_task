"""20 项汇总指标契约（前后端共享行契约的单一来源，2026-09 审计 C6 批次）。

行序即前端展示顺序；新增/调整指标只改本文件，两侧消费方
（backtest_multi_product_service 的预览行、backtest_report_query_service
的单品摘要行）同步生效。
"""

from __future__ import annotations

# (分类, 指标名, 指数字段, 模型结果字段, 数值类型)
# 指数字段为 None 表示该指标无对应指数口径（前端以 "-" 展示）。
SUMMARY_ROW_CONTRACT = [
    ("绝对收益", "年化收益", "index_annualized_return", "start_annualized_return", "percent"),
    ("绝对收益", "盈利年份百分比", "index_profit_annual", "start_profit_annual", "percent"),
    ("绝对收益", "月盈利百分比", "index_profit_monthly_percentage", "start_profit_monthly_percentage", "percent"),
    ("绝对收益", "平均月收益率", "index_avg_monthly_return", "start_avg_monthly_return", "percent"),
    ("绝对收益", "月收益率波动率", "index_monthly_return_volatility", "start_monthly_return_volatility", "percent"),
    ("相对收益", "年化超额收益", None, "annualized_return_diff", "percent"),
    ("相对收益", "跑赢年份(百分比)", None, "outperform_year", "percent"),
    ("相对收益", "月超额收益胜率", None, "monthly_excess_return_percentage", "percent"),
    ("相对收益", "平均月超额", None, "avg_monthly_excess_return", "percent"),
    ("相对收益", "月超额波动率", None, "monthly_excess_volatility", "percent"),
    ("回撤", "年最大超额回撤", None, "year_max_excess_drawdown", "percent"),
    ("回撤", "超额回撤胜率", None, "excess_drawdown_winning_rate", "percent"),
    ("回撤", "年最大回撤", None, "start_max_drawdown", "percent"),
    ("回撤", "最大修复天数", None, "start_maximum_number_of_backtest_repair_days", "number"),
    ("回撤", "超额最大修复天数", None, "excess_maximum_number_of_backtest_repair_days", "number"),
    ("比率", "夏普比率", "index_sharpe_ratio", "start_sharpe_ratio", "number"),
    ("比率", "卡玛比率", "index_kama_ratio", "start_kama_ratio", "number"),
    ("比率", "索提诺比率", "index_sortino_ratio", "start_sortino_ratio", "number"),
    ("夏普", "超额夏普", None, "excess_sharpe", "number"),
    ("索提诺", "超额索提诺比率", None, "excess_sortino", "number"),
]

# 仅标签序列（单品 C3 摘要按此对齐行序后追加其专属行）。
SUMMARY_ROW_LABELS = [(category, metric) for category, metric, *_ in SUMMARY_ROW_CONTRACT]

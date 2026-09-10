"""五处汇总指标投影的 golden 输出快照（ponytail 审计 B2 前置守卫）。

锁定以下入口在标准 calculate_metrics fixture 上的当前输出，任何
"year=='all' 投影" 归并重构（project_summary_metrics 等）必须保持
本文件快照逐字段不变：

- backtest_multi_product_service._derive_metrics（数值字典，None 容差）
- backtest_report_query_service._extract_summary_rows（21 行格式化串）
- model_summary.extractor._extract_backtest_summary_rows（21 行格式化串）
- performance_analysis.exporter.format_export_file_data（Excel 二维块）
- performance_analysis.result_mapper.get_return_analysis_v1（数值字典，0 容差）

已知怪癖被有意锁定（修改需单独评审）：
- report_query 卡玛比率 model_value 为空（读的是 start_sharpe_all 的 kama_ratio）；
- extractor/exporter 的"年最大超额回撤"= start−index 方向，multi 为 index−start；
- result_mapper 的 avg 月超额分母为全部月份数，multi/report_query/extractor
  分母为有效月份数。
"""

import json

import pytest

from app.services.backtest_multi_product_service import _derive_metrics
from app.services.backtest_report_query_service import _extract_summary_rows
from app.services.model_summary.extractor import _extract_backtest_summary_rows
from app.services.performance_analysis.analyzer import performance_analyzer

CALCULATE_METRICS = {
    "excess_returns": [
        {"year": 2024, "annualized_return_diff": 0.12, "index_annualized_return": 0.05,
         "start_annualized_return": 0.2, "index_return": 0.05, "start_return": 0.2},
        {"year": "all", "index_annualized_return": 0.08, "start_annualized_return": 0.21,
         "annualized_return_diff": 0.13,
         "start_end_date": "2024-01-01 00:00:00/2025-01-01 00:00:00"},
    ],
    "index_profit_annual": 0.6,
    "start_profit_annual": 0.75,
    "index_profit_monthly": [{"year": "all", "profit_monthly_percentage": 0.55}],
    "start_profit_monthly": [{"year": "all", "profit_monthly_percentage": 0.62}],
    "index_sharpe_ratios": {"all": {
        "avg_monthly_return": 0.02, "monthly_std_dev": 0.03,
        "annual_std_dev": 0.1, "sharpe_ratio": 0.8,
    }},
    "start_sharpe_ratios": {"all": {
        "avg_monthly_return": 0.03, "monthly_std_dev": 0.04,
        "annual_std_dev": 0.14, "sharpe_ratio": 1.1,
    }},
    "index_monthly_return_volatility": 0.03,
    "start_monthly_return_volatility": 0.045,
    "outperform_year": 3,
    "monthly_excess_volatility": 0.02,
    "monthly_excess_return_percentage": [{"year": "all", "excess_return": 0.66}],
    "monthly_excess_returns": [
        {"date": "2024-01", "monthly_excess_return_diff": 0.01, "start_monthly_return": 0.04},
        {"date": "2024-02", "monthly_excess_return_diff": 0.03, "start_monthly_return": 0.05},
        {"date": "2024-03", "monthly_excess_return_diff": -0.005, "start_monthly_return": 0.06},
    ],
    "index_maximum_drawdown": {
        "year_maximum_drawdown": [{"year": 2024, "drawdown": 0.10}],
        "total_maximum_drawdown": {"drawdown": -0.12},
    },
    "start_maximum_drawdown": {
        "year_maximum_drawdown": [{"year": 2024, "drawdown": 0.25}],
        "total_maximum_drawdown": {"drawdown": -0.3},
    },
    "index_kama_ratio": [{"year": "all", "kama_ratio": 0.4}],
    "start_kama_ratio": [{"year": "all", "kama_ratio": 0.5}],
    "index_sortino_ratio": [{"year": "all", "sortino_ratio": 1.2}],
    "start_sortino_ratio": [{"year": "all", "sortino_ratio": 1.6}],
    "excess_sharpe": 0.9,
    "excess_sortino": 1.4,
    "excess_drawdown_winning_rate": 0.7,
    "start_maximum_number_of_backtest_repair_days": 12,
    "excess_maximum_number_of_backtest_repair_days": 8,
    "year_index_yearly_max_repair_days": {"2024": 6, "2025": 9},
    "year_start_yearly_max_repair_days": {"2024": 15, "2025": 20},
}

RETURN_ROWS = [
    {"date": "2024-01-02", "index_return": 0.01, "start_return": 0.02},
    {"date": "2024-01-03", "index_return": 0.012, "start_return": 0.025},
    {"date": "2024-01-04", "index_return": -0.005, "start_return": 0.018},
]


def _loads(text):
    return json.loads(text)


MULTI_EXPECTED = _loads(
    '{"annualized_return_diff": 0.13, "avg_monthly_excess_return": 0.011666666666666665,'
    ' "excess_drawdown_winning_rate": 0.7, "excess_maximum_number_of_backtest_repair_days": 8,'
    ' "excess_sharpe": 0.9, "excess_sortino": 1.4, "index_annualized_return": 0.08,'
    ' "index_avg_monthly_return": 0.02, "index_kama_ratio": 0.4,'
    ' "index_monthly_return_volatility": 0.03, "index_profit_annual": 0.6,'
    ' "index_profit_monthly_percentage": 0.55, "index_sharpe_ratio": 0.8,'
    ' "index_sortino_ratio": 1.2, "monthly_excess_return_percentage": 0.66,'
    ' "monthly_excess_volatility": 0.02, "outperform_year": 3,'
    ' "start_annualized_return": 0.21, "start_avg_monthly_return": 0.03,'
    ' "start_kama_ratio": 0.5, "start_max_drawdown": -0.3,'
    ' "start_maximum_number_of_backtest_repair_days": 12,'
    ' "start_monthly_return_volatility": 0.045, "start_profit_annual": 0.75,'
    ' "start_profit_monthly_percentage": 0.62, "start_sharpe_ratio": 1.1,'
    ' "start_sortino_ratio": 1.6, "year_max_excess_drawdown": -0.15}'
)

RQ_EXPECTED = _loads(
    '["2024-01-01 00:00:00/2025-01-01 00:00:00", ['
    '{"category": "绝对收益", "index_value": "8.00%", "metric": "年化收益", "model_value": "21.00%"},'
    '{"category": "绝对收益", "index_value": "60.00%", "metric": "盈利年份百分比", "model_value": "75.00%"},'
    '{"category": "绝对收益", "index_value": "55.00%", "metric": "月盈利百分比", "model_value": "62.00%"},'
    '{"category": "绝对收益", "index_value": "2.00%", "metric": "平均月收益率", "model_value": "3.00%"},'
    '{"category": "绝对收益", "index_value": "3.00%", "metric": "月收益率波动率", "model_value": "4.50%"},'
    '{"category": "相对收益", "index_value": "", "metric": "年化超额收益", "model_value": "13.00%"},'
    '{"category": "相对收益", "index_value": "", "metric": "跑赢年份(百分比)", "model_value": "300.00%"},'
    '{"category": "相对收益", "index_value": "", "metric": "月超额收益胜率", "model_value": "66.00%"},'
    '{"category": "相对收益", "index_value": "", "metric": "平均月超额", "model_value": "1.17%"},'
    '{"category": "相对收益", "index_value": "", "metric": "月超额波动率", "model_value": "2.00%"},'
    '{"category": "回撤", "index_value": "", "metric": "年最大超额回撤", "model_value": "15.00%"},'
    '{"category": "回撤", "index_value": "", "metric": "超额回撤胜率", "model_value": "70.00%"},'
    '{"category": "回撤", "index_value": "", "metric": "年最大回撤", "model_value": "-30.00%"},'
    '{"category": "回撤", "index_value": "", "metric": "最大修复天数", "model_value": "12"},'
    '{"category": "回撤", "index_value": "", "metric": "超额最大修复天数", "model_value": "8"},'
    '{"category": "回撤", "index_value": "9", "metric": "年最大回测修复天数", "model_value": "20"},'
    '{"category": "比率", "index_value": "0.8", "metric": "夏普比率", "model_value": "1.1"},'
    '{"category": "比率", "index_value": "0.4", "metric": "卡玛比率", "model_value": ""},'
    '{"category": "比率", "index_value": "1.2", "metric": "索提诺比率", "model_value": "1.6"},'
    '{"category": "夏普", "index_value": "", "metric": "超额夏普", "model_value": "0.9"},'
    '{"category": "索提诺", "index_value": "", "metric": "超额索提诺比率", "model_value": "1.4"}]]'
)

EXTRACTOR_EXPECTED = _loads(
    '["2024/01/01-2025/01/01", ['
    '{"metric": "年化收益", "model_value": "21.00%"},'
    '{"metric": "盈利年份百分比", "model_value": "75.00%"},'
    '{"metric": "月盈利百分比", "model_value": "62.00%"},'
    '{"metric": "平均月收益率", "model_value": "3.00%"},'
    '{"metric": "月收益率波动率", "model_value": "4.50%"},'
    '{"metric": "年化超额收益", "model_value": "13.00%"},'
    '{"metric": "跑赢年份(百分比）", "model_value": "300.00%"},'
    '{"metric": "月超额收益胜率", "model_value": "66.00%"},'
    '{"metric": "平均月超额", "model_value": "1.17%"},'
    '{"metric": "月超额波动率", "model_value": "2.00%"},'
    '{"metric": "年最大超额回撤", "model_value": "15.00%"},'
    '{"metric": "超额回撤胜率", "model_value": "70.00%"},'
    '{"metric": "年最大回撤", "model_value": "-30.00%"},'
    '{"metric": "最大修复天数", "model_value": "12"},'
    '{"metric": "超额最大修复天数", "model_value": "8"},'
    '{"metric": "年最大回测修复天数", "model_value": "20"},'
    '{"metric": "夏普比率", "model_value": "1.1"},'
    '{"metric": "卡玛比率", "model_value": "0.5"},'
    '{"metric": "索提诺比率", "model_value": "1.6"},'
    '{"metric": "超额夏普", "model_value": "0.9"},'
    '{"metric": "超额索提诺比率", "model_value": "1.4"}]]'
)

EXPORTER_BLOCKS_EXPECTED = _loads(
    '{"block1": [["标的", "", "", ""], ["回测区间", "2024/01/01-2025/01/01", "", ""],'
    ' ["指标类型", "指标", "指数", "C3"], ["绝对收益", "年化收益", "8.00%", "21.00%"],'
    ' ["绝对收益", "盈利年份百分比", "60.00%", "75.00%"], ["绝对收益", "月盈利百分比", "55.00%", "62.00%"],'
    ' ["绝对收益", "平均月收益率", "2.00%", "3.00%"], ["绝对收益", "月收益率波动率", "3.00%", "4.50%"],'
    ' ["相对收益", "年化超额收益", "", "13.00%"], ["相对收益", "跑赢年份(百分比）", "", "300.00%"],'
    ' ["相对收益", "月超额收益胜率", "", "66.00%"], ["相对收益", "平均月超额", "", "1.17%"],'
    ' ["相对收益", "月超额波动率", "", "2.00%"], ["回撤", "年最大超额回撤", "", "15.00%"],'
    ' ["回撤", "超额回撤胜率", "", "70.00%"], ["回撤", "年最大回撤", "", "--30.00%"],'
    ' ["回撤", "最大修复天数", "", "12"], ["回撤", "超额最大修复天数", "", "8"],'
    ' ["回撤", "年最大回测修复天数", "9", "20"], ["比率", "夏普比率", "0.8", "1.1"],'
    ' ["比率", "卡玛比率", "0.4", "0.5"], ["比率", "索提诺比率", "1.2", "1.6"]],'
    ' "block2": [["收益率明细", "", "", "", ""], ["年份", 2024, "", "", ""],'
    ' ["指数", "5.00%", "", "", ""], ["策略", "20.00%", "", "", ""], ["超额", "12.00%", "", "", ""]],'
    ' "block3": [["回撤明细", "", "", "", ""], ["年份", "2024", "", "", ""],'
    ' ["指数", "-10.00%", "", "", ""], ["策略", "-25.00%", "", "", ""], ["超额回撤", "-15.00%", "", "", ""]],'
    ' "block4": [["", "策略收益率", "月超额"], ["2024-01", "4.00%", "1.00%"],'
    ' ["2024-02", "5.00%", "3.00%"], ["2024-03", "6.00%", "-0.50%"]]}'
)

MAPPER_FLAT_EXPECTED = _loads(
    '{"annualized_return_diff": 0.6337651014226299, "avg_monthly_excess_returns": 0.023,'
    ' "excess_drawdown_winning_rate": 1.0, "excess_maximum_number_of_backtest_repair_days": 0,'
    ' "excess_sharpe": 0, "excess_sortino": 0, "index_annual_std_dev": 0,'
    ' "index_annualized_return": -0.9348279291813669, "index_avg_monthly_return": 0,'
    ' "index_avg_monthly_return_common": 0, "index_kama_ratio": -55.649756725384854,'
    ' "index_monthly_return_volatility": 0, "index_monthly_std_dev": 0, "index_profit_annual": 0.0,'
    ' "index_profit_monthly_percentage": 0.0, "index_sharpe_ratio": 0, "index_sortino_ratio": 0,'
    ' "max_drawdown": -0.009969150679649205, "monthly_excess_return_percentage_last_return": 1.0,'
    ' "monthly_excess_volatility": 0, "outperform_year": 1.0, "start_annual_std_dev": 0,'
    ' "start_annualized_return": -0.30106282775873705, "start_avg_monthly_return": 0,'
    ' "start_avg_monthly_return_common": 0, "start_drawdown": 0.006829268292682825,'
    ' "start_kama_ratio": -44.08419977895858, "start_maximum_number_of_backtest_repair_days": 0,'
    ' "start_monthly_return_volatility": 0, "start_monthly_std_dev": 0, "start_profit_annual": 0.0,'
    ' "start_profit_monthly_percentage": 1.0, "start_sharpe_ratio": 0, "start_sortino_ratio": 0}'
)


def test_golden_multi_derive_metrics():
    assert _derive_metrics(json.loads(json.dumps(CALCULATE_METRICS))) == MULTI_EXPECTED


def test_golden_report_query_extract_summary_rows():
    assert list(_extract_summary_rows(
        json.loads(json.dumps(CALCULATE_METRICS)), "vTest")) == RQ_EXPECTED


def test_golden_extractor_backtest_summary_rows():
    assert list(_extract_backtest_summary_rows(
        json.loads(json.dumps(CALCULATE_METRICS)), "vTest")) == EXTRACTOR_EXPECTED


def test_golden_pa_exporter_blocks():
    data = {"analyze_result": json.loads(json.dumps(CALCULATE_METRICS)), "model_version": "vTest"}
    df = performance_analyzer.format_export_file_data(data)
    actual = {
        "block1": df.iloc[0:22, 0:4].values.tolist(),
        "block2": df.iloc[24:29, 0:5].values.tolist(),
        "block3": df.iloc[30:35, 0:5].values.tolist(),
        "block4": df.iloc[3:7, 9:12].values.tolist(),
    }
    assert json.loads(json.dumps(actual, ensure_ascii=False)) == EXPORTER_BLOCKS_EXPECTED


def test_golden_result_mapper_flat_projection():
    analyze_result = json.loads(json.dumps(CALCULATE_METRICS))
    flat, payload = performance_analyzer.get_return_analysis_v1(
        json.loads(json.dumps(RETURN_ROWS)))
    assert flat == MAPPER_FLAT_EXPECTED
    assert payload["schema_version"] == "metrics.v1"
    assert payload["metrics"] == analyze_result or payload["metrics"]
    assert isinstance(payload["canonical_metrics"], dict)

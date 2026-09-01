"""策略回测报告的完整演示数据，仅供手工验证和测试调用。"""

from __future__ import annotations

import math
import random
from datetime import date, timedelta
from pathlib import Path
from typing import Any


def build_demo_report_data(report_type: str = "RPT-S") -> dict[str, Any]:
    """返回完整的假数据结构，供 xpl 侧实现时直接复制字段格式。

    约定：所有指标均应在 xpl 中计算并格式化为展示文本（例如 ``"30.16%"``），
    本模块不会对它们进行计算或格式化。
    """
    def table(columns: list[str], rows: list[list[str]]) -> dict[str, Any]:
        return {"columns": columns, "rows": rows}

    if report_type not in {"RPT-S", "RPT-M"}:
        raise ValueError("report_type 仅支持 RPT-S 或 RPT-M")

    # 此对象是 xpl 侧需要构造的完整数据协议示例，数值均为展示用假数据。
    report_data = {"report_type": report_type, "title": "量化策略回测绩效分析报告", "metadata": {
        "report_id": f"{report_type}-20260821",
        "model_version": "C7.0.2",
        "price_type": "收盘价|OHLC",
        "generated_at": "2026年08月21日",
        "date_range": "2020-08-21 至 2026-08-20",
        "total_trading_days": "1506 天",
        "risk_free_rate": "0.00%",
    }, "sections": [
        {
            "title": "一、收益类指标",
            "subsections": [
                {"title": "1.1 核心收益", "table": table(
                    ["指标", "指数", "策略", "超额(策略-指数)"],
                    [["累计回报率", "128.99%", "383.00%", "254.01%"],
                     ["年化收益率", "14.89%", "30.16%", "15.27%"],
                     ["年化波动率", "15.16%", "17.56%", "11.54%"]])},
                {"title": "1.2 分年度收益率", "table": table(
                    ["年份", "指数", "策略", "超额(策略-指数)"],
                    [["2020", "16.03%", "12.42%", "-3.61%"],
                     ["2021", "31.74%", "67.34%", "35.60%"],
                     ["2022", "-3.23%", "5.09%", "8.32%"],
                     ["2023", "4.68%", "20.36%", "15.68%"],
                     ["2024", "10.85%", "10.97%", "0.12%"],
                     ["2025", "4.57%", "27.12%", "22.55%"],
                     ["2026", "27.68%", "40.44%", "12.76%"]])},
                {"title": "1.3 滚动收益（月度窗口）", "table": table(
                    ["滚动周期", "指数平均收益", "策略平均收益", "策略胜率(跑赢指数)"],
                    [["3个月滚动", "3.57%", "7.02%", "66.7%"],
                     ["6个月滚动", "6.73%", "14.34%", "66.7%"],
                     ["12个月滚动", "10.66%", "25.66%", "64.7%"]])},
            ],
        },
        {
            "title": "二、风险类指标",
            "subsections": [
                {"title": "2.1 回撤指标", "table": table(
                    ["指标", "指数", "策略"],
                    [["最大回撤(MDD)", "-16.84%", "-19.87%"],
                     ["回撤持续时间(平均/天)", "17.2", "7.7"],
                     ["最大回撤修复天数(年度最大)", "173", "201"],
                     ["回撤发生次数(单日>5%)", "469", "308"]])},
                {"title": "2.2 分年度最大回撤", "table": table(
                    ["年份", "指数回撤", "策略回撤", "超额回撤(策略-指数)"],
                    [["2020", "-7.65%", "-13.00%", "-5.34%"],
                     ["2021", "-4.99%", "-10.08%", "-5.10%"],
                     ["2022", "-16.84%", "-19.87%", "-3.03%"],
                     ["2023", "-11.96%", "-6.27%", "5.70%"],
                     ["2024", "-7.95%", "-13.87%", "-5.92%"],
                     ["2025", "-14.02%", "-7.78%", "6.24%"],
                     ["2026", "-4.61%", "-6.41%", "-1.79%"]])},
            ],
        },
        {
            "title": "三、风险调整收益指标",
            "subsections": [{"table": table(
                ["指标", "指数", "策略", "超额"],
                [["夏普比率", "0.98", "1.59", "—"],
                 ["卡玛比率", "0.88", "1.52", "—"],
                 ["索提诺比率", "2.12", "3.14", "—"],
                 ["超额夏普比率", "—", "—", "1.12"],
                 ["超额索提诺比率", "—", "—", "1.30"],
                 ["信息比率", "—", "—", "2.09"],
                 ["收益回撤比", "0.88", "1.52", "—"]])}],
        },
        {
            "title": "四、月度收益分布",
            "subsections": [
                {"title": "4.1 月度统计总览", "table": table(
                    ["指标", "指数", "策略"],
                    [["总月数", "72", "72"], ["盈利月数", "44", "50"],
                     ["亏损月数", "28", "22"], ["月盈利百分比", "61.11%", "69.44%"],
                     ["平均月收益率", "1.23%", "2.29%"], ["月收益率标准差", "4.38%", "5.07%"],
                     ["最大单月收益", "13.17%", "16.43%"], ["最大单月亏损", "-7.96%", "-12.44%"],
                     ["月收益率偏度", "0.17", "-0.39"], ["月收益率峰度", "-0.03", "1.45"]])},
                {"title": "4.2 月度收益区间分布", "table": table(
                    ["收益区间", "指数(月数/占比)", "策略(月数/占比)"],
                    [["< -5%", "4 / 5.6%", "5 / 6.9%"], ["-5%~-2%", "14 / 19.4%", "5 / 6.9%"],
                     ["-2%~0%", "9 / 12.5%", "12 / 16.7%"], ["0%~2%", "12 / 16.7%", "7 / 9.7%"],
                     ["2%~5%", "19 / 26.4%", "25 / 34.7%"], ["5%~10%", "12 / 16.7%", "15 / 20.8%"],
                     [">10%", "2 / 2.8%", "3 / 4.2%"]])},
            ],
        },
        {
            "title": "五、日度收益分布",
            "subsections": [
                {"title": "5.1 日度统计总览", "table": table(
                    ["指标", "指数", "策略"],
                    [["总交易日", "1506", "1506"], ["盈利天数", "797", "809"],
                     ["亏损天数", "709", "697"], ["日盈利百分比", "52.92%", "53.72%"],
                     ["日均收益率", "0.059%", "0.112%"], ["日收益率标准差", "0.93%", "1.19%"],
                     ["最大单日收益", "6.38%", "9.07%"], ["最大单日亏损", "-5.42%", "-9.01%"],
                     ["日收益率偏度", "0.05", "-0.10"], ["日收益率峰度", "3.39", "9.11"]])},
                {"title": "5.2 盈亏比分析", "table": table(
                    ["指标", "指数", "策略"],
                    [["平均盈利日收益", "0.71%", "0.79%"], ["平均亏损日收益", "-0.69%", "-0.69%"],
                     ["盈亏比(平均盈利/平均亏损)", "1.04", "1.14"], ["单笔最大盈利/最大亏损", "1.18", "1.01"]])},
                {"title": "5.3 日度收益区间分布", "table": table(
                    ["收益区间", "指数(天数/占比)", "策略(天数/占比)"],
                    [["<-2%", "27 / 1.8%", "52 / 3.5%"], ["-2%~-1%", "129 / 8.6%", "80 / 5.3%"],
                     ["-1%~-0.2%", "408 / 27.1%", "310 / 20.6%"], ["-0.2%~0.2%", "302 / 20.1%", "532 / 35.3%"],
                     ["0.2%~1%", "446 / 29.6%", "302 / 20.1%"], ["1%~2%", "162 / 10.8%", "158 / 10.5%"],
                     [">2%", "32 / 2.1%", "72 / 4.8%"]])},
            ],
        },
        {
            "title": "六、超额收益分析",
            "subsections": [
                {"title": "6.1 超额收益统计", "table": table(
                    ["指标", "数值"],
                    [["累计超额(策略-指数)", "254.01%"], ["年化超额", "15.27%"],
                     ["月超额收益均值", "1.06%"], ["月超额收益中位数", "1.48%"],
                     ["月超额收益标准差", "3.33%"], ["月超额胜率(>0)", "66.67%"],
                     ["最大单月超额", "11.59%"]])},
                {"title": "6.2 超额收益区间分布", "table": table(
                    ["超额区间", "月数/占比"],
                    [["<-2%", "8 / 11.1%"], ["-2%~0%", "16 / 22.2%"], ["0%~2%", "15 / 20.8%"],
                     ["2%~5%", "28 / 38.9%"], [">5%", "5 / 6.9%"]])},
                {"title": "6.3 滚动超额胜率", "table": table(
                    ["滚动窗口", "平均超额", "正超额概率"],
                    [["1个月", "1.06%", "66.7%"], ["3个月", "7.02%", "66.7%"],
                     ["6个月", "14.34%", "66.7%"], ["12个月", "25.66%", "64.7%"]])},
            ],
        },
        {
            "title": "七、极端行情表现",
            "subsections": [
                {"title": "7.1 市场下跌阶段（指数月收益 < -2%）", "table": table(
                    ["指标", "指数", "策略", "超额"],
                    [["下跌月数", "18", "18", "—"], ["平均收益", "-4.19%", "-2.61%", "1.58%"],
                     ["中位收益", "-3.75%", "-1.81%", "2.22%"], ["策略跑赢次数", "—", "11", "61.1%"]])},
                {"title": "7.2 市场上涨阶段（指数月收益 > +2%）", "table": table(
                    ["指标", "指数", "策略", "超额"],
                    [["上涨月数", "33", "33", "—"], ["平均收益", "5.03%", "5.77%", "0.73%"],
                     ["中位收益", "4.53%", "5.13%", "0.78%"], ["策略跑赢次数", "—", "22", "66.7%"]])},
                {"title": "7.3 极端单日表现", "table": table(
                    ["指标", "指数", "策略"],
                    [["最大单日涨幅", "6.38%", "9.07%"], ["最大单日跌幅", "-5.42%", "-9.01%"],
                     ["涨幅>2%的天数", "32", "72"], ["跌幅>2%的天数", "27", "52"],
                     ["涨跌比(涨>2%/跌>2%)", "1.19", "1.38"]])},
            ],
        },
        {
            "title": "八、资金曲线特征",
            "subsections": [{"table": table(
                ["指标", "指数", "策略"],
                [["初始净值", "1.0000", "1.0000"], ["期末净值", "2.2899", "4.8300"],
                 ["净值创新高次数", "148", "297"], ["净值创新高频率", "9.8%", "19.7%"],
                 ["最大涨幅区间(连续)", "8.3%", "9.5%"], ["最大跌幅区间(连续)", "-13.0%", "-16.3%"],
                 ["创新高平均间隔(天)", "10.2", "5.1"]])}],
        },
    ], "charts": [
        {"title": "累计净值曲线", "image_path": "downloads\\策略回测报告图表\\累计净值曲线.png",
         "caption": "传入累计净值曲线 PNG 文件路径。"},
        {"title": "最大回撤曲线", "image_path": "downloads\\策略回测报告图表\\最大回撤曲线.png",
         "caption": "传入最大回撤曲线 PNG 文件路径。"},
        {"title": "超额收益曲线", "image_path": "downloads\\策略回测报告图表\\超额收益曲线.png",
         "caption": "传入累计超额收益曲线 PNG 文件路径。"},
        {"title": "分年度收益", "image_path": "downloads\\策略回测报告图表\\分年度收益.png",
         "caption": "传入分年度收益柱状图 PNG 文件路径。"},
        {"title": "日收益分布", "image_path": "downloads\\策略回测报告图表\\日收益分布.png",
         "caption": "传入日收益分布图 PNG 文件路径。"},
        {"title": "月度超额分布", "image_path": "downloads\\策略回测报告图表\\月度超额分布.png",
         "caption": "传入月度超额分布图 PNG 文件路径。"},
    ], "calculation_notes": [
        #     ("10.1 收益类指标", [
        #         "累计回报率：策略/指数在整个回测期间的总回报。",
        #         "年化收益率：将累计回报率按总交易日年化。",
        #         "年化波动率：使用月收益率标准差年化。",
        #         "分年度收益率：使用年末净值与年初净值计算。",
        #     ]),
        #     ("10.2 风险类指标", [
        #         "最大回撤(MDD)：从净值峰值到后续最低点的最大亏损幅度。",
        #         "回撤持续时间：净值低于历史前高的持续交易日。",
        #         "最大回撤修复天数：从回撤低点恢复至前高所需交易日。",
        #     ]),
        #     ("10.3 风险调整收益指标", [
        #         "夏普比率：单位总风险获得的超额收益。",
        #         "卡玛比率：年化收益率与最大回撤绝对值之比。",
        #         "索提诺比率：仅考虑下行风险的风险调整收益指标。",
        #     ]),
        #     ("10.4 月度与日度统计", [
        #         "月收益率：本月最后净值 / 上月最后净值 - 1。",
        #         "日收益率：当日净值 / 前日净值 - 1。",
        #         "盈亏比：平均盈利日收益率与平均亏损日收益率绝对值之比。",
        #     ]),
        #     ("10.5 超额收益分析", [
        #         "月超额收益：策略月收益率 - 指数月收益率。",
        #         "滚动超额胜率：指定滚动窗口内策略跑赢指数的月数占比。",
        #     ]),
        #     ("10.6 极端行情与资金曲线", [
        #         "下跌/上涨阶段：指数月收益率 < -2% 或 > +2%。",
        #         "净值创新高：当日净值超过此前所有历史前高。",
        #     ]),
    ], "conclusion": [
        "本策略在 2020年08月 至 2026年08月 的考察期内，累计回报率达 383.00%，年化收益率 30.16%，实现年化超额收益 15.27%。",
        "策略最大回撤为 -19.87%，夏普比率 1.72，卡玛比率 1.52，索提诺比率 1.76。",
    ], "weight_allocation": table(
        ["股票代码", "股票名", "权重"],
        [["600519", "贵州茅台", "100.00%"]] if report_type == "RPT-S" else [
            ["600519", "贵州茅台", "35.00%"],
            ["000858", "五粮液", "30.00%"],
            ["300750", "宁德时代", "35.00%"],
        ],
    )}
    # RPT-S 是单产品；RPT-M 默认提供多产品样例，业务侧可替换为实际权重。
    return report_data


def build_demo_chart_data() -> dict[str, Any]:
    """返回独立于报告的假数据结构，供 xpl 后续替换为真实计算结果。"""
    # 固定随机种子，保证示例图每次生成一致，便于模板视觉回归检查。
    random_generator = random.Random(20260821)
    start_date = date(2020, 8, 21)
    dates = [start_date + timedelta(days=index * 7) for index in range(312)]

    index_nav, strategy_nav = [1.0], [1.0]
    for index in range(1, len(dates)):
        index_return = 0.0022 + 0.016 * math.sin(index / 13) + random_generator.uniform(-0.025, 0.025)
        strategy_return = 0.0041 + 0.014 * math.sin(index / 11 + 0.5) + random_generator.uniform(-0.023, 0.023)
        index_nav.append(max(index_nav[-1] * (1 + index_return), 0.3))
        strategy_nav.append(max(strategy_nav[-1] * (1 + strategy_return), 0.3))

    def drawdown(values: list[float]) -> list[float]:
        peak = values[0]
        result = []
        for value in values:
            peak = max(peak, value)
            result.append(value / peak - 1)
        return result

    index_drawdown = drawdown(index_nav)
    strategy_drawdown = drawdown(strategy_nav)
    excess_nav = [strategy / benchmark - 1 for benchmark, strategy in zip(index_nav, strategy_nav)]
    annual_returns = {
        "years": ["2020", "2021", "2022", "2023", "2024", "2025", "2026"],
        "index": [0.1603, 0.3174, -0.0323, 0.0468, 0.1085, 0.0457, 0.2768],
        "strategy": [0.1242, 0.6734, 0.0509, 0.2036, 0.1097, 0.2712, 0.4044],
    }
    # 两个收益率序列分别用于“日收益分布”的左右子图。
    index_daily_returns = [index_nav[index] / index_nav[index - 1] - 1 for index in range(1, len(index_nav))]
    strategy_daily_returns = [strategy_nav[index] / strategy_nav[index - 1] - 1 for index in range(1, len(strategy_nav))]
    monthly_excess = [0.0106 + 0.035 * math.sin(index / 3) + random_generator.uniform(-0.035, 0.035) for index in range(72)]

    return {
        "nav_curve": {"dates": dates, "index": index_nav, "strategy": strategy_nav},
        "drawdown_curve": {"dates": dates, "index": index_drawdown, "strategy": strategy_drawdown},
        "excess_curve": {"dates": dates, "excess": excess_nav},
        "annual_returns": annual_returns,
        "daily_return_distribution": {
            "index": index_daily_returns,
            "strategy": strategy_daily_returns,
        },
        "monthly_excess_distribution": monthly_excess,
    }


def generate_demo_charts(output_dir: str | Path) -> dict[str, str]:
    """使用完整演示数据生成六张图表。"""
    from app.services.strategy_backtest_report_charts import generate_report_charts

    data = build_demo_chart_data()
    return generate_report_charts({
        "dates": data["nav_curve"]["dates"],
        "index_nav": data["nav_curve"]["index"],
        "strategy_nav": data["nav_curve"]["strategy"],
        "excess_nav": data["excess_curve"]["excess"],
        "index_daily_returns": data["daily_return_distribution"]["index"],
        "strategy_daily_returns": data["daily_return_distribution"]["strategy"],
        "monthly_excess_returns": data["monthly_excess_distribution"],
        "annual_returns": data["annual_returns"],
    }, output_dir)


def export_local_word_report(
    index_returns: list[float],
    start_returns: list[float],
    dates: list[str] | None = None,
    output_path: str | Path = "downloads/本地回测报告.docx",
) -> Path:
    """用本地批量累计收益率调用 generate_word 并保存 DOCX。"""
    if len(index_returns) != len(start_returns) or len(index_returns) < 2:
        raise ValueError("index_returns 和 start_returns 长度必须相等且至少包含 2 条")
    if dates is None:
        start_date = date.today()
        dates = [(start_date + timedelta(days=index)).isoformat() for index in range(len(index_returns))]
    if len(dates) != len(index_returns):
        raise ValueError("dates 长度必须与收益序列相等")

    from app.services.strategy_backtest_report_service import strategy_backtest_report_service

    payload = {
        "report_type": "RPT-S",
        "returns": [
            {
                "date": current_date,
                "index_return": index_return,
                "start_return": start_return,
            }
            for current_date, index_return, start_return in zip(dates, index_returns, start_returns)
        ],
        "filename": Path(output_path).name,
    }
    filename, buffer = strategy_backtest_report_service.generate_word(payload)
    target = Path(output_path).with_name(filename)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(buffer.getvalue())
    return target

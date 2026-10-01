// 统一指标词表（docs/design/performance-analysis-v3/01-设计方案.md §8）。
// V3 页面的 KPI / 图表系列名 / 表头 / 全量指标总表一律经此取名，页面禁止英文裸键。
// 行名与 RPT-S Word 报告（strategy_backtest_report_service.py）对齐；
// "模型"统一叫"策略"（跟报告口径）。sheet_result 的键不做映射（键来自模板 Sheet 本身）。
// 结构：key -> [中文名, 分组, 格式]；格式：pct(×100 百分号) / num4 / num6 / int / text。
"use strict";

(function () {
    const GROUP_LABELS = {
        RETURN: '收益类',
        RISK: '风险类',
        RISK_ADJUSTED: '风险调整收益',
        MONTHLY: '月度收益分布',
        DAILY: '日度收益分布',
        EXCESS: '超额收益分析',
        EXTREME: '极端行情表现',
        CAPITAL: '资金曲线特征',
        CALIBER: '口径',
        META: '元信息'
    };

    // 分组顺序即 RPT-S 报告章节顺序
    const GROUP_ORDER = [
        'RETURN', 'RISK', 'RISK_ADJUSTED', 'MONTHLY', 'DAILY',
        'EXCESS', 'EXTREME', 'CAPITAL', 'CALIBER', 'META'
    ];

    const METRICS = {
        // ---- 一、收益类 ----
        index_cumulative_return: ['基准累计回报率', 'RETURN', 'pct'],
        start_cumulative_return: ['策略累计回报率', 'RETURN', 'pct'],
        index_annualized_rates: ['基准年化收益率（分年度）', 'RETURN', 'array'],
        start_annualized_rates: ['策略年化收益率（分年度）', 'RETURN', 'array'],
        index_returns_rate: ['基准分年度收益率', 'RETURN', 'array'],
        start_returns_rate: ['策略分年度收益率', 'RETURN', 'array'],
        rolling_return_3_reason: ['3月滚动收益说明', 'RETURN', 'text'],
        rolling_return_6_reason: ['6月滚动收益说明', 'RETURN', 'text'],
        rolling_return_12_reason: ['12月滚动收益说明', 'RETURN', 'text'],
        index_rolling_return_3_avg_return: ['基准3月滚动平均收益', 'RETURN', 'pct'],
        start_rolling_return_3_avg_return: ['策略3月滚动平均收益', 'RETURN', 'pct'],
        rolling_return_3_win_rate: ['3月滚动胜率（策略跑赢基准）', 'RETURN', 'pct'],
        index_rolling_return_6_avg_return: ['基准6月滚动平均收益', 'RETURN', 'pct'],
        start_rolling_return_6_avg_return: ['策略6月滚动平均收益', 'RETURN', 'pct'],
        rolling_return_6_win_rate: ['6月滚动胜率（策略跑赢基准）', 'RETURN', 'pct'],
        index_rolling_return_12_avg_return: ['基准12月滚动平均收益', 'RETURN', 'pct'],
        start_rolling_return_12_avg_return: ['策略12月滚动平均收益', 'RETURN', 'pct'],
        rolling_return_12_win_rate: ['12月滚动胜率（策略跑赢基准）', 'RETURN', 'pct'],

        // ---- 二、风险类 ----
        index_maximum_drawdown: ['基准最大回撤（MDD）', 'RISK', 'object'],
        start_maximum_drawdown: ['策略最大回撤（MDD）', 'RISK', 'object'],
        index_drawdown_count: ['基准回撤发生次数', 'RISK', 'int'],
        start_drawdown_count: ['策略回撤发生次数', 'RISK', 'int'],
        index_maximum_number_of_backtest_repair_days: ['基准最大回测修复天数', 'RISK', 'int'],
        start_maximum_number_of_backtest_repair_days: ['策略最大回测修复天数', 'RISK', 'int'],
        excess_maximum_number_of_backtest_repair_days: ['超额最大回测修复天数', 'RISK', 'int'],
        year_index_yearly_max_repair_days: ['基准年度最大修复天数', 'RISK', 'object'],
        year_start_yearly_max_repair_days: ['策略年度最大修复天数', 'RISK', 'object'],
        index_dd_count: ['基准单日大跌次数', 'RISK', 'int'],
        start_dd_count: ['策略单日大跌次数', 'RISK', 'int'],
        index_dd_freq: ['基准单日大跌频率', 'RISK', 'pct'],
        start_dd_freq: ['策略单日大跌频率', 'RISK', 'pct'],

        // ---- 三、风险调整收益 ----
        index_sharpe_ratios: ['基准夏普比率（分区间）', 'RISK_ADJUSTED', 'object'],
        start_sharpe_ratios: ['策略夏普比率（分区间）', 'RISK_ADJUSTED', 'object'],
        index_kama_ratio: ['基准卡玛比率（分年度）', 'RISK_ADJUSTED', 'array'],
        start_kama_ratio: ['策略卡玛比率（分年度）', 'RISK_ADJUSTED', 'array'],
        index_sortino_ratio: ['基准索提诺比率（月频）', 'RISK_ADJUSTED', 'array'],
        start_sortino_ratio: ['策略索提诺比率（月频）', 'RISK_ADJUSTED', 'array'],
        index_weekly_sortino_ratio: ['基准索提诺比率（周频）', 'RISK_ADJUSTED', 'array'],
        start_weekly_sortino_ratio: ['策略索提诺比率（周频）', 'RISK_ADJUSTED', 'array'],

        // ---- 四、月度收益分布 ----
        total_months: ['总月数', 'MONTHLY', 'int'],
        index_profit_months: ['基准盈利月数', 'MONTHLY', 'int'],
        start_profit_months: ['策略盈利月数', 'MONTHLY', 'int'],
        index_loss_months: ['基准亏损月数', 'MONTHLY', 'int'],
        start_loss_months: ['策略亏损月数', 'MONTHLY', 'int'],
        index_profit_percentage: ['基准月盈利百分比', 'MONTHLY', 'pct'],
        start_profit_percentage: ['策略月盈利百分比', 'MONTHLY', 'pct'],
        index_max_monthly_return: ['基准最大单月收益', 'MONTHLY', 'pct'],
        start_max_monthly_return: ['策略最大单月收益', 'MONTHLY', 'pct'],
        index_max_monthly_loss: ['基准最大单月亏损', 'MONTHLY', 'pct'],
        start_max_monthly_loss: ['策略最大单月亏损', 'MONTHLY', 'pct'],
        index_monthly_return_skewness: ['基准月收益率偏度', 'MONTHLY', 'num4'],
        start_monthly_return_skewness: ['策略月收益率偏度', 'MONTHLY', 'num4'],
        index_monthly_return_kurtosis: ['基准月收益率峰度', 'MONTHLY', 'num4'],
        start_monthly_return_kurtosis: ['策略月收益率峰度', 'MONTHLY', 'num4'],
        index_monthly_return_volatility: ['基准月收益率波动率', 'MONTHLY', 'num6'],
        start_monthly_return_volatility: ['策略月收益率波动率', 'MONTHLY', 'num6'],
        index_monthly_distribution: ['基准月度收益区间分布（月数）', 'MONTHLY', 'object'],
        start_monthly_distribution: ['策略月度收益区间分布（月数）', 'MONTHLY', 'object'],
        index_monthly_distribution_pct: ['基准月度收益区间分布（占比）', 'MONTHLY', 'object'],
        start_monthly_distribution_pct: ['策略月度收益区间分布（占比）', 'MONTHLY', 'object'],
        index_profit_annual: ['基准盈利年百分比', 'MONTHLY', 'pct'],
        start_profit_annual: ['策略盈利年百分比', 'MONTHLY', 'pct'],
        index_profit_monthly: ['基准盈利月占比（分年度）', 'MONTHLY', 'array'],
        start_profit_monthly: ['策略盈利月占比（分年度）', 'MONTHLY', 'array'],
        monthly_excess_return_percentage: ['月超额收益占比（分年度）', 'MONTHLY', 'array'],

        // ---- 五、日度收益分布 ----
        total_trading_days: ['总交易日', 'DAILY', 'int'],
        index_profit_days: ['基准盈利天数', 'DAILY', 'int'],
        start_profit_days: ['策略盈利天数', 'DAILY', 'int'],
        index_loss_days: ['基准亏损天数', 'DAILY', 'int'],
        start_loss_days: ['策略亏损天数', 'DAILY', 'int'],
        index_days_profit_percentage: ['基准日盈利百分比', 'DAILY', 'pct'],
        start_days_profit_percentage: ['策略日盈利百分比', 'DAILY', 'pct'],
        index_mean_daily_return: ['基准日均收益率', 'DAILY', 'pct'],
        start_mean_daily_return: ['策略日均收益率', 'DAILY', 'pct'],
        index_daily_return_std: ['基准日收益率标准差', 'DAILY', 'num6'],
        start_daily_return_std: ['策略日收益率标准差', 'DAILY', 'num6'],
        index_mean_daily_skewness: ['基准日收益率偏度', 'DAILY', 'num4'],
        start_mean_daily_skewness: ['策略日收益率偏度', 'DAILY', 'num4'],
        index_mean_daily_kurtosis: ['基准日收益率峰度', 'DAILY', 'num4'],
        start_mean_daily_kurtosis: ['策略日收益率峰度', 'DAILY', 'num4'],
        index_avg_profit_day_return: ['基准平均盈利日收益', 'DAILY', 'pct'],
        start_avg_profit_day_return: ['策略平均盈利日收益', 'DAILY', 'pct'],
        index_avg_loss_day_return: ['基准平均亏损日收益', 'DAILY', 'pct'],
        start_avg_loss_day_return: ['策略平均亏损日收益', 'DAILY', 'pct'],
        index_profit_loss_ratio: ['基准盈亏比（平均盈利/平均亏损）', 'DAILY', 'num4'],
        start_profit_loss_ratio: ['策略盈亏比（平均盈利/平均亏损）', 'DAILY', 'num4'],
        index_max_profit_loss_ratio: ['基准单笔最大盈利/最大亏损', 'DAILY', 'num4'],
        start_max_profit_loss_ratio: ['策略单笔最大盈利/最大亏损', 'DAILY', 'num4'],
        index_max_profit_day: ['基准最大单日收益', 'DAILY', 'pct'],
        start_max_profit_day: ['策略最大单日收益', 'DAILY', 'pct'],
        index_max_loss_day: ['基准最大单日亏损', 'DAILY', 'pct'],
        start_max_loss_day: ['策略最大单日亏损', 'DAILY', 'pct'],
        index_days_distribution: ['基准日度收益区间分布（天数）', 'DAILY', 'object'],
        start_days_distribution: ['策略日度收益区间分布（天数）', 'DAILY', 'object'],
        index_days_distribution_pct: ['基准日度收益区间分布（占比）', 'DAILY', 'object'],
        start_days_distribution_pct: ['策略日度收益区间分布（占比）', 'DAILY', 'object'],
        index_return_dist: ['基准单日涨跌幅分布', 'DAILY', 'object'],
        start_return_dist: ['策略单日涨跌幅分布', 'DAILY', 'object'],

        // ---- 六、超额收益分析 ----
        excess_returns: ['超额收益（分年度）', 'EXCESS', 'array'],
        outperform_year: ['跑赢年份占比', 'EXCESS', 'pct'],
        monthly_excess_returns: ['月超额收益明细', 'EXCESS', 'array'],
        monthly_excess_volatility: ['月超额波动率', 'EXCESS', 'num4'],
        excess_drawdown_winning_rate: ['超额回撤胜率', 'EXCESS', 'pct'],
        excess_sharpe: ['超额夏普比率', 'EXCESS', 'num4'],
        excess_sortino: ['超额索提诺比率', 'EXCESS', 'num4'],
        excess_cumulative_return: ['累计超额收益', 'EXCESS', 'pct'],
        excess_nav: ['超额净值（期末）', 'EXCESS', 'num4'],
        annualized_excess_returns: ['年化超额收益', 'EXCESS', 'pct'],
        average_monthly_excess_return: ['月超额收益均值', 'EXCESS', 'pct'],
        monthly_excess_return_standard_deviation: ['月超额收益标准差', 'EXCESS', 'num6'],
        monthly_excess_win_rate: ['月超额胜率（>0）', 'EXCESS', 'pct'],
        max_monthly_excess: ['最大单月超额', 'EXCESS', 'pct'],
        excess_distribution: ['超额月度收益区间分布（月数）', 'EXCESS', 'object'],
        excess_distribution_pct: ['超额月度收益区间分布（占比）', 'EXCESS', 'object'],
        excess_rolling_return_3_reason: ['3月滚动超额说明', 'EXCESS', 'text'],
        excess_rolling_return_6_reason: ['6月滚动超额说明', 'EXCESS', 'text'],
        excess_rolling_return_12_reason: ['12月滚动超额说明', 'EXCESS', 'text'],
        excess_rolling_return_3_avg_return: ['3月滚动超额平均收益', 'EXCESS', 'pct'],
        excess_rolling_return_6_avg_return: ['6月滚动超额平均收益', 'EXCESS', 'pct'],
        excess_rolling_return_12_avg_return: ['12月滚动超额平均收益', 'EXCESS', 'pct'],
        excess_rolling_return_3_win_rate: ['3月滚动正超额概率', 'EXCESS', 'pct'],
        excess_rolling_return_6_win_rate: ['6月滚动正超额概率', 'EXCESS', 'pct'],
        excess_rolling_return_12_win_rate: ['12月滚动正超额概率', 'EXCESS', 'pct'],

        // ---- 七、极端行情表现 ----
        index_downfall_months_len: ['基准下跌阶段月数', 'EXTREME', 'int'],
        start_downfall_months_len: ['策略下跌阶段月数', 'EXTREME', 'int'],
        index_downfall_avg_return: ['基准下跌阶段月均年化', 'EXTREME', 'pct'],
        start_downfall_avg_return: ['策略下跌阶段月均年化', 'EXTREME', 'pct'],
        downfall_win_rate: ['下跌阶段策略胜率', 'EXTREME', 'pct'],
        downfall_outperform_count: ['下跌阶段跑赢次数', 'EXTREME', 'int'],
        downfall_excess_avg_return: ['下跌阶段超额均值', 'EXTREME', 'pct'],
        index_upward_months_len: ['基准上涨阶段月数', 'EXTREME', 'int'],
        start_upward_months_len: ['策略上涨阶段月数', 'EXTREME', 'int'],
        index_upward_avg_return: ['基准上涨阶段月均年化', 'EXTREME', 'pct'],
        start_upward_avg_return: ['策略上涨阶段月均年化', 'EXTREME', 'pct'],
        upward_win_rate: ['上涨阶段策略胜率', 'EXTREME', 'pct'],
        upward_outperform_count: ['上涨阶段跑赢次数', 'EXTREME', 'int'],
        upward_excess_avg_return: ['上涨阶段超额均值', 'EXTREME', 'pct'],
        index_max_daily_gain: ['基准最大单日涨幅', 'EXTREME', 'pct'],
        start_max_daily_gain: ['策略最大单日涨幅', 'EXTREME', 'pct'],
        index_max_daily_loss: ['基准最大单日跌幅', 'EXTREME', 'pct'],
        start_max_daily_loss: ['策略最大单日跌幅', 'EXTREME', 'pct'],
        index_daily_gain_days: ['基准涨幅超阈值天数', 'EXTREME', 'int'],
        start_daily_gain_days: ['策略涨幅超阈值天数', 'EXTREME', 'int'],
        index_daily_loss_days: ['基准跌幅超阈值天数', 'EXTREME', 'int'],
        start_daily_loss_days: ['策略跌幅超阈值天数', 'EXTREME', 'int'],
        index_daily_gain_loss_ratio: ['基准极端涨跌比', 'EXTREME', 'num4'],
        start_daily_gain_loss_ratio: ['策略极端涨跌比', 'EXTREME', 'num4'],

        // ---- 八、资金曲线特征 ----
        index_net_value_left: ['基准初始净值', 'CAPITAL', 'num4'],
        start_net_value_left: ['策略初始净值', 'CAPITAL', 'num4'],
        index_net_value_right: ['基准期末净值', 'CAPITAL', 'num4'],
        start_net_value_right: ['策略期末净值', 'CAPITAL', 'num4'],
        index_consecutive: ['基准连涨连跌月数', 'CAPITAL', 'consecutive'],
        start_consecutive: ['策略连涨连跌月数', 'CAPITAL', 'consecutive'],
        index_new_high_count: ['基准创新高次数', 'CAPITAL', 'int'],
        start_new_high_count: ['策略创新高次数', 'CAPITAL', 'int'],
        index_new_high_frequency: ['基准创新高频率', 'CAPITAL', 'pct'],
        start_new_high_frequency: ['策略创新高频率', 'CAPITAL', 'pct'],
        index_new_high_avg_interval_months: ['基准创新高平均间隔（月）', 'CAPITAL', 'num4'],
        start_new_high_avg_interval_months: ['策略创新高平均间隔（月）', 'CAPITAL', 'num4'],

        // ---- 口径回显 ----
        market_downturn_threshold: ['市场下跌阶段阈值', 'CALIBER', 'pct'],
        market_upturn_threshold: ['市场上涨阶段阈值', 'CALIBER', 'pct'],
        daily_extreme_threshold: ['极端单日涨跌阈值', 'CALIBER', 'pct'],
        daily_drawdown_threshold: ['单日回撤统计阈值', 'CALIBER', 'pct'],

        // ---- 元信息 ----
        analysis_mode: ['分析模式', 'META', 'analysis_mode'],
        sheet_result: ['Sheet 结果区', 'META', 'text']
    };

    window.MetricNames = {
        GROUP_LABELS: GROUP_LABELS,
        GROUP_ORDER: GROUP_ORDER,
        zh: function (key) {
            const spec = METRICS[key];
            return spec ? spec[0] : key;
        },
        fmt: function (key) {
            const spec = METRICS[key];
            return spec ? spec[2] : 'text';
        },
        group: function (key) {
            const spec = METRICS[key];
            return spec ? spec[1] : 'META';
        },
        groupLabel: function (group) {
            return GROUP_LABELS[group] || group;
        },
        isKnown: function (key) {
            return Object.prototype.hasOwnProperty.call(METRICS, key);
        },
        // 全量指标总表用：按分组顺序输出 [key, 中文名, 分组, 格式]
        orderedEntries: function () {
            return GROUP_ORDER.flatMap((group) => Object.keys(METRICS)
                .filter((key) => METRICS[key][1] === group)
                .map((key) => [key, METRICS[key][0], group, METRICS[key][2]]));
        }
    };
})();

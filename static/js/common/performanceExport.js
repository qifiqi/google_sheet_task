// 绩效分析多 sheet Excel 导出构建器（v2 / v3 页面共用）。
// 输入是 analyze_v1 指标字典（页面上渲染数据明细/各 tab 的同一份 r），
// 输出 excelExport.exportSheets 所需的 [{sheetName, rows}] 结构。
// 数值保持原始量纲（比例为小数），不在构建器里做展示格式化，便于二次计算。
// 表头/行定义与页面渲染函数同源语义，改动指标口径时两侧同批修改。
"use strict";

(function () {
    function num(value) {
        const parsed = Number(value);
        return Number.isFinite(parsed) ? parsed : null;
    }

    // 支持点路径取嵌套值（如 index_sharpe_ratios.all.sharpe_ratio）
    function pick(obj, path) {
        return path.split(".").reduce((acc, key) => (acc == null ? undefined : acc[key]), obj);
    }

    // 标量行：[指标, 指数, 策略]
    function scalarRows(r, defs) {
        return defs
            .map(([label, idxKey, stKey]) => [label, num(pick(r, idxKey)), num(pick(r, stKey))])
            .filter((row) => row[1] !== null || row[2] !== null);
    }

    // 按年份/周期键合并指数/策略数组（同 idxByYear 语义）
    function byKey(list, valueKey) {
        const map = new Map();
        (Array.isArray(list) ? list : []).forEach((item) => {
            if (item && item.year !== undefined) map.set(String(item.year), item);
        });
        return { map, valueKey };
    }

    function mergedRows(indexList, startList, valueKeys) {
        const idx = byKey(indexList);
        const st = byKey(startList);
        const years = Array.from(new Set([...idx.map.keys(), ...st.map.keys()]))
            .filter((y) => y !== "all")
            .sort();
        return years.map((year) => [
            year,
            ...valueKeys.map(([vk]) => num(idx.map.get(year)?.[vk])),
            ...valueKeys.map(([vk]) => num(st.map.get(year)?.[vk])),
        ]);
    }

    function flattenObject(value) {
        if (value === null || value === undefined) return "";
        if (value instanceof Date) return value.toISOString();
        if (typeof value === "object") {
            try {
                return JSON.stringify(value);
            } catch (_e) {
                return String(value);
            }
        }
        return value;
    }

    function buildSheets(r) {
        if (!r || typeof r !== "object") return [];
        const sheets = [];

        // 一、指标总览（核心回报/风险/资金/月度概览的标量集合；点路径支持嵌套取值）
        const overviewDefs = [
            ["累计回报率", "index_cumulative_return", "start_cumulative_return"],
            ["超额累计回报率", "excess_cumulative_return", "excess_cumulative_return"],
            ["年化收益率", "index_annualized_rates.all.annualized_return", "start_annualized_rates.all.annualized_return"],
            ["最大回撤", "index_maximum_drawdown.maximum_drawdown", "start_maximum_drawdown.maximum_drawdown"],
            ["最大回撤修复天数", "index_maximum_number_of_backtest_repair_days", "start_maximum_number_of_backtest_repair_days"],
            ["夏普比率(all)", "index_sharpe_ratios.all.sharpe_ratio", "start_sharpe_ratios.all.sharpe_ratio"],
            ["初始净值", "index_net_value_left", "start_net_value_left"],
            ["期末净值", "index_net_value_right", "start_net_value_right"],
            ["创新高次数", "index_new_high_count", "start_new_high_count"],
            ["创新高频率", "index_new_high_frequency", "start_new_high_frequency"],
            ["总月数", "total_months", "total_months"],
            ["盈利月数", "index_profit_months", "start_profit_months"],
            ["月盈利百分比", "index_profit_percentage", "start_profit_percentage"],
            ["最大单月收益", "index_max_monthly_return", "start_max_monthly_return"],
            ["最大单月亏损", "index_max_monthly_loss", "start_max_monthly_loss"],
            ["总交易日", "total_trading_days", "total_trading_days"],
            ["盈利天数", "index_profit_days", "start_profit_days"],
            ["日均收益率", "index_mean_daily_return", "start_mean_daily_return"],
            ["盈亏比", "index_profit_loss_ratio", "start_profit_loss_ratio"],
            ["上涨阶段月均年化", "index_upward_avg_return", "start_upward_avg_return"],
            ["下跌阶段月均年化", "index_downfall_avg_return", "start_downfall_avg_return"],
            ["涨幅超阈值天数", "index_daily_gain_days", "start_daily_gain_days"],
            ["跌幅超阈值天数", "index_daily_loss_days", "start_daily_loss_days"],
        ];
        sheets.push({
            sheetName: "指标总览",
            rows: [
                ["指标", "指数", "策略"],
                ...overviewDefs
                    .map(([label, idxKey, stKey]) => [label, num(pick(r, idxKey)), num(pick(r, stKey))])
                    .filter((row) => row[1] !== null || row[2] !== null),
            ],
        });

        // 二、年度收益与回撤
        const annualIdx = byKey(r.index_returns_rate);
        const annualSt = byKey(r.start_returns_rate);
        const ddIdx = byKey(r.index_maximum_drawdown?.year_maximum_drawdown);
        const ddSt = byKey(r.start_maximum_drawdown?.year_maximum_drawdown);
        const years = Array.from(new Set([
            ...annualIdx.map.keys(), ...annualSt.map.keys(),
            ...ddIdx.map.keys(), ...ddSt.map.keys(),
        ])).filter((y) => y !== "all").sort();
        sheets.push({
            sheetName: "年度收益与回撤",
            rows: [
                ["年份", "指数年化收益", "策略年化收益", "指数最大回撤", "策略最大回撤", "回撤日期(指数/策略)"],
                ...years.map((y) => [
                    y,
                    num(annualIdx.map.get(y)?.annual_return),
                    num(annualSt.map.get(y)?.annual_return),
                    num(ddIdx.map.get(y)?.drawdown),
                    num(ddSt.map.get(y)?.drawdown),
                    [ddIdx.map.get(y)?.date, ddSt.map.get(y)?.date].filter(Boolean).join(" / "),
                ]),
            ],
        });

        // 三、滚动收益（3/6/12 个月）
        sheets.push({
            sheetName: "滚动收益",
            rows: [
                ["窗口", "指数平均收益", "策略平均收益", "策略胜率"],
                ...[3, 6, 12].map((n) => [
                    `${n}个月`,
                    num(r[`index_rolling_return_${n}_avg_return`]),
                    num(r[`start_rolling_return_${n}_avg_return`]),
                    num(r[`rolling_return_${n}_win_rate`]),
                ]),
            ],
        });

        // 四、月度统计（概览 + 分布 + 月度超额百分比 + 盈利月统计）
        const monthlyRows = [
            ["项目", "指数", "策略"],
            ...scalarRows(r, [
                ["盈利月数", "index_profit_months", "start_profit_months"],
                ["亏损月数", "index_loss_months", "start_loss_months"],
                ["月盈利百分比", "index_profit_percentage", "start_profit_percentage"],
                ["盈利年百分比", "index_profit_annual", "start_profit_annual"],
                ["最大单月收益", "index_max_monthly_return", "start_max_monthly_return"],
                ["最大单月亏损", "index_max_monthly_loss", "start_max_monthly_loss"],
                ["月收益率波动率", "index_monthly_return_volatility", "start_monthly_return_volatility"],
                ["月收益率偏度", "index_monthly_return_skewness", "start_monthly_return_skewness"],
                ["月收益率峰度", "index_monthly_return_kurtosis", "start_monthly_return_kurtosis"],
                ["最大连涨月份", "index_consecutive.max_gain_months", "start_consecutive.max_gain_months"],
                ["最大连跌月份", "index_consecutive.max_loss_months", "start_consecutive.max_loss_months"],
            ]),
        ];
        sheets.push({ sheetName: "月度统计", rows: monthlyRows });

        // 五、月度超额（月度超额百分比 + 明细月超额两段）
        const monthlyExcessRows = [["年月", "指数月收益", "策略月收益", "超额"]];
        (Array.isArray(r.monthly_excess_return_percentage) ? r.monthly_excess_return_percentage : [])
            .forEach((item) => monthlyExcessRows.push([
                String(item?.year ?? ""),
                num(item?.index_monthly_return),
                num(item?.start_monthly_return),
                num(item?.excess_return),
            ]));
        if (Array.isArray(r.monthly_excess_returns) && r.monthly_excess_returns.length) {
            monthlyExcessRows.push([]);
            monthlyExcessRows.push(["年月", "指数月收益", "策略月收益", "超额差"]);
            r.monthly_excess_returns.forEach((item) => monthlyExcessRows.push([
                String(item?.year_month ?? ""),
                num(item?.index_monthly_return),
                num(item?.start_monthly_return),
                num(item?.monthly_excess_return_diff),
            ]));
        }
        sheets.push({ sheetName: "月度超额", rows: monthlyExcessRows });

        // 六、日度统计
        sheets.push({
            sheetName: "日度统计",
            rows: [
                ["指标", "指数", "策略"],
                ...scalarRows(r, [
                    ["总交易日", "total_trading_days", "total_trading_days"],
                    ["盈利天数", "index_profit_days", "start_profit_days"],
                    ["亏损天数", "index_loss_days", "start_loss_days"],
                    ["日盈利百分比", "index_days_profit_percentage", "start_days_profit_percentage"],
                    ["日均收益率", "index_mean_daily_return", "start_mean_daily_return"],
                    ["日收益率标准差", "index_daily_return_std", "start_daily_return_std"],
                    ["日收益率偏度", "index_mean_daily_skewness", "start_mean_daily_skewness"],
                    ["日收益率峰度", "index_mean_daily_kurtosis", "start_mean_daily_kurtosis"],
                    ["平均盈利日收益", "index_avg_profit_day_return", "start_avg_profit_day_return"],
                    ["平均亏损日收益", "index_avg_loss_day_return", "start_avg_loss_day_return"],
                    ["盈亏比", "index_profit_loss_ratio", "start_profit_loss_ratio"],
                    ["涨幅超阈值天数", "index_daily_gain_days", "start_daily_gain_days"],
                    ["跌幅超阈值天数", "index_daily_loss_days", "start_daily_loss_days"],
                ]),
            ],
        });

        // 七、年度超额收益
        sheets.push({
            sheetName: "年度超额收益",
            rows: [
                ["年份", "策略年化", "指数年化", "年化差", "区间"],
                ...(Array.isArray(r.excess_returns) ? r.excess_returns : []).map((item) => [
                    String(item?.year ?? ""),
                    num(item?.start_annualized_return),
                    num(item?.index_annualized_return),
                    num(item?.annualized_return_diff),
                    String(item?.start_end_date ?? ""),
                ]),
            ],
        });

        // 八、卡玛/索提诺/夏普（分年对比，同页面 tab 口径）
        const ratioBlocks = [
            ["卡玛比率", r.index_kama_ratio, r.start_kama_ratio, ["kama_ratio", "annualized_return", "drawdown"]],
            ["索提诺比率", r.index_sortino_ratio, r.start_sortino_ratio, ["sortino_ratio", "annualized_return", "drawdown"]],
        ];
        ratioBlocks.forEach(([name, idxList, stList, keys]) => {
            const rows = mergedRows(idxList, stList, keys.map((k) => [k]));
            if (rows.length) {
                sheets.push({
                    sheetName: name,
                    rows: [
                        ["年份", `指数${keys[0]}`, `策略${keys[0]}`, "指数年化", "策略年化", "指数回撤", "策略回撤"],
                        ...rows,
                    ],
                });
            }
        });
        const sharpeIdx = (r.index_sharpe_ratios && typeof r.index_sharpe_ratios === "object") ? r.index_sharpe_ratios : {};
        const sharpeSt = (r.start_sharpe_ratios && typeof r.start_sharpe_ratios === "object") ? r.start_sharpe_ratios : {};
        const sharpeKeys = Array.from(new Set([...Object.keys(sharpeIdx), ...Object.keys(sharpeSt)])).sort();
        if (sharpeKeys.length) {
            sheets.push({
                sheetName: "夏普比率",
                rows: [
                    ["周期", "指数夏普", "策略夏普", "指数月均收益", "策略月均收益", "指数月波动", "策略月波动", "指数年化波动", "策略年化波动"],
                    ...sharpeKeys.map((k) => [
                        k,
                        num(sharpeIdx[k]?.sharpe_ratio),
                        num(sharpeSt[k]?.sharpe_ratio),
                        num(sharpeIdx[k]?.avg_monthly_return),
                        num(sharpeSt[k]?.avg_monthly_return),
                        num(sharpeIdx[k]?.monthly_std_dev),
                        num(sharpeSt[k]?.monthly_std_dev),
                        num(sharpeIdx[k]?.annual_std_dev),
                        num(sharpeSt[k]?.annual_std_dev),
                    ]),
                ],
            });
        }

        // 九、修复天数分年
        const repairIdx = r.year_index_yearly_max_repair_days || {};
        const repairSt = r.year_start_yearly_max_repair_days || {};
        const repairYears = Array.from(new Set([
            ...Object.keys(repairIdx), ...Object.keys(repairSt),
        ])).sort();
        sheets.push({
            sheetName: "修复天数",
            rows: [
                ["年份", "指数修复天数", "策略修复天数"],
                ...repairYears.map((y) => [y, num(repairIdx[y]), num(repairSt[y])]),
                ["全部", num(r.index_maximum_number_of_backtest_repair_days), num(r.start_maximum_number_of_backtest_repair_days)],
            ],
        });

        // 十、Sheet 结果（analyze 附带的 sheet_result 字典）
        if (r.sheet_result && typeof r.sheet_result === "object") {
            sheets.push({
                sheetName: "Sheet结果",
                rows: [["键", "值"], ...Object.entries(r.sheet_result).map(([k, v]) => [k, flattenObject(v)])],
            });
        }

        // 十一、全部指标（原始指标字典全量扁平化，兜底细粒度）
        sheets.push({
            sheetName: "全部指标",
            rows: [["键", "值"], ...Object.entries(r).map(([k, v]) => [k, flattenObject(v)])],
        });

        return sheets.filter((sheet) => sheet.rows.length > 1);
    }

    window.PerformanceExport = { buildSheets: buildSheets };
})();

// K线数据页（/eastmoney-kline）：经本服务 /api/klines 拉取多数据源K线，
// 页面负责股票搜索、表格展示、波动率分析、Excel 导出与 klinecharts 图表查看。
// 引入顺序：template-auth.js → api.js → utils.js → klinecharts → xlsx-js-style → excelExport.js → 本文件。
"use strict";

// 页面状态。
let klineRows = [];
let queryData = null;
let volatility = null;
let selectedStock = null;
let securityCandidates = [];
let securitySearchTimer = null;
let securitySearchRequestId = 0;

// klinecharts 实例与当前副图指标（单实例切换）。
let klineChart = null;
let chartSubPane = null;

const volatilityPriceBases = {
    vwap: { field: "vwap", label: "VWAP" },
    open: { field: "open", label: "开盘价" },
    close: { field: "close", label: "收盘价" },
    high: { field: "high", label: "最高价" },
    low: { field: "low", label: "最低价" },
};

const DATA_SOURCE_LABELS = {
    dfcf: "东方财富",
    qq: "腾讯",
    akshare: "AKShare",
    tdx: "通达信",
    yahoo: "Yahoo",
    database: "内置K线库",
};

const KLINE_TABLE_COLUMNS = [
    { title: "日期", field: "stock_date", align: "start" },
    { title: "股票代码", field: "stock_code", align: "start" },
    { title: "开盘", field: "open", digits: 2 },
    { title: "收盘", field: "close", digits: 2 },
    { title: "最高", field: "high", digits: 2 },
    { title: "最低", field: "low", digits: 2 },
    { title: "成交量(股)", field: "volume", integer: true },
    { title: "成交额", field: "amount", integer: true },
    { title: "振幅%", field: "amplitude", digits: 2 },
    { title: "涨跌幅%", field: "pct_change", digits: 2 },
    { title: "换手率%", field: "turnover_rate", digits: 2 },
    { title: "VWAP", field: "vwap", digits: 4 },
];

// 顶部提示条：成功消息 4s 自动消退，错误/警告 10s（给足阅读时间）；传空串立即清除。
let messageTimer = null;

function showMessage(message, type = "danger") {
    const box = document.getElementById("messageBox");
    clearTimeout(messageTimer);
    if (!message) {
        box.classList.add("d-none");
        return;
    }
    box.className = `alert alert-${type} mb-3`;
    box.textContent = message;
    messageTimer = setTimeout(() => {
        box.classList.add("d-none");
    }, type === "success" ? 4000 : 10000);
}

function formatNumber(value, digits) {
    return Number.isFinite(value) ? value.toFixed(digits) : "-";
}

function formatPercent(value) {
    return Number.isFinite(value) ? (value * 100).toFixed(2) + "%" : "不可计算";
}

function getVolatilityPriceBasis(value) {
    return volatilityPriceBases[value] || volatilityPriceBases.vwap;
}

function getToday() {
    const today = new Date();
    return [
        today.getFullYear(),
        String(today.getMonth() + 1).padStart(2, "0"),
        String(today.getDate()).padStart(2, "0"),
    ].join("-");
}

function getKlineDate(row) {
    let value = String(row.stock_date || "").replace(/\//g, "-");
    if (value.length === 10) {
        value += "T00:00:00";
    } else {
        value = value.replace(" ", "T");
    }
    const date = new Date(value);
    return Number.isNaN(date.getTime()) ? null : date;
}

function formatKlineDate(date) {
    return [
        date.getFullYear(),
        String(date.getMonth() + 1).padStart(2, "0"),
        String(date.getDate()).padStart(2, "0"),
    ].join("-");
}

// 为文本单元格添加前导单引号，避免 Excel 按公式执行。
function safeExportText(value) {
    const text = String(value || "");
    return /^[=+\-@]/.test(text) ? "'" + text : text;
}

function getStockDisplayName() {
    if (!queryData) return "-";
    return queryData.stock_name || queryData.stock_code || "-";
}

function getDefaultExportFileName(calculation) {
    if (!queryData) return "K线数据";
    const oneYear = calculation && calculation.recent.values.find(
        (item) => item.label === "1年",
    );
    const oneYearVolatility = oneYear && oneYear.result
        ? formatPercent(oneYear.result.value)
        : "无数据";
    return `${queryData.stock_code}-${queryData.stock_name || "股票"}-${oneYearVolatility}`;
}

function getExportFileName() {
    const fileName = document.getElementById("export-file-name").value.trim()
        || getDefaultExportFileName(volatility);
    return fileName.replace(/[\\/:*?"<>|]/g, "_").replace(/\.xlsx$/i, "");
}

// 导出排序始终基于副本，避免影响页面当前的日期倒序展示。
function getExportRows(rows, dateOrder) {
    const exportRows = rows.slice();
    return dateOrder === "desc" ? exportRows.reverse() : exportRows;
}

// 股票搜索：走 /api/search-stocks，候选为 {code, name, market, market_type}。
function renderSecurityCandidates() {
    const suggestions = document.getElementById("stock-suggestions");
    suggestions.innerHTML = securityCandidates.map((item, index) =>
        `<button type="button" class="stock-suggestion list-group-item list-group-item-action py-1 px-2" data-index="${index}" role="option">${escapeHtml(item.displayName)}</button>`,
    ).join("");
    suggestions.hidden = !securityCandidates.length;
    document.getElementById("stock-keyword").setAttribute("aria-expanded", securityCandidates.length ? "true" : "false");
}

function hideSecurityCandidates() {
    document.getElementById("stock-suggestions").hidden = true;
    document.getElementById("stock-keyword").setAttribute("aria-expanded", "false");
}

function cacheSelectedStock(value) {
    const normalizedValue = String(value || "").trim().toUpperCase();
    const candidate = securityCandidates.find((item) =>
        item.displayName.toUpperCase() === normalizedValue
        || item.code.toUpperCase() === normalizedValue,
    );
    if (!candidate) {
        return false;
    }
    selectedStock = candidate;
    document.getElementById("stock-keyword").value = candidate.displayName;
    hideSecurityCandidates();
    return true;
}

// 通过请求序号丢弃过期响应，避免快速输入时旧结果覆盖新结果。
async function querySecurities(keyword) {
    const requestId = ++securitySearchRequestId;
    try {
        const data = await Api.endpoints.stock.search(
            `q=${encodeURIComponent(keyword)}&page_size=20`,
        );
        if (requestId !== securitySearchRequestId) return;
        const results = Array.isArray(data.results) ? data.results : [];
        securityCandidates = results.map((item) => ({
            code: item.code,
            name: item.name || "",
            market: item.market || "",
            market_type: item.market_type || "",
            displayName: item.code + (item.name ? " | " + item.name : ""),
        })).filter((item) => item.code && item.market);
        renderSecurityCandidates();
    } catch (error) {
        if (requestId === securitySearchRequestId) {
            securityCandidates = [];
            renderSecurityCandidates();
        }
    }
}

// 后端行可能来自内置K线库/akshare 等不带衍生指标的来源（null）；展示前统一：
// 缺失的振幅/涨跌幅/涨跌额用昨收推算（与东财口径一致），换手率无来源保持缺失。
function mapKlineRows(rows, klt) {
    const mapped = [];
    let invalidCount = 0;
    (rows || []).forEach((row) => {
        const open = Number(row.open);
        const high = Number(row.high);
        const low = Number(row.low);
        const close = Number(row.close);
        const volume = Number(row.volume);
        const amount = Number(row.amount);
        const values = [open, high, low, close, volume, amount];
        if (
            !getKlineDate({ stock_date: row.stock_date })
            || values.some((value) => !Number.isFinite(value))
            || open < 0
            || high < 0
            || low < 0
            || close < 0
            || high < Math.max(open, close)
            || low > Math.min(open, close)
        ) {
            invalidCount++;
            return;
        }
        const optional = (value) => (value === null || value === undefined || value === ""
            ? null
            : Number(value));
        const prevClose = mapped.length ? mapped[mapped.length - 1].close : null;
        let amplitude = optional(row.amplitude);
        let pctChange = optional(row.pct_change);
        let change = optional(row.change);
        if (prevClose && prevClose > 0) {
            if (amplitude === null) {
                amplitude = Number(((high - low) / prevClose * 100).toFixed(3));
            }
            if (change === null) {
                change = Number((close - prevClose).toFixed(3));
            }
            if (pctChange === null) {
                pctChange = Number(((close - prevClose) / prevClose * 100).toFixed(3));
            }
        }
        mapped.push({
            stock_date: row.stock_date,
            // 腾讯分钟线等来源不提供成交额，vwap 为 0 时按缺失展示。
            vwap: Number(row.vwap) > 0 ? Number(row.vwap) : null,
            open,
            close,
            high,
            low,
            volume,
            volume_unit: "股",
            amount,
            amplitude,
            pct_change: pctChange,
            change,
            turnover_rate: optional(row.turnover_rate),
            // 日K的当根数据在收盘前可能变化，标记待确认。
            is_final: String(klt) === "101" && String(row.stock_date).slice(0, 10) === getToday()
                ? "待确认"
                : "是",
        });
    });
    mapped.sort((left, right) => getKlineDate(left) - getKlineDate(right));
    return { rows: mapped, invalidCount };
}

// 波动率采用相邻价格简单收益率绝对值的算术平均。
function calculateAbsoluteVolatility(rows, priceField) {
    const prices = rows
        .map((row) => Number(row[priceField || "vwap"]))
        .filter((price) => Number.isFinite(price) && price > 0);
    if (prices.length < 2) {
        return null;
    }
    const absoluteReturns = [];
    for (let index = 1; index < prices.length; index++) {
        absoluteReturns.push(Math.abs((prices[index] - prices[index - 1]) / prices[index - 1]));
    }
    return {
        value: absoluteReturns.reduce((sum, value) => sum + value, 0) / absoluteReturns.length,
        observationCount: absoluteReturns.length,
    };
}

function filterRowsByDate(rows, startDate, endDate) {
    return rows.filter((row) => {
        const date = getKlineDate(row);
        return date && date >= startDate && date <= endDate;
    });
}

function hasCompleteSpan(rows, requiredDays, toleranceDays) {
    if (rows.length < 2) {
        return false;
    }
    const earliestDate = getKlineDate(rows[0]);
    const latestDate = getKlineDate(rows[rows.length - 1]);
    if (!earliestDate || !latestDate) {
        return false;
    }
    return (latestDate.getTime() - earliestDate.getTime()) / 86400000
        >= requiredDays - toleranceDays;
}

function shiftDate(referenceDate, days) {
    return new Date(referenceDate.getTime() - days * 86400000);
}

function getKlineDataRange(rows) {
    const dates = rows
        .map(getKlineDate)
        .filter((date) => date)
        .sort((left, right) => left - right);
    if (!dates.length) {
        return "-";
    }
    return formatKlineDate(dates[0]) + " 至 " + formatKlineDate(dates[dates.length - 1]);
}

// 以指定日期为基准，计算半年至七年的近年波动率。
function calculateRecentVolatilities(rows, priceField, referenceDate) {
    referenceDate = referenceDate || getKlineDate(rows[rows.length - 1]);
    const periods = [
        { key: "6m", label: "半年", days: 182, tolerance: 15 },
        { key: "1y", label: "1年", days: 365, tolerance: 30 },
        { key: "2y", label: "2年", days: 730, tolerance: 30 },
        { key: "3y", label: "3年", days: 1095, tolerance: 30 },
        { key: "4y", label: "4年", days: 1460, tolerance: 30 },
        { key: "5y", label: "5年", days: 1825, tolerance: 30 },
        { key: "6y", label: "6年", days: 2190, tolerance: 30 },
        { key: "7y", label: "7年", days: 2555, tolerance: 30 },
    ];
    const values = periods.map((period) => {
        const startDate = shiftDate(referenceDate, period.days);
        const periodRows = filterRowsByDate(rows, startDate, referenceDate);
        const isComplete = hasCompleteSpan(periodRows, period.days, period.tolerance);
        return {
            label: period.label,
            dataRange: getKlineDataRange(periodRows),
            result: isComplete
                ? calculateAbsoluteVolatility(periodRows, priceField)
                : null,
        };
    });
    values.push({
        label: "总体",
        dataRange: getKlineDataRange(rows),
        result: calculateAbsoluteVolatility(rows, priceField),
    });
    return { referenceDate, values };
}

// 将历史数据按连续 365 天划分年度，年度样本少于 200 条时不参与计算。
function calculateYearlyVolatilities(rows, referenceDate, priceField) {
    const values = [];
    let validYearRows = [];
    for (let year = 1; year <= 7; year++) {
        const endDate = shiftDate(referenceDate, (year - 1) * 365);
        const startDate = shiftDate(endDate, 365);
        const yearRows = filterRowsByDate(rows, startDate, endDate);
        const isComplete = yearRows.length >= 200;
        const result = isComplete ? calculateAbsoluteVolatility(yearRows, priceField) : null;
        if (result) {
            validYearRows = validYearRows.concat(yearRows);
        }
        values.push({
            label: `第${year}年`,
            dataRange: getKlineDataRange(yearRows),
            result,
        });
    }
    const calculatedValues = values
        .map((item) => (item.result ? item.result.value : null))
        .filter((value) => value !== null);
    values.push({
        label: "年度平均",
        detailLabel: "有效年度",
        dataRange: getKlineDataRange(validYearRows),
        result: calculatedValues.length
            ? {
                value: calculatedValues.reduce((sum, value) => sum + value, 0) / calculatedValues.length,
                observationCount: calculatedValues.length,
            }
            : null,
    });
    return values;
}

// 平均成交额使用每根有效 K 线的成交额算术平均。
function calculateAverageTurnover(rows) {
    const amounts = rows
        .map((row) => Number(row.amount))
        .filter((amount) => Number.isFinite(amount) && amount >= 0);
    if (!amounts.length) {
        return null;
    }
    return {
        value: amounts.reduce((sum, amount) => sum + amount, 0) / amounts.length,
        observationCount: amounts.length,
    };
}

// 平均成交额与年度波动率共用同一年度窗口和样本完整性规则。
function calculateYearlyAverageTurnovers(rows, referenceDate) {
    const values = [];
    for (let year = 1; year <= 7; year++) {
        const endDate = shiftDate(referenceDate, (year - 1) * 365);
        const startDate = shiftDate(endDate, 365);
        const yearRows = filterRowsByDate(rows, startDate, endDate);
        values.push({
            label: `第${year}年`,
            dataRange: getKlineDataRange(yearRows),
            result: yearRows.length >= 200 ? calculateAverageTurnover(yearRows) : null,
        });
    }
    values.push({
        label: "总体",
        dataRange: getKlineDataRange(rows),
        result: calculateAverageTurnover(rows),
    });
    return values;
}

// 汇总当前价格口径下的近年、年度波动率及年度平均成交额。
function calculateVolatilityAnalysis(rows, priceBasis, referenceDate) {
    const basis = getVolatilityPriceBasis(priceBasis);
    const recentVolatilities = calculateRecentVolatilities(rows, basis.field, referenceDate);
    return {
        priceBasis,
        recent: recentVolatilities,
        yearly: calculateYearlyVolatilities(rows, recentVolatilities.referenceDate, basis.field),
        turnover: calculateYearlyAverageTurnovers(rows, recentVolatilities.referenceDate),
    };
}

// 分析结果渲染（单元格只写 textContent，避免外部数据被当作 HTML 解析）。
function appendComparisonCells(row, values, unavailableText) {
    values.forEach((item) => {
        const cell = document.createElement("td");
        const detail = item.result
            ? (item.detailLabel || "有效收益率") + " " + item.result.observationCount + " 项"
            : unavailableText;
        cell.title = detail;
        const strong = document.createElement("strong");
        strong.textContent = item.result ? formatPercent(item.result.value) : "-";
        cell.appendChild(strong);
        row.appendChild(cell);
    });
}

function renderVolatilityAnalysis(recentVolatilities, yearlyVolatilities, yearlyTurnovers) {
    const comparisonBody = document.getElementById("volatility-comparison-body");
    const turnoverBody = document.getElementById("average-turnover-comparison-body");
    comparisonBody.innerHTML = "";
    turnoverBody.innerHTML = "";

    const recentRow = document.createElement("tr");
    const recentLabel = document.createElement("td");
    recentLabel.className = "fw-semibold";
    recentLabel.textContent = "近年";
    recentRow.appendChild(recentLabel);
    appendComparisonCells(recentRow, recentVolatilities.values, "数据跨度不足");
    comparisonBody.appendChild(recentRow);

    const yearlyRow = document.createElement("tr");
    const yearlyLabel = document.createElement("td");
    yearlyLabel.className = "fw-semibold";
    yearlyLabel.textContent = "年度";
    yearlyRow.appendChild(yearlyLabel);
    appendComparisonCells(yearlyRow, [{ result: null }].concat(yearlyVolatilities), "数据不足（至少200条）");
    comparisonBody.appendChild(yearlyRow);

    const turnoverRow = document.createElement("tr");
    const turnoverLabel = document.createElement("td");
    turnoverLabel.className = "fw-semibold";
    turnoverLabel.textContent = "平均成交额";
    turnoverRow.appendChild(turnoverLabel);
    yearlyTurnovers.forEach((item) => {
        const cell = document.createElement("td");
        cell.title = item.result
            ? `有效K线 ${item.result.observationCount} 条；数据范围：${item.dataRange}`
            : "数据不足（至少200条）";
        const strong = document.createElement("strong");
        strong.textContent = item.result
            ? item.result.value.toLocaleString("en-US", { maximumFractionDigits: 2 })
            : "-";
        cell.appendChild(strong);
        turnoverRow.appendChild(cell);
    });
    turnoverBody.appendChild(turnoverRow);

    const summary = document.getElementById("analysis-summary");
    summary.innerHTML = "";
    const items = [
        { label: "股票代码", value: queryData.stock_code },
        { label: "股票名称", value: getStockDisplayName() },
    ];
    items.forEach((item) => {
        const badge = document.createElement("span");
        badge.className = "analysis-copyable badge bg-light text-dark border";
        badge.title = "点击复制" + item.label;
        badge.dataset.copyText = item.value;
        badge.textContent = `${item.label}：${item.value}`;
        summary.appendChild(badge);
    });
    const reference = document.createElement("span");
    reference.className = "analysis-copyable badge bg-light text-dark border";
    reference.title = "点击复制参考日期";
    reference.dataset.copyText = formatKlineDate(recentVolatilities.referenceDate);
    reference.textContent = "参考日期：" + formatKlineDate(recentVolatilities.referenceDate);
    summary.appendChild(reference);

    document.getElementById("volatility-analysis").hidden = false;
}

// 优先使用现代剪贴板 API，非安全上下文退回到兼容方案。
function copyText(text) {
    function copyWithFallback() {
        const textarea = document.createElement("textarea");
        textarea.value = text;
        textarea.style.cssText = "position:fixed;opacity:0";
        document.body.appendChild(textarea);
        textarea.select();
        let copied = false;
        try {
            copied = document.execCommand("copy");
        } catch (error) {
            copied = false;
        }
        textarea.remove();
        showMessage(copied ? "已复制到剪切板" : "复制失败，请手动复制", copied ? "success" : "warning");
    }

    if (navigator.clipboard && window.isSecureContext) {
        navigator.clipboard.writeText(text).then(copyWithFallback).catch(copyWithFallback);
        return;
    }
    copyWithFallback();
}

function getDisplayRows(rows) {
    if (rows.length <= 40) {
        return rows.slice().reverse();
    }
    return rows.slice(-20).reverse().concat(rows.slice(0, 20).reverse());
}

// K线较多时仅展示最新和最早各 20 条，完整数据仍保留用于计算和导出。
function renderTable() {
    const displayRows = getDisplayRows(klineRows);
    document.getElementById("kline-table-head").innerHTML = KLINE_TABLE_COLUMNS
        .map((column) => `<th class="${column.align === "start" ? "text-start" : ""}">${column.title}</th>`)
        .join("");
    document.getElementById("kline-table-body").innerHTML = displayRows.map((row) => `<tr>${KLINE_TABLE_COLUMNS.map((column) => {
        if (column.align === "start") {
            const value = column.field === "stock_code"
                ? (queryData ? queryData.stock_code : "-")
                : row.stock_date;
            return `<td class="text-start text-nowrap">${escapeHtml(value)}</td>`;
        }
        const numeric = Number(row[column.field]);
        const text = !Number.isFinite(numeric)
            ? "-"
            : (column.integer ? numeric.toLocaleString("en-US") : formatNumber(numeric, column.digits));
        return `<td class="text-nowrap">${escapeHtml(text)}</td>`;
    }).join("")}</tr>`).join("");
    const meta = document.getElementById("table-meta");
    meta.textContent = klineRows.length > 40
        ? `共 ${klineRows.length} 条，已按日期倒序展示最新20条和最早20条`
        : `共 ${klineRows.length} 条，已按日期倒序展示全部`;
    meta.hidden = false;
}

// 重算不会重新请求接口，避免切换日期或价格口径时覆盖当前快照。
function refreshVolatilityAnalysis() {
    if (!klineRows.length || !queryData) {
        return;
    }
    const referenceDate = getVolatilityReferenceDate();
    if (!referenceDate) {
        showMessage("请选择有效的计算基准日期");
        return;
    }
    const oldDefaultFileName = getDefaultExportFileName(volatility);
    const currentFileName = document.getElementById("export-file-name").value.trim();
    queryData.priceBasis = document.getElementById("volatility-price-basis").value || "close";
    volatility = calculateVolatilityAnalysis(
        klineRows,
        queryData.priceBasis,
        referenceDate,
    );
    renderVolatilityAnalysis(volatility.recent, volatility.yearly, volatility.turnover);
    if (!currentFileName || currentFileName === oldDefaultFileName) {
        document.getElementById("export-file-name").value = getDefaultExportFileName(volatility);
    }
}

// 日K线只有日期，按所选日结束时刻计算以匹配桌面端 datetime.now() 的边界。
function getVolatilityReferenceDate() {
    const referenceDate = getKlineDate({
        stock_date: document.getElementById("volatility-reference-date").value,
    });
    if (referenceDate) {
        referenceDate.setHours(23, 59, 59, 999);
    }
    return referenceDate;
}

// klinecharts 渲染：一次性全量数据；换股票/周期后重新 applyNewData。
function toChartData(rows) {
    return rows.map((row) => {
        const date = getKlineDate(row);
        return {
            timestamp: date ? date.getTime() : 0,
            open: row.open,
            high: row.high,
            low: row.low,
            close: row.close,
            volume: row.volume,
            turnover: Number.isFinite(row.turnover_rate) ? row.turnover_rate : undefined,
        };
    });
}

// 后端 kline_type（东财 klt 口径）→ klinecharts v10 周期对象。
function chartPeriod(klineType) {
    const type = String(klineType || "101");
    if (type === "102") return { type: "week" };
    if (type === "103") return { type: "month" };
    if (["1", "5", "15", "30", "60"].includes(type)) {
        return { type: "minute", span: Number(type) };
    }
    return { type: "day" };
}

function applyChartSubIndicator() {
    if (!klineChart) return;
    const next = document.getElementById("kline-chart-indicator").value;
    if (chartSubPane && chartSubPane.name === next) return;
    if (chartSubPane) {
        try {
            // v10 指标 API：removeIndicator 只收单个 filter 对象；子 pane 无法删除
            // （v10 无 removePane），切换时只换指标、pane 复用。
            klineChart.removeIndicator({ paneId: chartSubPane.paneId, name: chartSubPane.name });
        } catch (error) {
            // 指标卸载失败不阻塞重建，下一次切换按当前状态继续。
            console.warn("副图指标卸载失败", error);
        }
        chartSubPane = null;
    }
    if (next) {
        // v10 签名 createIndicator(indicator, isStack)：paneId 放在指标对象内，
        // 不存在时自动建 pane；isStack=true 追加（false 会清空 pane 内已有指标）。
        klineChart.createIndicator({ name: next, paneId: "kline-sub-pane" }, true);
        klineChart.setPaneOptions({ id: "kline-sub-pane", height: 90 });
        chartSubPane = { paneId: "kline-sub-pane", name: next };
    }
}

// klinecharts 样式：跟随 html data-bs-theme 明暗主题；蜡烛红涨绿跌两主题通用。
function chartThemeStyles() {
    const dark = document.documentElement.getAttribute("data-bs-theme") === "dark";
    const gridColor = dark ? "rgba(255,255,255,0.14)" : "#e5e7eb";
    const textColor = dark ? "#9ca3af" : "#6b7280";
    const crosshairColor = dark ? "#6b7280" : "#9ca3af";
    return {
        grid: {
            horizontal: { color: gridColor },
            vertical: { show: false },
        },
        candle: {
            bar: {
                upColor: "#ef4444",
                downColor: "#159a57",
                noChangeColor: "#888888",
                upBorderColor: "#ef4444",
                downBorderColor: "#159a57",
                noChangeBorderColor: "#888888",
                upWickColor: "#ef4444",
                downWickColor: "#159a57",
                noChangeWickColor: "#888888",
            },
            tooltip: { showRule: "follow_cross" },
        },
        indicator: {
            bars: [{
                upColor: "#ef4444",
                downColor: "#159a57",
                noChangeColor: "#888888",
            }],
        },
        crosshair: {
            horizontal: { line: { color: crosshairColor }, text: { textColor } },
            vertical: { line: { color: crosshairColor }, text: { textColor } },
        },
        xAxis: {
            tickText: { textColor },
            line: { color: gridColor },
        },
        yAxis: {
            tickText: { textColor },
            line: { color: gridColor },
        },
        separator: { color: gridColor },
    };
}

function renderKlineChart() {
    const container = document.getElementById("kline-chart-container");
    if (!klineChart) {
        klineChart = klinecharts.init(container, { styles: chartThemeStyles() });
        // v10：paneId 在指标对象内，isStack=true 追加到主图，不清空已有指标
        klineChart.createIndicator(
            { name: "MA", calcParams: [5, 10, 20, 60], paneId: "candle_pane" },
            true,
        );
        chartSubPane = null;
        applyChartSubIndicator();
    } else {
        // 已有实例时同步当前主题（明暗切换后重新打开/换股即时生效）。
        klineChart.setStyles(chartThemeStyles());
    }
    // v10 无 setPriceVolumePrecision，精度随 symbol 设置；换股票时同步更新。
    klineChart.setSymbol({
        ticker: queryData.stock_code,
        pricePrecision: 3,
        volumePrecision: 0,
    });
    // v10 供数订阅要求 symbol/period/dataLoader 三者齐备；周期随查询参数同步。
    klineChart.setPeriod(chartPeriod(queryData.kline_type));
    // klinecharts v10 经 dataLoader 供数：callback 直接接收 (bars, more)。
    klineChart.setDataLoader({
        getBars: ({ callback }) => callback(toChartData(klineRows), false),
    });
    const sourceLabel = DATA_SOURCE_LABELS[queryData.data_source] || queryData.data_source;
    document.getElementById("kline-chart-modal-title").textContent =
        `${queryData.stock_code} ${getStockDisplayName()}（${sourceLabel} · ${queryData.kline_type === "101" ? "日K" : "周期" + queryData.kline_type}）`;
}

function openKlineChart() {
    if (!klineRows.length || !queryData) {
        showMessage("请先拉取K线数据");
        return;
    }
    showMessage("");
    bootstrap.Modal.getOrCreateInstance(document.getElementById("kline-chart-modal")).show();
}

async function fetchKlines() {
    const form = document.getElementById("kline-query-form");
    const limitInput = document.getElementById("kline-limit");
    const limit = Number(limitInput.value);
    if (!Number.isInteger(limit) || limit < 2 || limit > 10000) {
        limitInput.classList.add("is-invalid");
        return;
    }
    limitInput.classList.remove("is-invalid");
    if (!selectedStock) {
        showMessage("请先完成股票查询");
        return;
    }
    showMessage("");
    const fetchButton = document.getElementById("fetch-btn");
    fetchButton.disabled = true;
    try {
        const params = new URLSearchParams({
            stock_code: selectedStock.code,
            market_type: selectedStock.market_type || "",
            exchange_market: selectedStock.market || "",
            stock_name: selectedStock.name || "",
            data_source: document.getElementById("kline-data-source").value,
            kline_type: document.getElementById("kline-period").value,
            limit: String(limit),
            adjust_type: document.getElementById("kline-adjust").value,
        });
        const data = await Api.endpoints.stock.klines(params.toString());
        const parsed = mapKlineRows(data.rows, document.getElementById("kline-period").value);
        if (!parsed.rows.length) {
            showMessage("接口未返回有效K线数据" + (parsed.invalidCount ? `（${parsed.invalidCount} 条未通过字段校验）` : ""));
            return;
        }
        klineRows = parsed.rows;
        queryData = {
            stock_code: data.stock_code || selectedStock.code,
            stock_name: data.stock_name || selectedStock.name,
            data_source: data.data_source || document.getElementById("kline-data-source").value,
            kline_type: data.kline_type || document.getElementById("kline-period").value,
            adjust_type: data.adjust_type || document.getElementById("kline-adjust").value,
            priceBasis: document.getElementById("volatility-price-basis").value || "close",
        };
        volatility = calculateVolatilityAnalysis(
            klineRows,
            queryData.priceBasis,
            getVolatilityReferenceDate(),
        );
        renderVolatilityAnalysis(volatility.recent, volatility.yearly, volatility.turnover);
        renderTable();
        document.getElementById("export-file-name").value = getDefaultExportFileName(volatility);
        document.getElementById("export-btn").disabled = false;
        document.getElementById("kline-chart-btn").disabled = false;
        showMessage(
            `已拉取 ${klineRows.length} 条K线数据（${DATA_SOURCE_LABELS[queryData.data_source] || queryData.data_source}）`
            + (parsed.invalidCount ? `，${parsed.invalidCount} 条未通过字段校验已跳过` : ""),
            "success",
        );
    } catch (error) {
        showMessage(error.message || "K线接口请求失败");
    } finally {
        fetchButton.disabled = false;
    }
}

// 导出当前快照及与页面一致的分析结果。
function exportKlines() {
    if (!klineRows.length || !queryData || !volatility) {
        showMessage("请先拉取K线数据");
        return;
    }
    const klineExportRows = [[
        "证券标识", "证券代码", "证券名称", "日期", "VWAP",
        "开盘", "收盘", "最高", "最低",
        "成交量(股)", "成交额", "振幅%", "涨跌幅%", "涨跌额", "换手率%",
    ]];
    getExportRows(klineRows, document.getElementById("export-date-order").value).forEach((item) => {
        klineExportRows.push([
            queryData.stock_code,
            queryData.stock_code.split(".")[0],
            safeExportText(queryData.stock_name),
            item.stock_date,
            item.vwap,
            item.open,
            item.close,
            item.high,
            item.low,
            item.volume,
            item.amount,
            item.amplitude,
            item.pct_change,
            item.change,
            item.turnover_rate,
        ]);
    });
    const sourceLabel = DATA_SOURCE_LABELS[queryData.data_source] || queryData.data_source;
    const analysisRows = [
        [
            "数据源", sourceLabel,
            "证券标识", queryData.stock_code,
            "证券名称", safeExportText(queryData.stock_name),
            "K线周期", queryData.kline_type,
            "复权方式", queryData.adjust_type,
        ],
        [
            "取数时间", new Date().toISOString(),
            "成交量单位", klineRows[0].volume_unit,
            "波动率价格", getVolatilityPriceBasis(volatility.priceBasis).label,
            "算法版本", "mean_abs_simple_return",
        ],
        [],
        ["波动率参考日期", formatKlineDate(volatility.recent.referenceDate)],
        ["近年波动率"],
        ["区间", "波动率", "有效收益率数", "数据范围"],
    ];
    volatility.recent.values.forEach((item) => {
        analysisRows.push([
            item.label,
            item.result ? formatPercent(item.result.value) : "-",
            item.result ? item.result.observationCount : 0,
            item.dataRange,
        ]);
    });
    analysisRows.push(["年度波动率"]);
    analysisRows.push(["区间", "波动率", "有效收益率数", "数据范围"]);
    volatility.yearly.forEach((item) => {
        analysisRows.push([
            item.label,
            item.result ? formatPercent(item.result.value) : "-",
            item.result ? item.result.observationCount : 0,
            item.dataRange,
        ]);
    });
    try {
        excelExport.exportSheets([
            {
                rows: klineExportRows,
                sheetName: "K线数据",
                columnWidths: [16, 14, 18, 20, 15, 15, 15, 15, 18, 18, 20, 15, 12, 15, 14],
            },
            {
                rows: analysisRows,
                sheetName: "分析说明",
                columnWidths: [16, 18, 16, 18, 16, 18, 16, 18, 16, 18],
                getCellStyle: (rowIndex) => {
                    if (rowIndex === 4 || rowIndex === 5 || rowIndex === 15 || rowIndex === 16) {
                        return {
                            font: { bold: true },
                            fill: { patternType: "solid", fgColor: { rgb: "FFF2CC" } },
                        };
                    }
                },
            },
        ], getExportFileName());
    } catch (error) {
        showMessage(error.message || "Excel导出失败");
    }
}

function initSearchEvents() {
    const keywordInput = document.getElementById("stock-keyword");
    keywordInput.addEventListener("input", function () {
        const keyword = this.value.trim();
        securitySearchRequestId++;
        clearTimeout(securitySearchTimer);
        if (!keyword || cacheSelectedStock(keyword)) {
            if (!keyword) {
                selectedStock = null;
                securityCandidates = [];
                renderSecurityCandidates();
            }
            return;
        }
        selectedStock = null;
        securitySearchTimer = setTimeout(() => querySecurities(keyword), 300);
    });
    keywordInput.addEventListener("change", function () {
        cacheSelectedStock(this.value);
    });
    keywordInput.addEventListener("focus", function () {
        if (securityCandidates.length) {
            document.getElementById("stock-suggestions").hidden = false;
            this.setAttribute("aria-expanded", "true");
        }
    });
    keywordInput.addEventListener("keydown", (event) => {
        if (event.key === "Escape") {
            hideSecurityCandidates();
        }
    });
    document.getElementById("stock-suggestions").addEventListener("click", (event) => {
        const button = event.target.closest(".stock-suggestion");
        if (!button) return;
        const candidate = securityCandidates[Number(button.dataset.index)];
        if (candidate) {
            selectedStock = candidate;
            document.getElementById("stock-keyword").value = candidate.displayName;
            hideSecurityCandidates();
        }
    });
    document.addEventListener("mousedown", (event) => {
        if (!event.target.closest(".stock-search-control")) {
            hideSecurityCandidates();
        }
    });
    document.getElementById("analysis-summary").addEventListener("click", (event) => {
        const badge = event.target.closest(".analysis-copyable");
        if (badge) {
            copyText(badge.dataset.copyText);
        }
    });
}

function init() {
    initSearchEvents();

    document.getElementById("kline-query-form").addEventListener("submit", (event) => {
        event.preventDefault();
        fetchKlines();
    });

    document.getElementById("volatility-price-basis").addEventListener("change", refreshVolatilityAnalysis);
    document.getElementById("volatility-reference-date").value = getToday();
    document.getElementById("volatility-reference-date").addEventListener("change", refreshVolatilityAnalysis);

    document.getElementById("kline-chart-btn").addEventListener("click", openKlineChart);
    document.getElementById("export-btn").addEventListener("click", exportKlines);
    document.getElementById("kline-chart-indicator").addEventListener("change", applyChartSubIndicator);

    const chartModal = document.getElementById("kline-chart-modal");
    chartModal.addEventListener("shown.bs.modal", () => {
        if (klineRows.length) {
            renderKlineChart();
        }
    });
    chartModal.addEventListener("hidden.bs.modal", () => {
        if (klineChart) {
            klineChart.resize();
        }
    });
    window.addEventListener("resize", () => {
        if (klineChart) {
            klineChart.resize();
        }
    });
    // 明暗主题切换时刷新图表配色（template-auth 在 html 上切 data-bs-theme）。
    new MutationObserver(() => {
        if (klineChart) {
            klineChart.setStyles(chartThemeStyles());
        }
    }).observe(document.documentElement, { attributes: true, attributeFilter: ["data-bs-theme"] });
}

init();

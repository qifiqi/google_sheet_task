// V3 回测数据分析页（docs/design/performance-analysis-v3/01-设计方案.md）。
// 分层：来源适配（buildXxxRequest）→ 数据集登记（DatasetStore）→ 渲染（renderXxx(datasets[])）。
// 约定：红涨绿跌（.v3-up/.v3-down）；系列色只标识"是谁"（基准蓝/策略绿/超额橙），
// 涨跌色只标识"方向"；指标名一律经 window.MetricNames 取中文（common/metric-names.js）。
"use strict";

// ---- 常量 ----

const V3_COLORS = {
    bench: '#0d6efd',
    strat: '#198754',
    excess: '#fd7e14',
    benchSoft: 'rgba(13,110,253,0.45)',
    stratSoft: 'rgba(25,135,84,0.45)',
    excessSoft: 'rgba(253,126,20,0.45)',
    up: '#dc3545',
    upSoft: 'rgba(220,53,69,0.45)',
    down: '#198754',
    downSoft: 'rgba(25,135,84,0.45)',
    gray: '#6c757d'
};

// 对比模式下逐数据集的色板：首个数据集沿用策略绿，单数据集视觉与"策略"一致
const V3_DATASET_COLORS = ['#198754', '#0d6efd', '#6f42c1', '#d63384', '#fd7e14', '#20c997', '#6c757d'];

const V3_BUCKET_LABELS = ['<-5%', '-5%~-2%', '-2%~0%', '0%~2%', '2%~5%', '5%~10%', '>10%'];

const V3_RUNTIME_PARAMS_STORAGE_KEY = 'v3_runtime_params';

// ---- 状态 ----

let abortController = null;

const state = {
    // 数据集登记表（DatasetStore）：{ id, label, source, key, metrics, series, meta, wordPayload }
    datasets: [],
    // 当前选中（单视图图表消费：热力图/散点/极端/明细）
    activeDatasetId: null,
    // 参与对比的集合（多视图图表消费：净值/水下/年度/雷达/分布/KPI）
    compareIds: [],
    // Google Sheet 来源状态
    worksheets: [],
    spreadsheetId: '',
    lastFetchedSpreadsheetId: '',
    spreadsheetTitle: '',
    // 粘贴/Excel 来源状态
    manualDataTitle: '',
    manualDataSheetName: '',
    // 结果分析来源状态
    resultSeriesByResultId: new Map(),
    // Word 导出
    wordExportStock: null,
    wordExportStockPreset: null,
    wordExportSearchTimer: null,
    wordExportSearchAbortController: null,
    // 热力图视图
    heatmapView: 'index',
    charts: {}
};

// ---- 通用助手 ----

function fmtPct(v, digits = 2) {
    if (v === null || v === undefined || v === '' || Number.isNaN(Number(v))) return '-';
    return (Number(v) * 100).toFixed(digits) + '%';
}

function fmtNum(v, digits = 4) {
    if (v === null || v === undefined || v === '' || Number.isNaN(Number(v))) return '-';
    return Number(v).toFixed(digits);
}

function fmtInt(v) {
    if (v === null || v === undefined || v === '' || Number.isNaN(Number(v))) return '-';
    return String(Math.round(Number(v)));
}

// 已是百分数口径的值（分布占比由服务端 ×100 后下发）：只补 %，不再 ×100
function fmtPctRaw(v, digits = 2) {
    return isFiniteNum(v) ? `${Number(v).toFixed(digits)}%` : '-';
}

function numOrNull(v) {
    return isFiniteNum(v) ? Number(v) : null;
}

// 涨跌着色的百分比文本（红=正，绿=负；0 不着色）
function signedPctHtml(v, digits = 2) {
    if (v === null || v === undefined || v === '' || Number.isNaN(Number(v))) return '-';
    const num = Number(v);
    const cls = num > 0 ? 'v3-up' : (num < 0 ? 'v3-down' : '');
    return `<span class="${cls}">${fmtPct(num, digits)}</span>`;
}

function signedNumHtml(v, digits = 4) {
    if (v === null || v === undefined || v === '' || Number.isNaN(Number(v))) return '-';
    const num = Number(v);
    const cls = num > 0 ? 'v3-up' : (num < 0 ? 'v3-down' : '');
    return `<span class="${cls}">${fmtNum(num, digits)}</span>`;
}

// 数组中 year === 'all' 的条目（索提诺/卡玛/年化的整体值）
function allEntry(list) {
    if (!Array.isArray(list)) return null;
    return list.find((item) => item && String(item.year) === 'all') || list[0] || null;
}

// 分区间指标的 'all' 条目：夏普比率是字典 {'all': {...}, 'year_*': {...}}，
// 索提诺/卡玛是列表 [{year, ...}]；两种形状统一在此取整体值。
function periodEntry(value) {
    if (value && typeof value === 'object' && !Array.isArray(value)) {
        return value.all || Object.values(value)[0] || null;
    }
    return allEntry(value);
}

// 严格数值判定：Number(null)/Number('') 是 0，不能参与 delta/最优值比较
function isFiniteNum(value) {
    return value !== null && value !== undefined && value !== '' && Number.isFinite(Number(value));
}

// 分布数据取值：metrics 里分布被序列化为"按 7 档顺序排列的纯数组"（键丢失），
// 也兼容字典形状（label -> 值）。
function distValue(container, label) {
    if (Array.isArray(container)) {
        const index = V3_BUCKET_LABELS.indexOf(label);
        return index >= 0 ? container[index] : undefined;
    }
    return container ? container[label] : undefined;
}

// 分布标签：数组形状（键丢失）直接用固定 7 档；字典形状追加非标准档位
function distLabels(...containers) {
    const extras = [];
    containers.forEach((container) => {
        if (container && typeof container === 'object' && !Array.isArray(container)) {
            Object.keys(container).forEach((key) => {
                if (!V3_BUCKET_LABELS.includes(key) && !extras.includes(key)) extras.push(key);
            });
        }
    });
    return [...V3_BUCKET_LABELS, ...extras];
}

function yearMap(list, valueKey) {
    const m = new Map();
    if (Array.isArray(list)) {
        list.forEach((item) => {
            if (item) m.set(String(item.year), item[valueKey]);
        });
    }
    return m;
}

function objValuesSum(obj) {
    if (!obj || typeof obj !== 'object') return null;
    const values = Object.values(obj).map(Number).filter(Number.isFinite);
    return values.length ? values.reduce((a, b) => a + b, 0) : null;
}

function objMaxValue(obj) {
    if (!obj || typeof obj !== 'object' || Array.isArray(obj)) return null;
    const values = Object.values(obj).map(Number).filter(Number.isFinite);
    return values.length ? Math.max(...values) : null;
}

function totalDrawdown(metrics, key) {
    const payload = metrics?.[key];
    const total = payload?.total_maximum_drawdown;
    return total && typeof total === 'object' ? total.drawdown : null;
}

// ---- 数据集登记（DatasetStore，多数据对比接入口） ----
// 新数据源只需：构造 {key, label, source, metrics, series, meta, wordPayload} 调 addDataset。

function addDataset(entry) {
    const existingIndex = state.datasets.findIndex((ds) => ds.key === entry.key);
    let id;
    if (existingIndex >= 0) {
        id = state.datasets[existingIndex].id;
        entry.id = id;
        entry.color = state.datasets[existingIndex].color;
        state.datasets[existingIndex] = entry;
    } else {
        id = `ds-${Date.now()}-${state.datasets.length}`;
        entry.id = id;
        entry.color = V3_DATASET_COLORS[state.datasets.length % V3_DATASET_COLORS.length];
        state.datasets.push(entry);
    }
    // 新登记的数据集自动成为当前选中并参与对比
    state.activeDatasetId = id;
    if (!state.compareIds.includes(id)) {
        state.compareIds.push(id);
    }
    renderDatasetBar();
}

function removeDataset(id) {
    state.datasets = state.datasets.filter((ds) => ds.id !== id);
    state.compareIds = state.compareIds.filter((item) => item !== id);
    if (state.activeDatasetId === id) {
        state.activeDatasetId = state.compareIds[0] || state.datasets[0]?.id || null;
    }
    renderDatasetBar();
    renderAll();
}

function toggleCompare(id, checked) {
    if (checked) {
        if (!state.compareIds.includes(id)) state.compareIds.push(id);
    } else {
        state.compareIds = state.compareIds.filter((item) => item !== id);
    }
    renderAll();
}

function getDataset(id) {
    return state.datasets.find((ds) => ds.id === id) || null;
}

function activeDataset() {
    return getDataset(state.activeDatasetId) || state.datasets[0] || null;
}

function compareDatasets() {
    const ordered = state.compareIds.map(getDataset).filter(Boolean);
    return ordered.length ? ordered : (state.datasets.length ? [state.datasets[0]] : []);
}

function renderDatasetBar() {
    const bar = document.getElementById('v3-dataset-bar');
    const empty = document.getElementById('v3-dataset-empty');
    if (!bar) return;
    if (!state.datasets.length) {
        bar.innerHTML = '<span class="small text-body-secondary" id="v3-dataset-empty">暂无数据集，分析后自动登记。</span>';
        return;
    }
    if (empty) empty.remove();
    bar.innerHTML = '';
    state.datasets.forEach((ds) => {
        const chip = document.createElement('div');
        chip.className = 'v3-dataset-chip' + (ds.id === state.activeDatasetId ? ' active' : '');
        chip.title = `${ds.label}（点击设为当前；勾选参与对比）`;
        chip.innerHTML = `
            <input type="checkbox" class="form-check-input m-0" style="width:.85em;height:.85em" ${state.compareIds.includes(ds.id) ? 'checked' : ''} aria-label="参与对比">
            <span class="v3-dot" style="background:${ds.color}"></span>
            <span>${escapeHtml(ds.label)}</span>
            <button type="button" class="v3-remove" aria-label="移除">&times;</button>`;
        chip.querySelector('input').addEventListener('click', (e) => {
            e.stopPropagation();
            toggleCompare(ds.id, e.target.checked);
        });
        chip.querySelector('.v3-remove').addEventListener('click', (e) => {
            e.stopPropagation();
            removeDataset(ds.id);
        });
        chip.addEventListener('click', () => {
            state.activeDatasetId = ds.id;
            renderDatasetBar();
            renderAll();
        });
        bar.appendChild(chip);
    });
    const hint = document.createElement('span');
    hint.className = 'small text-body-secondary ms-1';
    hint.textContent = `共 ${state.datasets.length} 个，对比中 ${state.compareIds.length} 个`;
    bar.appendChild(hint);
}

// ---- Chart.js 通用 ----

// 坐标轴风格对齐 Word 报告：浅色横向网格、灰蓝轴线、深色刻度文字；
// 百分比轴刻度只显数值不带 %，单位由轴标题（%）说明（与报告 _set_percent_axis 同口径）。
// 颜色按 html data-bs-theme 明暗主题取值（template-auth 全局切换），暗色下保证刻度可读。
function v3AxisColors() {
    const dark = document.documentElement.getAttribute('data-bs-theme') === 'dark';
    return dark
        ? {grid: '#2C3440', border: '#5A6675', text: '#C9D2DD', label: '#AEB9C6'}
        : {grid: '#E1E6EC', border: '#9EADBD', text: '#333333', label: '#495057'};
}

function v3YScale(titleText, opts = {}) {
    const axis = v3AxisColors();
    return {
        title: {display: !!titleText, text: titleText, color: axis.text, font: {size: 11}},
        grid: {color: axis.grid},
        border: {display: true, color: axis.border},
        ticks: {color: axis.text, ...(opts.ticks || {})},
        beginAtZero: opts.beginAtZero === true,
        ...(opts.type ? {type: opts.type} : {})
    };
}

function v3XScale(opts = {}) {
    const axis = v3AxisColors();
    return {
        grid: {display: false},
        border: {display: true, color: axis.border},
        ticks: {color: axis.text, autoSkip: true, maxRotation: opts.maxRotation ?? 45, ...(opts.ticks || {})}
    };
}

// 柱顶数值标注插件（chart.$v3ValueLabelFormat 存在时生效）。
// 注意：format 回调不能放进 chart options——Chart.js v4 的 options 代理会把
// 函数值选项当"可脚本化回调"在解析期调用，造成 format->format 递归异常，
// 中断整个动画帧的绘制（表现为多张图同时空白）。
const v3ValueLabelsPlugin = {
    id: 'v3ValueLabels',
    afterDatasetsDraw(chart) {
        const opts = chart.options.plugins?.v3ValueLabels;
        if (!opts || !opts.enabled) return;
        const format = chart.$v3ValueLabelFormat;
        const {ctx} = chart;
        chart.data.datasets.forEach((dataset, di) => {
            if (dataset.type === 'line') return;
            const meta = chart.getDatasetMeta(di);
            if (meta.hidden) return;
            meta.data.forEach((bar, i) => {
                const v = dataset.data[i];
                if (v === null || v === undefined) return;
                ctx.save();
                ctx.fillStyle = v3AxisColors().label;
                ctx.font = '10px sans-serif';
                ctx.textAlign = 'center';
                ctx.fillText(format ? format(v) : String(v), bar.x, bar.y - 4);
                ctx.restore();
            });
        });
    }
};
Chart.register(v3ValueLabelsPlugin);

// 创建柱状图后的统一挂载：把 format 挂在实例上（不进 options 树，见上）
function attachValueLabelFormat(chart, format) {
    chart.$v3ValueLabelFormat = format || null;
    return chart;
}

// x=0 参照线（直方图用）：options.plugins.v3ZeroLine.index 为 category 轴索引（可为 0.5 边界）
const v3ZeroLinePlugin = {
    id: 'v3ZeroLine',
    afterDatasetsDraw(chart) {
        const opts = chart.options.plugins?.v3ZeroLine;
        if (!opts || opts.index === null || opts.index === undefined) return;
        const xScale = chart.scales.x;
        if (!xScale || xScale.type !== 'category') return;
        const x = xScale.getPixelForValue(opts.index);
        const {top, bottom} = chart.chartArea;
        const ctx = chart.ctx;
        ctx.save();
        ctx.strokeStyle = v3AxisColors().border;
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.moveTo(x, top);
        ctx.lineTo(x, bottom);
        ctx.stroke();
        ctx.restore();
    }
};
Chart.register(v3ZeroLinePlugin);

function destroyChart(key) {
    const chart = state.charts[key];
    if (chart) {
        try {
            chart.destroy();
        } catch (e) { /* 画布已移除时忽略 */ }
    }
    state.charts[key] = null;
}

function commonBarOptions(yTitle, format) {
    return {
        responsive: true,
        maintainAspectRatio: false,
        interaction: {mode: 'index', intersect: false},
        plugins: {
            legend: {position: 'top'},
            v3ValueLabels: {enabled: !!format}
        },
        scales: {
            y: v3YScale(yTitle ? `${yTitle}` : '', {beginAtZero: true}),
            x: v3XScale()
        }
    };
}

// ---- 渲染总入口 ----

function renderAll() {
    const datasets = compareDatasets();
    if (!datasets.length) {
        ['#v3-kpi-container', 'v3-heatmap', 'v3-dist-shape-cards', 'v3-capital-cards'].forEach((sel) => {
            const el = document.getElementById(sel.replace('#', ''));
            if (el) el.innerHTML = '';
        });
        Object.keys(state.charts).forEach(destroyChart);
        return;
    }
    const single = datasets.length === 1;
    const active = activeDataset() || datasets[0];
    const r = active.metrics || {};

    // 对比模式下隐藏"仅单数据集"卡片（基准 vs 策略语义）
    document.getElementById('v3-excess-annual-card')?.classList.toggle('d-none', !single);
    document.getElementById('v3-monthly-excess-card')?.classList.toggle('d-none', !single);
    document.getElementById('v3-dist-excess-card')?.classList.toggle('d-none', !single);

    renderCaliberChips(active);
    renderSourceInfo(active, datasets);
    renderKpi(datasets, single);
    renderNavCharts(datasets, single);
    renderExcessLineChart(datasets, single);
    renderAnnualCharts(datasets, single);
    renderMonthlyCharts(active, single);
    renderDistCharts(datasets, single);
    renderExtremeSection(active);
    renderDetails(active);
}

function renderCaliberChips(dataset) {
    const container = document.getElementById('v3-caliber-chips');
    if (!container) return;
    const r = dataset.metrics || {};
    const chips = [];
    const push = (label, value) => {
        if (value !== null && value !== undefined) chips.push(`${label} ${value}`);
    };
    push('下跌阈值', fmtPct(r.market_downturn_threshold));
    push('上涨阈值', fmtPct(r.market_upturn_threshold));
    push('极端单日', fmtPct(r.daily_extreme_threshold));
    push('单日回撤', fmtPct(r.daily_drawdown_threshold));
    const riskFree = Number(document.getElementById('config-risk-free-rate')?.value || 0);
    push('无风险利率', `${riskFree}%`);
    if (dataset.series?.dates?.length) {
        const dates = dataset.series.dates;
        chips.push(`区间 ${dates[0]} ~ ${dates[dates.length - 1]}`);
    }
    container.innerHTML = chips.map((chip) => `<span class="v3-caliber-chip ms-1">${escapeHtml(chip)}</span>`).join('');
}

function renderSourceInfo(active, datasets) {
    const el = document.getElementById('v3-source-info');
    if (!el) return;
    const parts = datasets.map((ds) => {
        const dot = `<span class="v3-swatch" style="background:${ds.color}"></span>`;
        return `${dot} ${escapeHtml(ds.label)}`;
    });
    let note = '';
    if (datasets.length > 1) {
        note = '（对比模式：曲线为各数据集策略净值，超额/散点等单视图图表展示当前选中数据集，各自基准独立）';
    }
    el.innerHTML = parts.join('　') + note;
}

// ---- KPI ----

function kpiRows(datasets) {
    // 行 = [中文名, 取值函数(metrics) => fraction|number|null, 格式, 更优方向]
    return [
        ['累计回报率', (r) => r.index_cumulative_return, (r) => r.start_cumulative_return, (r) => r.excess_cumulative_return, 'pct', 'higher'],
        ['年化收益率', (r) => allEntry(r.index_annualized_rates)?.annualized_return, (r) => allEntry(r.start_annualized_rates)?.annualized_return, (r) => allEntry(r.excess_returns)?.annualized_return_diff, 'pct', 'higher'],
        // 后端 drawdown 为正数量级（回撤深度），越小越优
        ['最大回撤（MDD）', (r) => totalDrawdown(r, 'index_maximum_drawdown'), (r) => totalDrawdown(r, 'start_maximum_drawdown'), () => null, 'pct', 'lower'],
        ['年化波动率', (r) => periodEntry(r.index_sharpe_ratios)?.annual_std_dev, (r) => periodEntry(r.start_sharpe_ratios)?.annual_std_dev, () => null, 'pct', 'lower'],
        ['夏普比率', (r) => periodEntry(r.index_sharpe_ratios)?.sharpe_ratio, (r) => periodEntry(r.start_sharpe_ratios)?.sharpe_ratio, (r) => r.excess_sharpe, 'num4', 'higher'],
        ['索提诺比率', (r) => allEntry(r.index_sortino_ratio)?.sortino_ratio, (r) => allEntry(r.start_sortino_ratio)?.sortino_ratio, (r) => r.excess_sortino, 'num4', 'higher'],
        ['卡玛比率', (r) => allEntry(r.index_kama_ratio)?.kama_ratio, (r) => allEntry(r.start_kama_ratio)?.kama_ratio, () => null, 'num4', 'higher'],
        ['月盈利百分比', (r) => r.index_profit_percentage, (r) => r.start_profit_percentage, () => null, 'pct', 'higher'],
        ['月超额胜率（>0）', () => null, () => null, (r) => r.monthly_excess_win_rate, 'pct', 'higher']
    ];
}

function fmtByType(value, type) {
    return type === 'pct' ? fmtPct(value) : fmtNum(value, 4);
}

function renderKpi(datasets, single) {
    const container = document.getElementById('v3-kpi-container');
    if (!container) return;

    if (single) {
        const r = datasets[0].metrics || {};
        const rows = kpiRows(datasets).map(([label, idxFn, stFn, exFn, type, better]) => {
            const idx = idxFn(r);
            const st = stFn(r);
            const ex = exFn(r);
            const delta = (isFiniteNum(st) && isFiniteNum(idx)) ? Number(st) - Number(idx) : null;
            const stCls = better === 'higher'
                ? (delta !== null && delta > 0 ? 'v3-up' : (delta !== null && delta < 0 ? 'v3-down' : ''))
                : (delta !== null && delta < 0 ? 'v3-up' : (delta !== null && delta > 0 ? 'v3-down' : ''));
            const fmtCell = (v) => `<td class="num">${fmtByType(v, type)}</td>`;
            return `<tr>
                <td>${label}</td>
                ${fmtCell(idx)}
                <td class="num">${fmtByType(st, type)}${delta !== null ? `<span class="v3-kpi-delta ${stCls}">(${fmtByType(delta, type)})</span>` : ''}</td>
                <td class="num">${ex === null ? '-' : `<span class="${Number(ex) >= 0 ? 'v3-up' : 'v3-down'}">${fmtByType(ex, type)}</span>`}</td>
            </tr>`;
        }).join('');
        container.innerHTML = `
            <div class="card border-0 shadow-sm">
                <div class="card-header py-2"><h6 class="card-title mb-0">核心指标（基准 / 策略 / 超额）</h6></div>
                <div class="card-body p-0">
                    <div class="table-responsive">
                        <table class="table table-sm mb-0 v3-kpi-table">
                            <thead><tr><th>指标</th><th class="num">基准</th><th class="num">策略</th><th class="num">超额</th></tr></thead>
                            <tbody>${rows}</tbody>
                        </table>
                    </div>
                </div>
            </div>`;
        return;
    }

    // 对比模式：每数据集一列（策略口径）
    const head = datasets.map((ds) => `<th class="num"><span class="v3-swatch" style="background:${ds.color}"></span> ${escapeHtml(ds.label)}</th>`).join('');
    const rows = kpiRows(datasets).map(([label, , stFn, , type, better]) => {
        const values = datasets.map((ds) => {
            const v = stFn(ds.metrics || {});
            return isFiniteNum(v) ? Number(v) : null;
        });
        const finite = values.filter((v) => v !== null);
        const best = finite.length ? (better === 'higher' ? Math.max(...finite) : Math.min(...finite)) : null;
        const cells = values.map((v) => {
            if (v === null) return '<td class="num">-</td>';
            const cls = v === best ? 'v3-best' : '';
            return `<td class="num ${cls}">${fmtByType(v, type)}</td>`;
        }).join('');
        return `<tr><td>${label}</td>${cells}</tr>`;
    }).join('');
    container.innerHTML = `
        <div class="card border-0 shadow-sm">
            <div class="card-header py-2"><h6 class="card-title mb-0">核心指标对比（策略口径，绿色描边为该行最优）</h6></div>
            <div class="card-body p-0">
                <div class="table-responsive">
                    <table class="table table-sm mb-0 v3-kpi-table">
                        <thead><tr><th>指标</th>${head}</tr></thead>
                        <tbody>${rows}</tbody>
                    </table>
                </div>
            </div>
        </div>`;
}

// ---- 净值与水下 ----

function drawdownSeries(navValues) {
    let peak = null;
    return navValues.map((v) => {
        if (v === null || v === undefined) return null;
        peak = peak === null ? v : Math.max(peak, v);
        return peak > 0 ? (v / peak - 1) * 100 : 0;
    });
}

function renderNavCharts(datasets, single) {
    const el = document.getElementById('v3-chart-nav');
    if (!el) return;
    destroyChart('nav');

    // 时间轴取第一个参与对比数据集的日期（各数据集独立分析，通常覆盖不同区间时请单独查看）
    const first = datasets[0];
    if (!first?.series?.dates?.length) {
        return;
    }
    const labels = first.series.dates;
    const navDatasets = [];

    if (single) {
        navDatasets.push({label: '基准净值', data: first.series.index_nav, borderColor: V3_COLORS.bench, backgroundColor: 'transparent', borderWidth: 1.5, pointRadius: 0, tension: 0});
        navDatasets.push({label: '策略净值', data: first.series.start_nav, borderColor: V3_COLORS.strat, backgroundColor: 'transparent', borderWidth: 1.8, pointRadius: 0, tension: 0});
        navDatasets.push({label: '超额净值', data: first.series.excess_nav, borderColor: V3_COLORS.excess, backgroundColor: 'transparent', borderWidth: 1.5, borderDash: [6, 4], pointRadius: 0, tension: 0});
    } else {
        navDatasets.push({
            label: `${first.label}·基准净值`, data: first.series.index_nav,
            borderColor: V3_COLORS.gray, borderWidth: 1.2, borderDash: [4, 4], pointRadius: 0, tension: 0
        });
        datasets.forEach((ds) => {
            if (!ds.series?.start_nav) return;
            navDatasets.push({
                label: `${ds.label}·策略净值`,
                data: alignSeries(ds.series.dates, ds.series.start_nav, labels),
                borderColor: ds.color, borderWidth: 1.8, pointRadius: 0, tension: 0
            });
        });
    }

    const logScale = document.getElementById('v3-nav-log-toggle')?.checked;
    state.charts.nav = new Chart(el, {
        type: 'line',
        data: {labels, datasets: navDatasets},
        options: {
            responsive: true,
            maintainAspectRatio: false,
            interaction: {mode: 'index', intersect: false},
            plugins: {legend: {position: 'top'}},
            scales: {
                // 对数轴开关在构造期传入——Chart.js 构造完成时 scale 已固化，事后改 options 不生效
                y: v3YScale('净值', {ticks: {maxTicksLimit: 8}, type: logScale ? 'logarithmic' : undefined}),
                x: v3XScale({maxRotation: 0, ticks: {maxTicksLimit: 8}})
            }
        }
    });

    // 水下回撤：策略（单模式叠加基准），填充至 0 轴以下
    const uwEl = document.getElementById('v3-chart-underwater');
    if (!uwEl) return;
    destroyChart('underwater');
    const uwDatasets = [];
    if (single) {
        uwDatasets.push({label: '基准回撤%', data: drawdownSeries(first.series.index_nav), borderColor: V3_COLORS.bench, backgroundColor: 'rgba(13,110,253,0.12)', fill: 'origin', borderWidth: 1.2, pointRadius: 0, tension: 0});
        uwDatasets.push({label: '策略回撤%', data: drawdownSeries(first.series.start_nav), borderColor: V3_COLORS.down, backgroundColor: 'rgba(25,135,84,0.15)', fill: 'origin', borderWidth: 1.5, pointRadius: 0, tension: 0});
    } else {
        datasets.forEach((ds) => {
            if (!ds.series?.start_nav) return;
            uwDatasets.push({
                label: `${ds.label}·策略回撤%`, data: drawdownSeries(alignSeries(ds.series.dates, ds.series.start_nav, labels)),
                borderColor: ds.color, backgroundColor: 'transparent', borderWidth: 1.4, pointRadius: 0, tension: 0
            });
        });
    }
    state.charts.underwater = new Chart(uwEl, {
        type: 'line',
        data: {labels, datasets: uwDatasets},
        options: {
            responsive: true,
            maintainAspectRatio: false,
            interaction: {mode: 'index', intersect: false},
            plugins: {legend: {position: 'top'}},
            scales: {
                y: v3YScale('距高点（%）', {ticks: {maxTicksLimit: 6, callback: (value) => Number(value).toFixed(1)}}),
                x: v3XScale({maxRotation: 0, ticks: {maxTicksLimit: 8}})
            }
        }
    });
}

// 累计超额收益曲线（对齐 Word 报告"超额收益曲线"：excess_nav - 1 即逐点累计超额）
function renderExcessLineChart(datasets, single) {
    const el = document.getElementById('v3-chart-excess-line');
    if (!el) return;
    destroyChart('excessLine');
    const first = datasets[0];
    if (!first?.series?.excess_nav?.length) return;
    const labels = first.series.dates;
    const toExcessPct = (nav) => nav.map((v) => (v === null || v === undefined ? null : (v - 1) * 100));
    const excessDatasets = [];
    if (single) {
        excessDatasets.push({label: '累计超额收益%', data: toExcessPct(first.series.excess_nav), borderColor: V3_COLORS.up, backgroundColor: 'transparent', borderWidth: 1.5, pointRadius: 0, tension: 0});
    } else {
        datasets.forEach((ds) => {
            if (!ds.series?.excess_nav) return;
            excessDatasets.push({
                label: `${ds.label}·累计超额%`,
                data: alignSeries(ds.series.dates, toExcessPct(ds.series.excess_nav), labels),
                borderColor: ds.color, borderWidth: 1.5, pointRadius: 0, tension: 0
            });
        });
    }
    state.charts.excessLine = new Chart(el, {
        type: 'line',
        data: {labels, datasets: excessDatasets},
        options: {
            responsive: true,
            maintainAspectRatio: false,
            interaction: {mode: 'index', intersect: false},
            plugins: {legend: {position: 'top'}},
            scales: {
                y: v3YScale('累计超额收益（%）', {ticks: {maxTicksLimit: 6, callback: (value) => Number(value).toFixed(1)}}),
                x: v3XScale({maxRotation: 0, ticks: {maxTicksLimit: 8}})
            }
        }
    });
}

// 把数据集自身的序列按目标日期轴对齐（缺失置 null，图上断线）
function alignSeries(sourceDates, values, targetDates) {
    if (!sourceDates || !values) return values;
    if (sourceDates.length === targetDates.length && sourceDates[0] === targetDates[0]) return values;
    const m = new Map(sourceDates.map((d, i) => [d, values[i]]));
    return targetDates.map((d) => (m.has(d) ? m.get(d) : null));
}

// ---- 年度绩效 ----

function renderAnnualCharts(datasets, single) {
    // 年度收益率
    const yearSet = new Set();
    datasets.forEach((ds) => {
        ['index_returns_rate', 'start_returns_rate'].forEach((key) => {
            (ds.metrics?.[key] || []).forEach((item) => {
                if (item && String(item.year) !== 'all') yearSet.add(String(item.year));
            });
        });
    });
    const years = Array.from(yearSet).sort();
    const annualDatasets = [];
    if (single) {
        annualDatasets.push({label: '基准收益%', data: years.map((y) => pctOrNull(yearMap(datasets[0].metrics?.index_returns_rate, 'annual_return').get(y))), backgroundColor: V3_COLORS.benchSoft, borderColor: V3_COLORS.bench, borderWidth: 1});
        annualDatasets.push({label: '策略收益%', data: years.map((y) => pctOrNull(yearMap(datasets[0].metrics?.start_returns_rate, 'annual_return').get(y))), backgroundColor: V3_COLORS.stratSoft, borderColor: V3_COLORS.strat, borderWidth: 1});
    } else {
        datasets.forEach((ds) => {
            annualDatasets.push({label: `${ds.label}·策略收益%`, data: years.map((y) => pctOrNull(yearMap(ds.metrics?.start_returns_rate, 'annual_return').get(y))), backgroundColor: hexToSoft(ds.color), borderColor: ds.color, borderWidth: 1});
        });
    }
    buildBarChart('v3-chart-annual-returns', 'annualReturns', years, annualDatasets, '%', (v) => `${Number(v).toFixed(1)}`);

    // 年度最大回撤（单模式基准 vs 策略；对比模式各数据集策略）
    const ddYearSet = new Set();
    datasets.forEach((ds) => {
        ['index_maximum_drawdown', 'start_maximum_drawdown'].forEach((key) => {
            (ds.metrics?.[key]?.year_maximum_drawdown || []).forEach((item) => {
                if (item && String(item.year) !== 'all') ddYearSet.add(String(item.year));
            });
        });
    });
    const ddYears = Array.from(ddYearSet).sort();
    const ddDatasets = [];
    if (single) {
        ddDatasets.push({label: '基准回撤%', data: ddYears.map((y) => pctOrNull(yearMap(datasets[0].metrics?.index_maximum_drawdown?.year_maximum_drawdown, 'drawdown').get(y))), backgroundColor: V3_COLORS.benchSoft, borderColor: V3_COLORS.bench, borderWidth: 1});
        ddDatasets.push({label: '策略回撤%', data: ddYears.map((y) => pctOrNull(yearMap(datasets[0].metrics?.start_maximum_drawdown?.year_maximum_drawdown, 'drawdown').get(y))), backgroundColor: V3_COLORS.stratSoft, borderColor: V3_COLORS.strat, borderWidth: 1});
    } else {
        datasets.forEach((ds) => {
            ddDatasets.push({label: `${ds.label}·策略回撤%`, data: ddYears.map((y) => pctOrNull(yearMap(ds.metrics?.start_maximum_drawdown?.year_maximum_drawdown, 'drawdown').get(y))), backgroundColor: hexToSoft(ds.color), borderColor: ds.color, borderWidth: 1});
        });
    }
    buildBarChart('v3-chart-annual-drawdown', 'annualDrawdown', ddYears, ddDatasets, '%', (v) => `${Number(v).toFixed(1)}`);

    // 年超额收益（仅单模式；正红负绿）
    const excessAnnualEl = document.getElementById('v3-chart-excess-annual');
    if (excessAnnualEl) {
        destroyChart('excessAnnual');
        if (single) {
            const list = (datasets[0].metrics?.excess_returns || []).filter((item) => item && String(item.year) !== 'all');
            const labels = list.map((item) => String(item.year));
            const values = list.map((item) => Number(item.annualized_return_diff ?? 0) * 100);
            state.charts.excessAnnual = attachValueLabelFormat(new Chart(excessAnnualEl, {
                type: 'bar',
                data: {
                    labels,
                    datasets: [{
                        label: '年超额收益%',
                        data: values,
                        backgroundColor: values.map((v) => (v >= 0 ? V3_COLORS.upSoft : V3_COLORS.downSoft)),
                        borderColor: values.map((v) => (v >= 0 ? V3_COLORS.up : V3_COLORS.down)),
                        borderWidth: 1
                    }]
                },
                options: commonBarOptions('%', (v) => `${Number(v).toFixed(1)}`)
            }), (v) => `${Number(v).toFixed(1)}`);
        }
    }

    renderRadar(datasets, single);
}

function renderRadar(datasets, single) {
    const el = document.getElementById('v3-chart-radar');
    if (!el) return;
    destroyChart('radar');

    const axisDefs = [
        {label: '夏普比率', get: (r) => periodEntry(r.index_sharpe_ratios)?.sharpe_ratio, getSt: (r) => periodEntry(r.start_sharpe_ratios)?.sharpe_ratio},
        {label: '索提诺比率', get: (r) => allEntry(r.index_sortino_ratio)?.sortino_ratio, getSt: (r) => allEntry(r.start_sortino_ratio)?.sortino_ratio},
        {label: '卡玛比率', get: (r) => allEntry(r.index_kama_ratio)?.kama_ratio, getSt: (r) => allEntry(r.start_kama_ratio)?.kama_ratio},
        {label: '年化收益率', get: (r) => allEntry(r.index_annualized_rates)?.annualized_return, getSt: (r) => allEntry(r.start_annualized_rates)?.annualized_return},
        {label: '月波动率(低更优)', get: (r) => r.index_monthly_return_volatility, getSt: (r) => r.start_monthly_return_volatility, invert: true}
    ];

    // 归一化：各轴按参与序列的最大值缩放到 0~1；波动率轴取反（越小得分越高）
    const rawPolygons = [];
    if (single) {
        rawPolygons.push({label: '基准', color: V3_COLORS.bench, values: axisDefs.map((axis) => axis.get(datasets[0].metrics || {}))});
    }
    datasets.forEach((ds) => {
        rawPolygons.push({label: single ? '策略' : ds.label, color: single ? V3_COLORS.strat : ds.color, values: axisDefs.map((axis) => axis.getSt(ds.metrics || {}))});
    });

    const normalized = axisDefs.map((axis, ai) => {
        const values = rawPolygons.map((poly) => Number(poly.values[ai])).filter(isFiniteNum);
        if (!values.length) return rawPolygons.map(() => null);
        const max = Math.max(...values, 0);
        const min = Math.min(...values, 0);
        return rawPolygons.map((poly) => {
            const v = Number(poly.values[ai]);
            if (!Number.isFinite(v) || max === min) return max === 0 ? null : 0.5;
            const score = (v - min) / (max - min);
            return axis.invert ? 1 - score : score;
        });
    });

    const radarDatasets = rawPolygons.map((poly, pi) => ({
        label: poly.label,
        data: axisDefs.map((_, ai) => normalized[ai][pi]),
        borderColor: poly.color,
        backgroundColor: hexToSoft(poly.color, 0.15),
        borderWidth: 1.6,
        pointRadius: 2
    }));

    state.charts.radar = new Chart(el, {
        type: 'radar',
        data: {labels: axisDefs.map((axis) => axis.label), datasets: radarDatasets},
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {legend: {position: 'top'}},
            scales: {r: {min: 0, max: 1, ticks: {display: false}}}
        }
    });
}

function pctOrNull(v) {
    return Number.isFinite(Number(v)) ? Number(v) * 100 : null;
}

function hexToSoft(hex, alpha = 0.45) {
    const value = hex.replace('#', '');
    const r = parseInt(value.substring(0, 2), 16);
    const g = parseInt(value.substring(2, 4), 16);
    const b = parseInt(value.substring(4, 6), 16);
    return `rgba(${r},${g},${b},${alpha})`;
}

function buildBarChart(canvasId, key, labels, datasets, yTitle, format) {
    const el = document.getElementById(canvasId);
    if (!el) return;
    destroyChart(key);
    state.charts[key] = attachValueLabelFormat(new Chart(el, {
        type: 'bar',
        data: {labels, datasets},
        options: commonBarOptions(yTitle, format)
    }), format);
}

// ---- 月度透视 ----

function renderMonthlyCharts(active, single) {
    renderHeatmap(active);
    if (single) {
        renderMonthlyExcessChart(active);
    }
    renderRollingChart(active, single);
    renderScatter(active);
}

function heatmapData(active) {
    const list = Array.isArray(active.metrics?.monthly_excess_returns) ? active.metrics.monthly_excess_returns : [];
    const years = new Set();
    const cells = new Map();
    list.forEach((item) => {
        if (!item?.year_month) return;
        const ym = String(item.year_month);
        const year = ym.slice(0, 4);
        const month = Number(ym.slice(5, 7));
        if (!month) return;
        years.add(year);
        const value = state.heatmapView === 'index' ? item.index_monthly_return
            : state.heatmapView === 'start' ? item.start_monthly_return
                : item.monthly_excess_return_diff;
        cells.set(`${year}-${month}`, Number.isFinite(Number(value)) ? Number(value) : null);
    });
    return {years: Array.from(years).sort(), cells};
}

function renderHeatmap(active) {
    const container = document.getElementById('v3-heatmap');
    if (!container) return;
    const {years, cells} = heatmapData(active);
    if (!years.length) {
        container.innerHTML = '<div class="small text-body-secondary p-2">无月度数据</div>';
        return;
    }
    const allValues = Array.from(cells.values()).filter((v) => v !== null);
    const maxAbs = Math.max(...allValues.map(Math.abs), 0.0001);

    const monthHeads = Array.from({length: 12}, (_, i) => `<th>${i + 1}月</th>`).join('');
    const yearCells = years.map((year) => {
        const tds = Array.from({length: 12}, (_, i) => {
            const value = cells.get(`${year}-${i + 1}`);
            if (value === null || value === undefined) {
                return '<td class="v3-hm-cell v3-hm-empty">-</td>';
            }
            const alpha = Math.min(Math.abs(value) / maxAbs, 1) * 0.72 + 0.06;
            const bg = value >= 0 ? `rgba(220,53,69,${alpha})` : `rgba(25,135,84,${alpha})`;
            const color = alpha > 0.5 ? '#fff' : 'inherit';
            return `<td class="v3-hm-cell" style="background:${bg};color:${color}">${(value * 100).toFixed(2)}</td>`;
        }).join('');
        // 全年合计：当月复利累乘（-1 回到收益口径）
        const yearTotal = Array.from(cells.entries())
            .filter(([k]) => k.startsWith(year))
            .reduce((acc, [, v]) => acc * (1 + (v || 0)), 1) - 1;
        return `<tr><th>${year}</th>${tds}<td class="v3-heatmap-year-col">${signedPctHtml(yearTotal)}</td></tr>`;
    }).join('');

    container.innerHTML = `
        <table class="v3-heatmap">
            <thead><tr><th>年</th>${monthHeads}<th>全年</th></tr></thead>
            <tbody>${yearCells}</tbody>
        </table>`;
}

function renderMonthlyExcessChart(active) {
    const el = document.getElementById('v3-chart-monthly-excess');
    if (!el) return;
    destroyChart('monthlyExcess');
    const list = Array.isArray(active.metrics?.monthly_excess_returns) ? active.metrics.monthly_excess_returns : [];
    const labels = list.map((item) => item?.year_month ?? '');
    const values = list.map((item) => Number(item?.monthly_excess_return_diff ?? 0) * 100);
    state.charts.monthlyExcess = new Chart(el, {
        type: 'bar',
        data: {
            labels,
            datasets: [{
                label: '月超额收益%',
                data: values,
                backgroundColor: values.map((v) => (v >= 0 ? V3_COLORS.upSoft : V3_COLORS.downSoft)),
                borderColor: values.map((v) => (v >= 0 ? V3_COLORS.up : V3_COLORS.down)),
                borderWidth: 1
            }]
        },
        options: commonBarOptions('%', null)
    });
}

function renderRollingChart(active, single) {
    const el = document.getElementById('v3-chart-rolling');
    if (!el) return;
    destroyChart('rolling');
    const windows = [3, 6, 12];
    const labels = windows.map((n) => `${n}个月`);
    const datasets = [];
    if (single) {
        datasets.push({
            type: 'bar', label: '基准平均收益%', order: 2,
            data: windows.map((n) => pctOrNull(active.metrics?.[`index_rolling_return_${n}_avg_return`])),
            backgroundColor: V3_COLORS.benchSoft, borderColor: V3_COLORS.bench, borderWidth: 1
        });
        datasets.push({
            type: 'bar', label: '策略平均收益%', order: 2,
            data: windows.map((n) => pctOrNull(active.metrics?.[`start_rolling_return_${n}_avg_return`])),
            backgroundColor: V3_COLORS.stratSoft, borderColor: V3_COLORS.strat, borderWidth: 1
        });
    } else {
        // 对比模式：只画各数据集策略均值（超额均值放明细表）
        datasets.push({
            type: 'bar', label: '平均收益%', order: 2,
            data: windows.map((n) => pctOrNull(active.metrics?.[`start_rolling_return_${n}_avg_return`])),
            backgroundColor: hexToSoft(active.color), borderColor: active.color, borderWidth: 1
        });
    }
    datasets.push({
        type: 'line', label: '策略胜率%', order: 1, yAxisID: 'y1',
        data: windows.map((n) => pctOrNull(active.metrics?.[`rolling_return_${n}_win_rate`])),
        borderColor: V3_COLORS.excess, backgroundColor: 'transparent', borderWidth: 2, pointRadius: 3, tension: 0
    });
    state.charts.rolling = new Chart(el, {
        data: {labels, datasets},
        options: {
            responsive: true,
            maintainAspectRatio: false,
            interaction: {mode: 'index', intersect: false},
            plugins: {legend: {position: 'top'}},
            scales: {
                y: {title: {display: true, text: '平均收益%'}},
                y1: {position: 'right', min: 0, max: 100, grid: {drawOnChartArea: false}, title: {display: true, text: '胜率%'}},
                x: {ticks: {maxRotation: 0}}
            }
        }
    });
}

function renderScatter(active) {
    const el = document.getElementById('v3-chart-scatter');
    if (!el) return;
    destroyChart('scatter');
    const list = Array.isArray(active.metrics?.monthly_excess_returns) ? active.metrics.monthly_excess_returns : [];
    const points = list
        .map((item) => ({x: Number(item?.index_monthly_return) * 100, y: Number(item?.start_monthly_return) * 100}))
        .filter((p) => Number.isFinite(p.x) && Number.isFinite(p.y));
    if (!points.length) return;
    const bound = Math.max(...points.flatMap((p) => [Math.abs(p.x), Math.abs(p.y)])) * 1.1;

    state.charts.scatter = new Chart(el, {
        type: 'scatter',
        data: {
            datasets: [
                {
                    label: '月度收益点',
                    data: points,
                    backgroundColor: points.map((p) => (p.y >= p.x ? V3_COLORS.upSoft : V3_COLORS.downSoft)),
                    borderColor: points.map((p) => (p.y >= p.x ? V3_COLORS.up : V3_COLORS.down)),
                    pointRadius: 3.5
                },
                {
                    label: '45°线（线上=跑赢）',
                    type: 'line',
                    data: [{x: -bound, y: -bound}, {x: bound, y: bound}],
                    borderColor: V3_COLORS.gray,
                    borderDash: [6, 4],
                    borderWidth: 1.2,
                    pointRadius: 0
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {legend: {position: 'top'}, tooltip: {callbacks: {label: (ctx) => `(${ctx.parsed.x.toFixed(2)}%, ${ctx.parsed.y.toFixed(2)}%)`}}},
            scales: {
                x: {title: {display: true, text: '基准月收益%'}},
                y: {title: {display: true, text: '策略月收益%'}}
            }
        }
    });
}

// ---- 收益分布 ----

function renderDistCharts(datasets, single) {
    // 月度分布
    const first = datasets[0].metrics || {};
    const monthlyLabels = distLabels(...datasets.map((ds) => ds.metrics?.index_monthly_distribution_pct), ...datasets.map((ds) => ds.metrics?.start_monthly_distribution_pct));
    const monthlyDatasets = [];
    if (single) {
        monthlyDatasets.push({label: '基准占比%', data: monthlyLabels.map((label) => numOrNull(distValue(first.index_monthly_distribution_pct, label))), backgroundColor: V3_COLORS.benchSoft, borderColor: V3_COLORS.bench, borderWidth: 1});
        monthlyDatasets.push({label: '策略占比%', data: monthlyLabels.map((label) => numOrNull(distValue(first.start_monthly_distribution_pct, label))), backgroundColor: V3_COLORS.stratSoft, borderColor: V3_COLORS.strat, borderWidth: 1});
    } else {
        datasets.forEach((ds) => {
            monthlyDatasets.push({label: `${ds.label}·策略占比%`, data: monthlyLabels.map((label) => numOrNull(distValue(ds.metrics?.start_monthly_distribution_pct, label))), backgroundColor: hexToSoft(ds.color), borderColor: ds.color, borderWidth: 1});
        });
    }
    buildBarChart('v3-chart-dist-monthly', 'distMonthly', monthlyLabels, monthlyDatasets, '%', null);

    // 日度分布
    const dailyLabels = distLabels(...datasets.map((ds) => ds.metrics?.index_days_distribution_pct), ...datasets.map((ds) => ds.metrics?.start_days_distribution_pct));
    const dailyDatasets = [];
    if (single) {
        dailyDatasets.push({label: '基准占比%', data: dailyLabels.map((label) => numOrNull(distValue(first.index_days_distribution_pct, label))), backgroundColor: V3_COLORS.benchSoft, borderColor: V3_COLORS.bench, borderWidth: 1});
        dailyDatasets.push({label: '策略占比%', data: dailyLabels.map((label) => numOrNull(distValue(first.start_days_distribution_pct, label))), backgroundColor: V3_COLORS.stratSoft, borderColor: V3_COLORS.strat, borderWidth: 1});
    } else {
        datasets.forEach((ds) => {
            dailyDatasets.push({label: `${ds.label}·策略占比%`, data: dailyLabels.map((label) => numOrNull(distValue(ds.metrics?.start_days_distribution_pct, label))), backgroundColor: hexToSoft(ds.color), borderColor: ds.color, borderWidth: 1});
        });
    }
    buildBarChart('v3-chart-dist-daily', 'distDaily', dailyLabels, dailyDatasets, '%', null);

    // 超额分布（仅单模式）
    const excessEl = document.getElementById('v3-chart-dist-excess');
    if (excessEl && single) {
        destroyChart('distExcess');
        const labels = distLabels(first.excess_distribution_pct);
        state.charts.distExcess = new Chart(excessEl, {
            type: 'bar',
            data: {
                labels,
                datasets: [{
                    label: '超额占比%',
                    data: labels.map((label) => numOrNull(distValue(first.excess_distribution_pct, label))),
                    backgroundColor: V3_COLORS.excessSoft,
                    borderColor: V3_COLORS.excess,
                    borderWidth: 1
                }]
            },
            options: commonBarOptions('%', null)
        });
    }

    renderDailyHistogram(activeDataset() || datasets[0]);
    renderShapeCards(datasets, single);
}

// ---- 日收益分布直方图（对齐 Word 报告 _draw_daily_distribution 算法） ----

// 从净值序列还原日收益率（%）：首点 nav-1，其后相邻比值-1
function dailyReturnsFromNav(navValues) {
    const out = [];
    for (let i = 0; i < navValues.length; i += 1) {
        const current = navValues[i];
        if (!isFiniteNum(current)) {
            out.push(null);
            continue;
        }
        const previous = i > 0 ? navValues[i - 1] : null;
        if (isFiniteNum(previous) && Number(previous) > 0) {
            out.push((Number(current) / Number(previous) - 1) * 100);
        } else {
            out.push((Number(current) - 1) * 100);
        }
    }
    return out;
}

// 对称直方图半轴：0.5%/99.5% 分位（非极值）×1.05，最小 1%（与报告同口径）
function symmetricHistogramLimit(valuesPct) {
    const ordered = valuesPct.filter(isFiniteNum).map(Number).sort((a, b) => a - b);
    if (!ordered.length) return null;
    const low = ordered[Math.floor((ordered.length - 1) * 0.005)];
    const high = ordered[Math.min(ordered.length - 1, Math.ceil((ordered.length - 1) * 0.995))];
    return Math.max(Math.abs(low), Math.abs(high), 1) * 1.05;
}

// 分箱数：Freedman–Diaconis 与 span/60 取大，向 1-2-2.5-5 网格取整，12~60（与报告同口径）
function histogramBinCount(valuesPct, limitPct) {
    const ordered = valuesPct.filter(isFiniteNum).map(Number).sort((a, b) => a - b);
    const span = limitPct * 2;
    let width = span / 60;
    if (ordered.length > 1) {
        const iqr = ordered[Math.floor((ordered.length - 1) * 0.75)] - ordered[Math.floor((ordered.length - 1) * 0.25)];
        width = Math.max(2 * iqr / Math.cbrt(ordered.length), span / 60);
    }
    const magnitude = Math.pow(10, Math.floor(Math.log10(width)));
    let niceWidth = 10 * magnitude;
    for (const mantissa of [1, 2, 2.5, 5, 10]) {
        if (mantissa * magnitude >= width) {
            niceWidth = mantissa * magnitude;
            break;
        }
    }
    return Math.max(12, Math.ceil(span / niceWidth));
}

function renderDailyHistogram(dataset) {
    const el = document.getElementById('v3-chart-hist-daily');
    if (!el) return;
    destroyChart('histDaily');
    const limitEl = document.getElementById('v3-hist-limit');
    if (!dataset?.series?.index_nav?.length) {
        if (limitEl) limitEl.textContent = '-';
        return;
    }

    const indexReturns = dailyReturnsFromNav(dataset.series.index_nav);
    const startReturns = dailyReturnsFromNav(dataset.series.start_nav);
    const all = [...indexReturns, ...startReturns].filter(isFiniteNum);
    const limitPct = symmetricHistogramLimit(all);
    if (limitPct === null) return;
    if (limitEl) limitEl.textContent = limitPct.toFixed(1);

    const binCount = histogramBinCount(all, limitPct);
    const binWidth = (limitPct * 2) / binCount;
    const clip = (value) => Math.min(Math.max(value, -limitPct), limitPct);
    const countsFor = (values) => {
        const counts = new Array(binCount).fill(0);
        values.filter(isFiniteNum).forEach((value) => {
            let bin = Math.floor((clip(Number(value)) + limitPct) / binWidth);
            if (bin >= binCount) bin = binCount - 1;
            counts[bin] += 1;
        });
        return counts;
    };

    // 分箱中值做 x 轴标签；0 恒位于正中分箱边界（对称分箱）
    const labels = Array.from({length: binCount}, (_, i) => {
        const center = -limitPct + (i + 0.5) * binWidth;
        return String(Number(center.toFixed(2)));
    });

    state.charts.histDaily = new Chart(el, {
        type: 'bar',
        data: {
            labels,
            datasets: [
                {label: '基准日收益频数', data: countsFor(indexReturns), backgroundColor: V3_COLORS.benchSoft, borderColor: V3_COLORS.bench, borderWidth: 0.6},
                {label: '策略日收益频数', data: countsFor(startReturns), backgroundColor: V3_COLORS.stratSoft, borderColor: V3_COLORS.strat, borderWidth: 0.6}
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            interaction: {mode: 'index', intersect: false},
            plugins: {
                legend: {position: 'top'},
                v3ZeroLine: {index: binCount / 2 - 0.5},
                tooltip: {callbacks: {title: (items) => `${items[0].label}% 分箱`}}
            },
            scales: {
                y: v3YScale('频数', {beginAtZero: true}),
                x: v3XScale({maxRotation: 0, ticks: {maxTicksLimit: 7}})
            }
        }
    });
}

function renderShapeCards(datasets, single) {
    const container = document.getElementById('v3-dist-shape-cards');
    if (!container) return;
    const rows = [
        ['月收益率偏度', (r) => r.index_monthly_return_skewness, (r) => r.start_monthly_return_skewness, 'num4'],
        ['月收益率峰度', (r) => r.index_monthly_return_kurtosis, (r) => r.start_monthly_return_kurtosis, 'num4'],
        ['月收益率波动率', (r) => r.index_monthly_return_volatility, (r) => r.start_monthly_return_volatility, 'num6'],
        ['日收益率标准差', (r) => r.index_daily_return_std, (r) => r.start_daily_return_std, 'num6'],
        ['日收益率偏度', (r) => r.index_mean_daily_skewness, (r) => r.start_mean_daily_skewness, 'num4'],
        ['日收益率峰度', (r) => r.index_mean_daily_kurtosis, (r) => r.start_mean_daily_kurtosis, 'num4']
    ];
    const head = single
        ? '<tr><th>指标</th><th class="num">基准</th><th class="num">策略</th></tr>'
        : `<tr><th>指标</th>${datasets.map((ds) => `<th class="num">${escapeHtml(ds.label)}</th>`).join('')}</tr>`;
    const body = rows.map(([label, idxFn, stFn, type]) => {
        const cells = single
            ? `<td class="num">${fmtNum(idxFn(datasets[0].metrics || {}), type === 'num6' ? 6 : 4)}</td>
               <td class="num">${fmtNum(stFn(datasets[0].metrics || {}), type === 'num6' ? 6 : 4)}</td>`
            : datasets.map((ds) => `<td class="num">${fmtNum(stFn(ds.metrics || {}), type === 'num6' ? 6 : 4)}</td>`).join('');
        return `<tr><td>${label}</td>${cells}</tr>`;
    }).join('');
    container.innerHTML = `
        <div class="table-responsive">
            <table class="table table-sm table-striped mb-0 v3-detail-table">
                <thead>${head}</thead><tbody>${body}</tbody>
            </table>
        </div>`;
}

// ---- 风险与极端行情 ----

function renderExtremeSection(active) {
    const r = active.metrics || {};

    // 阶段表现：下跌 / 上涨 月均年化对比 + 胜率标注
    const extremeEl = document.getElementById('v3-chart-extreme');
    if (extremeEl) {
        destroyChart('extreme');
        const labels = ['下跌阶段', '上涨阶段'];
        state.charts.extreme = attachValueLabelFormat(new Chart(extremeEl, {
            type: 'bar',
            data: {
                labels,
                datasets: [
                    {label: '基准月均年化%', data: [pctOrNull(r.index_downfall_avg_return), pctOrNull(r.index_upward_avg_return)], backgroundColor: V3_COLORS.benchSoft, borderColor: V3_COLORS.bench, borderWidth: 1},
                    {label: '策略月均年化%', data: [pctOrNull(r.start_downfall_avg_return), pctOrNull(r.start_upward_avg_return)], backgroundColor: V3_COLORS.stratSoft, borderColor: V3_COLORS.strat, borderWidth: 1}
                ]
            },
            options: commonBarOptions('%', (v) => `${Number(v).toFixed(1)}`)
        }), (v) => `${Number(v).toFixed(1)}`);
    }

    // 极端单日：超阈值天数
    const dailyEl = document.getElementById('v3-chart-daily-extreme');
    if (dailyEl) {
        destroyChart('dailyExtreme');
        const labels = ['涨幅超阈值天数', '跌幅超阈值天数'];
        state.charts.dailyExtreme = attachValueLabelFormat(new Chart(dailyEl, {
            type: 'bar',
            data: {
                labels,
                datasets: [
                    {label: '基准', data: [r.index_daily_gain_days ?? null, r.index_daily_loss_days ?? null], backgroundColor: V3_COLORS.upSoft, borderColor: V3_COLORS.up, borderWidth: 1},
                    {label: '策略', data: [r.start_daily_gain_days ?? null, r.start_daily_loss_days ?? null], backgroundColor: V3_COLORS.stratSoft, borderColor: V3_COLORS.strat, borderWidth: 1}
                ]
            },
            options: commonBarOptions('天', (v) => String(Math.round(Number(v))))
        }), (v) => String(Math.round(Number(v))));
    }

    // 修复天数：整体值为标量、分年度值为字典（year -> 天数），合并为"各年 + 全部"一轴
    const repairEl = document.getElementById('v3-chart-repair-days');
    if (repairEl) {
        destroyChart('repairDays');
        const yearKeys = new Set([
            ...Object.keys(r.year_index_yearly_max_repair_days || {}),
            ...Object.keys(r.year_start_yearly_max_repair_days || {}),
        ].map(String));
        const labels = [...yearKeys].sort();
        labels.push('全部');
        const seriesDefs = [
            {
                label: '基准修复天数',
                yearly: r.year_index_yearly_max_repair_days,
                total: r.index_maximum_number_of_backtest_repair_days,
                color: V3_COLORS.bench, soft: V3_COLORS.benchSoft
            },
            {
                label: '策略修复天数',
                yearly: r.year_start_yearly_max_repair_days,
                total: r.start_maximum_number_of_backtest_repair_days,
                color: V3_COLORS.strat, soft: V3_COLORS.stratSoft
            },
            {
                label: '超额修复天数',
                yearly: null,
                total: r.excess_maximum_number_of_backtest_repair_days,
                color: V3_COLORS.excess, soft: V3_COLORS.excessSoft
            }
        ];
        state.charts.repairDays = attachValueLabelFormat(new Chart(repairEl, {
            type: 'bar',
            data: {
                labels,
                datasets: seriesDefs.map((def) => ({
                    label: def.label,
                    data: labels.map((label, index) => {
                        if (index === labels.length - 1) {
                            return isFiniteNum(def.total) ? Math.round(Number(def.total)) : null;
                        }
                        const value = def.yearly?.[label] ?? def.yearly?.[Number(label)];
                        return isFiniteNum(value) ? Math.round(Number(value)) : null;
                    }),
                    backgroundColor: def.soft,
                    borderColor: def.color,
                    borderWidth: 1
                }))
            },
            options: commonBarOptions('天', (v) => String(Math.round(Number(v))))
        }), (v) => String(Math.round(Number(v))));
    }

    renderCapitalCards(active);
}

function renderCapitalCards(active) {
    const container = document.getElementById('v3-capital-cards');
    if (!container) return;
    const r = active.metrics || {};
    const rows = [
        ['初始净值', fmtNum(r.index_net_value_left, 4), fmtNum(r.start_net_value_left, 4), null],
        ['期末净值', fmtNum(r.index_net_value_right, 4), fmtNum(r.start_net_value_right, 4), null],
        ['最大连涨月份', fmtInt(r.index_consecutive?.max_gain_months), fmtInt(r.start_consecutive?.max_gain_months), null],
        ['最大连跌月份', fmtInt(r.index_consecutive?.max_loss_months), fmtInt(r.start_consecutive?.max_loss_months), null],
        ['创新高次数', fmtInt(r.index_new_high_count), fmtInt(r.start_new_high_count), null],
        ['创新高频率', fmtPct(r.index_new_high_frequency), fmtPct(r.start_new_high_frequency), null],
        ['创新高平均间隔（月）', fmtNum(r.index_new_high_avg_interval_months, 2), fmtNum(r.start_new_high_avg_interval_months, 2), null]
    ];
    container.innerHTML = `
        <div class="table-responsive">
            <table class="table table-sm table-striped mb-0 v3-detail-table">
                <thead><tr><th>指标</th><th class="num">基准</th><th class="num">策略</th></tr></thead>
                <tbody>${rows.map(([label, idx, st]) => `<tr><td>${label}</td><td class="num">${idx}</td><td class="num">${st}</td></tr>`).join('')}</tbody>
            </table>
        </div>`;
}

// ---- 数据明细（八章） ----

function renderDetails(active) {
    const r = active.metrics || {};
    setPreJson('pre-v3-raw-json', r);
    renderCoreReturnsTable(r);
    renderAnnualReturnTable(r);
    renderRollingTable(r);
    renderExcessReturnTables(r);
    renderRiskTables(r);
    renderRiskAdjustedTable(r);
    renderMonthlyTables(r);
    renderDailyTables(r);
    renderExcessTables(r);
    renderExtremeTables(r);
    renderCapitalTable(r);
    renderAllMetricsTable(r);
    renderSheetResultTable(r);
}

function twoColRows(rows) {
    return rows.map(([label, idx, st, better]) => {
        let bestCls = '';
        if (better && Number.isFinite(Number(idx)) && Number.isFinite(Number(st))) {
            const i = Number(idx);
            const s = Number(st);
            bestCls = (better === 'higher' ? s > i : s < i) ? 'v3-best' : '';
        }
        return `<tr><td>${label}</td><td class="num">${idx}</td><td class="num ${bestCls}">${st}</td></tr>`;
    }).join('');
}

function renderCoreReturnsTable(r) {
    const tbody = document.getElementById('tbl-v3-core-returns');
    if (!tbody) return;
    const rows = [
        ['累计回报率', fmtPct(r.index_cumulative_return), fmtPct(r.start_cumulative_return), signedPctHtml(r.excess_cumulative_return)],
        ['年化收益率', fmtPct(allEntry(r.index_annualized_rates)?.annualized_return), fmtPct(allEntry(r.start_annualized_rates)?.annualized_return), signedPctHtml(allEntry(r.excess_returns)?.annualized_return_diff)],
        ['年化波动率', fmtPct(periodEntry(r.index_sharpe_ratios)?.annual_std_dev), fmtPct(periodEntry(r.start_sharpe_ratios)?.annual_std_dev), '-']
    ];
    tbody.innerHTML = rows.map(([label, idx, st, ex]) => `<tr><td>${label}</td><td class="num">${idx}</td><td class="num">${st}</td><td class="num">${ex}</td></tr>`).join('');
}

function renderAnnualReturnTable(r) {
    const tbody = document.getElementById('tbl-v3-annual-returns');
    if (!tbody) return;
    const idx = yearMap(r.index_returns_rate, 'annual_return');
    const st = yearMap(r.start_returns_rate, 'annual_return');
    const years = Array.from(new Set([...idx.keys(), ...st.keys()])).filter((y) => y !== 'all').sort();
    tbody.innerHTML = years.map((y) => {
        const a1 = idx.get(y);
        const a2 = st.get(y);
        const diff = Number.isFinite(Number(a1)) && Number.isFinite(Number(a2)) ? Number(a2) - Number(a1) : null;
        return `<tr><td>${y}</td><td class="num">${signedPctHtml(a1)}</td><td class="num">${signedPctHtml(a2)}</td><td class="num">${signedPctHtml(diff)}</td></tr>`;
    }).join('');
}

function renderRollingTable(r) {
    const tbody = document.getElementById('tbl-v3-rolling');
    if (!tbody) return;
    tbody.innerHTML = [3, 6, 12].map((n) => {
        const reason = r[`rolling_return_${n}_reason`];
        if (reason) {
            return `<tr><td>${n}个月</td><td colspan="3" class="text-body-secondary">${escapeHtml(String(reason))}</td></tr>`;
        }
        return `<tr>
            <td>${n}个月</td>
            <td class="num">${signedPctHtml(r[`index_rolling_return_${n}_avg_return`])}</td>
            <td class="num">${signedPctHtml(r[`start_rolling_return_${n}_avg_return`])}</td>
            <td class="num">${fmtPct(r[`rolling_return_${n}_win_rate`])}</td>
        </tr>`;
    }).join('');
}

function renderExcessReturnTables(r) {
    const annualTbody = document.getElementById('tbl-v3-excess-returns');
    if (annualTbody) {
        const list = Array.isArray(r.excess_returns) ? r.excess_returns : [];
        annualTbody.innerHTML = list.map((item) => `<tr>
            <td>${item?.year ?? '-'}</td>
            <td class="num">${signedPctHtml(item?.index_annualized_return)}</td>
            <td class="num">${signedPctHtml(item?.start_annualized_return)}</td>
            <td class="num">${signedPctHtml(item?.annualized_return_diff)}</td>
            <td>${item?.start_end_date ?? '-'}</td>
        </tr>`).join('');
    }
    const monthlyTbody = document.getElementById('tbl-v3-monthly-excess');
    if (monthlyTbody) {
        const list = Array.isArray(r.monthly_excess_returns) ? r.monthly_excess_returns : [];
        monthlyTbody.innerHTML = list.map((item) => `<tr>
            <td>${item?.year_month ?? '-'}</td>
            <td class="num">${signedPctHtml(item?.index_monthly_return)}</td>
            <td class="num">${signedPctHtml(item?.start_monthly_return)}</td>
            <td class="num">${signedPctHtml(item?.monthly_excess_return_diff)}</td>
        </tr>`).join('');
    }
}

function renderRiskTables(r) {
    const core = document.getElementById('tbl-v3-risk-core');
    if (core) {
        const idxTotal = r.index_maximum_drawdown?.total_maximum_drawdown;
        const stTotal = r.start_maximum_drawdown?.total_maximum_drawdown;
        const rows = [
            ['最大回撤（MDD）', fmtPct(idxTotal?.drawdown), fmtPct(stTotal?.drawdown), 'lower'],
            ['最大回撤日期', idxTotal?.date ?? '-', stTotal?.date ?? '-', null],
            ['回撤发生次数', fmtInt(r.index_drawdown_count), fmtInt(r.start_drawdown_count), 'lower'],
            ['最大回测修复天数', fmtInt(r.index_maximum_number_of_backtest_repair_days), fmtInt(r.start_maximum_number_of_backtest_repair_days), 'lower'],
            ['单日大跌次数', fmtInt(r.index_dd_count), fmtInt(r.start_dd_count), 'lower'],
            ['单日大跌频率', fmtPct(r.index_dd_freq), fmtPct(r.start_dd_freq), 'lower']
        ];
        core.innerHTML = twoColRows(rows);
    }
    const annual = document.getElementById('tbl-v3-annual-drawdown');
    if (annual) {
        const idx = yearMap(r.index_maximum_drawdown?.year_maximum_drawdown, 'drawdown');
        const st = yearMap(r.start_maximum_drawdown?.year_maximum_drawdown, 'drawdown');
        const idxDates = yearMap(r.index_maximum_drawdown?.year_maximum_drawdown, 'date');
        const stDates = yearMap(r.start_maximum_drawdown?.year_maximum_drawdown, 'date');
        const years = Array.from(new Set([...idx.keys(), ...st.keys()])).filter((y) => y !== 'all').sort();
        annual.innerHTML = years.map((y) => `<tr>
            <td>${y}</td>
            <td class="num">-${fmtPct(idx.get(y))}</td>
            <td class="num">-${fmtPct(st.get(y))}</td>
            <td>${idxDates.get(y) ?? '-'} / ${stDates.get(y) ?? '-'}</td>
        </tr>`).join('');
    }
}

function renderRiskAdjustedTable(r) {
    const tbody = document.getElementById('tbl-v3-risk-adjusted');
    if (!tbody) return;
    const rows = [
        ['夏普比率', fmtNum(periodEntry(r.index_sharpe_ratios)?.sharpe_ratio), fmtNum(periodEntry(r.start_sharpe_ratios)?.sharpe_ratio), 'higher'],
        ['索提诺比率（月频）', fmtNum(allEntry(r.index_sortino_ratio)?.sortino_ratio), fmtNum(allEntry(r.start_sortino_ratio)?.sortino_ratio), 'higher'],
        ['索提诺比率（周频）', fmtNum(allEntry(r.index_weekly_sortino_ratio)?.sortino_ratio), fmtNum(allEntry(r.start_weekly_sortino_ratio)?.sortino_ratio), 'higher'],
        ['卡玛比率', fmtNum(allEntry(r.index_kama_ratio)?.kama_ratio), fmtNum(allEntry(r.start_kama_ratio)?.kama_ratio), 'higher'],
        ['超额夏普比率', '-', fmtNum(r.excess_sharpe), null],
        ['超额索提诺比率', '-', fmtNum(r.excess_sortino), null]
    ];
    tbody.innerHTML = twoColRows(rows);
}

function renderMonthlyTables(r) {
    const overview = document.getElementById('tbl-v3-monthly-overview');
    if (overview) {
        const rows = [
            ['总月数', fmtInt(r.total_months), fmtInt(r.total_months), null],
            ['盈利月数', fmtInt(r.index_profit_months), fmtInt(r.start_profit_months), 'higher'],
            ['亏损月数', fmtInt(r.index_loss_months), fmtInt(r.start_loss_months), 'lower'],
            ['月盈利百分比', fmtPct(r.index_profit_percentage), fmtPct(r.start_profit_percentage), 'higher'],
            ['盈利年百分比', fmtPct(r.index_profit_annual), fmtPct(r.start_profit_annual), 'higher'],
            ['最大单月收益', fmtPct(r.index_max_monthly_return), fmtPct(r.start_max_monthly_return), 'higher'],
            ['最大单月亏损', fmtPct(r.index_max_monthly_loss), fmtPct(r.start_max_monthly_loss), 'higher'],
            ['月收益率波动率', fmtNum(r.index_monthly_return_volatility, 6), fmtNum(r.start_monthly_return_volatility, 6), 'lower'],
            ['月收益率偏度', fmtNum(r.index_monthly_return_skewness), fmtNum(r.start_monthly_return_skewness), null],
            ['月收益率峰度', fmtNum(r.index_monthly_return_kurtosis), fmtNum(r.start_monthly_return_kurtosis), null]
        ];
        overview.innerHTML = twoColRows(rows);
    }
    const dist = document.getElementById('tbl-v3-monthly-dist');
    if (dist) {
        dist.innerHTML = distLabels(r.index_monthly_distribution, r.start_monthly_distribution).map((label) => `<tr>
            <td>${escapeHtml(label)}</td>
            <td class="num">${fmtInt(distValue(r.index_monthly_distribution, label))}</td>
            <td class="num">${fmtPctRaw(distValue(r.index_monthly_distribution_pct, label))}</td>
            <td class="num">${fmtInt(distValue(r.start_monthly_distribution, label))}</td>
            <td class="num">${fmtPctRaw(distValue(r.start_monthly_distribution_pct, label))}</td>
        </tr>`).join('');
    }
}

function renderDailyTables(r) {
    const overview = document.getElementById('tbl-v3-daily-overview');
    if (overview) {
        const rows = [
            ['总交易日', fmtInt(r.total_trading_days), fmtInt(r.total_trading_days), null],
            ['盈利天数', fmtInt(r.index_profit_days), fmtInt(r.start_profit_days), 'higher'],
            ['亏损天数', fmtInt(r.index_loss_days), fmtInt(r.start_loss_days), 'lower'],
            ['日盈利百分比', fmtPct(r.index_days_profit_percentage), fmtPct(r.start_days_profit_percentage), 'higher'],
            ['日均收益率', fmtPct(r.index_mean_daily_return), fmtPct(r.start_mean_daily_return), 'higher'],
            ['日收益率标准差', fmtNum(r.index_daily_return_std, 6), fmtNum(r.start_daily_return_std, 6), 'lower'],
            ['日收益率偏度', fmtNum(r.index_mean_daily_skewness), fmtNum(r.start_mean_daily_skewness), null],
            ['日收益率峰度', fmtNum(r.index_mean_daily_kurtosis), fmtNum(r.start_mean_daily_kurtosis), null],
            ['平均盈利日收益', fmtPct(r.index_avg_profit_day_return), fmtPct(r.start_avg_profit_day_return), 'higher'],
            ['平均亏损日收益', fmtPct(r.index_avg_loss_day_return), fmtPct(r.start_avg_loss_day_return), 'higher'],
            ['盈亏比（平均盈利/平均亏损）', fmtNum(r.index_profit_loss_ratio), fmtNum(r.start_profit_loss_ratio), 'higher'],
            ['单笔最大盈利/最大亏损', fmtNum(r.index_max_profit_loss_ratio), fmtNum(r.start_max_profit_loss_ratio), 'higher'],
            ['最大单日收益', fmtPct(r.index_max_profit_day), fmtPct(r.start_max_profit_day), 'higher'],
            ['最大单日亏损', fmtPct(r.index_max_loss_day), fmtPct(r.start_max_loss_day), 'higher']
        ];
        overview.innerHTML = twoColRows(rows);
    }
    const dist = document.getElementById('tbl-v3-daily-dist');
    if (dist) {
        dist.innerHTML = distLabels(r.index_days_distribution, r.start_days_distribution).map((label) => `<tr>
            <td>${escapeHtml(label)}</td>
            <td class="num">${fmtInt(distValue(r.index_days_distribution, label))}</td>
            <td class="num">${fmtPctRaw(distValue(r.index_days_distribution_pct, label))}</td>
            <td class="num">${fmtInt(distValue(r.start_days_distribution, label))}</td>
            <td class="num">${fmtPctRaw(distValue(r.start_days_distribution_pct, label))}</td>
        </tr>`).join('');
    }
}

function renderExcessTables(r) {
    const stats = document.getElementById('tbl-v3-excess-stats');
    if (stats) {
        const rows = [
            ['累计超额收益', fmtPct(r.excess_cumulative_return)],
            ['超额净值（期末）', fmtNum(r.excess_nav, 4)],
            ['年化超额收益', fmtPct(r.annualized_excess_returns)],
            ['月超额收益均值', fmtPct(r.average_monthly_excess_return)],
            ['月超额收益标准差', fmtNum(r.monthly_excess_return_standard_deviation, 6)],
            ['月超额胜率（>0）', fmtPct(r.monthly_excess_win_rate)],
            ['最大单月超额', fmtPct(r.max_monthly_excess)],
            ['月超额波动率', fmtNum(r.monthly_excess_volatility, 4)],
            ['超额夏普比率', fmtNum(r.excess_sharpe)],
            ['超额索提诺比率', fmtNum(r.excess_sortino)],
            ['超额回撤胜率', fmtPct(r.excess_drawdown_winning_rate)],
            ['跑赢年份占比', fmtPct(r.outperform_year)],
            ['超额最大回测修复天数', fmtInt(r.excess_maximum_number_of_backtest_repair_days)]
        ];
        stats.innerHTML = rows.map(([label, value]) => `<tr><td>${label}</td><td class="num">${value}</td></tr>`).join('');
    }
    const dist = document.getElementById('tbl-v3-excess-dist');
    if (dist) {
        dist.innerHTML = distLabels(r.excess_distribution).map((label) => `<tr>
            <td>${escapeHtml(label)}</td>
            <td class="num">${fmtInt(distValue(r.excess_distribution, label))}</td>
            <td class="num">${fmtPctRaw(distValue(r.excess_distribution_pct, label))}</td>
        </tr>`).join('');
    }
    const rolling = document.getElementById('tbl-v3-excess-rolling');
    if (rolling) {
        rolling.innerHTML = [3, 6, 12].map((n) => {
            const reason = r[`excess_rolling_return_${n}_reason`];
            if (reason) {
                return `<tr><td>${n}个月</td><td colspan="2" class="text-body-secondary">${escapeHtml(String(reason))}</td></tr>`;
            }
            return `<tr>
                <td>${n}个月</td>
                <td class="num">${signedPctHtml(r[`excess_rolling_return_${n}_avg_return`])}</td>
                <td class="num">${fmtPct(r[`excess_rolling_return_${n}_win_rate`])}</td>
            </tr>`;
        }).join('');
    }
}

function renderExtremeTables(r) {
    const downfall = document.getElementById('tbl-v3-downfall');
    if (downfall) {
        downfall.innerHTML = twoColRows([
            ['阶段月数', fmtInt(r.index_downfall_months_len), fmtInt(r.start_downfall_months_len), null],
            ['月均年化', signedPctHtml(r.index_downfall_avg_return), signedPctHtml(r.start_downfall_avg_return), 'higher'],
            ['策略胜率', '-', fmtPct(r.downfall_win_rate), null],
            ['跑赢次数', '-', fmtInt(r.downfall_outperform_count), null],
            ['超额均值', '-', signedPctHtml(r.downfall_excess_avg_return), null]
        ]);
    }
    const upward = document.getElementById('tbl-v3-upward');
    if (upward) {
        upward.innerHTML = twoColRows([
            ['阶段月数', fmtInt(r.index_upward_months_len), fmtInt(r.start_upward_months_len), null],
            ['月均年化', signedPctHtml(r.index_upward_avg_return), signedPctHtml(r.start_upward_avg_return), 'higher'],
            ['策略胜率', '-', fmtPct(r.upward_win_rate), null],
            ['跑赢次数', '-', fmtInt(r.upward_outperform_count), null],
            ['超额均值', '-', signedPctHtml(r.upward_excess_avg_return), null]
        ]);
    }
    const daily = document.getElementById('tbl-v3-daily-extreme');
    if (daily) {
        daily.innerHTML = twoColRows([
            ['最大单日涨幅', fmtPct(r.index_max_daily_gain), fmtPct(r.start_max_daily_gain), 'higher'],
            ['最大单日跌幅', fmtPct(r.index_max_daily_loss), fmtPct(r.start_max_daily_loss), 'higher'],
            ['涨幅超阈值天数', fmtInt(r.index_daily_gain_days), fmtInt(r.start_daily_gain_days), null],
            ['跌幅超阈值天数', fmtInt(r.index_daily_loss_days), fmtInt(r.start_daily_loss_days), null],
            ['极端涨跌比', fmtNum(r.index_daily_gain_loss_ratio), fmtNum(r.start_daily_gain_loss_ratio), 'higher'],
            ['单日大跌次数', fmtInt(r.index_dd_count), fmtInt(r.start_dd_count), 'lower'],
            ['单日大跌频率', fmtPct(r.index_dd_freq), fmtPct(r.start_dd_freq), 'lower']
        ]);
    }
}

function renderCapitalTable(r) {
    const tbody = document.getElementById('tbl-v3-capital');
    if (!tbody) return;
    tbody.innerHTML = twoColRows([
        ['初始净值', fmtNum(r.index_net_value_left, 4), fmtNum(r.start_net_value_left, 4), null],
        ['期末净值', fmtNum(r.index_net_value_right, 4), fmtNum(r.start_net_value_right, 4), 'higher'],
        ['最大连涨月份', fmtInt(r.index_consecutive?.max_gain_months), fmtInt(r.start_consecutive?.max_gain_months), 'higher'],
        ['最大连跌月份', fmtInt(r.index_consecutive?.max_loss_months), fmtInt(r.start_consecutive?.max_loss_months), 'lower'],
        ['创新高次数', fmtInt(r.index_new_high_count), fmtInt(r.start_new_high_count), 'higher'],
        ['创新高频率', fmtPct(r.index_new_high_frequency), fmtPct(r.start_new_high_frequency), 'higher'],
        ['创新高平均间隔（月）', fmtNum(r.index_new_high_avg_interval_months), fmtNum(r.start_new_high_avg_interval_months), 'lower']
    ]);
}

function renderAllMetricsTable(r) {
    const tbody = document.getElementById('tbl-v3-all-metrics');
    if (!tbody) return;
    const rows = [];
    let lastGroup = null;
    window.MetricNames.orderedEntries().forEach(([key, zh, group, fmtType]) => {
        if (!(key in r)) return;
        if (group !== lastGroup) {
            rows.push(`<tr class="v3-metrics-group-row"><td colspan="3">${escapeHtml(window.MetricNames.groupLabel(group))}</td></tr>`);
            lastGroup = group;
        }
        const raw = r[key];
        let value;
        if (fmtType === 'pct') {
            value = fmtPct(raw);
        } else if (fmtType === 'int') {
            value = fmtInt(raw);
        } else if (fmtType === 'num4' || fmtType === 'num6') {
            value = fmtNum(raw, fmtType === 'num6' ? 6 : 4);
        } else if (fmtType === 'consecutive') {
            value = `连涨 ${fmtInt(raw?.max_gain_months)} 月 / 连跌 ${fmtInt(raw?.max_loss_months)} 月`;
        } else if (fmtType === 'analysis_mode') {
            value = raw === 'dual' ? '双列（基准+策略）' : '单列';
        } else if (raw !== null && typeof raw === 'object') {
            value = `<code>${escapeHtml(JSON.stringify(raw).slice(0, 120))}</code>`;
        } else {
            value = escapeHtml(String(raw ?? '-'));
        }
        rows.push(`<tr><td>${escapeHtml(zh)}</td><td><code>${escapeHtml(key)}</code></td><td class="num">${value}</td></tr>`);
    });
    tbody.innerHTML = rows.join('');
}

function renderSheetResultTable(r) {
    const tabBtn = document.getElementById('tab-sheet-btn');
    const tbody = document.getElementById('tbl-v3-sheet-result');
    const hasSheetResult = r.sheet_result && typeof r.sheet_result === 'object' && !Array.isArray(r.sheet_result) && Object.keys(r.sheet_result).length > 0;
    if (tabBtn) tabBtn.classList.toggle('d-none', !hasSheetResult);
    if (!tbody) return;
    if (!hasSheetResult) {
        tbody.innerHTML = '<tr><td colspan="2" class="text-center text-body-secondary">当前数据集没有 Sheet 结果区（仅 Google Sheet 来源分析时存在）</td></tr>';
        return;
    }
    tbody.innerHTML = Object.keys(r.sheet_result).sort().map((key) => `<tr><td><code>${escapeHtml(key)}</code></td><td>${escapeHtml(String(r.sheet_result[key] ?? '-'))}</td></tr>`).join('');
}

function setPreJson(elId, obj) {
    const el = document.getElementById(elId);
    if (!el) return;
    try {
        el.textContent = JSON.stringify(obj, null, 2);
    } catch (e) {
        el.textContent = String(obj);
    }
}

// ---- 加载与提示 ----

function showLoading() {
    const overlay = document.getElementById('loading-overlay');
    if (overlay) overlay.classList.remove('d-none');

    const urlInput = document.getElementById('gs-url');
    const sheetSelect = document.getElementById('gs-sheet-name');
    const btnFetch = document.getElementById('btn-fetch-sheets');
    if (urlInput) urlInput.disabled = true;
    if (sheetSelect) sheetSelect.disabled = true;
    if (btnFetch) btnFetch.disabled = true;
    document.getElementById('btn-analyze-v3').disabled = true;

    const meta = document.getElementById('gs-meta');
    if (meta && meta.textContent) {
        meta.dataset.prev = meta.innerHTML;
        meta.innerHTML = `${meta.innerHTML} <span class="text-body-secondary">| 请求中...</span>`;
    }
}

function hideLoading() {
    const overlay = document.getElementById('loading-overlay');
    if (overlay) overlay.classList.add('d-none');

    const urlInput = document.getElementById('gs-url');
    const sheetSelect = document.getElementById('gs-sheet-name');
    const btnFetch = document.getElementById('btn-fetch-sheets');
    if (urlInput) urlInput.disabled = false;
    if (btnFetch) btnFetch.disabled = false;
    if (sheetSelect) sheetSelect.disabled = !(state.worksheets && state.worksheets.length > 0);
    updateAnalyzeButton();

    const meta = document.getElementById('gs-meta');
    if (meta && meta.dataset.prev) {
        meta.innerHTML = meta.dataset.prev;
        delete meta.dataset.prev;
    }
}

function showAlert(message, type = 'info') {
    const alert = document.createElement('div');
    alert.className = `alert alert-${type} alert-dismissible fade show`;
    alert.role = 'alert';
    alert.innerHTML = `${message}<button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>`;
    const container = document.createElement('div');
    container.className = 'position-fixed top-0 end-0 p-3';
    container.style.zIndex = '9999';
    container.appendChild(alert);
    document.body.appendChild(container);
    setTimeout(() => {
        try {
            const bsAlert = new bootstrap.Alert(alert);
            bsAlert.close();
        } catch (e) {
            alert.remove();
        }
        setTimeout(() => container.remove(), 150);
    }, 2500);
}

// ---- 来源适配：Google Sheet ----

function normalizeApiResponse(payload) {
    const isStandard = payload && typeof payload === 'object'
        && Object.prototype.hasOwnProperty.call(payload, 'status')
        && Object.prototype.hasOwnProperty.call(payload, 'data');
    const body = isStandard ? payload : (payload && payload.body ? payload.body : payload);
    const ok = isStandard ? payload.status === 'success' : Boolean(payload && payload.ok);
    return {
        ok,
        message: isStandard ? payload.message : (payload && payload.message) || '',
        data: isStandard ? payload.data : (payload && payload.data) || body
    };
}

function getWorksheetsPayload(api) {
    if (api.body?.worksheets !== undefined || api.body?.title !== undefined) {
        return api.body;
    }
    if (api.data && typeof api.data === 'object') {
        return api.data;
    }
    return {worksheets: Array.isArray(api.data) ? api.data : []};
}

function getAnalyzePayload(api) {
    return api.data || {};
}

function extractSheetId(url) {
    if (!url) return '';
    const m = url.match(/\/spreadsheets\/d\/([a-zA-Z0-9-_]+)/);
    if (m && m[1]) return m[1];
    return '';
}

function updateMeta() {
    const url = document.getElementById('gs-url').value.trim();
    const spreadsheetId = extractSheetId(url);
    const changed = spreadsheetId !== state.spreadsheetId;
    state.spreadsheetId = spreadsheetId;
    const meta = document.getElementById('gs-meta');
    if (!url) {
        meta.textContent = '';
        return changed;
    }
    if (!spreadsheetId) {
        meta.innerHTML = '<span class="text-danger">无法解析 spreadsheet_id</span>';
        return changed;
    }
    meta.innerHTML = `<span class="text-body-secondary">spreadsheet_id: </span><span class="fw-semibold">${spreadsheetId}</span>`;
    return changed;
}

function resetWorksheetSelect() {
    state.worksheets = [];
    state.spreadsheetTitle = '';
    const select = document.getElementById('gs-sheet-name');
    select.innerHTML = '<option value="">工作表：等待获取...</option>';
    select.disabled = true;
    updateAnalyzeButton();
}

function autoFetchWorksheets() {
    const url = document.getElementById('gs-url').value.trim();
    const spreadsheetId = extractSheetId(url);
    if (!url || !spreadsheetId) return;
    if (spreadsheetId === state.lastFetchedSpreadsheetId) return;
    fetchWorksheets(true);
}

async function fetchWorksheets(silent = false) {
    const url = document.getElementById('gs-url').value.trim();
    const spreadsheetId = extractSheetId(url);
    if (!url || !spreadsheetId) {
        if (!silent) showAlert('请先输入正确的 Google Sheet URL（需要能解析 spreadsheet_id）', 'warning');
        return;
    }

    state.lastFetchedSpreadsheetId = spreadsheetId;

    showLoading();
    abortController = new AbortController();

    try {
        const data = await Api.endpoints.performanceAnalysis.worksheets({spreadsheet_id: spreadsheetId}, {
            envelope: true,
            signal: abortController.signal
        });
        const api = normalizeApiResponse(data);
        if (!api.ok) {
            throw new Error(api.message || '请求失败');
        }

        const worksheetsPayload = getWorksheetsPayload(api);
        state.worksheets = Array.isArray(worksheetsPayload.worksheets) ? worksheetsPayload.worksheets : [];
        state.spreadsheetTitle = worksheetsPayload.title || '';

        const meta = document.getElementById('gs-meta');
        meta.innerHTML = `<span class="text-body-secondary">spreadsheet_id: </span><span class="fw-semibold">${spreadsheetId}</span>` + (state.spreadsheetTitle ? ` <span class="text-body-secondary">| 标题：</span><span class="fw-semibold">${escapeHtml(state.spreadsheetTitle)}</span>` : '');
        // meta 已更新为带标题的新内容，清除 loading 快照避免 hideLoading 还原旧文案
        delete meta.dataset.prev;

        const select = document.getElementById('gs-sheet-name');
        select.innerHTML = '';

        if (state.worksheets.length === 0) {
            select.innerHTML = '<option value="">未找到工作表</option>';
            select.disabled = true;
            updateAnalyzeButton();
            if (!silent) showAlert('未找到任何工作表', 'warning');
            return;
        }

        state.worksheets.forEach((name) => {
            const opt = document.createElement('option');
            opt.value = name;
            opt.textContent = name;
            select.appendChild(opt);
        });
        select.disabled = false;
        updateAnalyzeButton();
        if (!silent) showAlert('工作表已加载', 'success');
    } catch (e) {
        if (e.name === 'AbortError') {
            if (!silent) showAlert('操作已取消', 'info');
        } else {
            if (!silent) showAlert('获取工作表失败：' + (e.message || '未知错误'), 'danger');
        }
    } finally {
        abortController = null;
        hideLoading();
    }
}

// ---- 来源适配：粘贴 / Excel ----

function prepareDataRows(text) {
    const rows = text.split(/\r?\n/)
        .map((line) => line.trim())
        .filter(Boolean)
        .map((line) => line.split(/[\t,\s]+/).slice(0, 3));
    return prepareRows(rows);
}

function prepareRows(rows) {
    const dataRows = rows.filter((row) => row.some((cell) => String(cell ?? '').trim()));
    if (!dataRows.length) {
        throw new Error('请至少输入一行回测数据');
    }

    const hasHeader = isHeaderRow(dataRows[0]);
    const usableRows = hasHeader ? dataRows.slice(1) : dataRows;
    if (!usableRows.length) {
        throw new Error('列头后没有可分析的数据');
    }

    const normalizedRows = usableRows.map((row, index) => {
        const values = row.slice(0, 3).map((value) => String(value ?? '').trim());
        if (values.length < 3 || !isDateLike(values[0]) || !isNumberLike(values[1]) || !isNumberLike(values[2])) {
            throw new Error(`第 ${index + (hasHeader ? 2 : 1)} 行不是有效的日期、指数收益、模型收益数据`);
        }
        return values;
    });

    return {
        text: normalizedRows.map((row) => row.join('\t')).join('\n'),
        rowCount: normalizedRows.length,
        hasHeader
    };
}

function isHeaderRow(row) {
    const normalize = (value) => String(value ?? '').trim().toLowerCase().replace(/[\s_\-]/g, '');
    const headers = [
        new Set(['date', '日期', '时间', '交易日']),
        new Set(['indexreturn', '指数收益', '指数收益率']),
        new Set(['startreturn', '模型收益', '模型收益率', '策略收益', '策略收益率'])
    ];
    const values = row.slice(0, 3).map(normalize);
    if (values.every((value, index) => headers[index].has(value))) {
        return true;
    }
    return !isDateLike(row[0]) && !isNumberLike(row[1]) && !isNumberLike(row[2]);
}

function isDateLike(value) {
    const text = String(value ?? '').trim();
    if (!text) return false;
    return !Number.isNaN(Date.parse(text));
}

function isNumberLike(value) {
    const text = String(value ?? '').trim().replace(/%$/, '');
    return text !== '' && Number.isFinite(Number(text));
}

function updatePasteStatus() {
    const status = document.getElementById('v3-paste-status');
    try {
        const prepared = prepareDataRows(document.getElementById('v3-paste-data').value);
        status.className = 'small text-success mb-3';
        status.textContent = `已识别 ${prepared.rowCount} 行有效数据${prepared.hasHeader ? '，已跳过列头' : ''}。`;
    } catch (e) {
        status.className = 'small text-body-secondary mb-3';
        status.textContent = '需要三列：日期、指数收益、模型收益。';
    }
    updateAnalyzeButton();
}

async function handleExcelImport(event) {
    const file = event.target.files[0];
    const status = document.getElementById('v3-excel-status');
    if (!file) return;
    if (!window.XLSX) {
        showAlert('Excel 解析组件未加载，请刷新页面后重试', 'danger');
        return;
    }

    try {
        status.className = 'small text-body-secondary mt-2';
        status.textContent = '正在读取 Excel 文件...';
        const workbook = XLSX.read(await file.arrayBuffer(), {type: 'array', cellDates: true});
        const firstSheetName = workbook.SheetNames[0];
        if (!firstSheetName) {
            throw new Error('Excel 中未找到工作表');
        }
        const worksheet = workbook.Sheets[firstSheetName];
        const rows = XLSX.utils.sheet_to_json(worksheet, {header: 1, defval: '', raw: true})
            .map((row) => [formatExcelDate(row[0]), row[1], row[2]]);
        const prepared = prepareRows(rows);
        document.getElementById('v3-paste-data').value = prepared.text;
        state.manualDataTitle = file.name.replace(/\.[^.]+$/, '') || '本地 Excel';
        state.manualDataSheetName = firstSheetName;
        status.className = 'small text-success mt-2';
        status.textContent = `已读取“${firstSheetName}”的 ${prepared.rowCount} 行数据${prepared.hasHeader ? '，已跳过列头' : ''}。`;
        updatePasteStatus();
        bootstrap.Tab.getOrCreateInstance(document.getElementById('paste-data-tab')).show();
        showAlert('Excel 已导入，请确认数据后分析', 'success');
    } catch (e) {
        status.className = 'small text-danger mt-2';
        status.textContent = `导入失败：${e.message || '无法读取 Excel 文件'}`;
    } finally {
        event.target.value = '';
    }
}

function formatExcelDate(value) {
    if (value instanceof Date && !Number.isNaN(value.getTime())) {
        return `${value.getFullYear()}-${String(value.getMonth() + 1).padStart(2, '0')}-${String(value.getDate()).padStart(2, '0')}`;
    }
    if (typeof value === 'number' && value > 20000 && value < 80000 && XLSX?.SSF?.parse_date_code) {
        const date = XLSX.SSF.parse_date_code(value);
        if (date) {
            return `${date.y}-${String(date.m).padStart(2, '0')}-${String(date.d).padStart(2, '0')}`;
        }
    }
    return value;
}

// ---- 来源适配：结果分析 ----

// 下拉用的轻量字段集（fields 白名单投影）：避开 result 大 JSON
const RESULT_FIELDS_QUERY = 'fields=id,task_id,parameters,return_series_id,success,error_message,return_date_range';

function buildResultOptionLabel(item) {
    const params = item.parameters || {};
    const parts = [`结果 ${item.id}`];
    if (params.stock_code) parts.push(String(params.stock_code).toUpperCase());
    if (params.stock_name) parts.push(String(params.stock_name));
    if (params.year !== undefined && params.year !== null && `${params.year}` !== '') parts.push(`${params.year}年`);
    const parameterList = Array.isArray(params.parameter)
        ? params.parameter.filter((v) => v !== null && v !== undefined && `${v}` !== '').map(String)
        : [];
    if (parameterList.length) parts.push(`参数 ${parameterList.join('/')}`);
    const range = item.return_date_range;
    if (range?.start && range?.end) parts.push(`${range.start} ~ ${range.end}`);
    let label = parts.join(' · ');
    if (item.success === false) {
        const reason = String(item.error_message || '').trim().slice(0, 40);
        label += `（失败${reason ? '：' + reason : ''}）`;
    }
    return label;
}

function getResultInputValue() {
    return document.getElementById('v3-result-id-input').value.trim();
}

function isDirectResultId(value) {
    return /^\d+$/.test(value);
}

function updateResultControls() {
    const value = getResultInputValue();
    const selectWrap = document.getElementById('v3-result-select-wrap');
    const status = document.getElementById('v3-result-status');
    if (isDirectResultId(value)) {
        selectWrap.classList.add('d-none');
        status.textContent = `直接分析结果 ID：${value}`;
    } else {
        selectWrap.classList.add('d-none');
        status.textContent = value
            ? '回车或失焦获取该任务的结果列表。'
            : '输入任务 ID 后回车或失焦获取结果列表；直接输入结果 ID（纯数字）可直接分析。';
    }
    updateAnalyzeButton();
}

async function fetchTaskResults() {
    const taskId = getResultInputValue();
    if (!taskId || isDirectResultId(taskId)) return;
    const status = document.getElementById('v3-result-status');
    const select = document.getElementById('v3-result-select');
    status.textContent = '正在获取结果列表…';
    try {
        const data = await Api.endpoints.task.results(encodeURIComponent(taskId), RESULT_FIELDS_QUERY);
        if (getResultInputValue() !== taskId) return;
        const items = data?.items || [];
        state.resultSeriesByResultId.clear();
        select.innerHTML = '';
        items.forEach((item) => {
            const params = item.parameters || {};
            state.resultSeriesByResultId.set(String(item.id), {
                task_id: item.task_id || '',
                return_series_id: item.return_series_id || null,
                stockCode: String(params.stock_code || '').toUpperCase(),
                stockName: String(params.stock_name || params.product_name || ''),
                year: params.year,
                dateRange: item.return_date_range
            });
            const option = document.createElement('option');
            option.value = String(item.id);
            option.textContent = buildResultOptionLabel(item);
            option.disabled = item.success === false;
            select.appendChild(option);
        });
        if (!items.length) {
            status.textContent = '该任务下没有结果，请确认任务 ID。';
            updateAnalyzeButton();
            return;
        }
        document.getElementById('v3-result-select-wrap').classList.remove('d-none');
        status.textContent = `共 ${items.length} 个结果，选择后点击“分析”。`;
    } catch (error) {
        status.textContent = error.message || '获取结果列表失败';
    }
    updateAnalyzeButton();
}

async function resolveResultSeriesInfo(resultId) {
    let info = state.resultSeriesByResultId.get(String(resultId));
    if (info) return info;
    const detail = await Api.endpoints.adminResults.detail(resultId);
    info = {
        task_id: detail?.task_id || '',
        return_series_id: detail?.return_series_id || null,
        stockCode: String(detail?.parameters?.stock_code || '').toUpperCase(),
        stockName: String(detail?.parameters?.stock_name || detail?.parameters?.product_name || ''),
        year: detail?.parameters?.year,
        dateRange: null
    };
    state.resultSeriesByResultId.set(String(resultId), info);
    return info;
}

// ---- 参数配置 ----

function parseThresholdInput(inputId, fallback) {
    const raw = document.getElementById(inputId)?.value?.trim();
    if (raw === '' || raw === undefined) return fallback;
    const value = Number(raw);
    return Number.isFinite(value) ? value : fallback;
}

function collectRuntimeParams() {
    // 页面输入按百分比填写，payload 统一转换为小数阈值
    const riskFreePercent = Math.min(Math.max(parseThresholdInput('config-risk-free-rate', 0), 0), 100);
    return {
        market_downturn_threshold: parseThresholdInput('config-downturn-threshold', -2) / 100,
        market_upturn_threshold: parseThresholdInput('config-upturn-threshold', 2) / 100,
        daily_extreme_threshold: parseThresholdInput('config-daily-extreme-threshold', 2) / 100,
        daily_drawdown_threshold: parseThresholdInput('config-daily-drawdown-threshold', 5) / 100,
        risk_free_rate: riskFreePercent / 100
    };
}

function saveRuntimeParams() {
    try {
        localStorage.setItem(V3_RUNTIME_PARAMS_STORAGE_KEY, JSON.stringify(collectRuntimeParams()));
    } catch (e) {
        // localStorage 不可用（隐私模式等）时忽略，配置仅在当前页面生效。
    }
}

function restoreRuntimeParams() {
    let saved = null;
    try {
        saved = JSON.parse(localStorage.getItem(V3_RUNTIME_PARAMS_STORAGE_KEY) || 'null');
    } catch (e) {
        saved = null;
    }
    if (!saved || typeof saved !== 'object') return;
    const restore = (key, inputId) => {
        if (Number.isFinite(saved[key])) {
            document.getElementById(inputId).value = Number((saved[key] * 100).toFixed(6));
        }
    };
    restore('market_downturn_threshold', 'config-downturn-threshold');
    restore('market_upturn_threshold', 'config-upturn-threshold');
    restore('daily_extreme_threshold', 'config-daily-extreme-threshold');
    restore('daily_drawdown_threshold', 'config-daily-drawdown-threshold');
    restore('risk_free_rate', 'config-risk-free-rate');
}

// ---- 分析按钮可用性 ----

function getActiveSource() {
    return document.querySelector('#v3-source-tabs .nav-link.active')?.id || '';
}

function updateAnalyzeButton() {
    const button = document.getElementById('btn-analyze-v3');
    if (!button || abortController) return;

    const source = getActiveSource();
    if (source === 'google-sheet-tab') {
        button.disabled = !(state.worksheets && state.worksheets.length > 0);
        return;
    }
    if (source === 'paste-data-tab') {
        try {
            prepareDataRows(document.getElementById('v3-paste-data').value);
            button.disabled = false;
        } catch (e) {
            button.disabled = true;
        }
        return;
    }
    if (source === 'result-tab') {
        const directResultId = isDirectResultId(getResultInputValue());
        const selectedResultId = document.getElementById('v3-result-select').value;
        button.disabled = !(directResultId || selectedResultId);
        return;
    }
    button.disabled = true;
}

// ---- 分析入口 ----

async function runActiveAnalysis() {
    const source = getActiveSource();
    if (source === 'google-sheet-tab') {
        await analyzeGoogleSheet();
        return;
    }
    if (source === 'paste-data-tab') {
        await analyzePaste();
        return;
    }
    if (source === 'result-tab') {
        await analyzeResult();
    }
}

async function analyzeGoogleSheet() {
    const url = document.getElementById('gs-url').value.trim();
    const spreadsheetId = extractSheetId(url);
    const sheetName = document.getElementById('gs-sheet-name').value;
    if (!url) {
        showAlert('请输入 Google Sheet URL', 'warning');
        return;
    }
    if (!sheetName) {
        showAlert('请选择工作表', 'warning');
        return;
    }

    const runtimeParams = collectRuntimeParams();
    state.wordExportStockPreset = null;
    await requestAnalysis({
        google_sheet_url: url,
        spreadsheet_id: spreadsheetId,
        google_sheet_name: sheetName,
        runtime_params: runtimeParams,
        include_series: true
    }, {
        key: `sheet:${spreadsheetId}:${sheetName}`,
        label: `${state.spreadsheetTitle || 'Google Sheet'}·${sheetName}`,
        source: 'sheet',
        meta: {title: state.spreadsheetTitle, sheetName},
        wordPayload: {
            report_type: 'RPT-S',
            google_sheet_url: url,
            spreadsheet_id: spreadsheetId,
            google_sheet_name: sheetName,
            metadata: {sheet_title: state.spreadsheetTitle},
            runtime_params: runtimeParams
        }
    });
}

async function analyzePaste() {
    let prepared;
    try {
        prepared = prepareDataRows(document.getElementById('v3-paste-data').value);
    } catch (e) {
        showAlert(e.message || '请输入有效的三列数据', 'warning');
        return;
    }

    document.getElementById('v3-paste-data').value = prepared.text;
    updatePasteStatus();
    const runtimeParams = collectRuntimeParams();
    state.wordExportStockPreset = null;
    await requestAnalysis({
        data: prepared.text,
        time_format: 'auto',
        runtime_params: runtimeParams,
        include_series: true
    }, {
        key: `manual:${prepared.rowCount}:${prepared.text.slice(0, 64)}`,
        label: `${state.manualDataTitle || '手动数据'}·${state.manualDataSheetName || '粘贴数据'}`,
        source: 'paste',
        meta: {title: state.manualDataTitle, sheetName: state.manualDataSheetName},
        wordPayload: {
            report_type: 'RPT-S',
            returns: prepared.text.split('\n').map((line) => {
                const [date, indexReturn, startReturn] = line.split('\t');
                return {date, index_return: Number(indexReturn), start_return: Number(startReturn)};
            }),
            metadata: {model_version: '单产品'},
            runtime_params: runtimeParams
        }
    });
}

async function analyzeResult() {
    const raw = getResultInputValue();
    if (!raw) {
        showAlert('请输入任务 ID 或结果 ID', 'warning');
        return;
    }
    let resultId;
    if (isDirectResultId(raw)) {
        resultId = Number(raw);
    } else {
        resultId = Number(document.getElementById('v3-result-select').value || 0);
        if (!resultId) {
            showAlert('请先获取并选择结果 ID', 'warning');
            return;
        }
    }
    const runtimeParams = collectRuntimeParams();

    // Word 报告需要收益序列归属（task_id + return_series_id）：
    // 下拉路径在结果列表里已带；直接输结果 ID 时经结果详情接口补齐。
    let seriesInfo;
    try {
        seriesInfo = await resolveResultSeriesInfo(resultId);
    } catch (error) {
        showAlert(error.message || '读取结果详情失败', 'warning');
        return;
    }

    const metaParts = [`结果 ${resultId}`];
    if (seriesInfo.stockCode) metaParts.push(seriesInfo.stockCode + (seriesInfo.stockName ? `·${seriesInfo.stockName}` : ''));
    if (seriesInfo.year !== undefined && seriesInfo.year !== null && `${seriesInfo.year}` !== '') metaParts.push(`${seriesInfo.year}年`);
    const range = seriesInfo.dateRange;
    if (range?.start && range?.end) metaParts.push(`${range.start}~${range.end}`);

    let wordPayload = null;
    if (seriesInfo.task_id && seriesInfo.return_series_id) {
        wordPayload = {
            report_type: 'RPT-S',
            task_id: seriesInfo.task_id,
            return_series_id: seriesInfo.return_series_id,
            runtime_params: runtimeParams
        };
        if (seriesInfo.stockCode) {
            state.wordExportStockPreset = {
                code: seriesInfo.stockCode,
                name: seriesInfo.stockName || seriesInfo.stockCode
            };
        }
    }

    await requestAnalysis({
        result_id: resultId,
        runtime_params: runtimeParams,
        include_series: true
    }, {
        key: `result:${resultId}`,
        label: metaParts.join('·'),
        source: 'result',
        meta: seriesInfo,
        wordPayload
    });
}

async function requestAnalysis(body, datasetTemplate) {
    showLoading();
    abortController = new AbortController();

    try {
        const data = await Api.endpoints.performanceAnalysis.analyze(body, {
            envelope: true,
            signal: abortController.signal
        });
        const api = normalizeApiResponse(data);
        if (!api.ok) {
            throw new Error(api.message || '请求失败');
        }

        const payload = getAnalyzePayload(api);
        const results = payload?.results;
        if (!results) {
            showAlert('后端未返回 results', 'warning');
            return;
        }

        addDataset({
            ...datasetTemplate,
            metrics: results,
            series: payload.series || null
        });
        renderAll();
        showAlert('V3 分析完成，已登记为数据集', 'success');
    } catch (e) {
        if (e.name === 'AbortError') {
            showAlert('操作已取消', 'info');
        } else {
            showAlert('分析失败：' + (e.message || '未知错误'), 'danger');
        }
    } finally {
        abortController = null;
        hideLoading();
    }
}

// ---- 导出 Excel ----

async function exportDetails() {
    const active = activeDataset();
    if (!active) {
        showAlert('请先完成分析再导出', 'warning');
        return;
    }

    const btn = document.getElementById('btn-export-v3');
    if (btn) btn.disabled = true;

    try {
        const safe = (text) => String(text || 'v3').replaceAll(/[\\/:*?"<>|]/g, '_');
        const filenameSafeTitle = safe(active.meta?.title || active.label);
        const filenameSafeSheet = safe(active.meta?.sheetName || active.source);
        const defaultFilename = `${filenameSafeTitle}_${filenameSafeSheet}_details.xlsx`;
        const sourceFilename = `${filenameSafeTitle}_${filenameSafeSheet}_details.csv`;

        // 文件流下载，走原始 Response 端点（CSRF 头在端点内保持不变）
        const resp = await Api.endpoints.export.backtestResultPerformanceAnalysis({
            filename: sourceFilename,
            filename_title: filenameSafeTitle,
            analyze_result: active.metrics
        });

        if (!resp.ok) {
            const err = await resp.json().catch(() => ({}));
            const api = normalizeApiResponse(err);
            throw new Error(api.message || `HTTP error! status: ${resp.status}`);
        }

        const workbook = XLSX.read(await resp.text(), {type: 'string'});
        XLSX.writeFile(workbook, defaultFilename, {compression: true});
        showAlert(`文件已下载: ${defaultFilename}`, 'success');
    } catch (e) {
        if (e.name !== 'AbortError') {
            showAlert('导出失败：' + (e.message || '未知错误'), 'danger');
        }
    } finally {
        if (btn) btn.disabled = false;
    }
}

// ---- 导出 Word ----

async function exportWordReport() {
    const active = activeDataset();
    if (!active || !active.wordPayload) {
        showAlert('当前数据集不支持 Word 导出（仅结果分析 / Sheet / 粘贴来源）', 'warning');
        return;
    }

    if (active.wordPayload.report_type !== 'RPT-M') {
        showWordExportOptions(active);
        return;
    }

    await downloadWordReport(active.wordPayload);
}

function showWordExportOptions(active) {
    const input = document.getElementById('word-export-stock');
    const results = document.getElementById('word-export-stock-results');
    // 结果分析来源预填被分析结果自身的股票；其他来源每次打开清空重选。
    const preset = state.wordExportStockPreset;
    state.wordExportStock = preset ? {code: preset.code, name: preset.name} : null;
    input.value = preset ? `${preset.code} · ${preset.name}` : '';
    results.innerHTML = '';
    results.classList.add('d-none');
    // 弹窗里的无风险利率默认跟随「参数配置」页签，可按单次导出临时覆盖。
    const modalRiskFreeInput = document.getElementById('word-export-risk-free-rate');
    if (modalRiskFreeInput) {
        modalRiskFreeInput.value = String(parseThresholdInput('config-risk-free-rate', 0));
    }
    bootstrap.Modal.getOrCreateInstance(document.getElementById('word-export-options-modal')).show();
}

function scheduleWordExportStockSearch() {
    state.wordExportStock = null;
    window.clearTimeout(state.wordExportSearchTimer);
    state.wordExportSearchTimer = window.setTimeout(searchWordExportStocks, 250);
}

async function searchWordExportStocks() {
    const input = document.getElementById('word-export-stock');
    const results = document.getElementById('word-export-stock-results');
    const keyword = input.value.trim();
    if (!keyword) {
        results.classList.add('d-none');
        return;
    }
    if (state.wordExportSearchAbortController) {
        state.wordExportSearchAbortController.abort();
    }
    state.wordExportSearchAbortController = new AbortController();
    try {
        const data = await Api.endpoints.stock.search(`q=${encodeURIComponent(keyword)}&page_size=10`, {
            signal: state.wordExportSearchAbortController.signal
        });
        const items = Array.isArray(data?.results) ? data.results : [];
        results.innerHTML = items.length ? items.map((item) => `
            <button type="button" class="list-group-item list-group-item-action" data-code="${escapeHtml(item.code || '')}" data-name="${escapeHtml(item.name || item.code || '')}">
                <span class="fw-semibold">${escapeHtml(item.code || '')}</span>
                <span class="ms-2 small text-body-secondary">${escapeHtml(item.label || item.name || '')}</span>
            </button>
        `).join('') : '<div class="list-group-item text-body-secondary small">暂无匹配结果</div>';
        results.classList.remove('d-none');
    } catch (error) {
        if (error.name !== 'AbortError') {
            results.innerHTML = `<div class="list-group-item text-danger small">${escapeHtml(error.message || '股票搜索失败')}</div>`;
            results.classList.remove('d-none');
        }
    }
}

function selectWordExportStock(event) {
    const item = event.target.closest('[data-code]');
    if (!item) return;
    state.wordExportStock = {code: item.dataset.code, name: item.dataset.name};
    document.getElementById('word-export-stock').value = `${item.dataset.code} · ${item.dataset.name}`;
    document.getElementById('word-export-stock-results').classList.add('d-none');
}

// 弹窗内无风险利率按百分比填写（如 3 = 3%），payload 统一转小数（0.03）。
function readWordExportRiskFreeRate() {
    const raw = document.getElementById('word-export-risk-free-rate')?.value?.trim();
    if (raw === '' || raw === undefined) return {percent: 0, decimal: 0};
    const percent = Number(raw);
    if (!Number.isFinite(percent) || percent < 0 || percent > 100) {
        throw new Error('无风险利率需为 0～100 之间的数字（百分比）');
    }
    return {percent, decimal: percent / 100};
}

async function confirmWordExport() {
    if (!state.wordExportStock) {
        showAlert('请从搜索结果中选择股票', 'warning');
        return;
    }
    let riskFree;
    try {
        riskFree = readWordExportRiskFreeRate();
    } catch (error) {
        showAlert(error.message, 'warning');
        return;
    }
    const active = activeDataset();
    if (!active?.wordPayload) return;
    const priceMode = document.getElementById('word-export-price-type').value;
    const priceType = {
        kp_price: '开盘价',
        sp_price: '收盘价',
        vwap_price: '加权平均价',
        ohlc_price: 'OHLC（开高低收）',
        random_price: '随机价'
    }[priceMode] || '';
    const payload = JSON.parse(JSON.stringify(active.wordPayload));
    payload.products = [{
        stock_code: state.wordExportStock.code,
        product_name: state.wordExportStock.name,
        ratio: '100.00%'
    }];
    payload.metadata = {
        ...(payload.metadata || {}),
        price_type: priceType,
        risk_free_rate: `${riskFree.percent.toFixed(2)}%`
    };
    payload.runtime_params = {
        ...(payload.runtime_params || {}),
        risk_free_rate: riskFree.decimal
    };
    bootstrap.Modal.getInstance(document.getElementById('word-export-options-modal'))?.hide();
    await downloadWordReport(payload);
}

async function downloadWordReport(payload) {
    const button = document.getElementById('btn-export-word');
    if (button) button.disabled = true;
    try {
        // 文件流下载，走原始 Response 端点（CSRF 头在端点内保持不变）
        const response = await Api.endpoints.export.wordReport(payload);
        if (!response.ok) {
            const data = await response.json().catch(() => ({}));
            throw new Error(data.message || `HTTP error! status: ${response.status}`);
        }
        const blob = await response.blob();
        const filename = response.headers.get('Content-Disposition')
            ?.match(/filename[^;=\n]*=(?:UTF-8''|\")?([^;\n\"]+)/i)?.[1]
            || '策略回测绩效分析报告.docx';
        const link = document.createElement('a');
        const objectUrl = URL.createObjectURL(blob);
        link.href = objectUrl;
        link.download = decodeURIComponent(filename.replace(/^"|"$/g, ''));
        document.body.appendChild(link);
        link.click();
        link.remove();
        URL.revokeObjectURL(objectUrl);
        showAlert('Word 报告已下载', 'success');
    } catch (error) {
        showAlert('Word 导出失败：' + (error.message || '未知错误'), 'danger');
    } finally {
        if (button) button.disabled = false;
    }
}

// ---- JSON 复制 ----

async function copyRawJson() {
    const pre = document.getElementById('pre-v3-raw-json');
    const text = pre?.textContent || '';
    if (!text) {
        showAlert('无可复制内容', 'warning');
        return;
    }
    try {
        if (navigator.clipboard && navigator.clipboard.writeText) {
            await navigator.clipboard.writeText(text);
        } else {
            const ta = document.createElement('textarea');
            ta.value = text;
            ta.setAttribute('readonly', '');
            ta.style.position = 'fixed';
            ta.style.left = '-9999px';
            document.body.appendChild(ta);
            ta.select();
            const ok = document.execCommand('copy');
            document.body.removeChild(ta);
            if (!ok) throw new Error('copy failed');
        }
        showAlert('已复制', 'success');
    } catch (e) {
        showAlert('复制失败', 'danger');
    }
}

// ---- 分区锚点导航 + 滚动高亮 ----

function setupSectionNav() {
    const links = document.querySelectorAll('#v3-section-nav-list .nav-link');
    links.forEach((link) => {
        link.addEventListener('click', () => {
            const target = document.getElementById(link.dataset.target);
            if (target) {
                target.scrollIntoView({behavior: 'smooth', block: 'start'});
            }
        });
    });

    const sections = Array.from(links).map((link) => document.getElementById(link.dataset.target)).filter(Boolean);
    const observer = new IntersectionObserver((entries) => {
        entries.forEach((entry) => {
            if (!entry.isIntersecting) return;
            links.forEach((link) => link.classList.toggle('active', link.dataset.target === entry.target.id));
        });
    }, {rootMargin: '-20% 0px -70% 0px'});
    sections.forEach((section) => observer.observe(section));
}

// ---- URL 参数直达（C 系列/回测页跳转入口） ----

async function applyUrlParams() {
    const params = new URLSearchParams(window.location.search);
    const taskId = params.get('task_id');
    const resultId = params.get('result_id');
    if (resultId && /^\d+$/.test(resultId)) {
        bootstrap.Tab.getOrCreateInstance(document.getElementById('result-tab')).show();
        document.getElementById('v3-result-id-input').value = resultId;
        updateResultControls();
        await analyzeResult();
        return;
    }
    if (taskId) {
        bootstrap.Tab.getOrCreateInstance(document.getElementById('result-tab')).show();
        document.getElementById('v3-result-id-input').value = taskId;
        updateResultControls();
        await fetchTaskResults();
    }
}

// ---- 初始化 ----

document.addEventListener('DOMContentLoaded', () => {
    document.getElementById('btn-fetch-sheets').addEventListener('click', fetchWorksheets);
    document.getElementById('btn-analyze-v3').addEventListener('click', runActiveAnalysis);
    document.querySelectorAll('#v3-source-tabs [data-bs-toggle="tab"]').forEach((tab) => {
        tab.addEventListener('shown.bs.tab', updateAnalyzeButton);
    });
    document.getElementById('btn-select-v3-excel').addEventListener('click', () => {
        document.getElementById('v3-excel-file').click();
    });
    document.getElementById('v3-excel-file').addEventListener('change', handleExcelImport);
    document.getElementById('v3-result-id-input').addEventListener('change', () => {
        updateResultControls();
        if (!isDirectResultId(getResultInputValue())) {
            fetchTaskResults();
        }
    });
    document.getElementById('v3-result-id-input').addEventListener('keydown', (event) => {
        if (event.key !== 'Enter') return;
        event.preventDefault();
        updateResultControls();
        if (!isDirectResultId(getResultInputValue())) {
            fetchTaskResults();
        }
    });
    document.getElementById('v3-result-select').addEventListener('change', updateAnalyzeButton);
    document.getElementById('v3-paste-data').addEventListener('input', () => {
        state.manualDataTitle = '手动数据';
        state.manualDataSheetName = '粘贴数据';
        updatePasteStatus();
    });
    document.getElementById('btn-export-v3')?.addEventListener('click', exportDetails);
    document.getElementById('btn-export-word')?.addEventListener('click', exportWordReport);
    document.getElementById('word-export-stock')?.addEventListener('input', scheduleWordExportStockSearch);
    document.getElementById('word-export-stock-results')?.addEventListener('click', selectWordExportStock);
    document.getElementById('btn-confirm-word-export')?.addEventListener('click', confirmWordExport);
    document.getElementById('btn-copy-raw-json')?.addEventListener('click', copyRawJson);
    document.getElementById('gs-url').addEventListener('input', debounce(() => {
        const changed = updateMeta();
        if (changed) {
            resetWorksheetSelect();
        }
        autoFetchWorksheets();
    }, 500));
    document.getElementById('v3-nav-log-toggle')?.addEventListener('change', () => {
        renderNavCharts(compareDatasets(), compareDatasets().length === 1);
    });
    document.querySelectorAll('#v3-heatmap-switch button').forEach((btn) => {
        btn.addEventListener('click', () => {
            document.querySelectorAll('#v3-heatmap-switch button').forEach((item) => item.classList.remove('active'));
            btn.classList.add('active');
            state.heatmapView = btn.dataset.view;
            const active = activeDataset();
            if (active) renderHeatmap(active);
        });
    });

    updateMeta();
    updatePasteStatus();
    restoreRuntimeParams();
    ['config-downturn-threshold', 'config-upturn-threshold', 'config-daily-extreme-threshold',
        'config-daily-drawdown-threshold', 'config-risk-free-rate'].forEach((id) => {
        document.getElementById(id).addEventListener('input', saveRuntimeParams);
    });
    updateAnalyzeButton();
    setupSectionNav();

    Chart.defaults.font.size = 11;

    // 明暗主题切换时按新色板重绘全部图表（template-auth 在 html 上切 data-bs-theme）
    new MutationObserver(() => renderAll()).observe(document.documentElement, {
        attributes: true,
        attributeFilter: ['data-bs-theme']
    });

    applyUrlParams();
});

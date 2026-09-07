// backtest 回测结果页（backtest 双胞胎）批内收敛：bt/multi 两页规范化后逐字相同的函数提升至此（F4 dedupe pass，
// docs/design/frontend-refactor/02 §3.6）。函数体为页面原实现逐字节搬移；
// 页面调用点已改写为 Biz.*，页面差异（路径前缀、数据列、存储键、导出上限）保留在 pages JS。
window.Biz = window.Biz || {};
(function (Biz) {
'use strict';

function fmtPct(v, digits = 2) {
        if (v === null || v === undefined || Number.isNaN(v)) return '-';
        return (Number(v) * 100).toFixed(digits) + '%';
    }

function fmtNum(v, digits = 4) {
        if (v === null || v === undefined || Number.isNaN(v)) return '-';
        return Number(v).toFixed(digits);
    }

function fmtInt(v) {
        if (v === null || v === undefined || Number.isNaN(Number(v))) return '-';
        return String(Math.round(Number(v)));
    }

function idxByYear(list, valueKey) {
        const m = new Map();
        if (!Array.isArray(list)) return m;
        list.forEach(item => {
            if (!item) return;
            const y = String(item.year);
            const v = item[valueKey];
            m.set(y, item);
        });
        return m;
    }

function normalizeYearSeries(list, valueKey) {
        const m = new Map();
        if (Array.isArray(list)) {
            list.forEach(item => {
                if (!item) return;
                const y = String(item.year);
                if (y === 'all') return;
                m.set(y, item[valueKey]);
            });
        }
        const labels = Array.from(m.keys()).sort();
        const values = labels.map(y => m.get(y));
        return {labels, values, map: m};
    }

function profitMonthlySeries(list) {
        const m = new Map();
        if (Array.isArray(list)) {
            list.forEach(item => {
                if (!item) return;
                const y = String(item.year);
                m.set(y, item.profit_monthly_percentage);
            });
        }
        return m;
    }

function repairDaysValues(r) {
        return [
            ['index', r.index_maximum_number_of_backtest_repair_days],
            ['start', r.start_maximum_number_of_backtest_repair_days],
            ['excess', r.excess_maximum_number_of_backtest_repair_days]
        ].filter(([, value]) => value !== undefined && value !== null && !Number.isNaN(Number(value)));
    }

function formatSharpeKey(key) {
        const k = String(key ?? '');
        if (!k) return k;
        if (k === 'all') return 'all';

        const mPast = k.match(/^past_(\d+)(?:_.*)?$/);
        if (mPast) {
            const n = Number(mPast[1]);
            return `近${n}年`;
        }

        const mYear = k.match(/^year_\d+_(\d{4})$/);
        if (mYear) {
            return mYear[1];
        }

        return k;
    }

function sharpeEntriesToSeries(obj) {
        const arr = [];
        if (!obj || typeof obj !== 'object') return arr;
        Object.entries(obj).forEach(([k, v]) => {
            if (!v || typeof v !== 'object') return;
            if (v.sharpe_ratio === undefined || v.sharpe_ratio === null) return;
            arr.push({key: formatSharpeKey(k), sharpe: v.sharpe_ratio});
        });
        arr.sort((a, b) => {
            if (a.key === 'all' && b.key !== 'all') return -1;
            if (b.key === 'all' && a.key !== 'all') return 1;
            return a.key.localeCompare(b.key);
        });
        return arr;
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

function formatDisplayValue(value) {
        if (value === null || value === undefined || value === '') {
            return '-';
        }
        if (typeof value === 'number') {
            return Number.isInteger(value) ? String(value) : fmtNum(value, 6);
        }
        if (typeof value === 'boolean') {
            return value ? 'true' : 'false';
        }
        if (Array.isArray(value) || typeof value === 'object') {
            try {
                return `<pre class="mb-0 small text-wrap" style="white-space: pre-wrap; word-break: break-word;">${escapeHtml(JSON.stringify(value, null, 2))}</pre>`;
            } catch (e) {
                return `<code>${escapeHtml(String(value))}</code>`;
            }
        }
        return escapeHtml(String(value));
    }

function normalizeBacktestResultPayload(payload) {
        if (!payload || typeof payload !== 'object' || Array.isArray(payload)) {
            return null;
        }

        if (payload.calculate_metrics && typeof payload.calculate_metrics === 'object') {
            const sheetResult = payload.sheet_result && typeof payload.sheet_result === 'object'
                ? payload.sheet_result
                : Object.fromEntries(Object.entries(payload).filter(([key]) => key !== 'calculate_metrics'));
            return {
                ...payload.calculate_metrics,
                sheet_result: sheetResult,
                model_name: payload.model_name || ''
            };
        }

        return payload;
    }

function fillScalarsTable(tbodyId, r) {
        const tbody = document.getElementById(tbodyId);
        if (!tbody) return;
        tbody.innerHTML = '';

        const scalarNameMap = {
            outperform_year: '跑赢年份',
            monthly_excess_volatility: '月超额波动率',
            excess_drawdown_winning_rate: '超额回撤胜率',
            excess_sharpe: '超额夏普',
            excess_sortino: '超额索提诺',
            index_profit_annual: '指数盈利年百分比',
            start_profit_annual: '策略盈利年百分比',
            index_monthly_return_volatility: '指数月收益率波动率',
            start_monthly_return_volatility: '策略月收益率波动率',
            index_maximum_number_of_backtest_repair_days: '指数最大回测天数',
            start_maximum_number_of_backtest_repair_days: '策略最大回测天数',
            excess_maximum_number_of_backtest_repair_days: '超额最大回测天数'
        };

        const scalarKeys = [
            'outperform_year',
            'monthly_excess_volatility',
            'excess_drawdown_winning_rate',
            'excess_sharpe',
            'excess_sortino',
            'index_profit_annual',
            'start_profit_annual',
            'index_monthly_return_volatility',
            'start_monthly_return_volatility',
            'index_maximum_number_of_backtest_repair_days',
            'start_maximum_number_of_backtest_repair_days',
            'excess_maximum_number_of_backtest_repair_days'
        ];

        scalarKeys.forEach(k => {
            if (r[k] === undefined) return;
            const tr = document.createElement('tr');
            let v = r[k];
            if (k.includes('profit_annual') || k.includes('outperform_year') || k.includes('winning_rate')) {
                v = fmtPct(v, 2);
            } else if (k.includes('maximum_number_of_backtest_repair_days')) {
                v = fmtInt(v);
            } else if (typeof v === 'number') {
                v = fmtNum(v, 6);
            }
            tr.innerHTML = `<td><code>${escapeHtml(k)}</code></td><td>${escapeHtml(scalarNameMap[k] || '-')}</td><td>${v}</td>`;
            tbody.appendChild(tr);
        });
    }

function fillSheetResultTable(tbodyId, sheetResult) {
        const tbody = document.getElementById(tbodyId);
        if (!tbody) return;
        tbody.innerHTML = '';

        if (!sheetResult || typeof sheetResult !== 'object' || Array.isArray(sheetResult)) {
            tbody.innerHTML = '<tr><td colspan="2" class="text-center text-body-secondary">暂无数据</td></tr>';
            return;
        }

        const keys = Object.keys(sheetResult).sort();
        if (keys.length === 0) {
            tbody.innerHTML = '<tr><td colspan="2" class="text-center text-body-secondary">暂无数据</td></tr>';
            return;
        }

        keys.forEach(k => {
            const tr = document.createElement('tr');
            const v = sheetResult[k];
            tr.innerHTML = `<td><code>${escapeHtml(k)}</code></td><td>${formatDisplayValue(v)}</td>`;
            tbody.appendChild(tr);
        });
    }

function fillMonthlyExcessReturnsTable(list, tbodyId) {
        const tbody = document.getElementById(tbodyId);
        if (!tbody) return;
        tbody.innerHTML = '';

        if (!Array.isArray(list) || list.length === 0) {
            tbody.innerHTML = '<tr><td colspan="4" class="text-center text-body-secondary">暂无数据</td></tr>';
            return;
        }

        list.forEach(item => {
            const tr = document.createElement('tr');
            const diff = item?.monthly_excess_return_diff;
            tr.innerHTML = `
                <td>${item?.year_month ?? '-'}</td>
                <td class="${(item?.index_monthly_return || 0) >= 0 ? 'text-success' : 'text-danger'}">${fmtPct(item?.index_monthly_return, 2)}</td>
                <td class="${(item?.start_monthly_return || 0) >= 0 ? 'text-success' : 'text-danger'}">${fmtPct(item?.start_monthly_return, 2)}</td>
                <td class="${(diff || 0) >= 0 ? 'text-success' : 'text-danger'}">${fmtPct(diff, 2)}</td>
            `;
            tbody.appendChild(tr);
        });
    }

function fillExcessReturnsTable(r) {
        const tbody = document.getElementById('tbl-excess-returns');
        if (!tbody) return;
        tbody.innerHTML = '';

        if (!Array.isArray(r.excess_returns)) {
            tbody.innerHTML = '<tr><td colspan="5" class="text-center text-body-secondary">暂无数据</td></tr>';
            return;
        }

        r.excess_returns.forEach(item => {
            const tr = document.createElement('tr');
            const diff = item?.annualized_return_diff;
            tr.innerHTML = `
                <td>${item?.year ?? '-'}</td>
                <td class="${(item?.start_annualized_return || 0) >= 0 ? 'text-success' : 'text-danger'}">${fmtPct(item?.start_annualized_return, 2)}</td>
                <td class="${(item?.index_annualized_return || 0) >= 0 ? 'text-success' : 'text-danger'}">${fmtPct(item?.index_annualized_return, 2)}</td>
                <td class="${(diff || 0) >= 0 ? 'text-success' : 'text-danger'}">${fmtPct(diff, 2)}</td>
                <td>${item?.start_end_date ?? '-'}</td>
            `;
            tbody.appendChild(tr);
        });
    }

function fillKamaTable(list, tbodyId) {
        const tbody = document.getElementById(tbodyId);
        if (!tbody) return;
        tbody.innerHTML = '';

        if (!Array.isArray(list)) {
            tbody.innerHTML = '<tr><td colspan="4" class="text-center text-body-secondary">暂无数据</td></tr>';
            return;
        }

        list.forEach(item => {
            const tr = document.createElement('tr');
            tr.innerHTML = `
                <td>${item?.year ?? '-'}</td>
                <td>${fmtNum(item?.kama_ratio, 6)}</td>
                <td>${fmtPct(item?.annualized_return, 2)}</td>
                <td>${fmtPct(item?.drawdown, 2)}</td>
            `;
            tbody.appendChild(tr);
        });
    }

function fillKamaMerged(indexList, startList, tbodyId) {
        const tbody = document.getElementById(tbodyId);
        if (!tbody) return;
        tbody.innerHTML = '';

        const idx = idxByYear(indexList, 'kama_ratio');
        const st = idxByYear(startList, 'kama_ratio');
        const years = Array.from(new Set([...idx.keys(), ...st.keys()])).filter(y => y !== 'all').sort();

        if (years.length === 0) {
            tbody.innerHTML = '<tr><td colspan="7" class="text-center text-body-secondary">暂无数据</td></tr>';
            return;
        }

        years.forEach(y => {
            const i = idx.get(y);
            const s = st.get(y);
            const tr = document.createElement('tr');
            tr.innerHTML = `
                <td>${y}</td>
                <td>${fmtNum(i?.kama_ratio, 6)}</td>
                <td>${fmtNum(s?.kama_ratio, 6)}</td>
                <td>${fmtPct(i?.annualized_return, 2)}</td>
                <td>${fmtPct(s?.annualized_return, 2)}</td>
                <td>${fmtPct(i?.drawdown, 2)}</td>
                <td>${fmtPct(s?.drawdown, 2)}</td>
            `;
            tbody.appendChild(tr);
        });
    }

function fillSotinoTable(list, tbodyId) {
        const tbody = document.getElementById(tbodyId);
        if (!tbody) return;
        tbody.innerHTML = '';

        if (!Array.isArray(list)) {
            tbody.innerHTML = '<tr><td colspan="4" class="text-center text-body-secondary">暂无数据</td></tr>';
            return;
        }

        list.forEach(item => {
            const tr = document.createElement('tr');
            tr.innerHTML = `
                <td>${item?.year ?? '-'}</td>
                <td>${fmtNum(item?.sortino_ratio, 6)}</td>
                <td>${fmtNum(item?.average_monthly_annualized_return, 6)}</td>
                <td>${fmtNum(item?.downside_standard_deviation, 6)}</td>
            `;
            tbody.appendChild(tr);
        });
    }

function fillSotinoMerged(indexList, startList, tbodyId) {
        const tbody = document.getElementById(tbodyId);
        if (!tbody) return;
        tbody.innerHTML = '';

        const idx = idxByYear(indexList, 'sortino_ratio');
        const st = idxByYear(startList, 'sortino_ratio');
        const years = Array.from(new Set([...idx.keys(), ...st.keys()])).filter(y => y !== 'all').sort();

        if (years.length === 0) {
            tbody.innerHTML = '<tr><td colspan="7" class="text-center text-body-secondary">暂无数据</td></tr>';
            return;
        }

        years.forEach(y => {
            const i = idx.get(y);
            const s = st.get(y);
            const tr = document.createElement('tr');
            tr.innerHTML = `
                <td>${y}</td>
                <td>${fmtNum(i?.sortino_ratio, 6)}</td>
                <td>${fmtNum(s?.sortino_ratio, 6)}</td>
                <td>${fmtNum(i?.average_monthly_annualized_return, 6)}</td>
                <td>${fmtNum(s?.average_monthly_annualized_return, 6)}</td>
                <td>${fmtNum(i?.downside_standard_deviation, 6)}</td>
                <td>${fmtNum(s?.downside_standard_deviation, 6)}</td>
            `;
            tbody.appendChild(tr);
        });
    }

function fillSharpeTable(obj, tbodyId) {
        const tbody = document.getElementById(tbodyId);
        if (!tbody) return;
        tbody.innerHTML = '';

        if (!obj || typeof obj !== 'object') {
            tbody.innerHTML = '<tr><td colspan="7" class="text-center text-body-secondary">暂无数据</td></tr>';
            return;
        }

        const keys = Object.keys(obj).sort();
        keys.forEach(k => {
            const v = obj[k];
            if (!v || typeof v !== 'object') return;
            const tr = document.createElement('tr');
            tr.innerHTML = `
                <td><code>${k}</code></td>
                <td>${fmtNum(v?.sharpe_ratio, 6)}</td>
                <td>${fmtPct(v?.avg_monthly_return, 2)}</td>
                <td>${fmtPct(v?.monthly_std_dev, 2)}</td>
                <td>${fmtPct(v?.annual_std_dev, 2)}</td>
                <td>${v?.start_date ?? '-'}</td>
                <td>${v?.end_date ?? '-'}</td>
            `;
            tbody.appendChild(tr);
        });

        if (tbody.children.length === 0) {
            tbody.innerHTML = '<tr><td colspan="7" class="text-center text-body-secondary">无可展示条目</td></tr>';
        }
    }

function fillSharpeMerged(indexObj, startObj, tbodyId) {
        const tbody = document.getElementById(tbodyId);
        if (!tbody) return;
        tbody.innerHTML = '';

        const idx = (indexObj && typeof indexObj === 'object') ? indexObj : {};
        const st = (startObj && typeof startObj === 'object') ? startObj : {};
        const keys = Array.from(new Set([...Object.keys(idx), ...Object.keys(st)])).sort();

        if (keys.length === 0) {
            tbody.innerHTML = '<tr><td colspan="11" class="text-center text-body-secondary">暂无数据</td></tr>';
            return;
        }

        keys.forEach(k => {
            const i = idx[k];
            const s = st[k];
            const base = (i && typeof i === 'object') ? i : ((s && typeof s === 'object') ? s : null);
            if (!base) return;

            const tr = document.createElement('tr');
            tr.innerHTML = `
                <td><code>${formatSharpeKey(k)}</code></td>
                <td>${fmtNum(i?.sharpe_ratio, 6)}</td>
                <td>${fmtNum(s?.sharpe_ratio, 6)}</td>
                <td>${fmtPct(i?.avg_monthly_return, 2)}</td>
                <td>${fmtPct(s?.avg_monthly_return, 2)}</td>
                <td>${fmtPct(i?.monthly_std_dev, 2)}</td>
                <td>${fmtPct(s?.monthly_std_dev, 2)}</td>
                <td>${fmtPct(i?.annual_std_dev, 2)}</td>
                <td>${fmtPct(s?.annual_std_dev, 2)}</td>
                <td>${base?.start_date ?? '-'}</td>
                <td>${base?.end_date ?? '-'}</td>
            `;
            tbody.appendChild(tr);
        });

        if (tbody.children.length === 0) {
            tbody.innerHTML = '<tr><td colspan="11" class="text-center text-body-secondary">无可展示条目</td></tr>';
        }
    }

function fillProfitAnnualTable(r) {
        const tbody = document.getElementById('tbl-profit-annual');
        if (!tbody) return;
        tbody.innerHTML = '';
        const tr = document.createElement('tr');
        tr.innerHTML = `<td>${fmtPct(r.index_profit_annual, 2)}</td><td>${fmtPct(r.start_profit_annual, 2)}</td>`;
        tbody.appendChild(tr);
    }

function fillExcessMetricsTable(r) {
        const tbody = document.getElementById('tbl-excess-metrics');
        if (!tbody) return;
        tbody.innerHTML = '';

        const rows = [
            ['excess_sharpe', r.excess_sharpe],
            ['excess_sortino', r.excess_sortino]
        ];

        rows.forEach(([key, value]) => {
            const tr = document.createElement('tr');
            tr.innerHTML = `<td><code>${key}</code></td><td>${value === undefined ? '-' : fmtNum(value, 6)}</td>`;
            tbody.appendChild(tr);
        });
    }

function fillRepairDaysTable(r) {
        const tbody = document.getElementById('tbl-repair-days');
        if (!tbody) return;
        tbody.innerHTML = '';

        const rows = repairDaysValues(r);
        if (rows.length === 0) {
            tbody.innerHTML = '<tr><td colspan="2" class="text-center text-body-secondary">暂无数据</td></tr>';
            return;
        }

        rows.forEach(([key, value]) => {
            const tr = document.createElement('tr');
            const isExcess = key === 'excess';
            const colorClass = isExcess ? ((Number(value) || 0) >= 0 ? 'text-success' : 'text-danger') : '';
            tr.innerHTML = `<td><code>${key}</code></td><td class="${colorClass}">${fmtInt(value)}</td>`;
            tbody.appendChild(tr);
        });
        return;
        

        if (years.length === 0) {
            tbody.innerHTML = '<tr><td colspan="4" class="text-center text-body-secondary">暂无数据</td></tr>';
            return;
        }

        years.forEach(year => {
            const tr = document.createElement('tr');
            const excess = exMap.get(year);
            tr.innerHTML = `<td>${year}</td><td>${idxMap.get(year) ?? '-'}</td><td>${stMap.get(year) ?? '-'}</td><td class="${(excess ?? 0) >= 0 ? 'text-success' : 'text-danger'}">${excess ?? '-'}</td>`;
            tbody.appendChild(tr);
        });
    }

function fillProfitMonthlyTable(list, tbodyId) {
        const tbody = document.getElementById(tbodyId);
        if (!tbody) return;
        tbody.innerHTML = '';
        if (!Array.isArray(list)) {
            tbody.innerHTML = '<tr><td colspan="2" class="text-center text-body-secondary">暂无数据</td></tr>';
            return;
        }
        list.forEach(item => {
            const tr = document.createElement('tr');
            tr.innerHTML = `<td>${item?.year ?? '-'}</td><td>${fmtPct(item?.profit_monthly_percentage, 2)}</td>`;
            tbody.appendChild(tr);
        });
    }

function renderTabScalars(r) {
        fillScalarsTable('tbl-scalars', r);
    }

function renderTabSheetResult(r) {
        fillSheetResultTable('tbl-sheet-result', r.sheet_result);
    }

function renderTabAnnualAndDrawdown(r) {
        const idxAnnual = idxByYear(r.index_returns_rate, 'annual_return');
        const stAnnual = idxByYear(r.start_returns_rate, 'annual_return');

        const years = Array.from(new Set([...idxAnnual.keys(), ...stAnnual.keys()])).filter(y => y !== 'all').sort();
        const annualTbody = document.getElementById('tbl-annual-compare');
        annualTbody.innerHTML = '';

        years.forEach(y => {
            const a1 = idxAnnual.get(y)?.annual_return;
            const a2 = stAnnual.get(y)?.annual_return;
            const diff = (a2 !== undefined && a1 !== undefined) ? (a2 - a1) : null;
            const tr = document.createElement('tr');
            tr.innerHTML = `<td>${y}</td><td class="${(a1 || 0) >= 0 ? 'text-success' : 'text-danger'}">${fmtPct(a1, 2)}</td><td class="${(a2 || 0) >= 0 ? 'text-success' : 'text-danger'}">${fmtPct(a2, 2)}</td><td class="${(diff || 0) >= 0 ? 'text-success' : 'text-danger'}">${diff === null ? '-' : fmtPct(diff, 2)}</td>`;
            annualTbody.appendChild(tr);
        });

        const idxDd = idxByYear(r.index_maximum_drawdown?.year_maximum_drawdown, 'drawdown');
        const stDd = idxByYear(r.start_maximum_drawdown?.year_maximum_drawdown, 'drawdown');
        const ddYears = Array.from(new Set([...idxDd.keys(), ...stDd.keys()])).filter(y => y !== 'all').sort();
        const ddTbody = document.getElementById('tbl-drawdown-compare');
        ddTbody.innerHTML = '';
        ddYears.forEach(y => {
            const d1 = idxDd.get(y);
            const d2 = stDd.get(y);
            const tr = document.createElement('tr');
            tr.innerHTML = `<td>${y}</td><td class="text-danger">-${fmtPct(d1?.drawdown, 2)}</td><td class="text-danger">-${fmtPct(d2?.drawdown, 2)}</td><td>${(d1?.date || '-') + ' / ' + (d2?.date || '-')}</td>`;
            ddTbody.appendChild(tr);
        });

        const mPct = document.getElementById('tbl-monthly-excess-pct');
        mPct.innerHTML = '';
        if (Array.isArray(r.monthly_excess_return_percentage)) {
            r.monthly_excess_return_percentage.forEach(item => {
                const tr = document.createElement('tr');
                tr.innerHTML = `<td>${item.year}</td><td>${fmtPct(item.excess_return, 2)}</td>`;
                mPct.appendChild(tr);
            });
        }
    }

function renderTabExcessReturns(r) {
        fillExcessReturnsTable(r);
    }

function renderTabMonthlyExcessReturns(r) {
        fillMonthlyExcessReturnsTable(r.monthly_excess_returns, 'tbl-monthly-excess-returns');
    }

function renderTabKama(r) {
        fillKamaMerged(r.index_kama_ratio, r.start_kama_ratio, 'tbl-kama');
    }

function renderTabSotino(r) {
        fillSotinoMerged(r.index_sortino_ratio, r.start_sortino_ratio, 'tbl-sotino');
    }

function renderTabSharpe(r) {
        fillSharpeMerged(r.index_sharpe_ratios, r.start_sharpe_ratios, 'tbl-sharpe');
    }

function renderTabExcessMetrics(r) {
        fillExcessMetricsTable(r);
    }

function renderTabRepairDays(r) {
        fillRepairDaysTable(r);
    }

function renderTabProfit(r) {
        fillProfitAnnualTable(r);
        fillProfitMonthlyTable(r.index_profit_monthly, 'tbl-index-profit-monthly');
        fillProfitMonthlyTable(r.start_profit_monthly, 'tbl-start-profit-monthly');
    }

function renderSummary(r) {
        document.getElementById('v1-outperform-year').textContent = r.outperform_year !== undefined ? fmtPct(r.outperform_year, 2) : '-';
        document.getElementById('v1-monthly-excess-vol').textContent = r.monthly_excess_volatility !== undefined ? fmtNum(r.monthly_excess_volatility, 4) : '-';
        document.getElementById('v1-excess-dd-win').textContent = r.excess_drawdown_winning_rate !== undefined ? fmtPct(r.excess_drawdown_winning_rate, 2) : '-';

        const allExcess = Array.isArray(r.excess_returns) ? r.excess_returns.find(x => String(x.year) === 'all') : null;
        document.getElementById('v1-excess-annual-all').textContent = allExcess ? fmtPct(allExcess.annualized_return_diff, 2) : '-';

        document.getElementById('v1-index-profit-annual').textContent = r.index_profit_annual !== undefined ? fmtPct(r.index_profit_annual, 2) : '-';
        document.getElementById('v1-start-profit-annual').textContent = r.start_profit_annual !== undefined ? fmtPct(r.start_profit_annual, 2) : '-';
        document.getElementById('v1-index-monthly-vol').textContent = r.index_monthly_return_volatility !== undefined ? fmtNum(r.index_monthly_return_volatility, 6) : '-';
        document.getElementById('v1-start-monthly-vol').textContent = r.start_monthly_return_volatility !== undefined ? fmtNum(r.start_monthly_return_volatility, 6) : '-';
    }

function escapeHtml(str) {
        return String(str)
                .replaceAll('&', '&amp;')
                .replaceAll('<', '&lt;')
                .replaceAll('>', '&gt;')
                .replaceAll('"', '&quot;')
                .replaceAll("'", '&#039;');
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

Biz.fmtPct = fmtPct;
Biz.fmtNum = fmtNum;
Biz.fmtInt = fmtInt;
Biz.idxByYear = idxByYear;
Biz.normalizeYearSeries = normalizeYearSeries;
Biz.profitMonthlySeries = profitMonthlySeries;
Biz.repairDaysValues = repairDaysValues;
Biz.formatSharpeKey = formatSharpeKey;
Biz.sharpeEntriesToSeries = sharpeEntriesToSeries;
Biz.setPreJson = setPreJson;
Biz.formatDisplayValue = formatDisplayValue;
Biz.normalizeBacktestResultPayload = normalizeBacktestResultPayload;
Biz.fillScalarsTable = fillScalarsTable;
Biz.fillSheetResultTable = fillSheetResultTable;
Biz.fillMonthlyExcessReturnsTable = fillMonthlyExcessReturnsTable;
Biz.fillExcessReturnsTable = fillExcessReturnsTable;
Biz.fillKamaTable = fillKamaTable;
Biz.fillKamaMerged = fillKamaMerged;
Biz.fillSotinoTable = fillSotinoTable;
Biz.fillSotinoMerged = fillSotinoMerged;
Biz.fillSharpeTable = fillSharpeTable;
Biz.fillSharpeMerged = fillSharpeMerged;
Biz.fillProfitAnnualTable = fillProfitAnnualTable;
Biz.fillExcessMetricsTable = fillExcessMetricsTable;
Biz.fillRepairDaysTable = fillRepairDaysTable;
Biz.fillProfitMonthlyTable = fillProfitMonthlyTable;
Biz.renderTabScalars = renderTabScalars;
Biz.renderTabSheetResult = renderTabSheetResult;
Biz.renderTabAnnualAndDrawdown = renderTabAnnualAndDrawdown;
Biz.renderTabExcessReturns = renderTabExcessReturns;
Biz.renderTabMonthlyExcessReturns = renderTabMonthlyExcessReturns;
Biz.renderTabKama = renderTabKama;
Biz.renderTabSotino = renderTabSotino;
Biz.renderTabSharpe = renderTabSharpe;
Biz.renderTabExcessMetrics = renderTabExcessMetrics;
Biz.renderTabRepairDays = renderTabRepairDays;
Biz.renderTabProfit = renderTabProfit;
Biz.renderSummary = renderSummary;
Biz.escapeHtml = escapeHtml;
Biz.showAlert = showAlert;
})(window.Biz);

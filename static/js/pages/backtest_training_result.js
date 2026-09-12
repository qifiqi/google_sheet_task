// 回测结果页面逻辑（templates 页面脚本原样抽离，F4 de-jinja）。
// 批内收敛（F4 dedupe pass）：bt/multi 规范化后逐字相同的函数已提升至 common/business/（Biz.*）。
// 接口调用经 common/api.js。
    let abortController = null;
    const state = {
        resultId: (window.location.pathname.match(/\/result\/(\d+)/) || [])[1] || '',
        taskId: '',
        exportBaseName: '',
        lastResults: null,
        wordReportPayload: null,
        charts: {}
    };

    document.addEventListener('DOMContentLoaded', () => {
        const backToDetailLink = document.getElementById('backToDetailLink');
        if (backToDetailLink) {
            backToDetailLink.href = buildDetailHref();
        }
        document.getElementById('btn-reload-result')?.addEventListener('click', loadBacktestResult);
        document.getElementById('btn-export-v1')?.addEventListener('click', exportV1Details);
        document.getElementById('btn-export-word')?.addEventListener('click', exportWordReport);
        document.getElementById('btn-preview-export')?.addEventListener('click', openExportPreview);
        document.getElementById('btn-copy-raw-json')?.addEventListener('click', copyRawJson);
        loadBacktestResult();
    });

    function buildDetailHref() {
        const currentParams = new URLSearchParams(window.location.search);
        const detailParams = new URLSearchParams();
        ['list_page', 'list_per_page', 'result_page', 'result_per_page'].forEach((key) => {
            const value = currentParams.get(key);
            if (value) {
                detailParams.set(key, value);
            }
        });
        const query = detailParams.toString();
        return `/backtest-training/detail/${encodeURIComponent(state.taskId)}${query ? `?${query}` : ''}`;
    }

    function openExportPreview() {
        const currentParams = new URLSearchParams(window.location.search);
        const previewParams = new URLSearchParams();
        ['list_page', 'list_per_page', 'result_page', 'result_per_page'].forEach((key) => {
            const value = currentParams.get(key);
            if (value) {
                previewParams.set(key, value);
            }
        });
        const query = previewParams.toString();
        window.location.href = `/backtest-training/result/${encodeURIComponent(state.resultId)}/export-preview${query ? `?${query}` : ''}`;
    }

    async function copyRawJson() {
        const pre = document.getElementById('pre-raw-json');
        const text = pre?.textContent || '';
        if (!text) {
            Biz.showAlert('暂无可复制内容', 'warning');
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
            Biz.showAlert('复制成功', 'success');
        } catch (e) {
            Biz.showAlert('复制失败', 'danger');
        }
    }

    function showLoading() {
        const overlay = document.getElementById('loading-overlay');
        if (overlay) overlay.classList.remove('d-none');
        const reloadBtn = document.getElementById('btn-reload-result');
        const exportBtn = document.getElementById('btn-export-v1');
        const wordExportBtn = document.getElementById('btn-export-word');
        const previewBtn = document.getElementById('btn-preview-export');
        if (reloadBtn) reloadBtn.disabled = true;
        if (exportBtn) exportBtn.disabled = true;
        if (wordExportBtn) wordExportBtn.disabled = true;
        if (previewBtn) previewBtn.disabled = true;
    }

    function hideLoading() {
        const overlay = document.getElementById('loading-overlay');
        if (overlay) overlay.classList.add('d-none');
        const reloadBtn = document.getElementById('btn-reload-result');
        const exportBtn = document.getElementById('btn-export-v1');
        const wordExportBtn = document.getElementById('btn-export-word');
        const previewBtn = document.getElementById('btn-preview-export');
        if (reloadBtn) reloadBtn.disabled = false;
        if (exportBtn) exportBtn.disabled = !state.lastResults;
        if (wordExportBtn) wordExportBtn.disabled = !state.wordReportPayload;
        if (previewBtn) previewBtn.disabled = !state.lastResults;
   }

    

    

    function renderModelIdentity(modelName, resultData) {
        const normalizedModelName = String(modelName || '').trim().toUpperCase();
        const displayModelName = ['C3', 'C4', 'C5', 'C7'].includes(normalizedModelName)
            ? normalizedModelName
            : '';
        const badge = document.getElementById('result-model-badge');
        const description = document.getElementById('result-model-description');
        const pageTitle = document.getElementById('result-page-title');
        const resultMeta = document.getElementById('result-meta');
        const resultId = document.getElementById('result-meta-id');
        const taskId = document.getElementById('result-meta-task-id');
        const period = document.getElementById('result-meta-period');
        const periodWrap = document.getElementById('result-meta-period-wrap');
        const allPeriod = Array.isArray(resultData?.excess_returns)
            ? resultData.excess_returns.find((item) => String(item?.year).toLowerCase() === 'all')?.start_end_date
            : '';
        if (badge) {
            badge.textContent = displayModelName;
            badge.classList.toggle('d-none', !displayModelName);
        }
        if (pageTitle) {
            pageTitle.textContent = displayModelName ? `${displayModelName} 回测结果` : '回测结果';
        }
        if (description) {
            description.textContent = displayModelName
                ? `查看并导出当前任务的 ${displayModelName} V1 回测分析结果`
                : '查看并导出当前任务的 V1 回测分析结果';
        }
        if (resultMeta) resultMeta.classList.remove('d-none');
        if (resultId) resultId.textContent = state.resultId || '-';
        if (taskId) taskId.textContent = state.taskId || '-';
        if (period) period.textContent = allPeriod || '';
        if (periodWrap) periodWrap.classList.toggle('d-none', !allPeriod);
        document.title = displayModelName
            ? `${displayModelName} 回测结果 - Jaspil 任务管理系统`
            : '回测结果 - Jaspil 任务管理系统';
    }

    function buildExportBaseName(resultData) {
        const modelName = String(resultData?.model_name || '').trim().toUpperCase();
        const stockCode = String(resultData?.stock_code || '').trim().toUpperCase();
        const allPeriod = Array.isArray(resultData?.excess_returns)
            ? resultData.excess_returns.find((item) => String(item?.year).toLowerCase() === 'all')?.start_end_date
            : '';
        const years = String(allPeriod || '').match(/(?:19|20)\d{2}/g) || [];

        if (!modelName || !stockCode || !years.length) {
            return `backtest_result_${state.resultId}`;
        }

        const latestYear = Math.max(...years.map(Number));
        const earliestYear = Math.min(...years.map(Number));
        const period = latestYear === earliestYear
            ? String(latestYear)
            : `${latestYear}-${earliestYear}`;
        return `${modelName}-${stockCode}-${period}`;
    }

    async function loadBacktestResult() {
        showLoading();
        abortController = new AbortController();

        try {
            const data = await Api.endpoints.backtest.taskResult(encodeURIComponent(state.resultId), {
                signal: abortController.signal
            });

            const resultData = Biz.normalizeBacktestResultPayload(data && data.result);
            if (!resultData) {
                state.lastResults = null;
                Biz.showAlert('结果数据为空', 'warning');
                return;
            }

            state.lastResults = resultData;
            state.wordReportPayload = (data && data.word_report_payload) || null;
            // 静态化（03 §4.3）：task_id 改从结果接口响应推导；无 return_series 时与旧空串行为一致
            state.taskId = (state.wordReportPayload && state.wordReportPayload.task_id) || '';
            const backToDetailLink = document.getElementById('backToDetailLink');
            if (backToDetailLink) {
                backToDetailLink.href = buildDetailHref();
            }
            state.exportBaseName = buildExportBaseName(resultData);
            renderModelIdentity(resultData.model_name, resultData);
            const exportBtn = document.getElementById('btn-export-v1');
            if (exportBtn) exportBtn.disabled = false;
            const wordExportBtn = document.getElementById('btn-export-word');
            if (wordExportBtn) wordExportBtn.disabled = !state.wordReportPayload;
            const previewBtn = document.getElementById('btn-preview-export');
            if (previewBtn) previewBtn.disabled = false;
            Biz.renderSummary(resultData);
            renderTables(resultData);
            renderCharts(resultData);
            Biz.showAlert('结果加载完成', 'success');
        } catch (e) {
            if (e.name === 'AbortError') {
                Biz.showAlert('操作已取消', 'info');
            } else {
                state.lastResults = null;
                Biz.showAlert('加载结果失败：' + (e.message || '未知错误'), 'danger');
            }
        } finally {
            hideLoading();
            abortController = null;
        }
    }

    async function exportV1Details() {
        if (!state.lastResults) {
            Biz.showAlert('请先完成分析再导出', 'warning');
            return;
        }

        const btn = document.getElementById('btn-export-v1');
        if (btn) btn.disabled = true;

        try {
            const exportBaseName = state.exportBaseName || 'backtest_result';
            const defaultFilename = exportBaseName.startsWith('backtest_result_')
                ? `${exportBaseName}_details.csv`
                : `${exportBaseName}.csv`;

            const resp = await Api.endpoints.export.backtestResult(encodeURIComponent(state.resultId));

            if (!resp.ok) {
                const err = await resp.json().catch(() => ({}));
                throw new Error(err.message || `HTTP error! status: ${resp.status}`);
            }

            const blob = await resp.blob();
            
            // Try to use File System Access API (only works in secure contexts with user gesture)
            if (window.showSaveFilePicker && location.protocol === 'https:' && navigator.userAgent.includes('Chrome')) {
                try {
                    const fileHandle = await window.showSaveFilePicker({
                        suggestedName: defaultFilename,
                        types: [{
                            description: 'CSV files',
                            accept: { 'text/csv': ['.csv'] }
                        }]
                    });
                    const writable = await fileHandle.createWritable();
                    await writable.write(blob);
                    await writable.close();
                    Biz.showAlert('文件已保存', 'success');
                    return;
                } catch (err) {
                    if (err.name !== 'AbortError') {
                        console.warn('File System Access API failed, falling back to download:', err);
                    } else {
                        Biz.showAlert('用户取消了保存操作', 'info');
                        return;
                    }
                }
            }
            
            // Fallback: Create download with prompt for filename
            const userFilename = prompt('请输入文件名:', defaultFilename);
            if (userFilename === null) {
                Biz.showAlert('用户取消了保存操作', 'info');
                return;
            }
            
            const finalFilename = userFilename.trim() || defaultFilename;
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = finalFilename.endsWith('.csv') ? finalFilename : finalFilename + '.csv';
            document.body.appendChild(a);
            a.click();
            a.remove();
            window.URL.revokeObjectURL(url);
            Biz.showAlert(`开始下载：${finalFilename}`, 'success');
        } catch (e) {
            if (e.name !== 'AbortError') {
                Biz.showAlert('导出失败：' + (e.message || '未知错误'), 'danger');
            }
        } finally {
            if (btn) btn.disabled = false;
        }
    }

    async function exportWordReport() {
        if (!state.wordReportPayload) {
            Biz.showAlert('当前结果没有可导出的收益序列', 'warning');
            return;
        }

        const button = document.getElementById('btn-export-word');
        button.disabled = true;
        try {
            const response = await Api.endpoints.export.wordReport(state.wordReportPayload);
            if (!response.ok) {
                const data = await response.json().catch(() => ({}));
                throw new Error(data.message || `HTTP error! status: ${response.status}`);
            }
            const filename = response.headers.get('Content-Disposition')
                ?.match(/filename[^;=\n]*=(?:UTF-8''|\")?([^;\n\"]+)/i)?.[1]
                || 'RPT-S.docx';
            const link = document.createElement('a');
            const objectUrl = URL.createObjectURL(await response.blob());
            link.href = objectUrl;
            link.download = decodeURIComponent(filename.replace(/^\"|\"$/g, ''));
            document.body.appendChild(link);
            link.click();
            link.remove();
            URL.revokeObjectURL(objectUrl);
            Biz.showAlert('Word 报告已下载', 'success');
        } catch (error) {
            Biz.showAlert('Word 导出失败：' + (error.message || '未知错误'), 'danger');
        } finally {
            button.disabled = !state.wordReportPayload;
        }
    }

    

    

    

    

    

    

    

    

    

    

    // 月超额收益 tab：渲染每个月“模型 - 指数”的超额收益
    

    // 标量 tab：渲染页面顶部摘要对应的关键标量
    

    // Sheet结果 tab：渲染 analyze_v1 返回的 sheet_result（字典键值）
    

    // 年度收益/回撤 tab：渲染年度收益对比、年度回撤对比、月超额收益百分比
    

    // 超额收益 tab
    

    // 月超额收益 tab（monthly_excess_returns）
    

    // 卡玛 tab
    

    // 索提诺 tab
    

    // 夏普 tab
    

    // 超额指标 tab
    

    

    

    

    

    

    

    

    

    

    

    

    

    

    

    function renderTables(r) {
        Biz.setPreJson('pre-raw-json', r);
        Biz.renderTabScalars(r);
        Biz.renderTabSheetResult(r);
        Biz.renderTabAnnualAndDrawdown(r);
        Biz.renderTabExcessReturns(r);
        Biz.renderTabMonthlyExcessReturns(r);
        Biz.renderTabKama(r);
        Biz.renderTabSotino(r);
        Biz.renderTabSharpe(r);
        Biz.renderTabExcessMetrics(r);
        Biz.renderTabRepairDays(r);
        Biz.renderTabProfit(r);
    }

    function destroyChart(key) {
        const c = state.charts[key];
        if (c) {
            try {
                c.destroy();
            } catch (e) {
            }
        }
        state.charts[key] = null;
    }

    function buildLineChart(canvasId, key, labels, datasets, yTitle) {
        const el = document.getElementById(canvasId);
        if (!el) return;
        destroyChart(key);
        const singlePointMode = labels.length <= 1;
        const chartType = singlePointMode ? 'bar' : 'line';
        const normalizedDatasets = datasets.map(ds => ({
            ...ds,
            fill: singlePointMode ? false : ds.fill,
            tension: singlePointMode ? 0 : (ds.tension ?? 0.1),
            pointRadius: singlePointMode ? 0 : (ds.pointRadius ?? 3),
            pointHoverRadius: singlePointMode ? 0 : (ds.pointHoverRadius ?? 5),
            borderWidth: ds.borderWidth ?? 2
        }));
        state.charts[key] = new Chart(el, {
            type: chartType,
            data: {labels, datasets: normalizedDatasets},
            options: {
                responsive: true,
                maintainAspectRatio: false,
                interaction: {mode: 'index', intersect: false},
                scales: {
                    y: {
                        title: {display: true, text: yTitle},
                        grace: '8%'
                    },
                    x: {title: {display: true, text: 'Year'}}
                }
            }
        });
    }

    function buildBarChart(canvasId, key, labels, datasets, yTitle) {
        const el = document.getElementById(canvasId);
        if (!el) return;
        destroyChart(key);
        state.charts[key] = new Chart(el, {
            type: 'bar',
            data: {labels, datasets},
            options: {
                responsive: true,
                maintainAspectRatio: false,
                scales: {
                    y: {title: {display: true, text: yTitle}},
                    x: {title: {display: true, text: 'Year'}}
                }
            }
        });
    }

    

    function renderCharts(r) {
        const idxAnnual = Biz.normalizeYearSeries(r.index_returns_rate, 'annual_return');
        const stAnnual = Biz.normalizeYearSeries(r.start_returns_rate, 'annual_return');
        const labelsAnnual = Array.from(new Set([...idxAnnual.labels, ...stAnnual.labels])).sort();
        const idxAnnualVals = labelsAnnual.map(y => idxAnnual.map.get(y) ?? null);
        const stAnnualVals = labelsAnnual.map(y => stAnnual.map.get(y) ?? null);

        buildLineChart(
                'chart-annual-returns',
                'annualReturns',
                labelsAnnual,
                [
                    {
                        label: '指数年度收益(%)',
                        data: idxAnnualVals.map(v => v === null ? null : v * 100),
                        borderColor: '#0d6efd',
                        backgroundColor: 'rgba(13,110,253,0.08)',
                        tension: 0.1,
                        fill: true
                    },
                    {
                        label: '模型年度收益(%)',
                        data: stAnnualVals.map(v => v === null ? null : v * 100),
                        borderColor: '#198754',
                        backgroundColor: 'rgba(25,135,84,0.08)',
                        tension: 0.1,
                        fill: true
                    }
                ],
                'Return (%)'
        );

        const exMap = new Map();
        if (Array.isArray(r.excess_returns)) {
            r.excess_returns.forEach(item => {
                const y = String(item.year);
                if (y === 'all') return;
                exMap.set(y, item.annualized_return_diff);
            });
        }
        const exLabels = Array.from(exMap.keys()).sort();
        const exVals = exLabels.map(y => (exMap.get(y) ?? 0) * 100);
        buildBarChart(
                'chart-excess-annual',
                'excessAnnual',
                exLabels,
                [{
                    label: '年超额收益 (%)',
                    data: exVals,
                    backgroundColor: exVals.map(v => v >= 0 ? 'rgba(25,135,84,0.5)' : 'rgba(220,53,69,0.5)'),
                    borderColor: exVals.map(v => v >= 0 ? '#198754' : '#dc3545'),
                    borderWidth: 1
                }],
                'Excess Return (%)'
        );

        const idxDd = Biz.normalizeYearSeries(r.index_maximum_drawdown?.year_maximum_drawdown, 'drawdown');
        const stDd = Biz.normalizeYearSeries(r.start_maximum_drawdown?.year_maximum_drawdown, 'drawdown');
        const ddLabels = Array.from(new Set([...idxDd.labels, ...stDd.labels])).sort();
        const idxDdVals = ddLabels.map(y => idxDd.map.get(y) ?? null);
        const stDdVals = ddLabels.map(y => stDd.map.get(y) ?? null);
        buildLineChart(
                'chart-annual-drawdown',
                'annualDrawdown',
                ddLabels,
                [
                    {
                        label: '指数最大回撤 (%)',
                        data: idxDdVals.map(v => v === null ? null : v * 100),
                        borderColor: '#dc3545',
                        backgroundColor: 'rgba(220,53,69,0.08)',
                        tension: 0.1,
                        fill: true
                    },
                    {
                        label: '模型最大回撤 (%)',
                        data: stDdVals.map(v => v === null ? null : v * 100),
                        borderColor: '#fd7e14',
                        backgroundColor: 'rgba(253,126,20,0.08)',
                        tension: 0.1,
                        fill: true
                    }
                ],
                'Drawdown (%)'
        );

        const kamaIdx = Biz.normalizeYearSeries(r.index_kama_ratio, 'kama_ratio');
        const kamaSt = Biz.normalizeYearSeries(r.start_kama_ratio, 'kama_ratio');
        const kamaLabels = Array.from(new Set([...kamaIdx.labels, ...kamaSt.labels])).sort();
        const kamaIdxVals = kamaLabels.map(y => kamaIdx.map.get(y) ?? null);
        const kamaStVals = kamaLabels.map(y => kamaSt.map.get(y) ?? null);
        buildLineChart(
                'chart-kama',
                'kama',
                kamaLabels,
                [
                    {
                        label: '指数Kama',
                        data: kamaIdxVals,
                        borderColor: '#0dcaf0',
                        backgroundColor: 'rgba(13,202,240,0.08)',
                        tension: 0.1,
                        fill: true
                    },
                    {
                        label: '模型Kama',
                        data: kamaStVals,
                        borderColor: '#6610f2',
                        backgroundColor: 'rgba(102,16,242,0.08)',
                        tension: 0.1,
                        fill: true
                    }
                ],
                'Kama Ratio'
        );

        const sotIdx = Biz.normalizeYearSeries(r.index_sortino_ratio, 'sortino_ratio');
        const sotSt = Biz.normalizeYearSeries(r.start_sortino_ratio, 'sortino_ratio');
        const sotLabels = Array.from(new Set([...sotIdx.labels, ...sotSt.labels])).sort();
        const sotIdxVals = sotLabels.map(y => sotIdx.map.get(y) ?? null);
        const sotStVals = sotLabels.map(y => sotSt.map.get(y) ?? null);
        buildLineChart(
                'chart-sotino',
                'sotino',
                sotLabels,
                [
                    {
                        label: '指数Sotino',
                        data: sotIdxVals,
                        borderColor: '#20c997',
                        backgroundColor: 'rgba(32,201,151,0.08)',
                        tension: 0.1,
                        fill: true
                    },
                    {
                        label: '模型Sotino',
                        data: sotStVals,
                        borderColor: '#d63384',
                        backgroundColor: 'rgba(214,51,132,0.08)',
                        tension: 0.1,
                        fill: true
                    }
                ],
                'Sotino Ratio'
        );

        const volLabels = ['指数', '模型'];
        const volVals = [
            r.index_monthly_return_volatility !== undefined ? r.index_monthly_return_volatility : null,
            r.start_monthly_return_volatility !== undefined ? r.start_monthly_return_volatility : null
        ];
        destroyChart('monthlyVol');
        const volEl = document.getElementById('chart-monthly-vol');
        if (volEl) {
            state.charts.monthlyVol = new Chart(volEl, {
                type: 'bar',
                data: {
                    labels: volLabels,
                    datasets: [{
                        label: '月收益率波动率',
                        data: volVals,
                        backgroundColor: ['rgba(13,110,253,0.5)', 'rgba(25,135,84,0.5)'],
                        borderColor: ['#0d6efd', '#198754'],
                        borderWidth: 1
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    scales: {y: {title: {display: true, text: 'Volatility'}}}
                }
            });
        }

        renderMonthlyExcessReturnsChart(r);
        renderSharpeCompare(r);
        renderExcessMetricsChart(r);
        renderRepairDaysChart(r);
        renderProfitMonthly(r);
    }

    function renderMonthlyExcessReturnsChart(r) {
        const el = document.getElementById('chart-monthly-excess-returns');
        if (!el) return;
        destroyChart('monthlyExcessReturns');

        const list = Array.isArray(r.monthly_excess_returns) ? r.monthly_excess_returns : [];
        const sorted = list
            .filter(x => x && x.year_month)
            .slice()
            .sort((a, b) => String(a.year_month).localeCompare(String(b.year_month)));

        const labels = sorted.map(x => String(x.year_month));
        const vals = sorted.map(x => (x.monthly_excess_return_diff ?? null));
        const valsPct = vals.map(v => v === null ? null : Number(v) * 100);
        const colors = vals.map(v => (v ?? 0) >= 0 ? 'rgba(25,135,84,0.55)' : 'rgba(220,53,69,0.55)');
        const borderColors = vals.map(v => (v ?? 0) >= 0 ? '#198754' : '#dc3545');

        state.charts.monthlyExcessReturns = new Chart(el, {
            type: 'bar',
            data: {
                labels,
                datasets: [{
                    label: '月超额收益 (%)',
                    data: valsPct,
                    backgroundColor: colors,
                    borderColor: borderColors,
                    borderWidth: 1
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                scales: {
                    y: {title: {display: true, text: 'Excess Return (%)'}},
                    x: {ticks: {autoSkip: true, maxRotation: 60, minRotation: 0}}
                }
            }
        });
    }

    

    

    function renderSharpeCompare(r) {
        const idxSeries = Biz.sharpeEntriesToSeries(r.index_sharpe_ratios);
        const stSeries = Biz.sharpeEntriesToSeries(r.start_sharpe_ratios);
        const labels = Array.from(new Set([...idxSeries.map(x => x.key), ...stSeries.map(x => x.key)])).sort((a, b) => {
            if (a === 'all' && b !== 'all') return -1;
            if (b === 'all' && a !== 'all') return 1;
            return String(a).localeCompare(String(b));
        });
        const idxMap = new Map(idxSeries.map(x => [x.key, x.sharpe]));
        const stMap = new Map(stSeries.map(x => [x.key, x.sharpe]));
        const idxVals = labels.map(k => idxMap.get(k) ?? null);
        const stVals = labels.map(k => stMap.get(k) ?? null);

        const el = document.getElementById('chart-sharpe-compare');
        if (!el) return;
        destroyChart('sharpeCompare');
        state.charts.sharpeCompare = new Chart(el, {
            type: 'bar',
            data: {
                labels,
                datasets: [
                    {
                        label: '指数夏普',
                        data: idxVals,
                        backgroundColor: 'rgba(13,110,253,0.45)',
                        borderColor: '#0d6efd',
                        borderWidth: 1
                    },
                    {
                        label: '模型夏普',
                        data: stVals,
                        backgroundColor: 'rgba(25,135,84,0.45)',
                        borderColor: '#198754',
                        borderWidth: 1
                    }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                scales: {
                    y: {title: {display: true, text: 'Sharpe Ratio'}},
                    x: {ticks: {autoSkip: false, maxRotation: 60, minRotation: 20}}
                }
            }
        });
    }

    

    function renderProfitMonthly(r) {
        const idxMap = Biz.profitMonthlySeries(r.index_profit_monthly);
        const stMap = Biz.profitMonthlySeries(r.start_profit_monthly);
        const labels = Array.from(new Set([...idxMap.keys(), ...stMap.keys()])).sort();
        const idxVals = labels.map(y => (idxMap.get(y) ?? null));
        const stVals = labels.map(y => (stMap.get(y) ?? null));

        const el = document.getElementById('chart-profit-monthly');
        if (!el) return;
        destroyChart('profitMonthly');
        state.charts.profitMonthly = new Chart(el, {
            type: 'line',
            data: {
                labels,
                datasets: [
                    {
                        label: '指数盈利月占比 (%)',
                        data: idxVals.map(v => v === null ? null : v * 100),
                        borderColor: '#0d6efd',
                        backgroundColor: 'rgba(13,110,253,0.08)',
                        tension: 0.1,
                        fill: true
                    },
                    {
                        label: '模型盈利月占比 (%)',
                        data: stVals.map(v => v === null ? null : v * 100),
                        borderColor: '#198754',
                        backgroundColor: 'rgba(25,135,84,0.08)',
                        tension: 0.1,
                        fill: true
                    }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                scales: {
                    y: {title: {display: true, text: 'Percentage (%)'}, beginAtZero: true, max: 100}
                }
            }
        });
    }

    function renderExcessMetricsChart(r) {
        const el = document.getElementById('chart-excess-metrics');
        if (!el) return;
        destroyChart('excessMetrics');
        state.charts.excessMetrics = new Chart(el, {
            type: 'bar',
            data: {
                labels: ['excess_sharpe', 'excess_sortino'],
                datasets: [{
                    label: 'Value',
                    data: [r.excess_sharpe ?? null, r.excess_sortino ?? null],
                    backgroundColor: ['rgba(13,110,253,0.5)', 'rgba(25,135,84,0.5)'],
                    borderColor: ['#0d6efd', '#198754'],
                    borderWidth: 1
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                scales: {
                    y: {title: {display: true, text: 'Metric Value'}}
                }
            }
        });
    }

    function renderRepairDaysChart(r) {
        const el = document.getElementById('chart-repair-days');
        if (!el) return;
        destroyChart('repairDays');

        const rows = Biz.repairDaysValues(r);
        if (rows.length === 0) return;

        state.charts.repairDays = new Chart(el, {
            type: 'bar',
            data: {
                labels: rows.map(([key]) => key),
                datasets: [{
                    label: 'Repair Days',
                    data: rows.map(([, value]) => Number(value)),
                    backgroundColor: ['rgba(13,110,253,0.45)', 'rgba(25,135,84,0.45)', 'rgba(253,126,20,0.45)'].slice(0, rows.length),
                    borderColor: ['#0d6efd', '#198754', '#fd7e14'].slice(0, rows.length),
                    borderWidth: 1
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                scales: {
                    y: {title: {display: true, text: 'Days'}}
                }
            }
        });
        return;

        const idxMap = repairDaysEntries(r.index_maximum_number_of_backtest_repair_days);
        const stMap = repairDaysEntries(r.start_maximum_number_of_backtest_repair_days);
        const exMap = repairDaysEntries(r.excess_maximum_number_of_backtest_repair_days);
        const labels = Array.from(new Set([...idxMap.keys(), ...stMap.keys(), ...exMap.keys()])).sort();

        state.charts.repairDays = new Chart(el, {
            type: 'bar',
            data: {
                labels,
                datasets: [
                    {
                        label: 'index',
                        data: labels.map(year => idxMap.get(year) ?? null),
                        backgroundColor: 'rgba(13,110,253,0.45)',
                        borderColor: '#0d6efd',
                        borderWidth: 1
                    },
                    {
                        label: 'start',
                        data: labels.map(year => stMap.get(year) ?? null),
                        backgroundColor: 'rgba(25,135,84,0.45)',
                        borderColor: '#198754',
                        borderWidth: 1
                    },
                    {
                        label: 'excess',
                        data: labels.map(year => exMap.get(year) ?? null),
                        backgroundColor: 'rgba(253,126,20,0.45)',
                        borderColor: '#fd7e14',
                        borderWidth: 1
                    }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                scales: {
                    y: {title: {display: true, text: 'Days'}}
                }
            }
        });
    }

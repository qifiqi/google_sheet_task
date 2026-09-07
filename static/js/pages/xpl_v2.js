// 页面脚本（templates/xpl/v2.html 内联脚本原样抽离，F5 de-jinja）。
    let abortController = null;
    const state = {
        worksheets: [],
        spreadsheetId: '',
        lastFetchedSpreadsheetId: '',
        spreadsheetTitle: '',
        lastResults: null,
        lastSheetName: '',
        manualDataTitle: '',
        manualDataSheetName: '',
        wordReportPayload: null,
        wordExportStock: null,
        charts: {}
    };

    function normalizeApiResponse(payload) {
        const isStandard = payload
            && typeof payload === 'object'
            && Object.prototype.hasOwnProperty.call(payload, 'code')
            && Object.prototype.hasOwnProperty.call(payload, 'data');
        const body = isStandard && payload.data && typeof payload.data === 'object'
            ? payload.data
            : payload;
        return {
            ok: isStandard ? payload.code === 0 : body?.status === 'success',
            message: payload?.message || body?.message || '',
            body,
            data: isStandard ? payload.data : body
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

    function getAnalyzeResults(api) {
        return api.body?.results ?? api.data?.results ?? api.data;
    }

    document.addEventListener('DOMContentLoaded', () => {
        document.getElementById('btn-fetch-sheets').addEventListener('click', fetchWorksheets);
        document.getElementById('btn-analyze-v2').addEventListener('click', runActiveV2Analysis);
        document.querySelectorAll('#v2-source-tabs [data-bs-toggle="tab"]').forEach(tab => {
            tab.addEventListener('shown.bs.tab', updateV2AnalyzeButton);
        });
        document.getElementById('btn-select-v2-excel').addEventListener('click', () => {
            document.getElementById('v2-excel-file').click();
        });
        document.getElementById('v2-excel-file').addEventListener('change', handleV2ExcelImport);
        document.getElementById('v2-paste-data').addEventListener('input', () => {
            state.manualDataTitle = '手动数据';
            state.manualDataSheetName = '粘贴数据';
            updateV2PasteStatus();
        });
        document.getElementById('btn-export-v1')?.addEventListener('click', exportV1Details);
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
        updateMeta();
        updateV2PasteStatus();
        restoreV2RuntimeParams();
        document.getElementById('config-downturn-threshold').addEventListener('input', saveV2RuntimeParams);
        document.getElementById('config-upturn-threshold').addEventListener('input', saveV2RuntimeParams);
        document.getElementById('config-daily-extreme-threshold').addEventListener('input', saveV2RuntimeParams);
        document.getElementById('config-daily-drawdown-threshold').addEventListener('input', saveV2RuntimeParams);
        updateV2AnalyzeButton();
    });

    async function copyRawJson() {
        const pre = document.getElementById('pre-raw-json');
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

    function showLoading() {
        const overlay = document.getElementById('loading-overlay');
        if (overlay) overlay.classList.remove('d-none');

        const urlInput = document.getElementById('gs-url');
        const sheetSelect = document.getElementById('gs-sheet-name');
        const btnFetch = document.getElementById('btn-fetch-sheets');
        if (urlInput) urlInput.disabled = true;
        if (sheetSelect) sheetSelect.disabled = true;
        if (btnFetch) btnFetch.disabled = true;
        document.getElementById('btn-analyze-v2').disabled = true;

        const meta = document.getElementById('gs-meta');
        if (meta && meta.textContent) {
            meta.dataset.prev = meta.innerHTML;
            meta.innerHTML = meta.innerHTML + ' <span class="text-body-secondary">| 请求中...</span>';
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

        const hasSheets = state.worksheets && state.worksheets.length > 0;
        if (sheetSelect) sheetSelect.disabled = !hasSheets;
        updateV2AnalyzeButton();

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

    function extractSpreadsheetId(url) {
        if (!url) return '';
        const m1 = url.match(/\/spreadsheets\/d\/([a-zA-Z0-9-_]+)/);
        if (m1 && m1[1]) return m1[1];
        const m2 = url.match(/[?&]id=([a-zA-Z0-9-_]+)/);
        if (m2 && m2[1]) return m2[1];
        return '';
    }

    function updateMeta() {
        const url = document.getElementById('gs-url').value.trim();
        const spreadsheetId = extractSpreadsheetId(url);
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
        updateV2AnalyzeButton();
    }

    function autoFetchWorksheets() {
        const url = document.getElementById('gs-url').value.trim();
        const spreadsheetId = extractSpreadsheetId(url);
        if (!url || !spreadsheetId) return;
        if (spreadsheetId === state.lastFetchedSpreadsheetId) return;
        fetchWorksheets(true);
    }

    async function fetchWorksheets(silent = false) {
        const url = document.getElementById('gs-url').value.trim();
        const spreadsheetId = extractSpreadsheetId(url);
        if (!url || !spreadsheetId) {
            if (!silent) showAlert('请先输入正确的 Google Sheet URL（需要能解析 spreadsheet_id）', 'warning');
            return;
        }

        state.lastFetchedSpreadsheetId = spreadsheetId;

        showLoading();
        abortController = new AbortController();

        try {
            const resp = await fetch('/api/google-sheet/worksheets', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': document.querySelector('meta[name="csrf-token"]')?.content || ''
                },
                body: JSON.stringify({spreadsheet_id: spreadsheetId}),
                signal: abortController.signal
            });
            const data = await resp.json().catch(() => ({}));
            const api = normalizeApiResponse(data);
            if (!resp.ok || !api.ok) {
                throw new Error(api.message || `HTTP error! status: ${resp.status}`);
            }

            const worksheetsPayload = getWorksheetsPayload(api);
            state.worksheets = Array.isArray(worksheetsPayload.worksheets) ? worksheetsPayload.worksheets : [];
            state.spreadsheetTitle = worksheetsPayload.title || '';

            const meta = document.getElementById('gs-meta');
            meta.innerHTML = `<span class="text-body-secondary">spreadsheet_id: </span><span class="fw-semibold">${spreadsheetId}</span>` + (state.spreadsheetTitle ? ` <span class="text-body-secondary">| 标题：</span><span class="fw-semibold">${escapeHtml(state.spreadsheetTitle)}</span>` : '');

            const select = document.getElementById('gs-sheet-name');
            select.innerHTML = '';

            if (state.worksheets.length === 0) {
                select.innerHTML = '<option value="">未找到工作表</option>';
                select.disabled = true;
                updateV2AnalyzeButton();
                if (!silent) showAlert('未找到任何工作表', 'warning');
                return;
            }

            state.worksheets.forEach(name => {
                const opt = document.createElement('option');
                opt.value = name;
                opt.textContent = name;
                select.appendChild(opt);
            });
            select.disabled = false;
            updateV2AnalyzeButton();
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

    function applyV2ExportStyles(sheet) {
        const border = {
            top: {style: 'thin', color: {rgb: 'D0D0D0'}},
            bottom: {style: 'thin', color: {rgb: 'D0D0D0'}},
            left: {style: 'thin', color: {rgb: 'D0D0D0'}},
            right: {style: 'thin', color: {rgb: 'D0D0D0'}}
        };
        const titleStyle = {
            font: {name: 'Microsoft YaHei', sz: 12, bold: true},
            fill: {fgColor: {rgb: 'F7E1A1'}},
            alignment: {horizontal: 'center', vertical: 'center'},
            border
        };
        const headerStyle = {
            font: {name: 'Microsoft YaHei', sz: 11, bold: true},
            fill: {fgColor: {rgb: 'FCECC5'}},
            alignment: {horizontal: 'center', vertical: 'center'},
            border
        };
        const firstColumnStyle = {
            font: {name: 'Microsoft YaHei', sz: 10, bold: true},
            fill: {fgColor: {rgb: 'F7E1A1'}},
            alignment: {horizontal: 'center', vertical: 'center'},
            border
        };
        const bodyStyle = {
            font: {name: 'Microsoft YaHei', sz: 10},
            alignment: {horizontal: 'center', vertical: 'center'},
            border
        };
        const range = XLSX.utils.decode_range(sheet['!ref'] || 'A1:A1');

        for (let row = range.s.r; row <= range.e.r; row += 1) {
            for (let column = range.s.c; column <= range.e.c; column += 1) {
                const address = XLSX.utils.encode_cell({r: row, c: column});
                const cell = sheet[address];
                if (!cell || cell.v === '') continue;
                cell.s = bodyStyle;
            }
        }

        for (let column = 0; column < 4; column += 1) {
            const address = XLSX.utils.encode_cell({r: 0, c: column});
            const cell = sheet[address] || {t: 's', v: ''};
            cell.s = titleStyle;
            sheet[address] = cell;
        }
        [2, 24, 30].forEach(row => {
            for (let column = 0; column <= range.e.c; column += 1) {
                const cell = sheet[XLSX.utils.encode_cell({r: row, c: column})];
                if (cell && cell.v !== '') cell.s = headerStyle;
            }
        });
        for (let row = 3; row <= 23; row += 1) {
            const cell = sheet[XLSX.utils.encode_cell({r: row, c: 0})];
            if (cell && cell.v !== '') cell.s = firstColumnStyle;
        }

        sheet['!cols'] = [
            {wch: 16}, {wch: 28}, {wch: 16}, {wch: 18},
            {wch: 4}, {wch: 4}, {wch: 4}, {wch: 4}, {wch: 4},
            {wch: 16}, {wch: 16}, {wch: 16}
        ];
        sheet['!freeze'] = {xSplit: 0, ySplit: 3, topLeftCell: 'A4', activePane: 'bottomLeft', state: 'frozen'};
    }

    async function exportV1Details() {
        if (!state.lastResults) {
            showAlert('请先完成分析再导出', 'warning');
            return;
        }

        const btn = document.getElementById('btn-export-v1');
        if (btn) btn.disabled = true;

        try {
            const filenameSafeTitle = (state.spreadsheetTitle || 'v1').replaceAll(/[\\/:*?"<>|]/g, '_');
            const filenameSafeSheet = (state.lastSheetName || 'sheet').replaceAll(/[\\/:*?"<>|]/g, '_');
            const defaultFilename = `${filenameSafeTitle}_${filenameSafeSheet}_details.xlsx`;
            const sourceFilename = `${filenameSafeTitle}_${filenameSafeSheet}_details.csv`;

            const resp = await fetch('/api/exports/xpl', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': document.querySelector('meta[name="csrf-token"]')?.content || ''
                },
                body: JSON.stringify({
                    filename: sourceFilename,
                    filename_title:filenameSafeTitle,
                    analyze_result: state.lastResults
                })
            });

            if (!resp.ok) {
                const err = await resp.json().catch(() => ({}));
                const api = normalizeApiResponse(err);
                throw new Error(api.message || `HTTP error! status: ${resp.status}`);
            }

            const workbook = XLSX.read(await resp.text(), {type: 'string'});
            const sheet = workbook.Sheets[workbook.SheetNames[0]];
            applyV2ExportStyles(sheet);
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

    async function exportWordReport() {
        if (!state.lastResults || !state.wordReportPayload) {
            showAlert('请先完成分析再导出', 'warning');
            return;
        }

        if (state.wordReportPayload.report_type !== 'RPT-M') {
            showWordExportOptions();
            return;
        }

        await downloadWordReport(state.wordReportPayload);
    }

    function showWordExportOptions() {
        const input = document.getElementById('word-export-stock');
        const results = document.getElementById('word-export-stock-results');
        state.wordExportStock = null;
        input.value = '';
        results.innerHTML = '';
        results.classList.add('d-none');
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
            const response = await fetch(`/api/search-stocks?q=${encodeURIComponent(keyword)}&page_size=10`, {
                signal: state.wordExportSearchAbortController.signal
            });
            const data = await response.json();
            if (!response.ok || data.status !== 'success') {
                throw new Error(data.message || '股票搜索失败');
            }
            const items = Array.isArray(data.data?.results) ? data.data.results : [];
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
        state.wordExportStock = { code: item.dataset.code, name: item.dataset.name };
        document.getElementById('word-export-stock').value = `${item.dataset.code} · ${item.dataset.name}`;
        document.getElementById('word-export-stock-results').classList.add('d-none');
    }

    async function confirmWordExport() {
        if (!state.wordExportStock) {
            showAlert('请从搜索结果中选择股票', 'warning');
            return;
        }
        const priceMode = document.getElementById('word-export-price-type').value;
        const priceType = {
            kp_price: '开盘价',
            sp_price: '收盘价',
            vwap_price: '加权平均价',
            ohlc_price: 'OHLC（开高低收）',
            random_price: '随机价'
        }[priceMode] || '';
        const payload = JSON.parse(JSON.stringify(state.wordReportPayload));
        payload.products = [{
            stock_code: state.wordExportStock.code,
            product_name: state.wordExportStock.name,
            ratio: '100.00%'
        }];
        payload.metadata = { ...(payload.metadata || {}), price_type: priceType };
        bootstrap.Modal.getInstance(document.getElementById('word-export-options-modal'))?.hide();
        await downloadWordReport(payload);
    }

    async function downloadWordReport(payload) {

        const button = document.getElementById('btn-export-word');
        if (button) button.disabled = true;
        try {
            const response = await fetch('/api/exports/backtest-reports/word', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': document.querySelector('meta[name="csrf-token"]')?.content || ''
                },
                body: JSON.stringify(payload)
            });
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

    function getActiveV2Source() {
        return document.querySelector('#v2-source-tabs .nav-link.active')?.id || '';
    }

    const V2_RUNTIME_PARAMS_STORAGE_KEY = 'v2_runtime_params';

    function parseV2ThresholdInput(inputId, fallback) {
        const raw = document.getElementById(inputId)?.value?.trim();
        if (raw === '' || raw === undefined) return fallback;
        const value = Number(raw);
        return Number.isFinite(value) ? value : fallback;
    }

    function collectV2RuntimeParams() {
        // 页面输入按百分比填写，payload 统一转换为小数阈值。
        return {
            market_downturn_threshold: parseV2ThresholdInput('config-downturn-threshold', -2) / 100,
            market_upturn_threshold: parseV2ThresholdInput('config-upturn-threshold', 2) / 100,
            daily_extreme_threshold: parseV2ThresholdInput('config-daily-extreme-threshold', 2) / 100,
            daily_drawdown_threshold: parseV2ThresholdInput('config-daily-drawdown-threshold', 5) / 100
        };
    }

    function saveV2RuntimeParams() {
        try {
            localStorage.setItem(V2_RUNTIME_PARAMS_STORAGE_KEY, JSON.stringify(collectV2RuntimeParams()));
        } catch (e) {
            // localStorage 不可用（隐私模式等）时忽略，配置仅在当前页面生效。
        }
    }

    function restoreV2RuntimeParams() {
        let saved = null;
        try {
            saved = JSON.parse(localStorage.getItem(V2_RUNTIME_PARAMS_STORAGE_KEY) || 'null');
        } catch (e) {
            saved = null;
        }
        if (!saved || typeof saved !== 'object') return;
        if (Number.isFinite(saved.market_downturn_threshold)) {
            document.getElementById('config-downturn-threshold').value = Number((saved.market_downturn_threshold * 100).toFixed(6));
        }
        if (Number.isFinite(saved.market_upturn_threshold)) {
            document.getElementById('config-upturn-threshold').value = Number((saved.market_upturn_threshold * 100).toFixed(6));
        }
        if (Number.isFinite(saved.daily_extreme_threshold)) {
            document.getElementById('config-daily-extreme-threshold').value = Number((saved.daily_extreme_threshold * 100).toFixed(6));
        }
        if (Number.isFinite(saved.daily_drawdown_threshold)) {
            document.getElementById('config-daily-drawdown-threshold').value = Number((saved.daily_drawdown_threshold * 100).toFixed(6));
        }
    }

    function updateV2AnalyzeButton() {
        const button = document.getElementById('btn-analyze-v2');
        if (!button || abortController) return;

        if (getActiveV2Source() === 'google-sheet-tab') {
            button.disabled = !(state.worksheets && state.worksheets.length > 0);
            return;
        }
        if (getActiveV2Source() === 'paste-data-tab') {
            try {
                prepareV2DataRows(document.getElementById('v2-paste-data').value);
                button.disabled = false;
            } catch (e) {
                button.disabled = true;
            }
            return;
        }
        button.disabled = true;
    }

    async function runActiveV2Analysis() {
        if (getActiveV2Source() === 'google-sheet-tab') {
            await runAnalyzeV2Google();
            return;
        }
        if (getActiveV2Source() === 'paste-data-tab') {
            await runAnalyzeV2Paste();
        }
    }

    async function runAnalyzeV2Google() {
        const url = document.getElementById('gs-url').value.trim();
        const spreadsheetId = extractSpreadsheetId(url);
        const sheetName = document.getElementById('gs-sheet-name').value;
        if (!url) {
            showAlert('请输入 Google Sheet URL', 'warning');
            return;
        }
        if (!sheetName) {
            showAlert('请选择工作表', 'warning');
            return;
        }

        const runtimeParams = collectV2RuntimeParams();
        await requestV2Analysis('/xpl/v1/analyze', {
            google_sheet_url: url,
            spreadsheet_id: spreadsheetId,
            google_sheet_name: sheetName,
            runtime_params: runtimeParams
        }, sheetName, state.spreadsheetTitle || 'Google Sheet', {
            report_type: 'RPT-S',
            google_sheet_url: url,
            spreadsheet_id: spreadsheetId,
            google_sheet_name: sheetName,
            metadata: { sheet_title: state.spreadsheetTitle },
            runtime_params: runtimeParams
        });
    }

    async function runAnalyzeV2Paste(wordReportPayload = null) {
        let prepared;
        try {
            prepared = prepareV2DataRows(document.getElementById('v2-paste-data').value);
        } catch (e) {
            showAlert(e.message || '请输入有效的三列数据', 'warning');
            return;
        }

        document.getElementById('v2-paste-data').value = prepared.text;
        updateV2PasteStatus();
        const runtimeParams = collectV2RuntimeParams();
        await requestV2Analysis('/xpl/analyze', {
            data: prepared.text,
            time_format: 'auto',
            runtime_params: runtimeParams
        }, state.manualDataSheetName || '粘贴数据', state.manualDataTitle || '手动数据',
        wordReportPayload || {
            report_type: 'RPT-S',
            returns: prepared.text.split('\n').map((line) => {
                const [date, indexReturn, startReturn] = line.split('\t');
                return {
                    date,
                    index_return: Number(indexReturn),
                    start_return: Number(startReturn)
                };
            }),
            metadata: { model_version: '单产品' },
            runtime_params: runtimeParams
        });
    }

    async function requestV2Analysis(endpoint, body, sheetName, title, wordReportPayload = null) {
        showLoading();
        abortController = new AbortController();

        try {
            const resp = await fetch(endpoint, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': document.querySelector('meta[name="csrf-token"]')?.content || ''
                },
                body: JSON.stringify(body),
                signal: abortController.signal
            });
            const data = await resp.json().catch(() => ({}));
            const api = normalizeApiResponse(data);
            if (!resp.ok || !api.ok) {
                throw new Error(api.message || `HTTP error! status: ${resp.status}`);
            }

            const results = getAnalyzeResults(api);
            if (!results) {
                showAlert('后端未返回 results', 'warning');
                return;
            }

            state.lastResults = results;
            state.lastSheetName = sheetName;
            state.spreadsheetTitle = title;
            state.wordReportPayload = wordReportPayload;
            const exportBtn = document.getElementById('btn-export-v1');
            if (exportBtn) exportBtn.disabled = false;
            const wordExportBtn = document.getElementById('btn-export-word');
            if (wordExportBtn) wordExportBtn.disabled = !wordReportPayload;

            renderSummary(results);
            renderTables(results);
            renderCharts(results);
            showAlert('V2 分析完成', 'success');
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

    function prepareV2DataRows(text) {
        const rows = text.split(/\r?\n/)
            .map(line => line.trim())
            .filter(Boolean)
            .map(line => line.split(/[\t,\s]+/).slice(0, 3));
        return prepareV2Rows(rows);
    }

    function prepareV2Rows(rows) {
        const dataRows = rows.filter(row => row.some(cell => String(cell ?? '').trim()));
        if (!dataRows.length) {
            throw new Error('请至少输入一行回测数据');
        }

        const hasHeader = isV2HeaderRow(dataRows[0]);
        const usableRows = hasHeader ? dataRows.slice(1) : dataRows;
        if (!usableRows.length) {
            throw new Error('列头后没有可分析的数据');
        }

        const normalizedRows = usableRows.map((row, index) => {
            const values = row.slice(0, 3).map(value => String(value ?? '').trim());
            if (values.length < 3 || !isV2Date(values[0]) || !isV2Number(values[1]) || !isV2Number(values[2])) {
                throw new Error(`第 ${index + (hasHeader ? 2 : 1)} 行不是有效的日期、指数收益、模型收益数据`);
            }
            return values;
        });

        return {
            text: normalizedRows.map(row => row.join('\t')).join('\n'),
            rowCount: normalizedRows.length,
            hasHeader
        };
    }

    function isV2HeaderRow(row) {
        const normalize = value => String(value ?? '').trim().toLowerCase().replace(/[\s_\-]/g, '');
        const headers = [
            new Set(['date', '日期', '时间', '交易日']),
            new Set(['indexreturn', '指数收益', '指数收益率']),
            new Set(['startreturn', '模型收益', '模型收益率', '策略收益', '策略收益率'])
        ];
        const values = row.slice(0, 3).map(normalize);
        if (values.every((value, index) => headers[index].has(value))) {
            return true;
        }
        return !isV2Date(row[0]) && !isV2Number(row[1]) && !isV2Number(row[2]);
    }

    function isV2Date(value) {
        const text = String(value ?? '').trim();
        if (!text) return false;
        return !Number.isNaN(Date.parse(text));
    }

    function isV2Number(value) {
        const text = String(value ?? '').trim().replace(/%$/, '');
        return text !== '' && Number.isFinite(Number(text));
    }

    function updateV2PasteStatus() {
        const status = document.getElementById('v2-paste-status');
        try {
            const prepared = prepareV2DataRows(document.getElementById('v2-paste-data').value);
            status.className = 'small text-success mb-3';
            status.textContent = `已识别 ${prepared.rowCount} 行有效数据${prepared.hasHeader ? '，已跳过列头' : ''}。`;
        } catch (e) {
            status.className = 'small text-body-secondary mb-3';
            status.textContent = '需要三列：日期、指数收益、模型收益。';
        }
        updateV2AnalyzeButton();
    }

    async function handleV2ExcelImport(event) {
        const file = event.target.files[0];
        const status = document.getElementById('v2-excel-status');
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
                .map(row => [formatV2ExcelDate(row[0]), row[1], row[2]]);
            const prepared = prepareV2Rows(rows);
            document.getElementById('v2-paste-data').value = prepared.text;
            state.manualDataTitle = file.name.replace(/\.[^.]+$/, '') || '本地 Excel';
            state.manualDataSheetName = firstSheetName;
            status.className = 'small text-success mt-2';
            status.textContent = `已读取“${firstSheetName}”的 ${prepared.rowCount} 行数据${prepared.hasHeader ? '，已跳过列头' : ''}。`;
            updateV2PasteStatus();
            bootstrap.Tab.getOrCreateInstance(document.getElementById('paste-data-tab')).show();
            showAlert('Excel 已导入，请确认数据后分析', 'success');
        } catch (e) {
            status.className = 'small text-danger mt-2';
            status.textContent = `导入失败：${e.message || '无法读取 Excel 文件'}`;
        } finally {
            event.target.value = '';
        }
    }

    function formatV2ExcelDate(value) {
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

    function setPreJson(elId, obj) {
        const el = document.getElementById(elId);
        if (!el) return;
        try {
            el.textContent = JSON.stringify(obj, null, 2);
        } catch (e) {
            el.textContent = String(obj);
        }
    }

    function maxYearlyRepairDays(yearlyRepairDays) {
        if (!yearlyRepairDays || typeof yearlyRepairDays !== 'object' || Array.isArray(yearlyRepairDays)) {
            return null;
        }
        const values = Object.values(yearlyRepairDays)
            .map(Number)
            .filter(Number.isFinite);
        return values.length ? Math.max(...values) : null;
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
            excess_maximum_number_of_backtest_repair_days: '超额最大回测天数',
            year_index_yearly_max_repair_days: '指数年最大回测修复天数',
            year_start_yearly_max_repair_days: '策略年最大回测修复天数'
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

        const scalarValues = [
            ...scalarKeys.map(k => [k, r[k]]),
            ['year_index_yearly_max_repair_days', maxYearlyRepairDays(r.year_index_yearly_max_repair_days)],
            ['year_start_yearly_max_repair_days', maxYearlyRepairDays(r.year_start_yearly_max_repair_days)]
        ];

        scalarValues.forEach(([k, value]) => {
            if (value === undefined || value === null) return;
            const tr = document.createElement('tr');
            let v = value;
            if (k.includes('profit_annual') || k.includes('outperform_year') || k.includes('winning_rate')) {
                v = fmtPct(v, 2);
            } else if (k.includes('repair_days')) {
                v = fmtInt(v);
            } else if (typeof v === 'number') {
                v = fmtNum(v, 6);
            }
            tr.innerHTML = `<td><code>${k}</code></td><td>${scalarNameMap[k] || '-'}</td><td>${v}</td>`;
            tbody.appendChild(tr);
        });
    }

    function fillSheetResultTable(tbodyId, sheetResult) {
        const tbody = document.getElementById(tbodyId);
        if (!tbody) return;
        tbody.innerHTML = '';

        if (!sheetResult || typeof sheetResult !== 'object' || Array.isArray(sheetResult)) {
            tbody.innerHTML = '<tr><td colspan="2" class="text-center text-body-secondary">无数据</td></tr>';
            return;
        }

        const keys = Object.keys(sheetResult).sort();
        if (keys.length === 0) {
            tbody.innerHTML = '<tr><td colspan="2" class="text-center text-body-secondary">无数据</td></tr>';
            return;
        }

        keys.forEach(k => {
            const tr = document.createElement('tr');
            const v = sheetResult[k];
            tr.innerHTML = `<td><code>${k}</code></td><td>${v ?? '-'}</td>`;
            tbody.appendChild(tr);
        });
    }

    // 月超额收益 tab：渲染每个月“模型-指数”的超额收益
    function fillMonthlyExcessReturnsTable(list, tbodyId) {
        const tbody = document.getElementById(tbodyId);
        if (!tbody) return;
        tbody.innerHTML = '';

        if (!Array.isArray(list) || list.length === 0) {
            tbody.innerHTML = '<tr><td colspan="4" class="text-center text-body-secondary">无数据</td></tr>';
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

    // 标量 tab：渲染页面顶部摘要对应的关键标量
    function renderTabScalars(r) {
        fillScalarsTable('tbl-scalars', r);
    }

    // Sheet结果 tab：渲染 analyze_v1 返回的 sheet_result（字典键值）
    function renderTabSheetResult(r) {
        fillSheetResultTable('tbl-sheet-result', r.sheet_result);
    }

    // 年度收益/回撤 tab：渲染年度收益对比、年度回撤对比、月超额收益百分比
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

    // 年超额收益 tab
    function renderTabExcessReturns(r) {
        fillExcessReturnsTable(r);
    }

    // 月超额收益 tab（monthly_excess_returns）
    function renderTabMonthlyExcessReturns(r) {
        fillMonthlyExcessReturnsTable(r.monthly_excess_returns, 'tbl-monthly-excess-returns');
    }

    // 卡玛 tab
    function renderTabKama(r) {
        fillKamaMerged(r.index_kama_ratio, r.start_kama_ratio, 'tbl-kama');
    }

    // 索提诺 tab
    function renderTabSotino(r) {
        fillSotinoMerged(r.index_sortino_ratio, r.start_sortino_ratio, 'tbl-sotino');
    }

    // 夏普 tab
    function renderTabSharpe(r) {
        fillSharpeMerged(r.index_sharpe_ratios, r.start_sharpe_ratios, 'tbl-sharpe');
    }

    // 盈利统计 tab
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

    function fillExcessReturnsTable(r) {
        const tbody = document.getElementById('tbl-excess-returns');
        if (!tbody) return;
        tbody.innerHTML = '';

        if (!Array.isArray(r.excess_returns)) {
            tbody.innerHTML = '<tr><td colspan="5" class="text-center text-body-secondary">无数据</td></tr>';
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
            tbody.innerHTML = '<tr><td colspan="4" class="text-center text-body-secondary">无数据</td></tr>';
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
            tbody.innerHTML = '<tr><td colspan="7" class="text-center text-body-secondary">无数据</td></tr>';
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
            tbody.innerHTML = '<tr><td colspan="4" class="text-center text-body-secondary">无数据</td></tr>';
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
            tbody.innerHTML = '<tr><td colspan="7" class="text-center text-body-secondary">无数据</td></tr>';
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
            tbody.innerHTML = '<tr><td colspan="7" class="text-center text-body-secondary">无数据</td></tr>';
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
            tbody.innerHTML = '<tr><td colspan="11" class="text-center text-body-secondary">无数据</td></tr>';
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

    function repairDaysValues(r) {
        return [
            ['index', r.index_maximum_number_of_backtest_repair_days],
            ['start', r.start_maximum_number_of_backtest_repair_days],
            ['excess', r.excess_maximum_number_of_backtest_repair_days],
            ['year_index_max', maxYearlyRepairDays(r.year_index_yearly_max_repair_days)],
            ['year_start_max', maxYearlyRepairDays(r.year_start_yearly_max_repair_days)]
        ].filter(([, value]) => value !== undefined && value !== null && !Number.isNaN(Number(value)));
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
            tbody.innerHTML = '<tr><td colspan="4" class="text-center text-body-secondary">无数据</td></tr>';
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
            tbody.innerHTML = '<tr><td colspan="2" class="text-center text-body-secondary">无数据</td></tr>';
            return;
        }
        list.forEach(item => {
            const tr = document.createElement('tr');
            tr.innerHTML = `<td>${item?.year ?? '-'}</td><td>${fmtPct(item?.profit_monthly_percentage, 2)}</td>`;
            tbody.appendChild(tr);
        });
    }

    function renderTables(r) {
        setPreJson('pre-raw-json', r);
        renderTabScalars(r);
        renderTabSheetResult(r);
        renderTabAnnualAndDrawdown(r);
        renderTabExcessReturns(r);
        renderTabMonthlyExcessReturns(r);
        renderTabKama(r);
        renderTabSotino(r);
        renderTabSharpe(r);
        renderTabExcessMetrics(r);
        renderTabRepairDays(r);
        renderTabProfit(r);
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
        state.charts[key] = new Chart(el, {
            type: 'line',
            data: {labels, datasets},
            options: {
                responsive: true,
                maintainAspectRatio: false,
                interaction: {mode: 'index', intersect: false},
                scales: {
                    y: {title: {display: true, text: yTitle}},
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

    function renderCharts(r) {
        const idxAnnual = normalizeYearSeries(r.index_returns_rate, 'annual_return');
        const stAnnual = normalizeYearSeries(r.start_returns_rate, 'annual_return');
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
                    label: '年超额收益(%)',
                    data: exVals,
                    backgroundColor: exVals.map(v => v >= 0 ? 'rgba(25,135,84,0.5)' : 'rgba(220,53,69,0.5)'),
                    borderColor: exVals.map(v => v >= 0 ? '#198754' : '#dc3545'),
                    borderWidth: 1
                }],
                'Excess Return (%)'
        );

        const idxDd = normalizeYearSeries(r.index_maximum_drawdown?.year_maximum_drawdown, 'drawdown');
        const stDd = normalizeYearSeries(r.start_maximum_drawdown?.year_maximum_drawdown, 'drawdown');
        const ddLabels = Array.from(new Set([...idxDd.labels, ...stDd.labels])).sort();
        const idxDdVals = ddLabels.map(y => idxDd.map.get(y) ?? null);
        const stDdVals = ddLabels.map(y => stDd.map.get(y) ?? null);
        buildLineChart(
                'chart-annual-drawdown',
                'annualDrawdown',
                ddLabels,
                [
                    {
                        label: '指数最大回撤(%)',
                        data: idxDdVals.map(v => v === null ? null : v * 100),
                        borderColor: '#dc3545',
                        backgroundColor: 'rgba(220,53,69,0.08)',
                        tension: 0.1,
                        fill: true
                    },
                    {
                        label: '模型最大回撤(%)',
                        data: stDdVals.map(v => v === null ? null : v * 100),
                        borderColor: '#fd7e14',
                        backgroundColor: 'rgba(253,126,20,0.08)',
                        tension: 0.1,
                        fill: true
                    }
                ],
                'Drawdown (%)'
        );

        const kamaIdx = normalizeYearSeries(r.index_kama_ratio, 'kama_ratio');
        const kamaSt = normalizeYearSeries(r.start_kama_ratio, 'kama_ratio');
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

        const sotIdx = normalizeYearSeries(r.index_sortino_ratio, 'sortino_ratio');
        const sotSt = normalizeYearSeries(r.start_sortino_ratio, 'sortino_ratio');
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
                    label: '月超额收益(%)',
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

    function renderSharpeCompare(r) {
        const idxSeries = sharpeEntriesToSeries(r.index_sharpe_ratios);
        const stSeries = sharpeEntriesToSeries(r.start_sharpe_ratios);
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

    function renderProfitMonthly(r) {
        const idxMap = profitMonthlySeries(r.index_profit_monthly);
        const stMap = profitMonthlySeries(r.start_profit_monthly);
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
                        label: '指数盈利月占比(%)',
                        data: idxVals.map(v => v === null ? null : v * 100),
                        borderColor: '#0d6efd',
                        backgroundColor: 'rgba(13,110,253,0.08)',
                        tension: 0.1,
                        fill: true
                    },
                    {
                        label: '模型盈利月占比(%)',
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

        const rows = repairDaysValues(r);
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

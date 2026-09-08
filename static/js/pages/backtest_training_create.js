
const TASK_API_BASE = '/api/tasks';
const BACKTEST_TASK_TYPE = 'backtest_training';
const STOCK_SEARCH_DEBOUNCE_MS = 1000;
const DEFAULT_C3_COMMISSION = '0.0350%';
const FIELD_MAP = {
    c7: [
        { key: 'xm', label: 'X Multiplier (xm)' },
        { key: 'ml', label: 'ML (ml)' }
    ],
    c5: [
        { key: 'xm', label: 'X Multiplier (xm)' },
        { key: 'ml', label: 'ML (ml)' }
    ],
    c3: [
        { key: 'xm', label: 'X Multiplier (xm)' },
        { key: 'dbbh1', label: '单边保护 1' },
        { key: 'dbbh2', label: '单边保护 2' },
        { key: 'zlxc', label: '中立限仓' },
        { key: 'zsgz', label: '指数跟踪' },
        { key: 'ywf1', label: '一窝蜂 S' },
        { key: 'ywf2', label: '一窝蜂 B' }
    ]
};

let spreadsheetId = '';
let sheetTitle = '';
let selectedWorksheetName = '';
let currentModelVersion = 'c3';
let currentC7ModelVersion = 'c7_0_2';
let currentFields = FIELD_MAP.c3;
let backtestGoogleSheets = [];
let selectedGoogleSheetId = null;
let importedParameterRows = [];
let currentExcelImport = null;
let backtestTokens = [];
let isCreatingTask = false;
let stockSearchTimer = null;
let lastEditablePriceMode = 'sp_price';
let stockSearchAbortController = null;
let lastStockSearchResults = [];
let selectedStockSuggestion = null;
let taskNameTouched = false;

const currentYear = new Date().getFullYear();
const BACKTEST_GOOGLE_SHEETS_CACHE_KEY = 'backtest_training_google_sheets_v2';
const BACKTEST_GOOGLE_SHEETS_CACHE_TTL = 5 * 60 * 1000;
const PARAMETER_HELP_HTML = `
    <div class="param-help-content">
        <div><strong>C3 粘贴</strong>：每行 6 个业务参数时顺序为 <code>xm</code>、<code>单边保护 1</code>、<code>中立限仓</code>、<code>指数跟踪</code>、<code>一窝蜂 S</code>、<code>一窝蜂 B</code>，系统自动计算 <code>单边保护 2 = 2 - 单边保护 1</code>；每行 7 个业务参数时按完整字段处理。</div>
        <div><strong>C3 复制</strong>：复制当前表格为 Tab 分隔行，包含 <code>Commission</code> 和后续参数列，可直接贴到其他任务或 Excel。</div>
        <div><strong>C5 粘贴/复制</strong>：每行 2 列，顺序为 <code>X Multiplier</code>、<code>ML</code>。</div>
        <div><strong>C7 粘贴/复制</strong>：每行 2 列，顺序为 <code>X Multiplier</code>、<code>ML</code>。</div>
    </div>
`;
const modelUrlInput = document.getElementById('modelUrl');
const stockCodeInput = document.getElementById('stockCode');
const stockSearchResults = document.getElementById('stockSearchResults');
const analyzeBtn = document.getElementById('analyzeBtn');
const googleSheetMenuList = document.getElementById('googleSheetMenuList');
const configToggleBtn = document.getElementById('configToggleBtn');
const taskConfigCollapse = document.getElementById('taskConfigCollapse');
const taskNameInput = document.getElementById('taskName');
const tokenIdSelect = document.getElementById('tokenId');
const commissionInput = document.getElementById('commissionInput');
const commissionConfigGroup = document.getElementById('commissionConfigGroup');
const recentYearsCheck = document.getElementById('recentYearsCheck');
const fullYearsCheck = document.getElementById('fullYearsCheck');
const recentYearsOptions = document.getElementById('recentYearsOptions');
const fullYearsOptions = document.getElementById('fullYearsOptions');
const recentYearsCheckboxes = document.getElementById('recentYearsCheckboxes');
const fullYearsCheckboxes = document.getElementById('fullYearsCheckboxes');
const yearsContainerWrapper = document.getElementById('yearsContainerWrapper');
const recentYearsDisplay = document.getElementById('recentYearsDisplay');
const fullYearsDisplay = document.getElementById('fullYearsDisplay');
const recentYearsInfoDisplay = document.getElementById('recentYearsInfoDisplay');
const fullYearsInfoDisplay = document.getElementById('fullYearsInfoDisplay');
const endDateInput = document.getElementById('endDateInput');
const yearsDisplay = document.getElementById('yearsDisplay');
const sheetInfo = document.getElementById('sheetInfo');
const modelVersionBadge = document.getElementById('modelVersionBadge');
const sheetTitleEl = document.getElementById('sheetTitle');
const sheetNamesEl = document.getElementById('sheetNames');
const emptyHint = document.getElementById('emptyHint');
const paramTableHead = document.getElementById('paramTableHead');
const paramTableBody = document.getElementById('paramTableBody');
const excelFileInput = document.getElementById('excelFileInput');
const importExcelBtn = document.getElementById('importExcelBtn');
const paramHelpBtn = document.getElementById('paramHelpBtn');
const pasteClipboardBtn = document.getElementById('pasteClipboardBtn');
const copyParamBtn = document.getElementById('copyParamBtn');
const addParamBtn = document.getElementById('addParamBtn');
const createBtn = document.getElementById('createBtn');
const excelImportStatus = document.getElementById('excelImportStatus');
const marketTypeSelect = document.getElementById('market_type');
let stockMarkets = [];

function bindMarketTypeSelect() {
    marketTypeSelect.addEventListener('change', () => {
        if (selectedStockSuggestion) {
            if (marketTypeSelect.value !== selectedStockSuggestion.market_type) selectedStockSuggestion = null;
        }
        syncCommissionWithMarketType(marketTypeSelect.value);
        updateStockMeta();
    });
}

async function loadStockMarkets() {
    try {
        const payload = await Api.endpoints.meta.enums();
        stockMarkets = payload?.stock_markets || [];
        marketTypeSelect.innerHTML = stockMarkets.map((market) =>
            `<option value="${escapeHtml(market.value)}">${escapeHtml(market.label)}</option>`
        ).join('');
        marketTypeSelect.value = 'cn';
        bindMarketTypeSelect();
    } catch (error) {
        marketTypeSelect.innerHTML = '<option value="">市场枚举加载失败</option>';
        marketTypeSelect.disabled = true;
    }
}

function escapeHtml(value) {
    return String(value ?? '')
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/\"/g, '&quot;')
        .replace(/'/g, '&#39;');
}

function inferModelVersion(title) {
    const normalized = String(title || '').toUpperCase();
    if (normalized.includes('C7')) {
        return 'c7';
    }
    return normalized.includes('C5') || normalized.includes('C4') ? 'c5' : 'c3';
}

function resolveModelVersion(version) {
    return ['c5', 'c7'].includes(version) ? version : 'c3';
}

function inferC7ModelVersion(value) {
    const normalized = String(value || '').toUpperCase();
    return normalized.includes('C7.0.3') || normalized.includes('C7_0_3')
        ? 'c7_0_3'
        : 'c7_0_2';
}

function isC7V03Model() {
    return resolveModelVersion(currentModelVersion) === 'c7'
        && currentC7ModelVersion === 'c7_0_3';
}

function syncPriceModeForModel() {
    const priceModeInput = document.getElementById('priceModeInput');
    const ohlcOption = priceModeInput?.querySelector('option[value="ohlc_price"]');
    if (!priceModeInput) {
        return;
    }

    if (isC7V03Model()) {
        if (!priceModeInput.disabled && priceModeInput.value !== 'ohlc_price') {
            lastEditablePriceMode = priceModeInput.value;
        }
        if (ohlcOption) {
            ohlcOption.disabled = false;
        }
        priceModeInput.value = 'ohlc_price';
        priceModeInput.disabled = true;
        return;
    }

    if (priceModeInput.disabled && priceModeInput.value === 'ohlc_price') {
        priceModeInput.value = lastEditablePriceMode;
    }
    priceModeInput.disabled = false;
    if (ohlcOption) {
        ohlcOption.disabled = true;
    }
}

function normalizeMarketTypeValue(value) {
    const market = String(value || '').trim().toLowerCase();
    return stockMarkets.some((item) => item.value === market) ? market : (stockMarkets[0]?.value || 'cn');
}

function extractSpreadsheetId(value) {
    const rawValue = String(value || '').trim();
    const urlMatch = rawValue.match(/\/spreadsheets\/d\/([a-zA-Z0-9-_]+)/);
    if (urlMatch) {
        return urlMatch[1];
    }
    return /^[a-zA-Z0-9-_]+$/.test(rawValue) ? rawValue : '';
}

function buildGoogleSheetUrl(spreadsheetId) {
    return `https://docs.google.com/spreadsheets/d/${encodeURIComponent(spreadsheetId)}/edit`;
}

function getSelectedMarketType() {
    return normalizeMarketTypeValue(marketTypeSelect.value || 'cn');
}

function setMarketTypeSelection(value) {
    const normalized = normalizeMarketTypeValue(value);
    marketTypeSelect.value = normalized;
    syncCommissionWithMarketType(normalized);
}

function syncCommissionWithMarketType(value = getSelectedMarketType()) {
    const market = stockMarkets.find((item) => item.value === normalizeMarketTypeValue(value));
    commissionInput.value = market?.default_commission || '';
}

function updateStockMeta() {
    return;
}

function sanitizeTaskTitlePart(value) {
    return String(value || '')
        .trim()
        .replace(/\s+/g, '-')
        .replace(/[\\/:*?"<>|]+/g, '-')
        .replace(/-+/g, '-')
        .replace(/^-|-$/g, '');
}

<!--?function buildDefaultTaskName() {-->
<!--?    const stockCode = sanitizeTaskTitlePart(stockCodeInput.value.trim().toUpperCase());-->
<!--?    const modelVersion = resolveModelVersion(currentModelVersion).toUpperCase();-->
<!--?    return stockCode ? `${modelVersion}-${stockCode}` : '';-->
<!--?}-->
function buildDefaultTaskName() {
    const fallbackCode = stockCodeInput.value.trim()
            ? sanitizeTaskTitlePart(stockCodeInput.value.trim().toUpperCase())
            : '';
    const stockPart = selectedStockSuggestion && getSelectedMarketType() === 'cn'
        ? sanitizeTaskTitlePart(selectedStockSuggestion.name) || fallbackCode
        : fallbackCode;
    const modelVersion = resolveModelVersion(currentModelVersion).toUpperCase();
    return stockPart ? `${modelVersion}-${stockPart}` : '';
}

function syncTaskNameInput(force = false) {
    const nextName = buildDefaultTaskName();
    if (!nextName) {
        return;
    }
    if (force || !taskNameTouched || !taskNameInput.value.trim()) {
        taskNameInput.value = nextName;
        taskNameTouched = false;
    }
}

function clearSelectedStockSuggestion() {
    selectedStockSuggestion = null;
    updateStockMeta();
}

function buildYearCheckboxes() {
    [1, 2, 3, 5, 7].forEach((year, index) => {
        recentYearsCheckboxes.insertAdjacentHTML('beforeend', `
            <div class="form-check form-check-inline mb-0">
                <input class="form-check-input recent-year" type="checkbox" id="recent_year_${year}" value="${year}" ${index < 3 ? 'checked' : ''}>
                <label class="form-check-label" for="recent_year_${year}">近 ${year} 年</label>
            </div>
        `);
    });

    for (let index = 0; index < 7; index += 1) {
        const year = currentYear - index;
        fullYearsCheckboxes.insertAdjacentHTML('beforeend', `
            <div class="form-check form-check-inline mb-0">
                <input class="form-check-input full-year" type="checkbox" id="full_year_${year}" value="${year}" ${index < 3 ? 'checked' : ''}>
                <label class="form-check-label" for="full_year_${year}">${year}</label>
            </div>
        `);
    }
}

function ensureDefaultRecentYearsSelection() {
    const checked = document.querySelectorAll('.recent-year:checked').length;
    if (checked > 0) {
        return;
    }
    document.querySelectorAll('.recent-year').forEach((checkbox, index) => {
        checkbox.checked = index < 3;
    });
}

function ensureDefaultFullYearsSelection() {
    const checked = document.querySelectorAll('.full-year:checked').length;
    if (checked > 0) {
        return;
    }
    document.querySelectorAll('.full-year').forEach((checkbox, index) => {
        checkbox.checked = index < 3;
    });
}

function syncYearsWrapper() {
    const recentChecked = recentYearsCheck.checked;
    const fullChecked = fullYearsCheck.checked;
    recentYearsOptions.classList.toggle('d-none', !recentChecked);
    fullYearsOptions.classList.toggle('d-none', !fullChecked);
    yearsContainerWrapper.classList.toggle('d-none', !recentChecked && !fullChecked);
}

function getCheckedRecentYears() {
    return Array.from(document.querySelectorAll('.recent-year:checked'))
        .map((checkbox) => Number.parseInt(checkbox.value, 10))
        .filter((value) => Number.isFinite(value))
        .sort((a, b) => a - b);
}

function getCheckedFullYears() {
    return Array.from(document.querySelectorAll('.full-year:checked'))
        .map((checkbox) => Number.parseInt(checkbox.value, 10))
        .filter((value) => Number.isFinite(value))
        .sort((a, b) => a - b);
}

function syncYearsDisplay() {
    const recentYears = recentYearsCheck.checked ? getCheckedRecentYears() : [];
    const fullYears = fullYearsCheck.checked ? getCheckedFullYears() : [];

    recentYearsDisplay.textContent = recentYears.length ? recentYears.map((year) => `近 ${year} 年`).join('、') : '未选择';
    fullYearsDisplay.textContent = fullYears.length ? fullYears.join('、') : '未选择';
    recentYearsInfoDisplay.textContent = recentYears.length ? `共 ${recentYears.length} 个近年窗口。` : '用于按最近年份回测。';
    fullYearsInfoDisplay.textContent = fullYears.length ? `共 ${fullYears.length} 个完整年份。` : '用于按完整自然年回测。';
    yearsDisplay.textContent = `近 N 年：${recentYears.length ? recentYears.join('、') : '未选择'}；完整年份：${fullYears.length ? fullYears.join('、') : '未选择'}`;
}

function updateConfigToggleText() {
    configToggleBtn.innerHTML = `${taskConfigCollapse.classList.contains('show') ? '收起配置' : '展开配置'} <i class="bi bi-chevron-down ms-1"></i>`;
}

function updateTableHeader() {
    currentFields = FIELD_MAP[resolveModelVersion(currentModelVersion)] || FIELD_MAP.c3;
    const cells = currentFields.map((field) => `<th>${escapeHtml(field.label)}</th>`).join('');
    paramTableHead.innerHTML = `<tr>${cells}<th class="text-center">操作</th></tr>`;
    commissionConfigGroup.classList.toggle('d-none', resolveModelVersion(currentModelVersion) !== 'c3');
}

function syncEmptyState() {
    const hasRows = paramTableBody.querySelectorAll('tr').length > 0;
    emptyHint.classList.toggle('d-none', hasRows);
}

function addParameterRow(initialValues = {}) {
    const cells = currentFields.map((field) => {
        const value = initialValues[field.key] ?? '';
        return `
            <td>
                <input type="text" class="form-control form-control-sm param-input" data-key="${field.key}" value="${escapeHtml(value)}">
            </td>
        `;
    }).join('');

    paramTableBody.insertAdjacentHTML('beforeend', `
        <tr>
            ${cells}
            <td class="text-center">
                <button type="button" class="btn btn-sm btn-outline-danger delete-row">删除</button>
            </td>
        </tr>
    `);
    syncEmptyState();
}

function projectImportedRows(rows) {
    return (Array.isArray(rows) ? rows : [])
        .map((row) => {
            const projected = {};
            currentFields.forEach((field) => {
                projected[field.key] = row?.[field.key] ? String(row[field.key]).trim() : '';
            });
            return projected;
        })
        .filter((row) => Object.values(row).some(Boolean));
}

function splitPastedParameterLine(line) {
    const value = String(line || '').trim();
    if (!value) {
        return [];
    }
    if (value.includes('\t')) {
        return value.split('\t');
    }
    if (value.includes(',')) {
        return value.split(',');
    }
    if (value.includes('，')) {
        return value.split('，');
    }
    return value.split(/\s+/);
}

function normalizePastedCell(value) {
    return String(value ?? '')
        .replace(/\r/g, '')
        .trim();
}

function normalizeHeaderToken(value) {
    return String(value || '')
        .trim()
        .toLowerCase()
        .replace(/[\s_()（）:：/-]+/g, '');
}

function isCommissionCell(value) {
    const normalized = normalizePastedCell(value).toLowerCase();
    if (!normalized) {
        return false;
    }
    return normalized.includes('%') || normalized === 'commission' || normalized === '手续费';
}

function isPastedHeaderRow(cells) {
    const headerTokens = new Set([
        'commission',
        '手续费',
        'xm',
        'xmultiplier',
        'ml',
        'dbbh1',
        'dbbh2',
        'zlxc',
        'zsgz',
        'ywf1',
        'ywf2',
        '单边保护1',
        '单边保护2',
        '中立限仓',
        '指数跟踪'
    ]);
    return cells.some((cell) => headerTokens.has(normalizeHeaderToken(cell)));
}

function formatDerivedProtectionValue(value) {
    if (!Number.isFinite(value)) {
        return '';
    }
    const fixed = value.toFixed(12).replace(/0+$/, '').replace(/\.$/, '');
    return fixed === '-0' ? '0' : fixed;
}

function deriveSingleSideProtection2(value) {
    const normalized = normalizePastedCell(value).replace(/,/g, '');
    if (!normalized) {
        return '';
    }
    const numericValue = Number(normalized);
    if (!Number.isFinite(numericValue)) {
        return '';
    }
    return formatDerivedProtectionValue(2 - numericValue);
}

function normalizeC3BusinessCells(cells) {
    const sourceCells = cells.slice();
    if (sourceCells.length === 6) {
        return [
            sourceCells[0],
            sourceCells[1],
            deriveSingleSideProtection2(sourceCells[1]),
            sourceCells[2],
            sourceCells[3],
            sourceCells[4],
            sourceCells[5]
        ];
    }
    return sourceCells;
}

function parsePastedParameterRows(rawText) {
    const rows = String(rawText || '')
        .split(/\n+/)
        .map((line) => splitPastedParameterLine(line).map(normalizePastedCell))
        .filter((cells) => cells.some((cell) => cell !== ''));

    if (!rows.length) {
        return [];
    }

    const dataRows = isPastedHeaderRow(rows[0]) ? rows.slice(1) : rows;
    const c3Mode = resolveModelVersion(currentModelVersion) === 'c3';
    const expectedColumnCount = currentFields.length;
    const firstDataRow = dataRows[0] || [];
    const hasLeadingCommission = c3Mode
        && firstDataRow.length > expectedColumnCount - 1
        && (isCommissionCell(firstDataRow[0]) || firstDataRow.length === expectedColumnCount + 1);

    if (hasLeadingCommission && firstDataRow[0]) {
        commissionInput.value = firstDataRow[0];
    }

    return dataRows
        .map((cells) => {
            const sourceCells = c3Mode
                ? normalizeC3BusinessCells(hasLeadingCommission ? cells.slice(1) : cells)
                : (hasLeadingCommission ? cells.slice(1) : cells);
            const projected = {};
            currentFields.forEach((field, index) => {
                projected[field.key] = sourceCells[index] || '';
            });
            return projected;
        })
        .filter((row) => Object.values(row).some(Boolean));
}

function resetParameterTable(rows = []) {
    updateTableHeader();
    paramTableBody.innerHTML = '';
    const projectedRows = projectImportedRows(rows);
    if (projectedRows.length) {
        projectedRows.forEach((row) => addParameterRow(row));
    } else {
        addParameterRow();
    }
    syncEmptyState();
}

function collectParameterDraftRows() {
    return Array.from(paramTableBody.querySelectorAll('tr')).map((row) => {
        return currentFields.map((field) => row.querySelector(`[data-key="${field.key}"]`)?.value.trim() || '');
    });
}

function hasParameterDraftValues() {
    return collectParameterDraftRows().some((row) => row.some(Boolean));
}

function clearPlaceholderRowsBeforeAppend() {
    if (hasParameterDraftValues()) {
        return;
    }
    paramTableBody.innerHTML = '';
    syncEmptyState();
}

function getCommissionValue() {
    const value = commissionInput.value.trim();
    return value || DEFAULT_C3_COMMISSION;
}

function collectParameters() {
    const rows = collectParameterDraftRows().filter((row) => row.some(Boolean));
    if (resolveModelVersion(currentModelVersion) === 'c3') {
        const commission = getCommissionValue();
        return rows.map((row) => [commission, ...row]);
    }
    return rows;
}

async function queryClipboardReadPermission() {
    if (!navigator.permissions?.query) {
        return '';
    }
    try {
        const status = await navigator.permissions.query({ name: 'clipboard-read' });
        return status.state || '';
    } catch (error) {
        return '';
    }
}

function requestManualClipboardText(message) {
    return new Promise((resolve) => {
        if (!window.bootstrap?.Modal) {
            resolve(window.prompt(`${message}\n请粘贴参数内容：`, '') || '');
            return;
        }

        const modalEl = document.createElement('div');
        modalEl.className = 'modal fade';
        modalEl.tabIndex = -1;
        modalEl.setAttribute('aria-hidden', 'true');
        modalEl.innerHTML = `
            <div class="modal-dialog modal-dialog-centered modal-lg">
                <div class="modal-content">
                    <div class="modal-header">
                        <h5 class="modal-title">粘贴参数</h5>
                        <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="关闭"></button>
                    </div>
                    <div class="modal-body">
                        <div class="alert alert-warning py-2 small"></div>
                        <textarea class="form-control paste-parse-input" rows="8" placeholder="在这里粘贴从 Excel 或其他任务复制的参数"></textarea>
                    </div>
                    <div class="modal-footer">
                        <button type="button" class="btn btn-outline-secondary" data-bs-dismiss="modal">取消</button>
                        <button type="button" class="btn btn-primary confirm-manual-paste">追加参数</button>
                    </div>
                </div>
            </div>
        `;
        document.body.appendChild(modalEl);
        modalEl.querySelector('.alert').textContent = message;
        const textarea = modalEl.querySelector('textarea');
        const modal = new bootstrap.Modal(modalEl, { backdrop: 'static' });
        let resolved = false;

        modalEl.addEventListener('shown.bs.modal', () => textarea.focus(), { once: true });
        modalEl.addEventListener('hidden.bs.modal', () => {
            modal.dispose();
            modalEl.remove();
            if (!resolved) {
                resolve('');
            }
        }, { once: true });
        modalEl.querySelector('.confirm-manual-paste').addEventListener('click', () => {
            resolved = true;
            const value = textarea.value;
            modal.hide();
            resolve(value);
        });
        modal.show();
    });
}

async function readClipboardText() {
    const canUseClipboardApi = window.isSecureContext && navigator.clipboard?.readText;
    if (!canUseClipboardApi) {
        return requestManualClipboardText('当前页面不是 HTTPS，浏览器无法授予剪切板读取权限。请在下方粘贴参数后继续。');
    }

    const permissionState = await queryClipboardReadPermission();
    if (permissionState === 'denied') {
        return requestManualClipboardText('浏览器已拒绝剪切板读取权限。请在下方粘贴参数后继续。');
    }

    try {
        return await navigator.clipboard.readText();
    } catch (error) {
        return requestManualClipboardText('未完成剪切板权限授权，或浏览器暂时无法读取剪切板。请在下方粘贴参数后继续。');
    }
}

async function writeClipboardText(text) {
    if (navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(text);
        return;
    }
    const textarea = document.createElement('textarea');
    textarea.value = text;
    textarea.setAttribute('readonly', '');
    textarea.style.position = 'fixed';
    textarea.style.opacity = '0';
    document.body.appendChild(textarea);
    textarea.select();
    const ok = document.execCommand('copy');
    textarea.remove();
    if (!ok) {
        throw new Error('复制失败，请检查浏览器剪切板权限');
    }
}

function parameterRowsToClipboard() {
    return collectParameters()
        .filter((row) => Array.isArray(row) && row.some((value) => String(value ?? '').trim()))
        .map((row) => row.join('\t'))
        .join('\n');
}

async function pasteParametersFromClipboard() {
    try {
        const raw = await readClipboardText();
        const rows = parsePastedParameterRows(raw);
        if (!rows.length) {
            setExcelImportStatus('剪切板中没有解析到有效参数', 'danger');
            return;
        }
        clearPlaceholderRowsBeforeAppend();
        rows.forEach((row) => addParameterRow(row));
        syncEmptyState();
        setExcelImportStatus(`已追加 ${rows.length} 行参数`, 'success');
    } catch (error) {
        alert(error.message || '读取剪切板失败');
    }
}

async function copyParametersToClipboard() {
    try {
        const text = parameterRowsToClipboard();
        if (!text) {
            throw new Error('当前没有可复制的参数');
        }
        await writeClipboardText(text);
        setExcelImportStatus('参数已复制，可直接粘贴到其他单产品回测或 Excel', 'success');
    } catch (error) {
        alert(error.message || '复制失败');
    }
}

function setExcelImportStatus(message, tone = 'muted') {
    excelImportStatus.className = `small mb-3 text-${tone}`;
    excelImportStatus.textContent = message || '';
}

function setGoogleSheetLoading(isLoading) {
    modelUrlInput.disabled = isLoading;
    analyzeBtn.disabled = isLoading;
    analyzeBtn.innerHTML = isLoading
        ? '<span class="spinner-border spinner-border-sm me-1" aria-hidden="true"></span>识别中'
        : '<i class="bi bi-search me-1"></i>识别链接';
}

function setImportButtonState(isLoading) {
    importExcelBtn.disabled = isLoading;
    importExcelBtn.innerHTML = isLoading
        ? '<span class="spinner-border spinner-border-sm me-1" aria-hidden="true"></span>导入中'
        : '<i class="bi bi-file-earmark-excel me-1"></i>导入 Excel';
}

function setCreateButtonState(isLoading) {
    isCreatingTask = isLoading;
    createBtn.disabled = isLoading;
    createBtn.innerHTML = isLoading
        ? '<span class="spinner-border spinner-border-sm me-1" aria-hidden="true"></span>创建中'
        : '<i class="bi bi-play-circle me-1"></i>创建任务';
}

function renderSheetInfo(title, worksheets) {
    const modelVersion = inferModelVersion(title);
    currentModelVersion = modelVersion;
    currentC7ModelVersion = inferC7ModelVersion(title);
    sheetTitle = title || '';
    selectedWorksheetName = Array.isArray(worksheets) && worksheets.length ? String(worksheets[0]).trim() : '';
    modelVersionBadge.textContent = modelVersion.toUpperCase();
    sheetTitleEl.textContent = title || '-';
    sheetNamesEl.textContent = Array.isArray(worksheets) && worksheets.length ? worksheets.join(' / ') : '-';
    sheetInfo.classList.add('is-visible');
    importedParameterRows = [];
    currentExcelImport = null;
    syncPriceModeForModel();
    setExcelImportStatus('');
    syncTaskNameInput(true);
    resetParameterTable();
}

function renderTokenOptions(tokens) {
    tokenIdSelect.innerHTML = '';
    if (!Array.isArray(tokens) || !tokens.length) {
        tokenIdSelect.innerHTML = '<option value="">暂无可用 Token</option>';
        return;
    }

    tokens.forEach((token) => {
        const option = document.createElement('option');
        option.value = String(token.id);
        option.disabled = !token.is_available;
        option.textContent = `${token.name} | 占用 ${token.current_in_use_count || 0} | 累计 ${token.task_usage_count || 0} | 上限 ${Number(token.max_usage_count || 0) > 0 ? token.max_usage_count : '无限'}`;
        tokenIdSelect.appendChild(option);
    });

    const firstAvailable = Array.from(tokenIdSelect.options).find((option) => !option.disabled);
    if (firstAvailable) {
        firstAvailable.selected = true;
    }
}

async function loadBacktestTokens() {
    try {
        const data = await Api.endpoints.googleSheet.tokens('?task_type=backtest_training');
        backtestTokens = Array.isArray(data.tokens) ? data.tokens : [];
        renderTokenOptions(backtestTokens);
    } catch (error) {
        tokenIdSelect.innerHTML = '<option value="">加载 Token 失败</option>';
        console.error(error);
    }
}

function hideStockSearchResults() {
    stockSearchResults.classList.add('d-none');
}

function showStockSearchResults() {
    stockSearchResults.classList.remove('d-none');
}

function renderStockSearchResults(results, keyword) {
    lastStockSearchResults = Array.isArray(results) ? results : [];
    if (!lastStockSearchResults.length) {
        stockSearchResults.innerHTML = `
            <div class="px-3 py-2 text-body-secondary small">
                ${keyword ? `未找到 “${escapeHtml(keyword)}” 的匹配结果` : '请输入股票代码'}
            </div>
        `;
        showStockSearchResults();
        return;
    }

    stockSearchResults.innerHTML = lastStockSearchResults.map((item, index) => `
        <button type="button" class="stock-search-item ${index === 0 ? 'active' : ''}" data-index="${index}">
            <div class="fw-semibold">${escapeHtml(item.code || '')}</div>
            <div class="small text-body-secondary">${escapeHtml(item.label || item.name || '')}</div>
        </button>
    `).join('');
    showStockSearchResults();
}

function selectStockSuggestion(item) {
    if (!item) {
        return;
    }
    stockCodeInput.value = item.code || '';
    selectedStockSuggestion = item;
    setMarketTypeSelection(item.market_type);
    syncTaskNameInput(true);
    updateStockMeta();
    showStockSearchResults();
}

async function fetchStockSuggestions(keyword, options = {}) {
    const trimmedKeyword = String(keyword || '').trim();
    if (!trimmedKeyword) {
        lastStockSearchResults = [];
        hideStockSearchResults();
        return [];
    }

    if (stockSearchAbortController) {
        stockSearchAbortController.abort();
    }
    stockSearchAbortController = new AbortController();

    try {
        const data = await Api.endpoints.stock.search(`q=${encodeURIComponent(trimmedKeyword)}&market_type=${encodeURIComponent(getSelectedMarketType())}`, {
            signal: stockSearchAbortController.signal
        });
        renderStockSearchResults((data && data.results) || [], trimmedKeyword);
        if (options.keepOpen) {
            showStockSearchResults();
        }
        return (data && data.results) || [];
    } catch (error) {
        if (error.name === 'AbortError') {
            return [];
        }
        stockSearchResults.innerHTML = `<div class="px-3 py-2 text-danger small">${escapeHtml(error.message || '股票搜索失败')}</div>`;
        showStockSearchResults();
        return [];
    }
}

function scheduleStockSearch() {
    window.clearTimeout(stockSearchTimer);
    stockSearchTimer = window.setTimeout(() => {
        fetchStockSuggestions(stockCodeInput.value.trim(), { keepOpen: false });
    }, STOCK_SEARCH_DEBOUNCE_MS);
}

function padNumber(value) {
    return String(value).padStart(2, '0');
}

function getDefaultEndDateValue() {
    return TradingDate.formatDate(TradingDate.previousWeekday());
}

function buildMinuteTimestamp() {
    const now = new Date();
    return `${now.getFullYear()}${padNumber(now.getMonth() + 1)}${padNumber(now.getDate())}${padNumber(now.getHours())}${padNumber(now.getMinutes())}`;
}

function buildRunYearLabel() {
    const recentYears = recentYearsCheck.checked ? getCheckedRecentYears() : [];
    const fullYears = fullYearsCheck.checked ? getCheckedFullYears() : [];
    const parts = [];

    if (fullYears.length) {
        parts.push(`整_${fullYears[0]}_${fullYears[fullYears.length - 1]}`);
    }
    if (recentYears.length) {
        const maxRecentYear = Math.max(...recentYears);
        parts.push(`近_${currentYear - maxRecentYear}_${currentYear}`);
    }
    return parts.join('_') || '未选年份';
}

function buildC3TaskName() {
    return buildDefaultTaskName();
}

function clearSelectedSheetInfo() {
    spreadsheetId = '';
    sheetTitle = '';
    selectedWorksheetName = '';
    currentModelVersion = 'c3';
    currentC7ModelVersion = 'c7_0_2';
    syncPriceModeForModel();
    updateTableHeader();
    sheetInfo.classList.remove('is-visible');
    sheetTitleEl.textContent = '-';
    sheetNamesEl.textContent = '-';
}

function showGoogleSheetOptions() {
    googleSheetMenuList.classList.remove('d-none');
}

function hideGoogleSheetOptions() {
    googleSheetMenuList.classList.add('d-none');
}

function getCachedBacktestGoogleSheets() {
    try {
        const cached = JSON.parse(sessionStorage.getItem(BACKTEST_GOOGLE_SHEETS_CACHE_KEY) || 'null');
        if (cached && cached.expires_at > Date.now() && Array.isArray(cached.items)) {
            return cached.items;
        }
    } catch (error) {
        sessionStorage.removeItem(BACKTEST_GOOGLE_SHEETS_CACHE_KEY);
    }
    return null;
}

function cacheBacktestGoogleSheets(items) {
    try {
        sessionStorage.setItem(BACKTEST_GOOGLE_SHEETS_CACHE_KEY, JSON.stringify({
            expires_at: Date.now() + BACKTEST_GOOGLE_SHEETS_CACHE_TTL,
            items
        }));
    } catch (error) {
        return;
    }
}

function renderBacktestGoogleSheetOptions(items) {
    googleSheetMenuList.innerHTML = '';
    if (!items.length) {
        googleSheetMenuList.innerHTML = '<div class="px-3 py-3 small text-body-secondary">暂无可用预设 Sheet</div>';
        return;
    }
    items.forEach((sheet) => {
        const option = document.createElement('button');
        option.type = 'button';
        option.className = 'sheet-selector-item';
        option.dataset.sheetId = String(sheet.id);
        option.innerHTML = `<div class="fw-semibold">${escapeHtml(sheet.name || '未命名 Sheet')} <span class="text-body-secondary">ID: ${escapeHtml(sheet.spreadsheet_id || '-')}</span></div>${sheet.remark ? `<div class="small text-body-secondary">${escapeHtml(sheet.remark)}</div>` : ''}`;
        googleSheetMenuList.appendChild(option);
    });
}

async function loadBacktestGoogleSheets() {
    const cachedItems = getCachedBacktestGoogleSheets();
    if (cachedItems) {
        backtestGoogleSheets = cachedItems;
        renderBacktestGoogleSheetOptions(backtestGoogleSheets);
        showGoogleSheetOptions();
        return;
    }

    googleSheetMenuList.innerHTML = '<div class="px-3 py-3 small text-body-secondary">加载中...</div>';
    showGoogleSheetOptions();
    try {
        const data = await Api.endpoints.googleSheet.sheets('?table_type=backtest_training');
        backtestGoogleSheets = Array.isArray(data?.items) ? data.items : [];
        cacheBacktestGoogleSheets(backtestGoogleSheets);
        renderBacktestGoogleSheetOptions(backtestGoogleSheets);
    } catch (error) {
        backtestGoogleSheets = [];
        googleSheetMenuList.innerHTML = '<div class="px-3 py-3 small text-danger">加载单品回测 Sheet 失败</div>';
    }
}

async function selectBacktestGoogleSheet(googleSheetId) {
    const selectedSheet = backtestGoogleSheets.find((sheet) => String(sheet.id) === String(googleSheetId));
    if (!selectedSheet) {
        return;
    }

    selectedGoogleSheetId = Number(selectedSheet.id);
    modelUrlInput.value = buildGoogleSheetUrl(selectedSheet.spreadsheet_id);
    hideGoogleSheetOptions();
    await analyzeSheetInput();
}

async function analyzeSheetInput() {
    spreadsheetId = extractSpreadsheetId(modelUrlInput.value);
    if (!spreadsheetId) {
        clearSelectedSheetInfo();
        alert('请输入有效的 Google Sheet 链接或 Sheet ID');
        return;
    }

    setGoogleSheetLoading(true);
    try {
        const data = await Api.endpoints.googleSheet.worksheets({ spreadsheet_id: spreadsheetId });
        renderSheetInfo(data.title || '', data.worksheets || []);
    } catch (error) {
        clearSelectedSheetInfo();
        alert(error.message || '识别链接失败');
    } finally {
        setGoogleSheetLoading(false);
    }
}

async function importExcelFile(file) {
    if (!file) {
        return;
    }

    const formData = new FormData();
    formData.append('file', file);
    setImportButtonState(true);

    try {
        const data = await Api.endpoints.backtest.importExcel(formData);

        currentModelVersion = inferModelVersion(data.model_version || 'c3');
        currentC7ModelVersion = inferC7ModelVersion(data.model_version || sheetTitle);
        importedParameterRows = Array.isArray(data.parameters) ? data.parameters : [];
        currentExcelImport = data.excel_import || null;
        if (data.stock_code) {
            stockCodeInput.value = String(data.stock_code).trim().toUpperCase();
        }
        if (Array.isArray(data.recent_years)) {
            document.querySelectorAll('.recent-year').forEach((checkbox) => {
                checkbox.checked = data.recent_years.includes(Number.parseInt(checkbox.value, 10));
            });
            recentYearsCheck.checked = data.recent_years.length > 0;
        }
        if (Array.isArray(data.full_years)) {
            document.querySelectorAll('.full-year').forEach((checkbox) => {
                checkbox.checked = data.full_years.includes(Number.parseInt(checkbox.value, 10));
            });
            fullYearsCheck.checked = data.full_years.length > 0;
        }
        if (data.end_date) {
            endDateInput.value = String(data.end_date);
        }

        syncYearsWrapper();
        syncYearsDisplay();
        syncPriceModeForModel();
        modelVersionBadge.textContent = currentModelVersion.toUpperCase();
        if (data.sheet_name) {
            selectedWorksheetName = String(data.sheet_name).trim();
        }
        if (sheetTitle || selectedWorksheetName) {
            sheetInfo.classList.add('is-visible');
            if (!sheetTitle && data.sheet_name) {
                sheetTitle = String(data.sheet_name).trim();
            }
            sheetTitleEl.textContent = sheetTitle || '-';
            sheetNamesEl.textContent = selectedWorksheetName || sheetNamesEl.textContent || '-';
        }
        syncTaskNameInput(true);
        resetParameterTable(importedParameterRows);
        setExcelImportStatus(`已导入 ${importedParameterRows.length} 组参数`, 'success');
    } catch (error) {
        setExcelImportStatus(error.message || 'Excel 导入失败', 'danger');
    } finally {
        setImportButtonState(false);
        excelFileInput.value = '';
    }
}

async function createTask() {
    if (isCreatingTask) {
        return;
    }

    const taskName = buildDefaultTaskName();
    const stockCode = stockCodeInput.value.trim().toUpperCase();
    const tokenId = tokenIdSelect.value;
    const parameters = collectParameters();
    const recentYears = recentYearsCheck.checked ? getCheckedRecentYears() : [];
    const fullYears = fullYearsCheck.checked ? getCheckedFullYears() : [];
    const endDate = endDateInput.value;

    if (!taskName) {
        alert('请填写任务名称');
        return;
    }
    if (!spreadsheetId) {
        alert('请选择并识别单品回测 Google Sheet');
        return;
    }
    if (!stockCode) {
        alert('请输入股票代码');
        return;
    }
    if (stockCode.includes(',') || stockCode.includes('，')) {
        alert('当前仅支持单个股票代码');
        return;
    }
    if (!tokenId) {
        alert('请选择回测 Token');
        return;
    }
    if (!parameters.length) {
        alert('请至少填写一组参数');
        return;
    }
    if (!sheetTitle) {
        alert('请先识别链接或导入 Excel');
        return;
    }
    if (!selectedWorksheetName) {
        alert('未识别到可用工作表');
        return;
    }

    setCreateButtonState(true);
    try {
        const sheetConfig = {
            spreadsheet_id: spreadsheetId,
            sheet_name: selectedWorksheetName,
            title: sheetTitle
        };
        if (resolveModelVersion(currentModelVersion) === 'c7') {
            sheetConfig.c7_model_version = currentC7ModelVersion;
        }
        if (selectedGoogleSheetId) {
            sheetConfig.google_sheet_id = selectedGoogleSheetId;
        }
        const config = {
            sheet: sheetConfig,
            stock_code: stockCode,
            market_type: getSelectedMarketType(),
            kline_adjustment: document.getElementById('klineAdjustmentInput')?.value || 'forward',
            kline_data_source: document.getElementById('klineDataSourceInput')?.value || 'akshare',
            price_mode: document.getElementById('priceModeInput')?.value || 'vwap_price',
            token_type: 'file',
            token_id: Number(tokenId),
            parameters,
            recent_years: recentYears,
            full_years: fullYears,
            end_date: endDate || undefined
        };
        if (selectedStockSuggestion) {
            config.stock_name = selectedStockSuggestion.name || undefined;
            config.exchange_market = selectedStockSuggestion.market || undefined;
            config.security_type_name = selectedStockSuggestion.security_type_name || undefined;
            config.stock_source = selectedStockSuggestion.source || undefined;
        }
        if (currentExcelImport) {
            config.excel_import = currentExcelImport;
        }

        const data = await Api.endpoints.task.create({
            name: taskName,
            description: `backtest training task for ${sheetTitleEl.textContent.trim() || 'sheet'}`,
            task_type: BACKTEST_TASK_TYPE,
            config
        });
        if (!data.task_id) {
            throw new Error('任务创建失败');
        }
        alert('任务创建成功');
        window.location.href = '/backtest-training/list';
    } catch (error) {
        alert(error.message || '任务创建失败');
    } finally {
        setCreateButtonState(false);
    }
}

buildYearCheckboxes();
endDateInput.value = getDefaultEndDateValue();
ensureDefaultRecentYearsSelection();
ensureDefaultFullYearsSelection();
resetParameterTable();
syncYearsWrapper();
syncYearsDisplay();
updateConfigToggleText();
updateStockMeta();
loadBacktestTokens();

analyzeBtn.addEventListener('click', analyzeSheetInput);
modelUrlInput.addEventListener('focus', loadBacktestGoogleSheets);
modelUrlInput.addEventListener('click', () => {
    if (googleSheetMenuList.classList.contains('d-none')) {
        loadBacktestGoogleSheets();
    }
});
modelUrlInput.addEventListener('input', () => {
    selectedGoogleSheetId = null;
    clearSelectedSheetInfo();
});
modelUrlInput.addEventListener('keydown', (event) => {
    if (event.key === 'Enter') {
        event.preventDefault();
        analyzeSheetInput();
    }
});
googleSheetMenuList.addEventListener('click', (event) => {
    const target = event.target.closest('.sheet-selector-item');
    if (target) {
        selectBacktestGoogleSheet(target.dataset.sheetId);
    }
});

stockCodeInput.addEventListener('input', () => {
    clearSelectedStockSuggestion();
    syncTaskNameInput();
    if (!stockCodeInput.value.trim()) {
        hideStockSearchResults();
        return;
    }
    scheduleStockSearch();
});

stockCodeInput.addEventListener('keydown', async (event) => {
    if (event.key !== 'Enter') {
        return;
    }
    event.preventDefault();
    window.clearTimeout(stockSearchTimer);
    await fetchStockSuggestions(stockCodeInput.value.trim(), { keepOpen: true });
    showStockSearchResults();
});

stockCodeInput.addEventListener('focus', () => {
    if (lastStockSearchResults.length) {
        showStockSearchResults();
    }
});

taskNameInput.addEventListener('input', () => {
    taskNameTouched = Boolean(taskNameInput.value.trim());
});

stockSearchResults.addEventListener('click', (event) => {
    const target = event.target.closest('.stock-search-item');
    if (!target) {
        return;
    }
    const index = Number.parseInt(target.dataset.index, 10);
    const item = lastStockSearchResults[index];
    selectStockSuggestion(item);
});

loadStockMarkets();

document.addEventListener('click', (event) => {
    if (!event.target.closest('.stock-search-shell')) {
        hideStockSearchResults();
    }
    if (!event.target.closest('.sheet-selector-shell')) {
        hideGoogleSheetOptions();
    }
});

recentYearsCheck.addEventListener('change', () => {
    if (recentYearsCheck.checked) {
        ensureDefaultRecentYearsSelection();
    }
    syncYearsWrapper();
    syncYearsDisplay();
});
fullYearsCheck.addEventListener('change', () => {
    if (fullYearsCheck.checked) {
        ensureDefaultFullYearsSelection();
    }
    syncYearsWrapper();
    syncYearsDisplay();
});
document.addEventListener('change', (event) => {
    if (event.target.classList.contains('recent-year') || event.target.classList.contains('full-year')) {
        syncYearsDisplay();
    }
});

taskConfigCollapse.addEventListener('shown.bs.collapse', updateConfigToggleText);
taskConfigCollapse.addEventListener('hidden.bs.collapse', updateConfigToggleText);

if (paramHelpBtn && window.bootstrap?.Popover) {
    paramHelpBtn.setAttribute('data-bs-content', PARAMETER_HELP_HTML);
    new bootstrap.Popover(paramHelpBtn, {
        container: 'body',
        customClass: 'param-help-popover',
        html: true,
        placement: 'top',
        sanitize: false,
        title: '粘贴与复制说明',
        trigger: 'focus'
    });
}

pasteClipboardBtn.addEventListener('click', pasteParametersFromClipboard);
copyParamBtn.addEventListener('click', copyParametersToClipboard);

addParamBtn.addEventListener('click', () => addParameterRow());
paramTableBody.addEventListener('click', (event) => {
    const deleteButton = event.target.closest('.delete-row');
    if (!deleteButton) {
        return;
    }
    deleteButton.closest('tr')?.remove();
    syncEmptyState();
});

importExcelBtn.addEventListener('click', () => excelFileInput.click());
excelFileInput.addEventListener('change', (event) => {
    importExcelFile(event.target.files?.[0]);
});

createBtn.addEventListener('click', createTask);

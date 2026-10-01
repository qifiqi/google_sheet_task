
const TASK_API_BASE = '/api/tasks';
const TASK_TYPE = 'backtest_multi_product';
const PARAMETER_HELP_HTML = `
    <div class="param-help-content">
        <div><strong>C3 粘贴</strong>：每行 6 列时按不含手续费处理，系统按当前市场自动补手续费（A股 0.035%，美股 0.002%）；每行 7 列时第 1 列按手续费处理。</div>
        <div><strong>C3 复制</strong>：复制当前表格为 Tab 分隔行，包含 <code>Commission</code> 和后续参数列，可直接贴到其他产品或 Excel。</div>
        <div><strong>C5 粘贴/复制</strong>：每行 2 列，顺序为 <code>X Multiplier</code>、<code>ML</code>。</div>
        <div><strong>C7 粘贴/复制</strong>：每行 2 列，顺序为 <code>X Multiplier</code>、<code>ML</code>。</div>
    </div>
`;
const FIELD_MAP = {
    c3: [
        { key: 'commission', label: 'Commission' },
        { key: 'xm', label: 'X Multiplier' },
        { key: 'dbbh1', label: '单边保护1' },
        { key: 'dbbh2', label: '单边保护2' },
        { key: 'zlxc', label: '中立限仓' },
        { key: 'zsgz', label: '指数跟踪' },
        { key: 'ywf1', label: '一窝蜂 S' },
        { key: 'ywf2', label: '一窝蜂 B' }
    ],
    c5: [
        { key: 'xm', label: 'X Multiplier' },
        { key: 'ml', label: 'ML' }
    ],
    c7: [
        { key: 'xm', label: 'X Multiplier' },
        { key: 'ml', label: 'ML' }
    ]
};

let productSeq = 0;
let stockTimers = {};
let stockAbortControllers = {};
let sheetTimers = {};
let sheetAbortControllers = {};
let stockMarkets = [];

const productsContainer = document.getElementById('productsContainer');
const tokenIdSelect = document.getElementById('tokenId');
const ratioTotal = document.getElementById('ratioTotal');
const createStatus = document.getElementById('createStatus');
const globalSheetUrlInput = document.getElementById('globalSheetUrl');
const globalMarketTypeSelect = document.getElementById('globalMarketType');
const globalKlineAdjustmentSelect = document.getElementById('globalKlineAdjustment');
const globalPriceModeSelect = document.getElementById('globalPriceMode');
const globalKlineDataSourceSelect = document.getElementById('globalKlineDataSource');
const globalSheetInfo = document.getElementById('globalSheetInfo');
const globalParamSection = document.getElementById('globalParamSection');
let globalSheetTimer = null;
let globalParamPropagationTimer = null;
let globalSheetRequestId = 0;
let globalSheetLastId = '';
let globalSheetStatus = 'idle';

function extractSpreadsheetId(rawUrl) {
    const match = String(rawUrl || '').trim().match(/\/spreadsheets\/d\/([a-zA-Z0-9-_]+)/);
    return match ? match[1] : '';
}

function inferModelVersion(title) {
    const normalized = String(title || '').toUpperCase();
    if (normalized.includes('C7')) {
        return 'c7';
    }
    return normalized.includes('C5') || normalized.includes('C4') ? 'c5' : 'c3';
}

// Sheet 标题含 C7.0.3 时价格模式默认切换为 OHLC（开高低收，后端对 C7.0.3 强制 OHLC，
// 这里只保证界面显示与实际生效一致）：
// - 自有链接的卡片按自身 Sheet 检测结果锁定，不再被全局价格模式覆盖；
// - 继承全局链接的卡片只切值不锁定，跟随全局（全局识别到 C7.0.3 时自身已切 OHLC）；
// - 用户手动改过价格模式后不再自动切换；换回非 C7.0.3 Sheet 时自动解锁并回到全局当前值。
function applyPriceModeDefault(card, title) {
    if (card.dataset.priceModeTouched === '1') {
        return;
    }
    const priceSelect = card.querySelector('.price-mode');
    if (!priceSelect) {
        return;
    }
    const isC703 = String(title || '').toUpperCase().includes('C7.0.3');
    if (isC703) {
        priceSelect.value = 'ohlc_price';
        if (card.querySelector('.sheet-url')?.value.trim()) {
            card.dataset.priceTouched = '1';
            card.dataset.priceModeAuto = '1';
        }
        return;
    }
    if (card.dataset.priceModeAuto === '1') {
        delete card.dataset.priceTouched;
        delete card.dataset.priceModeAuto;
        priceSelect.value = globalPriceModeSelect?.value || 'sp_price';
    }
}

function marketOptionsHtml(selectedMarket) {
    return stockMarkets.map((market) => `
        <option value="${escapeHtml(market.value)}" ${market.value === selectedMarket ? 'selected' : ''}>${escapeHtml(market.label)}</option>
    `).join('');
}

async function loadStockMarkets() {
    const payload = await Api.endpoints.meta.enums();
    stockMarkets = payload?.stock_markets || [];
    if (!stockMarkets.length) throw new Error('市场枚举为空');
    if (globalMarketTypeSelect) {
        globalMarketTypeSelect.innerHTML = marketOptionsHtml(globalMarketTypeSelect.value || 'cn');
    }
}

// 继承自全局设置的当前取值；产品卡片创建时作为默认值。
function getGlobalDefaults() {
    return {
        market_type: globalMarketTypeSelect?.value || 'cn',
        kline_adjustment: globalKlineAdjustmentSelect?.value || 'forward',
        price_mode: globalPriceModeSelect?.value || 'sp_price',
        kline_data_source: globalKlineDataSourceSelect?.value || 'akshare'
    };
}

// 产品 Sheet 链接的生效值：卡片自有链接优先，留空则继承全局链接。
function getCardSheetUrl(card) {
    const ownUrl = card.querySelector('.sheet-url')?.value.trim();
    if (ownUrl) {
        return ownUrl;
    }
    return globalSheetUrlInput?.value.trim() || '';
}

// 市场联动数据源：非 A股统一 Yahoo；切回 A股时，仅当 Yahoo 是此前联动自动切的
// 才恢复默认 AKShare，用户手动选的数据源不动。
function syncCardDataSourceWithMarket(card, marketType) {
    const sourceSelect = card.querySelector('.kline-data-source');
    if (!sourceSelect) {
        return;
    }
    if (String(marketType || '').trim().toLowerCase() !== 'cn') {
        sourceSelect.value = 'yahoo';
        card.dataset.sourceTouched = '1';
        card.dataset.sourceAuto = '1';
        return;
    }
    if (card.dataset.sourceAuto === '1') {
        sourceSelect.value = 'akshare';
        delete card.dataset.sourceTouched;
        delete card.dataset.sourceAuto;
    }
}

// 与后端 infer_market_type 同规则：标准后缀优先，其次纯数字按 A股，其余按美股。
const STOCK_SUFFIX_MARKETS = {
    '.SS': 'cn', '.SH': 'cn', '.SZ': 'cn', '.BJ': 'cn',
    '.US': 'en', '.TO': 'ca', '.KS': 'kr', '.T': 'jp', '.HK': 'hk',
    '.L': 'uk', '.PA': 'fr', '.DE': 'de', '.SI': 'sg', '.AX': 'au', '.KL': 'my'
};

function inferMarketTypeFromCode(rawCode) {
    const code = String(rawCode || '').trim().toUpperCase();
    // 含中文等非代码字符（如股票名称）不推断，避免误判市场。
    if (!code || !/^[A-Z0-9./-]+$/.test(code)) {
        return '';
    }
    const dotIndex = code.lastIndexOf('.');
    if (dotIndex > 0) {
        const market = STOCK_SUFFIX_MARKETS[code.slice(dotIndex)];
        if (market) {
            return market;
        }
    }
    return /^\d+$/.test(code) ? 'cn' : 'en';
}

// 手输股票代码联动市场：按代码推断并同步市场/手续费/数据源；
// 用户点过搜索建议或手动选过市场（marketManual）后以用户选择为准，不再推断。
function applyStockMarketInference(card, rawCode) {
    if (card.dataset.marketManual === '1') {
        return;
    }
    const market = inferMarketTypeFromCode(rawCode);
    const marketSelect = card.querySelector('.market-type');
    if (!market || !marketSelect || marketSelect.value === market) {
        return;
    }
    marketSelect.value = market;
    card.dataset.marketTouched = '1';
    syncCardDataSourceWithMarket(card, market);
    syncEmptyCommissionRows(card);
    updateProductSummary(card);
}

function getDefaultCommissionByMarket(marketType) {
    return stockMarkets.find((market) => market.value === marketType)?.default_commission || '';
}

function getCardMarketType(card) {
    // 全局参数区是"伪卡片"（复用参数表工具函数），市场取全局市场下拉。
    if (card?.dataset?.isGlobalParam === '1') {
        return globalMarketTypeSelect?.value || 'cn';
    }
    return card.querySelector('.market-type')?.value || 'cn';
}

function getCardDefaultCommission(card) {
    return getDefaultCommissionByMarket(getCardMarketType(card));
}

function isReusableParameterRow(card, row) {
    const version = card.dataset.modelVersion || 'c3';
    const inputs = Array.from(row.querySelectorAll('.param-input'));
    if (!inputs.length) {
        return true;
    }
    if (version !== 'c3') {
        return inputs.every((input) => !input.value.trim());
    }
    return inputs.slice(1).every((input) => !input.value.trim());
}

function syncEmptyCommissionRows(card) {
    const defaultCommission = getCardDefaultCommission(card);
    Array.from(card.querySelectorAll('.param-body tr')).forEach((row) => {
        if (!isReusableParameterRow(card, row)) {
            return;
        }
        const commissionInput = row.querySelector('.param-input[data-key="commission"]');
        if (commissionInput) {
            commissionInput.value = defaultCommission;
        }
    });
}

function getProductCards() {
    return Array.from(productsContainer.querySelectorAll('.product-card'));
}

function updateRatioTotal() {
    const total = getProductCards().reduce((sum, card) => {
        const value = Number(card.querySelector('.ratio-input')?.value || 0);
        return sum + (Number.isFinite(value) ? value : 0);
    }, 0);
    ratioTotal.textContent = `${Number(total.toFixed(4))}%`;
    ratioTotal.className = 'text-body';
}

function formatMarketLabel(marketType) {
    const normalized = String(marketType || '').trim().toLowerCase();
    if (!normalized || normalized === 'cn') {
        return 'A股 cn';
    }
    if (normalized === 'en') {
        return '美股 en';
    }
    // 其余市场（香港/日本/期货等）按全局市场下拉的选项文案展示。
    const option = globalMarketTypeSelect?.querySelector(`option[value="${normalized}"]`);
    return option ? `${option.textContent} ${normalized}` : normalized;
}

function updateProductSummary(card) {
    const productName = card.querySelector('.product-name')?.value.trim() || '未命名产品';
    const stockCode = card.querySelector('.stock-code')?.value.trim().toUpperCase() || '未填写';
    const marketType = card.querySelector('.market-type')?.value || 'cn';
    const ratio = card.querySelector('.ratio-input')?.value.trim();
    const title = card.querySelector('.product-title');
    const stockSummary = card.querySelector('.summary-stock');
    const marketSummary = card.querySelector('.summary-market');
    const ratioSummary = card.querySelector('.summary-ratio');
    if (title) {
        title.textContent = productName;
        title.title = productName;
    }
    if (stockSummary) {
        stockSummary.textContent = stockCode;
        stockSummary.title = `${productName} / ${stockCode}`;
    }
    if (marketSummary) {
        marketSummary.textContent = formatMarketLabel(marketType);
    }
    if (ratioSummary) {
        ratioSummary.textContent = `比例 ${ratio || 0}%`;
    }
}

function setProductCollapsed(card, collapsed) {
    card.classList.toggle('is-collapsed', collapsed);
    const toggle = card.querySelector('.product-collapse-toggle');
    if (!toggle) {
        return;
    }
    toggle.setAttribute('aria-expanded', collapsed ? 'false' : 'true');
    toggle.setAttribute('title', collapsed ? '展开产品' : '折叠产品');
    toggle.setAttribute('aria-label', collapsed ? '展开产品' : '折叠产品');
}

function buildParameterHead(version) {
    const fields = FIELD_MAP[version] || FIELD_MAP.c3;
    return `<tr>${fields.map((field) => `<th>${escapeHtml(field.label)}</th>`).join('')}<th class="text-end">操作</th></tr>`;
}

function addParameterRow(card, values = []) {
    const version = card.dataset.modelVersion || 'c3';
    const fields = FIELD_MAP[version] || FIELD_MAP.c3;
    const tbody = card.querySelector('.param-body');
    const defaultCommission = getCardDefaultCommission(card);
    const rowValues = Array.isArray(values) ? [...values] : [];
    if (version === 'c3' && !String(rowValues[0] ?? '').trim()) {
        rowValues[0] = defaultCommission;
    }
    const row = document.createElement('tr');
    row.innerHTML = `${fields.map((field, index) => `
        <td><input class="form-control form-control-sm param-input" data-key="${field.key}" value="${escapeHtml(rowValues[index] ?? (field.key === 'commission' ? defaultCommission : ''))}"></td>
    `).join('')}<td class="text-end"><button class="btn btn-sm btn-outline-danger delete-param" type="button"><i class="bi bi-trash"></i></button></td>`;
    tbody.appendChild(row);
}

function initParameterHelpPopover(card) {
    const helpButton = card.querySelector('.param-help-button');
    if (!helpButton || !window.bootstrap?.Popover) {
        return;
    }
    helpButton.setAttribute('data-bs-content', PARAMETER_HELP_HTML);
    new bootstrap.Popover(helpButton, {
        container: 'body',
        customClass: 'param-help-popover',
        html: true,
        placement: 'top',
        sanitize: false,
        title: '粘贴与复制说明',
        trigger: 'focus'
    });
}

function resetParameterTable(card, version) {
    card.dataset.modelVersion = version;
    card.querySelector('.model-badge').textContent = version.toUpperCase();
    card.querySelector('.param-head').innerHTML = buildParameterHead(version);
    card.querySelector('.param-body').innerHTML = '';
    addParameterRow(card);
}

function addProduct(defaults = {}) {
    productSeq += 1;
    const productId = `product-${productSeq}`;
    const fixedInputId = `fixedProduct${productSeq}`;
    // 新产品继承当前全局设置；显式传入的 defaults 优先。
    const inherited = { ...getGlobalDefaults(), ...defaults };
    const card = document.createElement('div');
    card.className = 'product-card';
    card.dataset.productId = productId;
    card.dataset.modelVersion = 'c3';
    card.innerHTML = `
        <div class="p-3 border-bottom bg-body-tertiary d-flex justify-content-between align-items-center flex-wrap gap-2 product-card-header">
            <div class="d-flex align-items-center gap-2 flex-grow-1 product-card-title-group">
                <button class="btn btn-sm btn-outline-secondary product-collapse-toggle" type="button" title="折叠产品" aria-label="折叠产品" aria-expanded="true">
                    <i class="bi bi-chevron-up"></i>
                </button>
                <span class="badge text-bg-primary rounded-pill model-badge">C3</span>
                <div class="product-card-title-group">
                    <strong class="product-title">产品 ${productSeq}</strong>
                    <div class="product-summary small">
                        <span class="product-summary-item summary-stock">未填写</span>
                        <span class="product-summary-item summary-market">A股 cn</span>
                        <span class="product-summary-item summary-ratio">比例 ${escapeHtml(inherited.ratio ?? '') || '0'}%</span>
                    </div>
                </div>
            </div>
            <div class="d-flex align-items-center gap-3 product-card-actions">
                <div class="form-check form-switch fixed-product-switch">
                    <input class="form-check-input fixed-product" id="${fixedInputId}" type="checkbox" role="switch" ${inherited.is_fixed ? 'checked' : ''}>
                    <label class="form-check-label small text-body-secondary" for="${fixedInputId}">固定</label>
                </div>
                <button class="btn btn-sm btn-outline-danger delete-product" type="button" title="删除产品" aria-label="删除产品"><i class="bi bi-trash"></i></button>
            </div>
        </div>
        <div class="p-3 d-grid gap-3 product-card-body">
            <div class="row g-3 align-items-end">
                <div class="col-xl-3">
                    <label class="form-label">产品名称</label>
                    <input class="form-control product-name" value="${escapeHtml(inherited.product_name || `产品 ${productSeq}`)}">
                </div>
                <div class="col-xl-2">
                    <label class="form-label">股票代码</label>
                    <div class="stock-search-shell">
                        <input class="form-control stock-code" autocomplete="off" value="${escapeHtml(inherited.stock_code || '')}">
                        <div class="stock-search-results d-none"></div>
                    </div>
                </div>
                <div class="col-xl-2">
                    <label class="form-label">市场</label>
                    <select class="form-select market-type">
                        ${marketOptionsHtml(inherited.market_type || 'cn')}
                    </select>
                </div>
                <div class="col-xl-2">
                    <label class="form-label">K线复权</label>
                    <select class="form-select kline-adjustment">
                        <option value="forward">前复权</option>
                        <option value="back">后复权</option>
                        <option value="none">不复权</option>
                    </select>
                </div>
                <div class="col-xl-2">
                    <label class="form-label">价格模式</label>
                    <select class="form-select price-mode" title="识别到 C7.0.3 Sheet 时自动切换为 OHLC；手动修改后不再自动切换">
                        <option value="vwap_price">加权平均价</option>
                        <option value="kp_price">开盘价</option>
                        <option value="sp_price" selected>收盘价</option>
                        <option value="ohlc_price">OHLC（开高低收）</option>
                    </select>
                </div>
                <div class="col-xl-2">
                    <label class="form-label">K线数据源</label>
                    <select class="form-select kline-data-source">
                        <option value="akshare">AKShare（默认）</option>
                        <option value="dfcf">东方财富</option>
                        <option value="qq">腾讯</option>
                        <option value="yahoo">Yahoo</option>
                        <option value="tdx">通达信（仅A股）</option>
                    </select>
                </div>
                <div class="col-xl-2">
                    <label class="form-label">比例 %</label>
                    <input class="form-control ratio-input" type="number" min="0" step="0.0001" value="${escapeHtml(inherited.ratio ?? '')}">
                </div>
                <div class="col-xl-3">
                    <label class="form-label">Google Sheet 链接</label>
                    <input class="form-control sheet-url" value="${escapeHtml(inherited.sheet_url || '')}" placeholder="留空继承顶部全局链接">
                </div>
            </div>
            <div class="small text-body-secondary sheet-info">尚未识别 Sheet</div>
            <div class="d-flex flex-wrap gap-2 param-toolbar">
                <button class="btn btn-outline-secondary btn-sm add-param" type="button"><i class="bi bi-plus-lg me-1"></i>添加参数行</button>
                <button class="btn btn-outline-secondary btn-sm paste-param" type="button"><i class="bi bi-clipboard2-plus me-1"></i>粘贴追加</button>
                <button class="btn btn-outline-secondary btn-sm copy-param" type="button"><i class="bi bi-copy me-1"></i>复制参数</button>
                <button class="btn btn-outline-secondary btn-sm param-help-button" type="button" aria-label="查看粘贴与复制说明">
                    <i class="bi bi-exclamation-circle"></i>
                </button>
                <span class="badge text-bg-warning rounded-pill param-custom-badge d-none" title="该产品参数已手动修改，不再跟随全局参数">参数已自定义</span>
                <button class="btn btn-outline-secondary btn-sm reset-params d-none" type="button" title="放弃当前参数，重新跟随全局参数"><i class="bi bi-arrow-counterclockwise me-1"></i>重置为全局参数</button>
                <span class="small text-body-secondary align-self-center param-action-status"></span>
            </div>
            <div class="table-responsive">
                <table class="table table-bordered align-middle param-table mb-0">
                    <thead class="table-light param-head"></thead>
                    <tbody class="param-body"></tbody>
                </table>
            </div>
        </div>
    `;
    productsContainer.appendChild(card);
    card.querySelector('.kline-adjustment').value = inherited.kline_adjustment || 'forward';
    card.querySelector('.price-mode').value = inherited.price_mode || 'sp_price';
    card.querySelector('.kline-data-source').value = inherited.kline_data_source || 'akshare';
    resetParameterTable(card, 'c3');
    initParameterHelpPopover(card);
    // 新卡片创建时继承全局参数行（版本一致且有内容时）。
    applyGlobalParamsToCard(card);
    card.querySelector('.ratio-input').addEventListener('input', () => {
        updateRatioTotal();
        updateProductSummary(card);
    });
    card.querySelector('.product-name').addEventListener('input', () => {
        updateProductSummary(card);
    });
    card.querySelector('.stock-code').addEventListener('input', () => {
        updateProductSummary(card);
    });
    card.querySelector('.market-type').addEventListener('change', () => {
        syncEmptyCommissionRows(card);
        updateProductSummary(card);
    });
    // 有自有链接直接识别；留空时按继承的全局链接识别（全局也为空则提示待填）。
    scheduleSheetAnalyze(card, { immediate: true });
    updateRatioTotal();
    updateProductSummary(card);
}

function setSheetInfo(card, message, className = 'small text-body-secondary sheet-info') {
    const info = card.querySelector('.sheet-info');
    info.className = className;
    info.textContent = message;
}

function setParamActionStatus(card, message, className = 'small text-body-secondary align-self-center param-action-status') {
    const status = card.querySelector('.param-action-status');
    status.className = className;
    status.textContent = message;
}

// 产品参数表一旦手动编辑即脱钩，不再跟随全局参数；"重置为全局参数"恢复跟随。
function markParamTouched(card) {
    if (!card || card.dataset.paramTouched === '1') {
        return;
    }
    card.dataset.paramTouched = '1';
    updateParamFollowStatus(card);
}

function updateParamFollowStatus(card) {
    const touched = card.dataset.paramTouched === '1';
    card.querySelector('.param-custom-badge')?.classList.toggle('d-none', !touched);
    card.querySelector('.reset-params')?.classList.toggle('d-none', !touched);
}

function clearSheetMeta(card) {
    delete card.dataset.spreadsheetId;
    delete card.dataset.sheetName;
    delete card.dataset.sheetTitle;
    delete card.dataset.lastAnalyzedSpreadsheetId;
    delete card.dataset.pendingSpreadsheetId;
    card.dataset.sheetStatus = 'idle';
}

function scheduleSheetAnalyze(card, options = {}) {
    const spreadsheetId = extractSpreadsheetId(getCardSheetUrl(card));
    if (card.dataset.lastAnalyzedSpreadsheetId && card.dataset.lastAnalyzedSpreadsheetId !== spreadsheetId) {
        clearSheetMeta(card);
        setSheetInfo(card, spreadsheetId ? '等待自动识别 Sheet...' : '尚未识别 Sheet');
    }
    const productId = card.dataset.productId;
    window.clearTimeout(sheetTimers[productId]);
    const delay = options.immediate ? 0 : 500;
    sheetTimers[productId] = window.setTimeout(() => analyzeSheet(card, { silent: true }), delay);
}

async function analyzeSheet(card, options = {}) {
    const urlInput = card.querySelector('.sheet-url');
    const ownUrl = urlInput.value.trim();
    const spreadsheetId = extractSpreadsheetId(getCardSheetUrl(card));
    if (!spreadsheetId) {
        clearSheetMeta(card);
        if (ownUrl) {
            setSheetInfo(card, '未识别到有效的 Google Sheet 链接', 'small text-danger sheet-info');
        } else {
            setSheetInfo(card, '尚未识别 Sheet（可留空继承顶部全局链接）');
        }
        return;
    }
    if (card.dataset.sheetStatus === 'success' && card.dataset.lastAnalyzedSpreadsheetId === spreadsheetId) {
        return;
    }

    const productId = card.dataset.productId;
    if (sheetAbortControllers[productId]) {
        sheetAbortControllers[productId].abort();
    }
    sheetAbortControllers[productId] = new AbortController();
    card.dataset.sheetStatus = 'loading';
    card.dataset.pendingSpreadsheetId = spreadsheetId;
    setSheetInfo(card, '正在自动识别 Sheet...', 'small text-primary sheet-info');
    try {
        const data = await Api.endpoints.googleSheet.worksheets({ spreadsheet_id: spreadsheetId }, { signal: sheetAbortControllers[productId].signal });
        const sheetName = Array.isArray(data.worksheets) && data.worksheets.length ? data.worksheets[0] : 'data';
        const title = data.title || '';
        card.dataset.spreadsheetId = spreadsheetId;
        card.dataset.sheetName = sheetName;
        card.dataset.sheetTitle = title;
        card.dataset.lastAnalyzedSpreadsheetId = spreadsheetId;
        card.dataset.sheetStatus = 'success';
        delete card.dataset.pendingSpreadsheetId;
        const nextVersion = inferModelVersion(title);
        if (card.dataset.modelVersion !== nextVersion) {
            resetParameterTable(card, nextVersion);
        }
        applyPriceModeDefault(card, title);
        // 卡片版本随自有 Sheet 变化后重新对齐全局参数（未自定义且版本一致时下发）。
        applyGlobalParamsToCard(card);
        setSheetInfo(card, `${title || spreadsheetId} / ${sheetName}`, 'small text-success sheet-info');
    } catch (error) {
        if (error.name === 'AbortError') {
            return;
        }
        clearSheetMeta(card);
        setSheetInfo(card, error.message || '识别失败', 'small text-danger sheet-info');
        if (!options.silent) {
            alert(error.message || '识别失败');
        }
    } finally {
        if (card.dataset.sheetStatus === 'loading' && card.dataset.pendingSpreadsheetId === spreadsheetId) {
            card.dataset.sheetStatus = 'idle';
            delete card.dataset.pendingSpreadsheetId;
        }
    }
}

async function fetchStockSuggestions(card, keyword) {
    const productId = card.dataset.productId;
    const resultsEl = card.querySelector('.stock-search-results');
    if (!keyword.trim()) {
        resultsEl.classList.add('d-none');
        return;
    }
    if (stockAbortControllers[productId]) {
        stockAbortControllers[productId].abort();
    }
    stockAbortControllers[productId] = new AbortController();
    try {
        const marketType = getCardMarketType(card);
        const data = await Api.endpoints.stock.search(`q=${encodeURIComponent(keyword.trim())}&market_type=${encodeURIComponent(marketType)}`, {
            signal: stockAbortControllers[productId].signal
        });
        const results = Array.isArray(data && data.results) ? data.results : [];
        resultsEl.innerHTML = results.length ? results.map((item) => `
            <button class="stock-search-item" type="button" data-code="${escapeHtml(item.code)}" data-market="${escapeHtml(item.market_type || getCardMarketType(card))}" data-exchange-market="${escapeHtml(item.market || '')}" data-name="${escapeHtml(item.name || item.code)}">
                <div class="fw-semibold">${escapeHtml(item.code)}</div>
                <div class="small text-body-secondary">${escapeHtml(item.label || '')}</div>
            </button>
        `).join('') : '<div class="px-3 py-2 small text-body-secondary">暂无匹配结果</div>';
        resultsEl.classList.remove('d-none');
    } catch (error) {
        if (error.name !== 'AbortError') {
            resultsEl.innerHTML = `<div class="px-3 py-2 small text-danger">${escapeHtml(error.message || '搜索失败')}</div>`;
            resultsEl.classList.remove('d-none');
        }
    }
}

function collectParameterRows(card) {
    const version = card.dataset.modelVersion || 'c3';
    return Array.from(card.querySelectorAll('.param-body tr'))
        .map((row) => Array.from(row.querySelectorAll('.param-input')).map((input) => input.value.trim()))
        .filter((row) => version === 'c3' ? row.slice(1).some(Boolean) : row.some(Boolean));
}

function parseParameterClipboard(raw) {
    return String(raw || '')
        .split(/\r?\n/)
        .map((line) => line.split(/\t|,/).map((item) => item.trim()))
        .filter((row) => row.some(Boolean));
}

function normalizePastedParameterRow(card, row) {
    const version = card.dataset.modelVersion || 'c3';
    const values = row.map((item) => String(item ?? '').trim());
    if (version !== 'c3') {
        return values;
    }
    if (values.length === 6) {
        return [getCardDefaultCommission(card), ...values];
    }
    if (values.length === 7) {
        values[0] = values[0] || getCardDefaultCommission(card);
        return values;
    }
    return values;
}

function parameterRowsToClipboard(card) {
    return collectParameterRows(card)
        .map((row) => row.join('\t'))
        .join('\n');
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

function setButtonBusy(button, text) {
    if (!button) return () => {};
    const originalHtml = button.innerHTML;
    button.disabled = true;
    button.innerHTML = text;
    return () => {
        button.disabled = false;
        button.innerHTML = originalHtml;
    };
}

async function pasteParametersFromClipboard(card, button) {
    const restore = setButtonBusy(button, '<span class="spinner-border spinner-border-sm me-1"></span>读取中');
    try {
        const raw = await readClipboardText();
        const rows = parseParameterClipboard(raw);
        if (!rows.length) {
            throw new Error('剪切板中没有可追加的参数行');
        }
        rows.forEach((row) => {
            const normalizedRow = normalizePastedParameterRow(card, row);
            const reusableRow = Array.from(card.querySelectorAll('.param-body tr'))
                .find((tr) => isReusableParameterRow(card, tr));
            if (reusableRow) {
                const inputs = Array.from(reusableRow.querySelectorAll('.param-input'));
                inputs.forEach((input, index) => {
                    input.value = normalizedRow[index] ?? (input.dataset.key === 'commission' ? getCardDefaultCommission(card) : '');
                });
                return;
            }
            addParameterRow(card, normalizedRow);
        });
        setParamActionStatus(card, `已追加 ${rows.length} 行参数`, 'small text-success align-self-center param-action-status');
    } catch (error) {
        alert(error.message || '读取剪切板失败');
    } finally {
        restore();
    }
}

async function copyParametersToClipboard(card, button) {
    const restore = setButtonBusy(button, '<span class="spinner-border spinner-border-sm me-1"></span>复制中');
    try {
        const text = parameterRowsToClipboard(card);
        if (!text) {
            throw new Error('当前产品没有可复制的参数');
        }
        await writeClipboardText(text);
        setParamActionStatus(card, '参数已复制，可直接粘贴到其他产品或 Excel', 'small text-success align-self-center param-action-status');
    } catch (error) {
        alert(error.message || '复制失败');
    } finally {
        restore();
    }
}

function collectProducts() {
    return getProductCards().map((card, index) => ({
        product_index: index,
        product_name: card.querySelector('.product-name').value.trim() || `产品 ${index + 1}`,
        stock_code: card.querySelector('.stock-code').value.trim().toUpperCase(),
        market_type: card.querySelector('.market-type').value,
        exchange_market: card.dataset.exchangeMarket || undefined,
        kline_adjustment: card.querySelector('.kline-adjustment').value || 'forward',
        kline_data_source: card.querySelector('.kline-data-source')?.value || 'akshare',
        price_mode: card.querySelector('.price-mode').value || 'sp_price',
        ratio: card.querySelector('.ratio-input').value.trim(),
        is_fixed: Boolean(card.querySelector('.fixed-product')?.checked),
        sheet: {
            spreadsheet_id: card.dataset.sheetStatus === 'success' ? card.dataset.spreadsheetId : '',
            sheet_name: card.dataset.sheetName || 'data',
            title: card.dataset.sheetTitle || ''
        },
        parameters: collectParameterRows(card)
    }));
}

function cloneProductForTask(product, index) {
    const cloned = JSON.parse(JSON.stringify(product));
    cloned.product_index = index;
    return cloned;
}

function buildTaskProductGroups(products) {
    const fixedProducts = products.filter((product) => product.is_fixed);
    const activeProducts = products.filter((product) => !product.is_fixed);
    if (fixedProducts.length && activeProducts.length) {
        return activeProducts.map((activeProduct) => [...fixedProducts, activeProduct]
            .map((product, index) => cloneProductForTask(product, index)));
    }
    return [products.map((product, index) => cloneProductForTask(product, index))];
}

function buildBatchId() {
    if (window.crypto?.randomUUID) {
        return window.crypto.randomUUID();
    }
    return `batch-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function buildTaskName(products) {
    return products.map((product, index) => (
        product.product_name?.trim() || product.stock_code?.trim() || `产品 ${index + 1}`
    )).join('-');
}

function validatePayload(products) {
    if (products.length < 2) {
        throw new Error('至少需要 2 个产品');
    }
    const expectedRows = products[0].parameters.length;
    products.forEach((product, index) => {
        if (!product.stock_code) throw new Error(`产品 ${index + 1} 缺少股票代码`);
        if (!product.sheet.spreadsheet_id) throw new Error(`产品 ${index + 1} 缺少 Google Sheet`);
        const card = getProductCards()[index];
        if (card?.dataset.sheetStatus === 'loading') throw new Error(`产品 ${index + 1} 的 Google Sheet 正在识别，请稍后`);
        if (card?.dataset.sheetStatus !== 'success') throw new Error(`产品 ${index + 1} 的 Google Sheet 尚未自动识别成功`);
        if (!product.parameters.length) throw new Error(`产品 ${index + 1} 缺少参数`);
        if (product.parameters.length !== expectedRows) throw new Error('所有产品参数行数必须一致');
    });
}

async function loadBacktestTokens() {
    try {
        const data = await Api.endpoints.googleSheet.tokens('task_type=backtest_training');
        const allTokens = Array.isArray(data.tokens) ? data.tokens : [];
        // 只展示回测可用的 Token：启用且未达到最大占用。
        const tokens = allTokens.filter((token) => token.is_active && token.is_available);
        tokenIdSelect.innerHTML = tokens.length ? tokens.map((token) => `
            <option value="${escapeHtml(token.id)}" ${token.is_available ? '' : 'disabled'}>
                ${escapeHtml(token.name)} | 占用 ${escapeHtml(token.current_in_use_count || 0)}
            </option>
        `).join('') : '<option value="">暂无可用 Token</option>';
    } catch (error) {
        tokenIdSelect.innerHTML = '<option value="">加载 Token 失败</option>';
    }
}

async function createTask() {
    createStatus.className = 'small text-body-secondary align-self-center';
    createStatus.textContent = '';
    const createButton = document.getElementById('createBtn');
    createButton.disabled = true;
    try {
        const products = collectProducts();
        validatePayload(products);
        const taskGroups = buildTaskProductGroups(products);
        const batchId = buildBatchId();
        const startDate = document.getElementById('startDate').value;
        const endDate = document.getElementById('endDate').value;
        if (!startDate || !endDate) throw new Error('请选择 K 线数据时间范围');
        if (!tokenIdSelect.value) throw new Error('请选择回测 Token');

        for (let index = 0; index < taskGroups.length; index += 1) {
            const groupProducts = taskGroups[index];
            createStatus.className = 'small text-body-secondary align-self-center';
            createStatus.textContent = `正在创建 ${index + 1}/${taskGroups.length}`;
            await Api.endpoints.task.create({
                name: buildTaskName(groupProducts),
                description: 'multi product backtest task',
                task_type: TASK_TYPE,
                config: {
                    start_date: startDate,
                    end_date: endDate,
                    token_type: 'file',
                    token_id: Number(tokenIdSelect.value),
                    fixed_product_batch_id: batchId,
                    // 旧版累计收益直接加权算法已停用，固定使用日收益加权后复利。
                    weighting_mode: 'daily_compound',
                    products: groupProducts
                }
            });
        }
        window.location.href = '/backtest-multi-product/list';
    } catch (error) {
        createStatus.className = 'small text-danger align-self-center';
        createStatus.textContent = error.message || '任务创建失败';
    } finally {
        createButton.disabled = false;
    }
}

productsContainer.addEventListener('click', (event) => {
    const card = event.target.closest('.product-card');
    if (!card) return;
    if (event.target.closest('.product-collapse-toggle')) {
        setProductCollapsed(card, !card.classList.contains('is-collapsed'));
        return;
    }
    const header = event.target.closest('.product-card-header');
    if (header && !event.target.closest('button, input, label, select, a, .form-check')) {
        setProductCollapsed(card, !card.classList.contains('is-collapsed'));
        return;
    }
    if (event.target.closest('.delete-product')) {
        card.remove();
        updateRatioTotal();
        return;
    }
    if (event.target.closest('.add-param')) {
        addParameterRow(card);
        markParamTouched(card);
        return;
    }
    if (event.target.closest('.delete-param')) {
        event.target.closest('tr')?.remove();
        markParamTouched(card);
        return;
    }
    if (event.target.closest('.reset-params')) {
        resetCardParamsToGlobal(card);
        return;
    }
    const pasteButton = event.target.closest('.paste-param');
    if (pasteButton) {
        markParamTouched(card);
        pasteParametersFromClipboard(card, pasteButton);
        return;
    }
    const copyButton = event.target.closest('.copy-param');
    if (copyButton) {
        copyParametersToClipboard(card, copyButton);
        return;
    }
    const stockItem = event.target.closest('.stock-search-item');
    if (stockItem) {
        card.querySelector('.stock-code').value = stockItem.dataset.code || '';
        card.querySelector('.product-name').value = stockItem.dataset.name || stockItem.dataset.code || '';
        card.querySelector('.market-type').value = stockItem.dataset.market || 'cn';
        card.dataset.exchangeMarket = stockItem.dataset.exchangeMarket || '';
        card.dataset.marketTouched = '1';
        card.dataset.marketManual = '1';
        syncCardDataSourceWithMarket(card, card.querySelector('.market-type').value);
        syncEmptyCommissionRows(card);
        updateProductSummary(card);
        card.querySelector('.stock-search-results').classList.add('d-none');
    }
});

productsContainer.addEventListener('input', (event) => {
    const sheetInput = event.target.closest('.sheet-url');
    if (sheetInput) {
        const card = event.target.closest('.product-card');
        card.dataset.sheetTouched = '1';
        scheduleSheetAnalyze(card);
        return;
    }
    const paramInput = event.target.closest('.param-input');
    if (paramInput) {
        markParamTouched(event.target.closest('.product-card'));
        return;
    }
    const stockInput = event.target.closest('.stock-code');
    if (!stockInput) return;
    const card = event.target.closest('.product-card');
    card.dataset.exchangeMarket = '';
    window.clearTimeout(stockTimers[card.dataset.productId]);
    stockTimers[card.dataset.productId] = window.setTimeout(() => {
        applyStockMarketInference(card, stockInput.value);
        fetchStockSuggestions(card, stockInput.value);
    }, 600);
});

// 产品卡片内手动修改过的字段记为"已自定义"，不再跟随全局设置变化。
productsContainer.addEventListener('change', (event) => {
    const card = event.target.closest('.product-card');
    if (!card) return;
    if (event.target.closest('.price-mode')) {
        card.dataset.priceTouched = '1';
        card.dataset.priceModeTouched = '1';
        return;
    }
    if (event.target.closest('.market-type')) {
        card.dataset.marketTouched = '1';
        card.dataset.marketManual = '1';
        syncCardDataSourceWithMarket(card, event.target.value);
        return;
    }
    if (event.target.closest('.kline-adjustment')) {
        card.dataset.klineTouched = '1';
        return;
    }
    if (event.target.closest('.kline-data-source')) {
        card.dataset.sourceTouched = '1';
        delete card.dataset.sourceAuto;
    }
});

// 全局设置变化：同步到所有未被自定义覆盖的产品卡片。
function applyGlobalSettingsToCards() {
    const cards = getProductCards();
    if (!cards.length) {
        return;
    }
    cards.forEach((card) => {
        if (card.dataset.marketTouched !== '1') {
            const marketSelect = card.querySelector('.market-type');
            if (marketSelect && marketSelect.value !== globalMarketTypeSelect.value) {
                marketSelect.value = globalMarketTypeSelect.value;
                syncEmptyCommissionRows(card);
            }
        }
        if (card.dataset.klineTouched !== '1') {
            const klineSelect = card.querySelector('.kline-adjustment');
            if (klineSelect) klineSelect.value = globalKlineAdjustmentSelect.value;
        }
        if (card.dataset.priceTouched !== '1') {
            const priceSelect = card.querySelector('.price-mode');
            if (priceSelect) priceSelect.value = globalPriceModeSelect.value;
        }
        if (card.dataset.sourceTouched !== '1') {
            const sourceSelect = card.querySelector('.kline-data-source');
            // 自定义了市场的卡片，数据源由卡片自己的市场联动决定，不被全局覆盖。
            if (sourceSelect && card.dataset.marketTouched !== '1') {
                sourceSelect.value = globalKlineDataSourceSelect.value;
            }
        }
        updateProductSummary(card);
        if (!card.querySelector('.sheet-url').value.trim()) {
            scheduleSheetAnalyze(card);
        }
    });
}

// ---- 全局参数下发 ----
// 顶部全局参数表整表下发到"未自定义参数 且 模板版本一致"的产品卡片，保持行号对齐；
// 版本不同的卡片（自有 Sheet 是别的模板）跳过继承，需自行填写参数。
function isParamFollowEnabled(card) {
    const cardVersion = card.dataset.modelVersion || 'c3';
    const globalVersion = globalParamSection?.dataset.modelVersion || 'c3';
    return card.dataset.paramTouched !== '1' && cardVersion === globalVersion;
}

function applyGlobalParamsToCard(card) {
    if (!globalParamSection || !isParamFollowEnabled(card)) {
        return;
    }
    const version = card.dataset.modelVersion || 'c3';
    const globalRows = collectParameterRows(globalParamSection);
    // C3 手续费默认值按市场不同：全局默认值原样下发会带错费率，
    // 命中全局市场默认值的单元格替换为目标卡片市场的默认值，自定义值原样透传。
    const globalCommissionDefault = String(getCardDefaultCommission(globalParamSection)).trim();
    const cardCommissionDefault = String(getCardDefaultCommission(card)).trim();
    card.querySelector('.param-body').innerHTML = '';
    if (!globalRows.length) {
        addParameterRow(card);
        return;
    }
    globalRows.forEach((row) => {
        const values = [...row];
        if (version === 'c3' && globalCommissionDefault
            && String(values[0] ?? '').trim() === globalCommissionDefault) {
            values[0] = cardCommissionDefault || values[0];
        }
        addParameterRow(card, values);
    });
}

function applyGlobalParamsToCards() {
    getProductCards().forEach(applyGlobalParamsToCard);
}

// 表格输入类操作密集触发，下发做 250ms 防抖；结构性操作（粘贴/加行）完成后同样收敛到这里。
function scheduleGlobalParamPropagation() {
    if (!globalParamSection) {
        return;
    }
    window.clearTimeout(globalParamPropagationTimer);
    globalParamPropagationTimer = window.setTimeout(applyGlobalParamsToCards, 250);
}

function resetCardParamsToGlobal(card) {
    delete card.dataset.paramTouched;
    updateParamFollowStatus(card);
    if (!isParamFollowEnabled(card)) {
        setParamActionStatus(
            card,
            `产品模板为 ${(card.dataset.modelVersion || 'c3').toUpperCase()}，与全局参数版本不一致，未跟随`,
            'small text-warning align-self-center param-action-status'
        );
        return;
    }
    applyGlobalParamsToCard(card);
    setParamActionStatus(card, '已重置为全局参数', 'small text-success align-self-center param-action-status');
}

// 全局价格模式的 C7.0.3 默认：识别全局 Sheet 标题后切换全局价格模式，
// 再经 applyGlobalSettingsToCards 下发到未自定义的产品卡片；手动改过全局价格模式后不再自动切换。
function applyGlobalPriceModeDefault(title) {
    if (!globalPriceModeSelect || globalPriceModeSelect.dataset.touched === '1') {
        return;
    }
    const isC703 = String(title || '').toUpperCase().includes('C7.0.3');
    const nextValue = isC703 ? 'ohlc_price' : 'sp_price';
    if (globalPriceModeSelect.value !== nextValue) {
        globalPriceModeSelect.value = nextValue;
        applyGlobalSettingsToCards();
    }
}

function setGlobalSheetInfo(message, className = 'small text-body-secondary') {
    if (!globalSheetInfo) {
        return;
    }
    globalSheetInfo.className = className;
    globalSheetInfo.textContent = message;
}

// 全局链接单独识别一次，用于驱动全局价格模式的 C7.0.3 默认值与识别状态展示；
// 产品卡片继承同一链接时仍各自识别（卡片还需标题推断模型版本）。
async function analyzeGlobalSheet() {
    const spreadsheetId = extractSpreadsheetId(globalSheetUrlInput?.value || '');
    if (!spreadsheetId) {
        globalSheetRequestId += 1;
        globalSheetLastId = '';
        globalSheetStatus = 'idle';
        setGlobalSheetInfo('尚未识别全局 Sheet（下方产品可留空继承）');
        return;
    }
    if (globalSheetStatus === 'success' && globalSheetLastId === spreadsheetId) {
        return;
    }
    const requestId = ++globalSheetRequestId;
    globalSheetStatus = 'loading';
    setGlobalSheetInfo('正在自动识别全局 Sheet...', 'small text-primary');
    try {
        const data = await Api.endpoints.googleSheet.worksheets({ spreadsheet_id: spreadsheetId });
        if (requestId !== globalSheetRequestId) {
            return;
        }
        globalSheetLastId = spreadsheetId;
        globalSheetStatus = 'success';
        const title = data.title || '';
        const sheetName = Array.isArray(data.worksheets) && data.worksheets.length ? data.worksheets[0] : 'data';
        applyGlobalPriceModeDefault(title);
        if (globalParamSection) {
            const nextVersion = inferModelVersion(title);
            if (globalParamSection.dataset.modelVersion !== nextVersion) {
                resetParameterTable(globalParamSection, nextVersion);
            }
            scheduleGlobalParamPropagation();
        }
        setGlobalSheetInfo(`${title || spreadsheetId} / ${sheetName}`, 'small text-success');
    } catch (error) {
        if (requestId !== globalSheetRequestId) {
            return;
        }
        globalSheetLastId = '';
        globalSheetStatus = 'idle';
        setGlobalSheetInfo(error.message || '全局 Sheet 识别失败', 'small text-danger');
    }
}

// 全局市场联动全局数据源：非 A股统一切 Yahoo；切回 A股时仅恢复联动自动切换的值。
globalMarketTypeSelect?.addEventListener('change', () => {
    if (globalKlineDataSourceSelect) {
        if (globalMarketTypeSelect.value !== 'cn') {
            globalKlineDataSourceSelect.value = 'yahoo';
            globalKlineDataSourceSelect.dataset.autoSource = '1';
        } else if (globalKlineDataSourceSelect.dataset.autoSource === '1') {
            globalKlineDataSourceSelect.value = 'akshare';
            delete globalKlineDataSourceSelect.dataset.autoSource;
        }
    }
    applyGlobalSettingsToCards();
    if (globalParamSection) {
        // 全局市场决定全局参数表 C3 手续费默认值；下发时按各卡片市场换算。
        syncEmptyCommissionRows(globalParamSection);
        scheduleGlobalParamPropagation();
    }
});
globalKlineAdjustmentSelect?.addEventListener('change', applyGlobalSettingsToCards);
globalPriceModeSelect?.addEventListener('change', () => {
    // 手动修改后全局价格模式不再跟随 C7.0.3 自动切换（程序赋值不触发 change）。
    globalPriceModeSelect.dataset.touched = '1';
    applyGlobalSettingsToCards();
});
globalKlineDataSourceSelect?.addEventListener('change', () => {
    // 手动选过数据源后，市场联动不再自动改写全局数据源（程序赋值不触发 change）。
    delete globalKlineDataSourceSelect.dataset.autoSource;
    globalKlineDataSourceSelect.dataset.touched = '1';
    applyGlobalSettingsToCards();
});
globalSheetUrlInput?.addEventListener('input', () => {
    window.clearTimeout(globalSheetTimer);
    globalSheetTimer = window.setTimeout(() => {
        applyGlobalSettingsToCards();
        analyzeGlobalSheet();
    }, 500);
});

productsContainer.addEventListener('paste', (event) => {
    const sheetInput = event.target.closest('.sheet-url');
    if (!sheetInput) return;
    const card = event.target.closest('.product-card');
    window.setTimeout(() => scheduleSheetAnalyze(card, { immediate: true }), 0);
});

document.addEventListener('click', (event) => {
    if (!event.target.closest('.stock-search-shell')) {
        document.querySelectorAll('.stock-search-results').forEach((el) => el.classList.add('d-none'));
    }
});

document.getElementById('addProductBtn').addEventListener('click', () => addProduct());
document.getElementById('createBtn').addEventListener('click', createTask);

// 全局参数区（伪卡片）自身的表格操作；编辑后防抖下发到未自定义的产品。
globalParamSection?.addEventListener('click', (event) => {
    if (event.target.closest('.add-param')) {
        addParameterRow(globalParamSection);
        scheduleGlobalParamPropagation();
        return;
    }
    if (event.target.closest('.delete-param')) {
        event.target.closest('tr')?.remove();
        scheduleGlobalParamPropagation();
        return;
    }
    const pasteButton = event.target.closest('.paste-param');
    if (pasteButton) {
        pasteParametersFromClipboard(globalParamSection, pasteButton)
            .finally(scheduleGlobalParamPropagation);
        return;
    }
    const copyButton = event.target.closest('.copy-param');
    if (copyButton) {
        copyParametersToClipboard(globalParamSection, copyButton);
    }
});

globalParamSection?.addEventListener('input', (event) => {
    if (event.target.closest('.param-input')) {
        scheduleGlobalParamPropagation();
    }
});

const defaultDateRange = TradingDate.defaultDateRange(3);
document.getElementById('endDate').value = TradingDate.formatDate(defaultDateRange.end);
document.getElementById('startDate').value = TradingDate.formatDate(defaultDateRange.start);
loadStockMarkets().then(() => {
    // 全局参数表先就位（含 C3 手续费默认值），产品卡片创建时才能继承。
    resetParameterTable(globalParamSection, 'c3');
    initParameterHelpPopover(globalParamSection);
    addProduct({ ratio: 50 });
    addProduct({ ratio: 50 });
}).catch((error) => {
    createStatus.textContent = error.message || '市场枚举加载失败';
    createStatus.className = 'small align-self-center text-danger';
});
loadBacktestTokens();

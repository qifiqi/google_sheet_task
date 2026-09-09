// ------------------------------
// c4/c5/c7 创建页三胞胎共享：表单状态/Token 选择/产品 chips/URL 回填（02 §3.6，F3 收敛 pass）。
// 来源：static/js/pages/google_sheet_c{4,5,7}_create.js（正本以 c5/c7 同源脚本为准）。
// 表单状态（token 列表/待回填 token 选择/产品代码）由本模块持有；
// 页面差异逻辑（模板回填 fillFormWithTemplate / 重启回填 loadRestartConfig /
// 本地草稿 loadSavedFormData）留在 pages 层，页面在 initFromUrlParams() 之前
// 经 Biz.formState.hooks = {...} 注册；调用点经 Biz.formState.* 访问。
// ------------------------------
(function () {
    window.Biz = window.Biz || {};

    let pendingTokenSelection = null;
    let googleSheetTokens = [];
    let googleSheetRandomValue = '__random__';
    let productCodes = [];

    function callPageHook(name, ...args) {
        const hook = (window.Biz.formState && window.Biz.formState.hooks)
            ? window.Biz.formState.hooks[name]
            : null;
        return typeof hook === 'function' ? hook(...args) : undefined;
    }

    function showError(message) {
        if (typeof showNotification === 'function') {
            showNotification(message, 'error');
        } else {
            alert(message);
        }
    }

    function syncSelectedTokenMeta() {
        const tokenTypeEl = document.getElementById('token_type');
        const tokenIdEl = document.getElementById('token_id');
        const tokenFileEl = document.getElementById('token_file');
        if (!tokenTypeEl || !tokenIdEl || !tokenFileEl) {
            return;
        }
    
        if (tokenTypeEl.value !== 'file') {
            tokenFileEl.value = '';
            return;
        }
    
        const selected = googleSheetTokens.find(token => String(token.id) === String(tokenIdEl.value));
        tokenFileEl.value = selected ? (selected.token_file || '') : '';
    }

    function applyPendingTokenSelection() {
        if (!pendingTokenSelection) {
            syncSelectedTokenMeta();
            return;
        }
    
        const tokenIdEl = document.getElementById('token_id');
        const tokenFileEl = document.getElementById('token_file');
        if (!tokenIdEl || !tokenFileEl) {
            return;
        }
    
        const tokenId = pendingTokenSelection.token_id;
        const tokenFile = pendingTokenSelection.token_file;
        let matchedValue = '';
    
        if (tokenId && Array.from(tokenIdEl.options).some(option => option.value === String(tokenId))) {
            matchedValue = String(tokenId);
        } else if (tokenFile) {
            const matchedToken = googleSheetTokens.find(token => token.token_file === tokenFile);
            if (matchedToken) {
                matchedValue = String(matchedToken.id);
            }
        }
    
        if (!matchedValue && pendingTokenSelection.token_selection_mode === googleSheetRandomValue) {
            matchedValue = googleSheetRandomValue;
        }
    
        if (matchedValue) {
            tokenIdEl.value = matchedValue;
        }
        tokenFileEl.value = tokenFile || '';
        syncSelectedTokenMeta();
    }

    function renderGoogleSheetTokenOptions(tokens) {
        const tokenIdEl = document.getElementById('token_id');
        if (!tokenIdEl) {
            return;
        }
    
        tokenIdEl.innerHTML = '';
    
        const randomOption = document.createElement('option');
        randomOption.value = googleSheetRandomValue;
        randomOption.textContent = '随机Token（按最低使用数均衡分配）';
        tokenIdEl.appendChild(randomOption);
    
        tokens.forEach(token => {
            const option = document.createElement('option');
            option.value = String(token.id);
            option.textContent = `${token.name} | 占用 ${token.current_in_use_count || 0} | 累计 ${token.task_usage_count} | 上限 ${token.max_usage_count > 0 ? token.max_usage_count : '无限'}`;
            option.disabled = !token.is_available;
            tokenIdEl.appendChild(option);
        });
    
        applyPendingTokenSelection();
    }

    function loadGoogleSheetTokens(preferredValue = null) {
        if (preferredValue) {
            pendingTokenSelection = { token_id: preferredValue };
        }
    
        Api.endpoints.googleSheet.tokens('?task_type=google_sheet')
            .then(data => {
                googleSheetTokens = Array.isArray(data.tokens) ? data.tokens : [];
                googleSheetRandomValue = data.random_value || '__random__';
                renderGoogleSheetTokenOptions(googleSheetTokens);
            })
            .catch(error => {
                const tokenIdEl = document.getElementById('token_id');
                if (tokenIdEl) {
                    tokenIdEl.innerHTML = '<option value="">加载Token失败</option>';
                }
                console.error('加载Google Sheet Token失败:', error);
            });
    }

    function importGoogleSheetToken() {
        const input = document.getElementById('token_import_path');
        const tokenFile = input ? input.value.trim() : '';
        if (!tokenFile) {
            showNotification('请输入Token文件路径', 'warning');
            return;
        }
    
        Api.endpoints.googleSheet.importToken({ token_file: tokenFile })
            .then(data => {
                showNotification(data.message || 'Token导入成功', 'success');
                pendingTokenSelection = { token_id: data.token && data.token.id ? String(data.token.id) : '' };
                loadGoogleSheetTokens();
                if (input) {
                    input.value = '';
                }
            })
            .catch(error => {
                showNotification(`导入Token失败: ${error.message}`, 'error');
            });
    }

    function applyDateRangeModes(raw) {
        const fullEl = document.getElementById('date_range_full');
        const recentEl = document.getElementById('date_range_recent');
        let modes = [];
        if (Array.isArray(raw)) {
            modes = raw;
        } else if (typeof raw === 'string' && raw) {
            modes = [raw];
        }
        if (modes.length === 0) {
            modes = ['full'];
        }
        if (fullEl) {
            fullEl.checked = modes.includes('full');
        }
        if (recentEl) {
            recentEl.checked = modes.includes('recent');
        }
    }

    function initDefaultDatesIfEmpty() {
        const startInput = document.getElementById('start_date');
        const endInput = document.getElementById('end_date');
        if (!startInput || !endInput) return;
    
        // 已有值（来自模板/重启/本地存储），不覆盖
        if (startInput.value || endInput.value) {
            return;
        }
    
        const range = TradingDate.defaultDateRange(5);
        endInput.value = TradingDate.formatDate(range.end);
        startInput.value = TradingDate.formatDate(range.start);
    }

    function initProductCodeChipsFromParam1() {
        const param1El = document.getElementById('param1');
        if (!param1El) return;
    
        let arr = [];
        if (param1El.value && param1El.value.trim()) {
            const parsed = parseJsonArray(param1El.value);
            if (Array.isArray(parsed)) {
                arr = parsed;
            }
        }
        productCodes = arr;
        renderProductCodeChips();
        callPageHook('syncProductCodesToParam1');
    }

    function renderProductCodeChips() {
        const container = document.getElementById('product_code_chips');
        if (!container) return;
    
        container.innerHTML = '';
        productCodes.forEach(function(code) {
            const span = document.createElement('span');
            span.className = 'badge bg-primary text-white d-inline-flex align-items-center';
            span.style.fontSize = '0.75rem';
            span.style.paddingRight = '0.35rem';
            span.innerHTML = `
                <span class="me-1">${code}</span>
                <button type="button" class="btn-close btn-close-white btn-sm ms-1" data-code-remove="${code}" style="font-size: 0.45rem;"></button>
            `;
            container.appendChild(span);
        });
    
        callPageHook('syncProductCodesToParam1');
    }

    function initFromUrlParams() {
        const params = new URLSearchParams(window.location.search);
        const templateId = params.get('template_id');
        const restartTaskId = params.get('restart_task_id');
    
        if (templateId) {
            callPageHook('fillFormWithTemplate', templateId);
            return;
        }

        if (restartTaskId) {
            fillFormWithRestartTask(restartTaskId);
            return;
        }

        callPageHook('loadSavedFormData');
    }

    function fillFormWithRestartTask(taskId) {
        Api.endpoints.task.detail(encodeURIComponent(taskId))
            .then(data => {
                const task = (data && data.task) ? data.task : null;
                const configRaw = task ? task.config : null;
                if (!configRaw) {
                    showNotification('加载原任务配置失败：config为空', 'error');
                    return;
                }
                callPageHook('loadRestartConfig', configRaw, taskId);
            })
            .catch(err => {
                console.error('加载原任务失败:', err);
                showNotification('加载原任务失败', 'error');
            });
    }

    async function loadStockMarkets(selectedValue = 'cn') {
        const select = document.getElementById('market_type');
        const payload = await Api.endpoints.meta.enums();
        select.innerHTML = (payload?.stock_markets || []).map((market) =>
            `<option value="${market.value}">${market.label}</option>`
        ).join('');
        select.value = selectedValue;
    }

    function setPendingTokenSelection(selection) {
        pendingTokenSelection = selection || null;
    }

    function getProductCodes() {
        return productCodes;
    }

    function setProductCodes(codes) {
        productCodes = Array.isArray(codes) ? codes : [];
    }

    Biz.formState = {
        showError: showError,
        syncSelectedTokenMeta: syncSelectedTokenMeta,
        applyPendingTokenSelection: applyPendingTokenSelection,
        setPendingTokenSelection: setPendingTokenSelection,
        renderGoogleSheetTokenOptions: renderGoogleSheetTokenOptions,
        loadGoogleSheetTokens: loadGoogleSheetTokens,
        importGoogleSheetToken: importGoogleSheetToken,
        applyDateRangeModes: applyDateRangeModes,
        initDefaultDatesIfEmpty: initDefaultDatesIfEmpty,
        initProductCodeChipsFromParam1: initProductCodeChipsFromParam1,
        renderProductCodeChips: renderProductCodeChips,
        getProductCodes: getProductCodes,
        setProductCodes: setProductCodes,
        initFromUrlParams: initFromUrlParams,
        fillFormWithRestartTask: fillFormWithRestartTask,
        loadStockMarkets: loadStockMarkets
    };
})();

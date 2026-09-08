// Google Sheet 创建任务页（C7）（templates/google_sheet_c7/create.html 的页面逻辑）。
// 批内收敛：同名函数已提升至 static/js/common/business/（Biz.*），见 F3 收敛 pass。
// 自 templates/google_sheet_c7/create.html 内联脚本原样抽离；接口调用经 common/api.js。

// ── 原 Jinja 服务端渲染点的前端等价实现（静态化，docs/design/frontend-refactor/03 §5）──
// 原 `url_for('google_sheet.index', version=request.args.get('version', 'c7'))`
const versionParam = new URLSearchParams(location.search).get('version');
if (versionParam && versionParam !== 'c7') {
    const backLink = document.querySelector('a[href="/google-sheet/?version=c7"]');
    if (backLink) {
        backLink.href = '/google-sheet/?version=' + encodeURIComponent(versionParam);
    }
}
    const GOOGLE_SHEET_TABLE_TYPE = 'c7';
    let googleSheetTokens = [];
    let googleSheetRandomValue = '__random__';
    let pendingTokenSelection = null;

    let currentTaskId = null;
    let eventSource = null;
    let productCodes = [];

    // 本页专用错误提示封装
    // 从模板加载数据
    function loadFromTemplate(template) {
        if (!template) return;

        try {
            // 填充基本信息
            if (template.name) {
                document.getElementById('task_name').value = template.name;
            }
            if (template.description) {
                document.getElementById('task_description').value = template.description;
            }

            // 填充配置信息
            if (template.config) {
                let config = template.config;
                if (typeof config === 'string') {
                    config = JSON.parse(config);
                }

                config = normalizeC4Config(config);
                applySheetsToForm(config.sheets);

                if (config.token_type) {
                    document.getElementById('token_type').value = config.token_type;
                    document.getElementById('token_type').dispatchEvent(new Event('change'));
                }

                pendingTokenSelection = {
                    token_id: config.token_id || '',
                    token_file: config.token_file || '',
                    token_selection_mode: config.token_selection_mode || ''
                };
                Biz.formState.applyPendingTokenSelection();

                if (config.token_file) {
                    document.getElementById('token_file').value = config.token_file;
                }

                if (config.token_json) {
                    document.getElementById('token_json').value = config.token_json;
                }

                if (config.proxy_url) {
                    document.getElementById('proxy_url').value = config.proxy_url;
                }

                if (config.kline_source) {
                    const sourceInput = document.querySelector(`input[name="kline_source"][value="${config.kline_source}"]`);
                    if (sourceInput) {
                        sourceInput.checked = true;
                    }
                }

                if (config.market_type) document.getElementById('market_type').value = config.market_type;
                if (config.kline_adjustment) {
                    const adjustSelect = document.getElementById('kline_adjustment');
                    if (adjustSelect) adjustSelect.value = config.kline_adjustment;
                }
                if (config.kline_data_source) {
                    const sourceSelect = document.getElementById('kline_data_source');
                    if (sourceSelect) sourceSelect.value = config.kline_data_source;
                }

                if (config.date_range_mode !== undefined) {
                    Biz.formState.applyDateRangeModes(config.date_range_mode);
                }

                // 填充参数配置
                if (config.parameters && Array.isArray(config.parameters)) {
                    config.parameters.forEach((param, index) => {
                        const paramId = `param${index + 1}`;
                        const paramElement = document.getElementById(paramId);
                        if (paramElement && Array.isArray(param)) {
                            paramElement.value = JSON.stringify(param);
                        }
                    });
                }

                // 更新组合计算
                updateCustomKlineModeAvailability();
                calculateCombinations();
                showNotification('已加载模板配置', 'success');

                // 更新页面标题和提示
            }
        } catch (error) {
            console.error('加载模板失败:', error);
            Biz.formState.showError('加载模板配置失败: ' + error.message);
        }
    }

    // 防抖函数
    function debounce(func, wait) {
        let timeout;
        return function executedFunction(...args) {
            const later = () => {
                clearTimeout(timeout);
                func(...args);
            };
            clearTimeout(timeout);
            timeout = setTimeout(later, wait);
        };
    }

    function getSheetConfigElements(item) {
        if (!item) {
            return {};
        }

        return {
            spreadsheetSelect: item.querySelector('.google-sheet-select') || item.querySelector('#spreadsheet'),
            googleSheetIdInput: item.querySelector('#google_sheet_id'),
            spreadsheetHelp: item.querySelector('#spreadsheet-help'),
            modelVersionSelect: item.querySelector('.c7-model-version-select') || item.querySelector('#c7_model_version'),
            titleInput: item.querySelector('.spreadsheet-title-input') || item.querySelector('#spreadsheet_title'),
            worksheetInput: item.querySelector('.worksheet-name-input') || item.querySelector('#sheet_name'),
            refreshWorksheetsBtn: item.querySelector('.refresh-worksheets-btn') || item.querySelector('#refresh-sheets'),
            sheetHelp: item.querySelector('.sheet-name-help') || item.querySelector('#sheet-name-help'),
            customContainer: item.querySelector('.custom-sheet-container') || item.querySelector('#custom-sheet-container'),
            customInput: item.querySelector('.custom-sheet-name-input') || item.querySelector('#custom_sheet_name'),
            refreshGoogleSheetsBtn: item.querySelector('#refresh-google-sheets')
        };
    }

    function getConfiguredC7ModelVersions(excludeItem = null) {
        const versions = new Set();
        document.querySelectorAll('#sheet-config-list .sheet-config-item').forEach(function(item) {
            if (item === excludeItem) {
                return;
            }
            const { spreadsheetSelect, modelVersionSelect } = getSheetConfigElements(item);
            if (extractSpreadsheetId(spreadsheetSelect?.value || '') && modelVersionSelect?.value) {
                versions.add(modelVersionSelect.value);
            }
        });
        return versions;
    }

    function enforceC7PriceMode() {
        const priceModeSelect = document.getElementById('price_mode');
        const randomOptions = document.querySelectorAll('.random-price-option');
        const priceModeHelp = document.getElementById('c7-price-mode-help');
        const forceOhlcPrice = getConfiguredC7ModelVersions().has('c7_0_3');
        if (!priceModeSelect) {
            return;
        }

        const ohlcOption = priceModeSelect.querySelector('option[value="ohlc_price"]');
        if (ohlcOption) {
            ohlcOption.disabled = !forceOhlcPrice;
        }
        if (forceOhlcPrice) {
            priceModeSelect.value = 'ohlc_price';
        } else if (priceModeSelect.value === 'ohlc_price') {
            priceModeSelect.value = 'vwap_price';
        }
        const showRandomOptions = priceModeSelect.value === 'random_price'
            && !isCustomKlineMode()
            && !forceOhlcPrice;
        randomOptions.forEach(option => {
            option.classList.toggle('d-none', !showRandomOptions);
            option.querySelectorAll('select, input').forEach(control => {
                setControlDisabled(control, !showRandomOptions);
            });
        });
        setControlDisabled(priceModeSelect, isCustomKlineMode() || forceOhlcPrice);
        if (priceModeHelp) {
            priceModeHelp.classList.toggle('d-none', !forceOhlcPrice);
        }
    }

    function updateC7ModelVersionControls() {
        const versions = getConfiguredC7ModelVersions();
        const activeVersion = versions.size === 1 ? Array.from(versions)[0] : '';

        document.querySelectorAll('#sheet-config-list .sheet-config-item').forEach(function(item) {
            const { spreadsheetSelect, modelVersionSelect } = getSheetConfigElements(item);
            if (!modelVersionSelect) {
                return;
            }

            Array.from(modelVersionSelect.options).forEach(function(option) {
                option.disabled = Boolean(activeVersion && option.value !== activeVersion);
            });
            if (!extractSpreadsheetId(spreadsheetSelect?.value || '') && activeVersion) {
                modelVersionSelect.value = activeVersion;
            }
        });

        enforceC7PriceMode();
    }

    function ensureC7ModelVersionConsistency(changedItem, clearChangedSheet = false) {
        const otherVersions = getConfiguredC7ModelVersions(changedItem);
        const { spreadsheetSelect, titleInput, worksheetInput, modelVersionSelect } = getSheetConfigElements(changedItem);
        const selectedVersion = modelVersionSelect?.value || '';

        if (otherVersions.size === 1 && !otherVersions.has(selectedVersion)) {
            const activeVersion = Array.from(otherVersions)[0];
            if (clearChangedSheet && spreadsheetSelect) {
                spreadsheetSelect.value = '';
                if (titleInput) titleInput.value = '';
                if (worksheetInput) worksheetInput.value = '';
                updateWorksheetSelectionUI(changedItem);
            }
            if (modelVersionSelect) {
                modelVersionSelect.value = activeVersion;
                modelVersionSelect.dataset.manual = 'true';
            }
            updateC7ModelVersionControls();
            showNotification('C7.0.2 与 C7.0.3 不能同时配置，请选择相同版本的 Google Sheet', 'error');
            return false;
        }

        updateC7ModelVersionControls();
        return true;
    }

    function validateC7ModelVersionSet(sheets, showMessage = true) {
        const versions = new Set(
            sheets
                .map(sheet => sheet.c7_model_version || 'c7_0_2')
                .filter(Boolean)
        );
        if (versions.size <= 1) {
            return true;
        }
        if (showMessage) {
            showNotification('C7.0.2 与 C7.0.3 不能同时添加到 Sheet 配置', 'error');
        }
        return false;
    }

    function syncSelectedGoogleSheetMetaForItem(item) {
        const { spreadsheetSelect, googleSheetIdInput, spreadsheetHelp } = getSheetConfigElements(item);
        if (!spreadsheetSelect || !googleSheetIdInput || !spreadsheetHelp) {
            return;
        }

        const selectedOption = spreadsheetSelect.options[spreadsheetSelect.selectedIndex];
        googleSheetIdInput.value = selectedOption ? (selectedOption.dataset.googleSheetId || '') : '';

        if (spreadsheetSelect.value) {
            spreadsheetHelp.innerHTML = `<i class="bi bi-info-circle"></i> 已选择 Google Sheet：${spreadsheetSelect.value}`;
        } else {
            spreadsheetHelp.innerHTML = '<i class="bi bi-info-circle"></i> 请从列表中选择可用的 Google Sheet';
        }
    }

    function updateWorksheetSelectionUI(item) {
        const { worksheetInput, sheetHelp } = getSheetConfigElements(item);
        if (!worksheetInput || !sheetHelp) {
            return;
        }
        sheetHelp.textContent = worksheetInput.value
            ? `默认使用第一个工作表：${worksheetInput.value}`
            : '默认展示接口返回的第一个工作表';
    }

    function loadGoogleSheetsForItem(item, preferredSpreadsheetId = '') {
        const { spreadsheetSelect, refreshGoogleSheetsBtn } = getSheetConfigElements(item);
        if (!item || !spreadsheetSelect) {
            return Promise.resolve();
        }

        spreadsheetSelect.disabled = true;
        if (refreshGoogleSheetsBtn) {
            refreshGoogleSheetsBtn.disabled = true;
        }

        return Api.endpoints.googleSheet.sheets(`only_available=1&table_type=${encodeURIComponent(GOOGLE_SHEET_TABLE_TYPE)}`)
            .then(data => {
                const items = Array.isArray(data?.items) ? data.items : [];
                spreadsheetSelect.innerHTML = '<option value="">请选择 Google Sheet</option>';

                items.forEach(sheetItem => {
                    const option = document.createElement('option');
                    option.value = sheetItem.spreadsheet_id || '';
                    option.textContent = `${sheetItem.name} (${sheetItem.spreadsheet_id})`;
                    option.dataset.googleSheetId = sheetItem.id || '';
                    spreadsheetSelect.appendChild(option);
                });

                if (preferredSpreadsheetId) {
                    const exists = Array.from(spreadsheetSelect.options).some(option => option.value === preferredSpreadsheetId);
                    if (!exists) {
                        const option = document.createElement('option');
                        option.value = preferredSpreadsheetId;
                        option.textContent = `当前配置 (${preferredSpreadsheetId})`;
                        option.dataset.googleSheetId = '';
                        spreadsheetSelect.appendChild(option);
                    }
                    spreadsheetSelect.value = preferredSpreadsheetId;
                }

                syncSelectedGoogleSheetMetaForItem(item);
                if (spreadsheetSelect.value) {
                    return loadWorksheetsForItem(item, false);
                }
            })
            .catch(error => {
                spreadsheetSelect.innerHTML = '<option value="">加载 Google Sheet 失败</option>';
                showNotification(`加载 Google Sheet 失败：${error.message}`, 'error');
            })
            .finally(() => {
                spreadsheetSelect.disabled = false;
                if (refreshGoogleSheetsBtn) {
                    refreshGoogleSheetsBtn.disabled = false;
                }
            });
    }

    // 获取单个配置块的工作表列表
    function loadWorksheetsForItem(item, isManualRefresh = false) {
        const {
            spreadsheetSelect,
            titleInput,
            worksheetInput,
            modelVersionSelect
        } = getSheetConfigElements(item);

        if (!item || !spreadsheetSelect || !titleInput || !worksheetInput) {
            return Promise.resolve();
        }

        const spreadsheetId = extractSpreadsheetId(spreadsheetSelect.value || '');
        const tokenType = document.getElementById('token_type').value;
        const tokenId = document.getElementById('token_id') ? document.getElementById('token_id').value : '';
        const tokenFile = document.getElementById('token_file').value;
        const proxyUrl = document.getElementById('proxy_url').value;

        if (!spreadsheetId) {
            worksheetInput.value = '';
            updateWorksheetSelectionUI(item);
            return Promise.resolve();
        }

        const requestData = {
            spreadsheet_id: spreadsheetId,
            token_id: tokenType === 'file' ? tokenId : undefined,
            token_file: tokenType === 'file' ? tokenFile : undefined,
            proxy_url: proxyUrl || undefined
        };

        return Api.endpoints.googleSheet.worksheets(requestData)
            .then(data => {
                if (!Array.isArray(data.worksheets)) {
                    throw new Error(data.message || '获取工作表列表失败');
                }

                const sheetTitle = typeof data.title === 'string' ? data.title.trim() : '';
                if (titleInput && sheetTitle) {
                    titleInput.value = sheetTitle;
                }
                const isManualModelVersion = modelVersionSelect?.dataset.manual === 'true';
                if (modelVersionSelect && !isManualModelVersion) {
                    modelVersionSelect.value = sheetTitle.startsWith('C7.0.3') ? 'c7_0_3' : 'c7_0_2';
                }
                worksheetInput.value = Array.isArray(data.worksheets) && data.worksheets.length > 0
                    ? (data.worksheets[0] || '')
                    : '';
                updateWorksheetSelectionUI(item);
                if (isManualModelVersion) {
                    updateC7ModelVersionControls();
                } else {
                    ensureC7ModelVersionConsistency(item, true);
                }
                showNotification(isManualRefresh ? '表标题已刷新' : '表标题已自动加载', 'success');
            })
            .catch(error => {
                console.error('获取工作表列表失败:', error);
                worksheetInput.value = '';
                updateWorksheetSelectionUI(item);
                Biz.formState.showError('获取工作表列表失败: ' + error.message);
            });
    }

    function loadGoogleSheets(preferredSpreadsheetId = '') {
        const firstItem = document.querySelector('#sheet-config-list .sheet-config-item');
        return firstItem ? loadGoogleSheetsForItem(firstItem, preferredSpreadsheetId) : Promise.resolve();
    }

    // 保持原有接口，默认针对第一组主配置块
    function loadWorksheets(isManualRefresh = false) {
        const firstItem = document.querySelector('#sheet-config-list .sheet-config-item');
        return firstItem ? loadWorksheetsForItem(firstItem, isManualRefresh) : Promise.resolve();
    }

    // 页面加载完成后绑定事件
    document.addEventListener('DOMContentLoaded', async function() {
        await Biz.formState.loadStockMarkets();
        bindEvents();
        loadGoogleSheets();
        Biz.formState.loadGoogleSheetTokens();
        loadTemplates(); // 加载模板列表

        // URL 参数驱动的数据加载：
        // - ?template_id=xxx -> /api/templates/xxx
        // - ?restart_task_id=xxx -> /api/tasks/xxx
        // - 其它 -> loadSavedFormData()
        Biz.formState.initFromUrlParams();

        // 初始化日期默认值（如果未从模板/重启/本地恢复）
        Biz.formState.initDefaultDatesIfEmpty();

        // 初始化产品代码chips（基于隐藏的param1值）
        Biz.formState.initProductCodeChipsFromParam1();

        updateCustomKlineModeAvailability();
        calculateCombinations();

        // 创建防抖版本的函数
        const debouncedLoadWorksheets = debounce(loadWorksheets, 500);
        const debouncedCalculateCombinations = debounce(calculateCombinations, 300);
        const debouncedSaveFormData = debounce(saveFormData, 300);

        // 监听spreadsheet选择变化
        const spreadsheetInput = document.getElementById('spreadsheet');
        spreadsheetInput.addEventListener('change', debouncedLoadWorksheets);

        // 为参数输入添加防抖
        document.querySelectorAll('textarea[id^="param"]').forEach(function(textarea) {
            textarea.addEventListener('input', function() {
                debouncedCalculateCombinations();
                debouncedSaveFormData();
            });
        });

        // 为其他输入字段添加防抖的自动保存
        const inputFields = [
            'task_name', 'task_description',
            'token_import_path', 'token_json', 'proxy_url'
        ];

        inputFields.forEach(function(fieldId) {
            const field = document.getElementById(fieldId);
            if (field) {
                field.addEventListener('input', debouncedSaveFormData);
                field.addEventListener('change', debouncedSaveFormData);
            }
        });
    });

    // 加载模板列表
    function loadTemplates() {
        // 只加载 c7 类型的模板（后端按 config.task_type 精确匹配，必须传 task_type= 查询串）
        Api.endpoints.template.list('task_type=google_sheet_c7')
            .then(data => {
                if (!data || !Array.isArray(data.templates)) {
                    console.error('Invalid response format:', data);
                    return;
                }

                const templateSelect = document.getElementById('task_template');
                data.templates.forEach(template => {
                    const option = document.createElement('option');
                    option.value = template.id;
                    option.textContent = template.name;
                    templateSelect.appendChild(option);
                });
            })
            .catch(error => {
                console.error('加载模板列表失败:', error);
                Biz.formState.showError('加载模板列表失败');
            });
    }

    // 使用模板填充表单
    function fillFormWithTemplate(templateId) {
        if (!templateId) {
            return;
        }

        Api.endpoints.template.detail(templateId)
            .then(template => {
                let config = template.config;
                console.log('[c7 fillFormWithTemplate] config =', config);

                if (typeof config === 'string') {
                    try {
                        config = JSON.parse(config);
                    } catch (e) {
                        console.error('解析模板配置失败:', e);
                        return;
                    }
                }

                applyConfigToForm(config, {
                    mode: 'template'
                });
            })
            .catch(error => {
                console.error('加载模板详情失败:', error);
                showNotification('加载模板失败', 'error');
            });
    }

    function ensureSheetConfigItemsCount(targetCount) {
        const list = document.getElementById('sheet-config-list');
        if (!list) return;
        while (list.querySelectorAll('.sheet-config-item').length < targetCount) {
            addVisualSheetConfigItem();
        }
    }

    function applySheetsToForm(sheets) {
        if (!Array.isArray(sheets) || sheets.length === 0) {
            return;
        }

        ensureSheetConfigItemsCount(sheets.length);
        const list = document.getElementById('sheet-config-list');
        if (!list) return;
        const items = list.querySelectorAll('.sheet-config-item');

        const loadPromises = [];

        sheets.forEach((sheetCfg, idx) => {
            const item = items[idx];
            if (!item) return;

            const {
                spreadsheetSelect,
                titleInput,
                worksheetInput,
                modelVersionSelect
            } = getSheetConfigElements(item);

            if (spreadsheetSelect && sheetCfg.spreadsheet_id) {
                spreadsheetSelect.value = sheetCfg.spreadsheet_id;
            }
            if (titleInput && sheetCfg.title !== undefined) {
                titleInput.value = sheetCfg.title || '';
            }
            if (modelVersionSelect && sheetCfg.c7_model_version) {
                modelVersionSelect.value = sheetCfg.c7_model_version;
                modelVersionSelect.dataset.manual = 'true';
            }
            if (worksheetInput && sheetCfg.sheet_name) {
                worksheetInput.value = sheetCfg.sheet_name || '';
                updateWorksheetSelectionUI(item);
            }

            if (sheetCfg.spreadsheet_id) {
                loadPromises.push(loadGoogleSheetsForItem(item, sheetCfg.spreadsheet_id));
            }
        });

        Promise.allSettled(loadPromises).catch(error => {
            console.warn('自动加载 Google Sheet 配置失败:', error);
        });
        updateC7ModelVersionControls();
    }

    function applyConfigToForm(rawConfig, options = {}) {
        const mode = options.mode || 'template';
        const originalTaskId = options.originalTaskId || '';

        let config = rawConfig;
        if (typeof config === 'string') {
            try {
                config = JSON.parse(config);
            } catch (e) {
                console.error('解析配置失败:', e);
                showNotification('解析配置失败', 'error');
                return;
            }
        }

        const normalized = normalizeC4Config(config);

        // sheets（统一处理）
        applySheetsToForm(normalized.sheets);

        // token
        if (normalized.token_type) {
            document.getElementById('token_type').value = normalized.token_type;
            document.getElementById('token_type').dispatchEvent(new Event('change'));
        }
        pendingTokenSelection = {
            token_id: normalized.token_id || '',
            token_file: normalized.token_file || '',
            token_selection_mode: normalized.token_selection_mode || ''
        };
        Biz.formState.applyPendingTokenSelection();
        if (normalized.token_file) {
            document.getElementById('token_file').value = normalized.token_file;
        }
        if (normalized.token_json) {
            document.getElementById('token_json').value = normalized.token_json;
        }
        if (normalized.proxy_url) {
            document.getElementById('proxy_url').value = normalized.proxy_url;
        }

        if (normalized.kline_source) {
            const sourceInput = document.querySelector(`input[name="kline_source"][value="${normalized.kline_source}"]`);
            if (sourceInput) {
                sourceInput.checked = true;
            }
        }

        // count mode
        if (normalized.count_mode) {
            const modeInput = document.querySelector(`input[name="count_mode"][value="${normalized.count_mode}"]`);
            if (modeInput) {
                modeInput.checked = true;
            }
            if (normalized.count_mode === 'n_plus_1') {
                document.querySelectorAll('input[type="checkbox"]').forEach(checkbox => {
                    checkbox.disabled = false;
                });
            }
        }

        // date range mode / market type / dates
        if (normalized.date_range_mode !== undefined) {
            Biz.formState.applyDateRangeModes(normalized.date_range_mode);
        }
        const priceModeSelect = document.getElementById('price_mode');
        if (priceModeSelect) {
            priceModeSelect.value = normalized.price_mode || 'vwap_price';
        }
        const randomRangeSelect = document.getElementById('random_price_range');
        if (randomRangeSelect) randomRangeSelect.value = normalized.random_price_range || 'high_low';
        const randomGroupInput = document.getElementById('random_group_count');
        if (randomGroupInput) randomGroupInput.value = normalized.random_group_count || 1;
        if (normalized.market_type) document.getElementById('market_type').value = normalized.market_type;
        if (normalized.kline_adjustment) {
            const adjustSelect = document.getElementById('kline_adjustment');
            if (adjustSelect) adjustSelect.value = normalized.kline_adjustment;
        }
        if (normalized.kline_data_source) {
            const sourceSelect = document.getElementById('kline_data_source');
            if (sourceSelect) sourceSelect.value = normalized.kline_data_source;
        }
        if (normalized.start_date) {
            const sd = document.getElementById('start_date');
            if (sd) sd.value = normalized.start_date;
        }
        if (normalized.end_date) {
            const ed = document.getElementById('end_date');
            if (ed) ed.value = normalized.end_date;
        }

        // parameters
        if (normalized.parameters && Array.isArray(normalized.parameters)) {
            normalized.parameters.forEach((paramGroup, idx) => {
                const el = document.getElementById(`param${idx + 1}`);
                if (el && Array.isArray(paramGroup)) {
                    el.value = JSON.stringify(paramGroup);
                }
            });
            Biz.formState.initProductCodeChipsFromParam1();
        }

        // mode-specific title/header
        if (mode === 'restart') {
            document.title = '重启任务 - Google Sheet 参数批量校验';
            const cardHeader = document.querySelector('.card-header h4');
            if (cardHeader) {
                cardHeader.innerHTML = '<i class="bi bi-arrow-clockwise"></i> 重启任务 (基于原任务: ' + originalTaskId + ')';
            }
        }

        updateCustomKlineModeAvailability();
        calculateCombinations();

        if (mode === 'restart') {
            showNotification('已加载原任务配置', 'info');
        } else {
            showNotification('已加载模板配置', 'success');
        }
    }

    // 初始化日期默认值：结束=最近工作日，开始=结束往前推5年后的最近工作日（仅在两者都为空时）
    function getSelectedDateRangeModes() {
        if (isCustomKlineMode()) {
            return [];
        }
        const modes = [];
        const fullEl = document.getElementById('date_range_full');
        const recentEl = document.getElementById('date_range_recent');
        if (fullEl && fullEl.checked) {
            modes.push('full');
        }
        if (recentEl && recentEl.checked) {
            modes.push('recent');
        }
        if (modes.length === 0) {
            if (fullEl) {
                fullEl.checked = true;
            }
            return ['full'];
        }
        return modes;
    }

    function getExcludedRecentYears() {
        if (isCustomKlineMode()) {
            return [];
        }
        const recentEl = document.getElementById('date_range_recent');
        // 如果没有勾选"近年"，返回空数组
        if (!recentEl || !recentEl.checked) {
            return [];
        }
        const excluded = [];
        const checkboxes = document.querySelectorAll('.recent-year-checkbox:checked');
        checkboxes.forEach(cb => {
            // 近半年为 0.5，必须用 parseFloat，parseInt 会截断成 0
            excluded.push(parseFloat(cb.value));
        });
        return excluded;
    }

    function isCustomKlineMode() {
        return document.querySelector('input[name="kline_source"]:checked')?.value === 'custom';
    }

    function setControlDisabled(element, disabled) {
        if (!element) {
            return;
        }
        element.disabled = disabled;
        if (element.id) {
            const label = document.querySelector(`label[for="${element.id}"]`);
            if (label) {
                label.classList.toggle('disabled', disabled);
            }
        }
    }

    function updateCustomKlineModeAvailability() {
        const customMode = isCustomKlineMode();
        const countModeTotal = document.getElementById('count_mode_total');
        const countModeRadios = document.querySelectorAll('input[name="count_mode"]');
        const marketTypeSelect = document.getElementById('market_type');
        const dateRangeFull = document.getElementById('date_range_full');
        const dateRangeRecent = document.getElementById('date_range_recent');
        const recentYearsContainer = document.getElementById('recent_years_container');
        const currentCountMode = document.querySelector('input[name="count_mode"]:checked')?.value || 'total';
        const enableDateRange = !customMode && currentCountMode === 'n_plus_1';

        if (customMode && countModeTotal) {
            countModeTotal.checked = true;
        }
        countModeRadios.forEach(radio => setControlDisabled(radio, customMode));

        if (marketTypeSelect) {
            if (customMode) marketTypeSelect.value = '';
            else if (!marketTypeSelect.value) marketTypeSelect.value = 'cn';
            setControlDisabled(marketTypeSelect, customMode);
        }

        ['price_mode', 'kline_adjustment', 'start_date', 'end_date'].forEach(id => {
            setControlDisabled(document.getElementById(id), customMode);
        });

        [dateRangeFull, dateRangeRecent].forEach(input => {
            setControlDisabled(input, !enableDateRange);
            if (!enableDateRange && input) {
                input.checked = false;
            }
        });

        document.querySelectorAll('.recent-year-checkbox').forEach(checkbox => {
            setControlDisabled(checkbox, customMode || !dateRangeRecent || !dateRangeRecent.checked);
            if (customMode || !dateRangeRecent || !dateRangeRecent.checked) {
                checkbox.checked = false;
            }
        });

        if (recentYearsContainer) {
            recentYearsContainer.classList.toggle('d-none', !dateRangeRecent || !dateRangeRecent.checked);
        }

        enforceC7PriceMode();
    }

    function bindSheetConfigItemEvents(item, debouncedSaveFormData) {
        const {
            spreadsheetSelect,
            titleInput,
            worksheetInput,
            modelVersionSelect,
            customInput,
            refreshWorksheetsBtn,
            refreshGoogleSheetsBtn
        } = getSheetConfigElements(item);

        if (spreadsheetSelect) {
            spreadsheetSelect.addEventListener('change', function() {
                if (modelVersionSelect) {
                    delete modelVersionSelect.dataset.manual;
                }
                syncSelectedGoogleSheetMetaForItem(item);
                loadWorksheetsForItem(item, false);
                calculateCombinations();
                debouncedSaveFormData();
            });
        }

        if (refreshGoogleSheetsBtn) {
            refreshGoogleSheetsBtn.addEventListener('click', function() {
                loadGoogleSheetsForItem(item, spreadsheetSelect ? spreadsheetSelect.value : '');
            });
        }

        if (refreshWorksheetsBtn) {
            refreshWorksheetsBtn.addEventListener('click', function() {
                loadWorksheetsForItem(item, true);
            });
        }

        if (modelVersionSelect) {
            modelVersionSelect.addEventListener('change', function() {
                modelVersionSelect.dataset.manual = 'true';
                ensureC7ModelVersionConsistency(item);
                debouncedSaveFormData();
            });
        }

        [titleInput, worksheetInput, customInput].forEach(function(field) {
            if (!field) {
                return;
            }
            field.addEventListener('input', debouncedSaveFormData);
            field.addEventListener('change', debouncedSaveFormData);
        });
    }

    function bindEvents() {
        // 创建防抖版本的函数
        const debouncedLoadWorksheets = debounce(loadWorksheets, 500);
        const debouncedCalculateCombinations = debounce(calculateCombinations, 300);
        const debouncedSaveFormData = debounce(saveFormData, 300);

        // 统计方式与时间范围类型联动
        const countModeRadios = document.querySelectorAll('input[name="count_mode"]');
        const drmFull = document.getElementById('date_range_full');
        const drmRecent = document.getElementById('date_range_recent');
        const recentYearsContainer = document.getElementById('recent_years_container');

        function updateDateRangeModeAvailability() {
            updateCustomKlineModeAvailability();
        }

        // 近年复选框变化时显示/隐藏年份选择
        if (drmRecent && recentYearsContainer) {
            drmRecent.addEventListener('change', function() {
                updateCustomKlineModeAvailability();
            });
        }

        countModeRadios.forEach(r => {
            r.addEventListener('change', updateDateRangeModeAvailability);
        });
        updateDateRangeModeAvailability();

        document.querySelectorAll('input[name="kline_source"]').forEach(function(field) {
            field.addEventListener('change', function() {
                updateCustomKlineModeAvailability();
                calculateCombinations();
                debouncedSaveFormData();
            });
        });

        // 模板选择变化事件
        document.getElementById('task_template').addEventListener('change', function() {
            fillFormWithTemplate(this.value);
        });

        // 任务名称和描述变化事件
        document.getElementById('task_name').addEventListener('input', debouncedSaveFormData);
        document.getElementById('task_description').addEventListener('input', debouncedSaveFormData);

        // 认证方式选择变化事件
        document.getElementById('token_type').addEventListener('change', function() {
            const fileContainer = document.getElementById('token_file_container');
            const jsonContainer = document.getElementById('token_json_container');
            if (this.value === 'file') {
                fileContainer.classList.remove('d-none');
                jsonContainer.classList.add('d-none');
                Biz.formState.syncSelectedTokenMeta();
            } else {
                fileContainer.classList.add('d-none');
                jsonContainer.classList.remove('d-none');
            }
            debouncedSaveFormData();
        });

        const tokenIdEl = document.getElementById('token_id');
        if (tokenIdEl) {
            tokenIdEl.addEventListener('change', function() {
                Biz.formState.syncSelectedTokenMeta();
                debouncedSaveFormData();
            });
        }

        const importTokenBtn = document.getElementById('import-token-btn');
        if (importTokenBtn) {
            importTokenBtn.addEventListener('click', Biz.formState.importGoogleSheetToken);
        }

        // 参数输入变化事件
        document.querySelectorAll('textarea[id^="param"]').forEach(function(textarea) {
            textarea.addEventListener('input', function() {
                debouncedCalculateCombinations();
                debouncedSaveFormData();
            });
        });

        // 产品代码添加事件
        const addProductBtn = document.getElementById('add_product_code_btn');
        const productInput = document.getElementById('product_code_input');
        if (addProductBtn && productInput) {
            addProductBtn.addEventListener('click', function() {
                addProductCodesFromInput();
            });

            productInput.addEventListener('keydown', function(e) {
                if (e.key === 'Enter') {
                    e.preventDefault();
                    addProductCodesFromInput();
                }
            });
        }

        // 产品代码删除事件（事件委托）
        const chipsContainer = document.getElementById('product_code_chips');
        if (chipsContainer) {
            chipsContainer.addEventListener('click', function(e) {
                const target = e.target;
                const removeBtn = target.closest('[data-code-remove]');
                if (removeBtn) {
                    const code = removeBtn.getAttribute('data-code-remove');
                    removeProductCode(code);
                }
            });
        }

        // 为所有输入字段添加自动保存
        const inputFields = [
            'token_file', 'token_json', 'proxy_url',
            'start_date', 'end_date', 'price_mode', 'random_price_range', 'random_group_count', 'kline_adjustment'
        ];

        inputFields.forEach(function(fieldId) {
            const field = document.getElementById(fieldId);
            if (field) {
                field.addEventListener('input', debouncedSaveFormData);
                field.addEventListener('change', debouncedSaveFormData);
            }
        });

        document.querySelectorAll('#sheet-config-list .sheet-config-item').forEach(function(item) {
            bindSheetConfigItemEvents(item, debouncedSaveFormData);
        });

        document.getElementById('market_type')?.addEventListener('change', debouncedSaveFormData);
        const priceModeSelect = document.getElementById('price_mode');
        if (priceModeSelect) {
            priceModeSelect.addEventListener('change', function() {
                enforceC7PriceMode();
                debouncedCalculateCombinations();
                debouncedSaveFormData();
            });
        }

        // 添加一组表格配置（仅用于前端展示，实际提交仍使用第一组带有固定ID的配置）
        const addSheetConfigBtn = document.getElementById('add-sheet-config-btn');
        if (addSheetConfigBtn) {
            addSheetConfigBtn.addEventListener('click', function() {
                addVisualSheetConfigItem();
            });
        }

        // 移除最后一组表格配置（至少保留第一组主配置）
        const removeSheetConfigBtn = document.getElementById('remove-sheet-config-btn');
        if (removeSheetConfigBtn) {
            removeSheetConfigBtn.addEventListener('click', function() {
                removeLastVisualSheetConfigItem();
            });
        }

        // 高级配置折叠切换
        const toggleAdvancedBtn = document.getElementById('toggle-advanced-config-btn');
        if (toggleAdvancedBtn) {
            toggleAdvancedBtn.addEventListener('click', function() {
                const advanced = document.getElementById('advanced-config');
                const textSpan = document.getElementById('advanced-config-toggle-text');
                const icon = document.getElementById('advanced-config-toggle-icon');
                if (!advanced || !textSpan || !icon) return;
                const isHidden = advanced.classList.toggle('d-none');
                textSpan.textContent = isHidden ? '收起' : '展开';
                icon.classList.toggle('bi-chevron-down', !isHidden);
                icon.classList.toggle('bi-chevron-up', isHidden);
            });
        }

        // 创建任务按钮点击事件（不使用表单submit，防止回车键误触发）
        document.getElementById('execute-btn').addEventListener('click', function() {
            submitTask();
        });
    }

    // 克隆一组仅用于展示的 Google Sheet 配置（移除重复ID，避免影响实际提交逻辑）
    function addVisualSheetConfigItem() {
        const list = document.getElementById('sheet-config-list');
        if (!list) return;

        const templateItem = list.querySelector('.sheet-config-item');
        if (!templateItem) return;

        const newIndex = list.querySelectorAll('.sheet-config-item').length;
        const clone = templateItem.cloneNode(true);

        clone.setAttribute('data-sheet-config-index', String(newIndex));

        // 清空克隆中的输入值并移除ID，防止与主配置冲突
        const inputs = clone.querySelectorAll('input, select, textarea');
        inputs.forEach(function(el) {
            if (el.id === 'spreadsheet' ||
                el.id === 'google_sheet_id' ||
                el.id === 'refresh-google-sheets' ||
                el.id === 'spreadsheet_title' ||
                el.id === 'sheet_name' ||
                el.id === 'custom_sheet_name' ||
                el.id === 'refresh-sheets') {
                el.removeAttribute('id');
            }
            if (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA') {
                el.value = '';
            }
            if (el.tagName === 'SELECT') {
                el.selectedIndex = 0;
            }
        });

        // 同时移除帮助文本上的ID，避免与主块冲突
        ['sheet-name-help', 'spreadsheet-help', 'custom-sheet-container'].forEach(function(idValue) {
            const el = clone.querySelector(`#${idValue}`);
            if (el) {
                el.removeAttribute('id');
            }
        });

        const debouncedSaveFormData = debounce(saveFormData, 300);
        bindSheetConfigItemEvents(clone, debouncedSaveFormData);

        list.appendChild(clone);
        updateC7ModelVersionControls();
    }

    // 移除最后一组仅用于展示的 Google Sheet 配置（保留第一组主配置）
    function removeLastVisualSheetConfigItem() {
        const list = document.getElementById('sheet-config-list');
        if (!list) return;

        const items = list.querySelectorAll('.sheet-config-item');
        if (items.length <= 1) {
            // 只剩下主配置，不再删除
            showNotification('至少保留一组表格配置', 'info');
            return;
        }

        const lastItem = items[items.length - 1];
        lastItem.remove();
        updateC7ModelVersionControls();
        showNotification('已移除最后一组表格配置', 'success');
    }

    // ==== 产品代码 chips 管理，基于隐藏的 param1 ====

    // 从隐藏的 param1 初始化 productCodes 和 chips 展示
    // 将 productCodes 数组同步到隐藏的 param1 文本域（JSON 字符串）
    function syncProductCodesToParam1() {
        const param1El = document.getElementById('param1');
        if (!param1El) return;
        try {
            param1El.value = JSON.stringify(productCodes);
        } catch (e) {
            console.warn('同步产品代码到 param1 失败:', e);
        }
        // 每次变更后更新组合数量并记录日志
        const count = calculateCombinations();
        const p1 = parseJsonArray(param1El.value) || [];
        const p2 = parseJsonArray(document.getElementById('param2').value) || [];
        const p3 = parseJsonArray(document.getElementById('param3').value) || [];
        console.log('[c7] syncProductCodesToParam1 -> 当前参数长度:', {
            param1_len: p1.length,
            param2_len: p2.length,
            param3_len: p3.length,
            combination_count: count,
        });
        // 同步保存表单
        saveFormData();
    }

    // 渲染产品代码 chips
    // 从输入框解析并添加产品代码（支持逗号、空格等分隔，一次多个）
    function addProductCodesFromInput() {
        const inputEl = document.getElementById('product_code_input');
        if (!inputEl) return;

        const raw = inputEl.value || '';
        const parts = raw
            .split(/[,\s]+/) // 逗号或空白分隔
            .map(p => p.trim())
            .filter(p => p.length > 0);

        if (parts.length === 0) {
            return;
        }

        // 合并并去重
        const set = new Set(productCodes);
        parts.forEach(code => set.add(code));
        productCodes = Array.from(set);

        inputEl.value = '';
        Biz.formState.renderProductCodeChips();
        console.log('[c7] addProductCodesFromInput 添加代码:', parts);
        showNotification(`已添加 ${parts.length} 个产品代码`, 'success');
    }

    // 删除单个产品代码
    function removeProductCode(code) {
        if (!code) return;
        productCodes = productCodes.filter(c => c !== code);
        Biz.formState.renderProductCodeChips();
        console.log('[c7] removeProductCode 移除代码:', code, '剩余数量:', productCodes.length);
        showNotification(`已移除产品代码 ${code}`, 'info');
    }

    // 计算参数组合数量（参数1 * 参数2 * 参数3 的乘积）
    function calculateCombinations() {
        const param1 = parseJsonArray(document.getElementById('param1').value) || [];
        const param2 = parseJsonArray(document.getElementById('param2').value) || [];
        const param3 = parseJsonArray(document.getElementById('param3').value) || [];

        const spreadsheetInput = document.getElementById('spreadsheet');
        const spreadsheetId = spreadsheetInput ? extractSpreadsheetId(spreadsheetInput.value) : null;

        // 组合方式：电子表格ID或URL * 参数1 * 参数2 * 参数3
        // 参数1 必须有值，否则不执行；参数2/3 为空时按 1 处理，相当于不增加维度
        let count = 0;
        if (spreadsheetId && param1.length > 0) {
            const len1 = param1.length;
            const len2 = param2.length || 1;
            const len3 = param3.length || 1;
            const randomGroups = document.getElementById('price_mode')?.value === 'random_price'
                ? Math.max(1, parseInt(document.getElementById('random_group_count')?.value || '1', 10))
                : 1;
            count = len1 * len2 * len3 * randomGroups;
        }

        const infoDiv = document.getElementById('combination-info');
        const countSpan = document.getElementById('combination-count');

        if (count > 0) {
            infoDiv.classList.remove('d-none');
            countSpan.textContent = count;
        } else {
            infoDiv.classList.add('d-none');
        }
        return count;
    }

    // 显示参数组合预览
    function showCombinationPreview() {
        const param1 = parseJsonArray(document.getElementById('param1').value) || [];
        const param2 = parseJsonArray(document.getElementById('param2').value) || [];
        const param3 = parseJsonArray(document.getElementById('param3').value) || [];

        const parameters = [param1];
        if (param2.length) parameters.push(param2);
        if (param3.length) parameters.push(param3);
        const combinations = Biz.taskSubmit.generateCombinations(parameters);

        const previewContainer = document.getElementById('combination-preview');
        previewContainer.innerHTML = '';

        // 只显示前20个组合
        const displayCombinations = combinations.slice(0, 20);

        displayCombinations.forEach((combination, index) => {
            const div = document.createElement('div');
            div.className = 'mb-2 p-2 border rounded';
            div.innerHTML = `
                <strong>组合 ${index + 1}:</strong>
                <div class="small text-muted">${combination.join(', ')}</div>
            `;
            previewContainer.appendChild(div);
        });

        if (combinations.length > 20) {
            const moreDiv = document.createElement('div');
            moreDiv.className = 'text-center text-muted';
            moreDiv.textContent = `... 还有 ${combinations.length - 20} 个组合`;
            previewContainer.appendChild(moreDiv);
        }

        const modal = new bootstrap.Modal(document.getElementById('previewModal'));
        modal.show();
    }

    // 生成参数组合（C4 中仅使用产品代码 param1）
    // 提交任务
    function submitTask() {
        // 计算参数组合数量
        const combinationCount = calculateCombinations();
        if (combinationCount === 0) {
            showNotification('请至少输入一个参数', 'error');
            return;
        }

        // 获取Google Sheet配置
        const tokenType = document.getElementById('token_type').value;
        const tokenId = document.getElementById('token_id') ? document.getElementById('token_id').value : '';
        const tokenFile = document.getElementById('token_file').value;
        const tokenJson = document.getElementById('token_json').value;
        const proxyUrl = document.getElementById('proxy_url').value;
        const klineSource = document.querySelector('input[name="kline_source"]:checked')?.value || 'auto';
        const isCustomKline = klineSource === 'custom';
        const countMode = isCustomKline ? 'total' : (document.querySelector('input[name="count_mode"]:checked')?.value || 'total');
        let priceMode = isCustomKline ? null : (document.getElementById('price_mode')?.value || 'vwap_price');
        const marketType = isCustomKline ? null : (document.getElementById('market_type')?.value || 'cn');
        const klineAdjustment = isCustomKline ? null : (document.getElementById('kline_adjustment')?.value || 'forward');
        const dateRangeModes = isCustomKline ? [] : getSelectedDateRangeModes();
        const startDate = isCustomKline ? null : (document.getElementById('start_date')?.value || null);
        const endDate = isCustomKline ? null : (document.getElementById('end_date')?.value || null);
        const randomGroupCount = parseInt(document.getElementById('random_group_count')?.value || '1', 10);

        if (priceMode === 'random_price' && (!Number.isInteger(randomGroupCount) || randomGroupCount < 1)) {
            showNotification('随机组数必须是正整数', 'error');
            return;
        }

        if (tokenType === 'file' && !tokenId) {
            showNotification('请选择Token', 'error');
            return;
        }

        if (tokenType === 'json' && !tokenJson) {
            showNotification('请输入Token JSON字符串', 'error');
            return;
        }

        // 获取参数配置
        const param1 = parseJsonArray(document.getElementById('param1').value);
        const param2 = parseJsonArray(document.getElementById('param2').value);
        const param3 = parseJsonArray(document.getElementById('param3').value);

        // 检查是否有解析错误
        if (param1 === null || param2 === null || param3 === null) {
            showNotification('参数格式错误，请检查 JSON 数组格式', 'error');
            return;
        }

        // 构造参数列表：只加入非空数组
        const parameters = [];
        if (Array.isArray(param1) && param1.length) parameters.push(param1);
        if (Array.isArray(param2) && param2.length) parameters.push(param2);
        if (Array.isArray(param3) && param3.length) parameters.push(param3);

        // 收集所有表格配置（主配置 + 其他可视配置）
        const sheets = [];
        const sheetConfigList = document.getElementById('sheet-config-list');
        if (sheetConfigList) {
            const items = sheetConfigList.querySelectorAll('.sheet-config-item');
            items.forEach((item, index) => {
                let sid = '';
                let stitle = '';

                const {
                    spreadsheetSelect,
                    titleInput,
                    worksheetInput,
                    modelVersionSelect
                } = getSheetConfigElements(item);

                if (spreadsheetSelect) {
                    sid = extractSpreadsheetId(spreadsheetSelect.value || '');
                }
                if (titleInput) {
                    stitle = titleInput.value.trim();
                }

                if (sid) {
                    const sheetConfig = {
                        spreadsheet_id: sid,
                        title: stitle,
                        c7_model_version: modelVersionSelect ? (modelVersionSelect.value || 'c7_0_2') : 'c7_0_2'
                    };
                    if (worksheetInput && worksheetInput.value.trim()) {
                        sheetConfig.sheet_name = worksheetInput.value.trim();
                    }
                    sheets.push(sheetConfig);
                    console.log(`添加表格配置：${sid} - ${stitle}`);
                }
            });
        }

        if (!validateC7ModelVersionSet(sheets)) {
            return;
        }
        if (!isCustomKline && sheets.some(sheet => sheet.c7_model_version === 'c7_0_3')) {
            priceMode = 'ohlc_price';
        }

        // 构造任务配置（c7 任务仅使用 sheets 数组，不再重复顶层 spreadsheet_id/sheet_name）
        const taskConfig = {
            token_type: tokenType,
            token_id: tokenType === 'file' ? tokenId : null,
            token_file: tokenFile,
            token_json: tokenJson,
            proxy_url: proxyUrl || null,
            kline_source: klineSource,
            count_mode: countMode,
            price_mode: priceMode,
            random_price_range: priceMode === 'random_price' ? (document.getElementById('random_price_range')?.value || 'high_low') : null,
            random_group_count: priceMode === 'random_price' ? randomGroupCount : 1,
            market_type: marketType,
            kline_adjustment: klineAdjustment,
            kline_data_source: document.getElementById('kline_data_source')?.value || 'akshare',
            date_range_mode: dateRangeModes,
            exclude_recent_years: isCustomKline ? [] : getExcludedRecentYears(),
            start_date: startDate,
            end_date: endDate,
            parameters: parameters,
            sheets: sheets
        };

        // 禁用执行按钮
        const executeBtn = document.getElementById('execute-btn');
        executeBtn.disabled = true;
        executeBtn.innerHTML = '<i class="bi bi-hourglass-split"></i> 创建任务中...';

        // 获取任务名称和描述
        const taskName = document.getElementById('task_name').value.trim();
        const taskDescription = document.getElementById('task_description').value.trim();

        // 如果没有输入任务名称，使用默认生成逻辑
        const finalTaskName = taskName || `Google Sheet 任务 - ${new Date().toLocaleString()}`;

        // 发送执行请求
        const taskData = {
            name: finalTaskName,
            description: taskDescription || `批量执行 ${combinationCount} 个参数组合`,
            task_type: 'google_sheet_C7',
            config: taskConfig
        };

        Api.endpoints.task.create(taskData).then(function(data) {
            executeBtn.disabled = false;
            executeBtn.innerHTML = '<i class="bi bi-play-circle"></i> 创建任务并执行';

            currentTaskId = data.task_id;
            showNotification('任务创建成功，正在跳转到详情页面...', 'success');

            // 清空表单
            document.getElementById('parameter-form').reset();
            // 隐藏组合信息
            document.getElementById('combination-info').classList.add('d-none');
            // 清除保存的表单数据
            clearSavedFormData();

            // 延迟1秒后跳转到详情页面（c7 模式）
            setTimeout(function() {
                window.location.href = `/google-sheet/detail?task_id=${currentTaskId}&version=c7`;
            }, 1000);
        }).catch(function(err) {
            executeBtn.disabled = false;
            executeBtn.innerHTML = '<i class="bi bi-play-circle"></i> 创建任务并执行';

            showNotification('创建任务失败: ' + (err && err.message ? err.message : '未知错误'), 'error');
        });
    }

    // SSE相关功能已移除，任务创建后直接跳转到详情页面

    // 处理任务事件（保留以备将来使用）
    // 任务状态日志更新功能已移除

    // 确认和取消执行功能已移除，任务创建后直接跳转到详情页面

    // 任务状态模态框功能已移除，任务创建后直接跳转到详情页面

    // 页面卸载时清理资源（SSE功能已移除）

    // 保存表单数据到localStorage
    function saveFormData() {
        const formData = {
            task_name: document.getElementById('task_name').value,
            task_description: document.getElementById('task_description').value,
            spreadsheet: document.getElementById('spreadsheet').value,
            spreadsheet_title: document.getElementById('spreadsheet_title').value,
            sheet_name: document.getElementById('sheet_name').value,
            token_type: document.getElementById('token_type').value,
            token_id: document.getElementById('token_id') ? document.getElementById('token_id').value : '',
            token_file: document.getElementById('token_file').value,
            token_json: document.getElementById('token_json').value,
            proxy_url: document.getElementById('proxy_url').value,
            kline_source: document.querySelector('input[name="kline_source"]:checked')?.value || 'auto',
            count_mode: document.querySelector('input[name="count_mode"]:checked')?.value || 'total',
            price_mode: document.getElementById('price_mode')?.value || 'vwap_price',
            random_price_range: document.getElementById('random_price_range')?.value || 'high_low',
            random_group_count: parseInt(document.getElementById('random_group_count')?.value || '1', 10),
            market_type: document.getElementById('market_type')?.value || 'cn',
            kline_adjustment: document.getElementById('kline_adjustment')?.value || 'forward',
            kline_data_source: document.getElementById('kline_data_source')?.value || 'akshare',
            date_range_mode: getSelectedDateRangeModes(),
            exclude_recent_years: getExcludedRecentYears(),
            param1: document.getElementById('param1').value,
            param2: document.getElementById('param2').value,
            param3: document.getElementById('param3').value
        };
        formData.sheet_configs = Array.from(document.querySelectorAll('#sheet-config-list .sheet-config-item')).map(item => {
            const { spreadsheetSelect, titleInput, worksheetInput, modelVersionSelect } = getSheetConfigElements(item);
            return {
                spreadsheet_id: extractSpreadsheetId(spreadsheetSelect?.value || ''),
                title: titleInput?.value || '',
                sheet_name: worksheetInput?.value || '',
                c7_model_version: modelVersionSelect?.value || 'c7_0_2'
            };
        }).filter(item => item.spreadsheet_id);

        try {
            // localStorage.setItem('google_sheet_c7_form_data', JSON.stringify(formData));
            // 静默保存，不显示提示
        } catch (e) {
            console.warn('无法保存表单数据到localStorage:', e);
        }
    }

    // 从localStorage加载表单数据
    function loadSavedFormData() {
        try {
            const savedData = localStorage.getItem('google_sheet_c7_form_data');
            if (savedData) {
                const formData = JSON.parse(savedData);

                // 恢复表单字段
                if (formData.task_name) document.getElementById('task_name').value = formData.task_name;
                if (formData.task_description) document.getElementById('task_description').value = formData.task_description;
                if (formData.spreadsheet) {
                    loadGoogleSheets(formData.spreadsheet);
                }
                if (Array.isArray(formData.sheet_configs) && formData.sheet_configs.length) {
                    applySheetsToForm(formData.sheet_configs);
                }
                if (formData.spreadsheet_title) document.getElementById('spreadsheet_title').value = formData.spreadsheet_title;
                if (formData.sheet_name) document.getElementById('sheet_name').value = formData.sheet_name;
                if (formData.token_type) document.getElementById('token_type').value = formData.token_type;
                if (formData.token_id) {
                    pendingTokenSelection = { token_id: formData.token_id, token_file: formData.token_file || '' };
                }
                if (formData.token_file) document.getElementById('token_file').value = formData.token_file;
                if (formData.token_json) document.getElementById('token_json').value = formData.token_json;
                if (formData.proxy_url) document.getElementById('proxy_url').value = formData.proxy_url;
                const param1El = document.getElementById('param1');
                if (formData.param1 && param1El) param1El.value = formData.param1;
                const param2El = document.getElementById('param2');
                if (formData.param2 && param2El) param2El.value = formData.param2;
                const param3El = document.getElementById('param3');
                if (formData.param3 && param3El) param3El.value = formData.param3;

                if (formData.market_type) document.getElementById('market_type').value = formData.market_type;
                if (formData.kline_source) {
                    const sourceInput = document.querySelector(`input[name="kline_source"][value="${formData.kline_source}"]`);
                    if (sourceInput) {
                        sourceInput.checked = true;
                    }
                }
                if (formData.kline_adjustment) {
                    const adjustSelect = document.getElementById('kline_adjustment');
                    if (adjustSelect) adjustSelect.value = formData.kline_adjustment;
                }
                if (formData.kline_data_source) {
                    const sourceSelect = document.getElementById('kline_data_source');
                    if (sourceSelect) sourceSelect.value = formData.kline_data_source;
                }

                if (formData.count_mode) {
                    const cmInput = document.querySelector(`input[name="count_mode"][value="${formData.count_mode}"]`);
                    if (cmInput) {
                        cmInput.checked = true;
                    }
                }

                if (formData.price_mode) {
                    const priceModeSelect = document.getElementById('price_mode');
                    if (priceModeSelect) priceModeSelect.value = formData.price_mode;
                }
                if (formData.random_price_range) document.getElementById('random_price_range').value = formData.random_price_range;
                if (formData.random_group_count) document.getElementById('random_group_count').value = formData.random_group_count;

                if (formData.date_range_mode !== undefined) {
                    Biz.formState.applyDateRangeModes(formData.date_range_mode);
                }

                // 触发相关事件以更新UI状态
                document.getElementById('token_type').dispatchEvent(new Event('change'));
                Biz.formState.initProductCodeChipsFromParam1();
                updateCustomKlineModeAvailability();

                console.log('表单数据已恢复');

                // 显示恢复状态
                showNotification('表单数据已恢复', 'info');
            }
        } catch (e) {
            console.warn('无法从localStorage加载表单数据:', e);
        }
    }

    // 清除保存的表单数据（仅清理 c7 自己的缓存）
    function clearSavedFormData() {
        try {
            localStorage.removeItem('google_sheet_c7_form_data');
            // 重置表单
            document.getElementById('parameter-form').reset();
            // 隐藏组合信息
            document.getElementById('combination-info').classList.add('d-none');
            // 恢复自定义K线联动状态
            updateCustomKlineModeAvailability();
            // 重新计算组合数量
            calculateCombinations();
            console.log('已清除 c7 表单缓存');
            showNotification('已清除 c7 表单缓存', 'success');
        } catch (e) {
            console.warn('无法清除localStorage数据:', e);
        }
    }

    // 保存为模板
    // 获取当前配置
    function getCurrentConfig() {
        try {
            const spreadsheetInput = document.getElementById('spreadsheet').value;
            const spreadsheetId = extractSpreadsheetId(spreadsheetInput);
            const sheetName = document.getElementById('sheet_name').value.trim();
            const tokenType = document.getElementById('token_type').value;
            const tokenId = document.getElementById('token_id') ? document.getElementById('token_id').value : '';
            const tokenFile = document.getElementById('token_file').value;
            const tokenJson = document.getElementById('token_json').value;
            const proxyUrl = document.getElementById('proxy_url').value;
            const klineSource = document.querySelector('input[name="kline_source"]:checked')?.value || 'auto';
            const isCustomKline = klineSource === 'custom';
            const countMode = isCustomKline ? 'total' : (document.querySelector('input[name="count_mode"]:checked')?.value || 'total');
            let priceMode = isCustomKline ? null : (document.getElementById('price_mode')?.value || 'vwap_price');
            const marketType = isCustomKline ? null : (document.getElementById('market_type')?.value || 'cn');
            const klineAdjustment = isCustomKline ? null : (document.getElementById('kline_adjustment')?.value || 'forward');
            const dateRangeModes = isCustomKline ? [] : getSelectedDateRangeModes();
            const startDate = isCustomKline ? null : (document.getElementById('start_date')?.value || null);
            const endDate = isCustomKline ? null : (document.getElementById('end_date')?.value || null);
            const randomGroupCount = parseInt(document.getElementById('random_group_count')?.value || '1', 10);

            if (priceMode === 'random_price' && (!Number.isInteger(randomGroupCount) || randomGroupCount < 1)) {
                Biz.formState.showError('随机组数必须是正整数');
                return null;
            }

            // 验证必要字段
            if (!spreadsheetId) {
                Biz.formState.showError('请选择 Google Sheet');
                return null;
            }

            if (tokenType === 'file' && !tokenId) {
                Biz.formState.showError('请选择Token');
                return null;
            }

            if (tokenType === 'json' && !tokenJson) {
                Biz.formState.showError('请输入Token JSON字符串');
                return null;
            }

            // 获取参数配置
            const param1 = parseJsonArray(document.getElementById('param1').value) || [];
            const param2 = parseJsonArray(document.getElementById('param2').value) || [];
            const param3 = parseJsonArray(document.getElementById('param3').value) || [];

            // 检查是否有解析错误
            if (param1 === null || param2 === null || param3 === null) {
                Biz.formState.showError('参数格式错误，请检查 JSON 数组格式');
                return null;
            }

            // 收集所有表格配置
            const sheets = [];
            const sheetConfigList = document.getElementById('sheet-config-list');
            if (sheetConfigList) {
                const items = sheetConfigList.querySelectorAll('.sheet-config-item');
                items.forEach((item, index) => {
                    let sid = '';
                    let stitle = '';
                    const {
                        spreadsheetSelect,
                        titleInput,
                        worksheetInput,
                        modelVersionSelect
                    } = getSheetConfigElements(item);

                    if (spreadsheetSelect) {
                        sid = extractSpreadsheetId(spreadsheetSelect.value || '');
                    }
                    if (titleInput) {
                        stitle = titleInput.value || '';
                    }
                    const sheetNameValue = worksheetInput ? worksheetInput.value.trim() : '';

                    if (sid) {
                        const sheetConfig = {
                            spreadsheet_id: sid,
                            title: stitle,
                            c7_model_version: modelVersionSelect ? (modelVersionSelect.value || 'c7_0_2') : 'c7_0_2'
                        };
                        if (sheetNameValue) {
                            sheetConfig.sheet_name = sheetNameValue;
                        }
                        sheets.push(sheetConfig);
                        console.log(`添加工作表：${sid} - ${stitle}`);
                    }
                });
            }

            if (!validateC7ModelVersionSet(sheets)) {
                return null;
            }
            if (!isCustomKline && sheets.some(sheet => sheet.c7_model_version === 'c7_0_3')) {
                priceMode = 'ohlc_price';
            }

            // 构造参数列表：只加入非空数组
            const parameters = [];
            if (Array.isArray(param1)) parameters.push(param1);
            if (Array.isArray(param2) && param2.length) parameters.push(param2);
            if (Array.isArray(param3) && param3.length) parameters.push(param3);

            // 构造配置对象（c7 结构，包含 task_type，供模板过滤）
            return {
                task_type: 'google_sheet_c7',
                token_type: tokenType,
                token_id: tokenType === 'file' ? tokenId : null,
                token_file: tokenFile,
                token_json: tokenJson,
                proxy_url: proxyUrl || null,
                kline_source: klineSource,
                count_mode: countMode,
                price_mode: priceMode,
                random_price_range: priceMode === 'random_price' ? (document.getElementById('random_price_range')?.value || 'high_low') : null,
                random_group_count: priceMode === 'random_price' ? randomGroupCount : 1,
                market_type: marketType,
                kline_adjustment: klineAdjustment,
                kline_data_source: document.getElementById('kline_data_source')?.value || 'akshare',
                date_range_mode: dateRangeModes,
                exclude_recent_years: isCustomKline ? [] : getExcludedRecentYears(),
                start_date: startDate,
                end_date: endDate,
                parameters: parameters,
                sheets: sheets
            };
        } catch (error) {
            console.error('获取当前配置失败:', error);
            Biz.formState.showError('获取当前配置失败: ' + error.message);
            return null;
        }
    }

    // 提交模板
    // 将可能的旧结构配置转换为 C4 统一结构
    function normalizeC4Config(raw) {
        if (!raw || typeof raw !== 'object') {
            return {};
        }

        // 已经是 C4 新结构（有 sheets 数组）则直接返回
        if (Array.isArray(raw.sheets) && raw.sheets.length > 0) {
            return {
                ...raw,
                kline_source: raw.kline_source || 'auto'
            };
        }

        // 兼容旧结构：顶层有 spreadsheet_id / sheet_name
        const sheets = [];
        if (raw.spreadsheet_id) {
            sheets.push({
                spreadsheet_id: raw.spreadsheet_id,
                sheet_name: raw.sheet_name || '',
                title: raw.title || ''
            });
        }

        return {
            kline_source: raw.kline_source || 'auto',
            kline_data_source: raw.kline_data_source || 'akshare',
            count_mode: raw.count_mode || 'total',
            price_mode: raw.price_mode || 'vwap_price',
            random_price_range: raw.random_price_range || 'high_low',
            random_group_count: raw.random_group_count || 1,
            start_date: raw.start_date || null,
            end_date: raw.end_date || null,
            market_type: raw.market_type || 'cn',
            kline_adjustment: raw.kline_adjustment || 'forward',
            token_type: raw.token_type || 'file',
            token_id: raw.token_id || '',
            token_file: raw.token_file || 'data/token.json',
            token_json: raw.token_json || '',
            proxy_url: raw.proxy_url || null,
            parameters: Array.isArray(raw.parameters) ? raw.parameters : [[]],
            sheets: sheets
        };
    }

    // 加载重启配置
    function loadRestartConfig(restartConfigRaw, originalTaskId) {
        try {
            applyConfigToForm(restartConfigRaw, {
                mode: 'restart',
                originalTaskId: originalTaskId
            });
        } catch (e) {
            console.warn('加载重启配置失败:', e);
        }
    }
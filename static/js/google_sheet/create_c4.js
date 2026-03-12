let currentTaskId = null;
    let eventSource = null;
    let productCodes = [];

    // 本页专用错误提示封装
    function showError(message) {
        if (typeof showNotification === 'function') {
            showNotification(message, 'error');
        } else {
            alert(message);
        }
    }

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

                // 优先使用新版 sheets 数组结构，兼容旧的 spreadsheet_id/sheet_name 字段
                let primarySpreadsheetId = '';
                let primarySheetName = '';

                if (Array.isArray(config.sheets) && config.sheets.length > 0) {
                    const firstSheet = config.sheets[0] || {};
                    primarySpreadsheetId = firstSheet.spreadsheet_id || '';
                    primarySheetName = firstSheet.sheet_name || '';
                } else {
                    primarySpreadsheetId = config.spreadsheet_id || '';
                    primarySheetName = config.sheet_name || '';
                }

                if (primarySpreadsheetId) {
                    document.getElementById('spreadsheet').value = primarySpreadsheetId;
                }

                if (primarySheetName) {
                    const sheetSelect = document.getElementById('sheet_name');
                    sheetSelect.setAttribute('data-saved-value', primarySheetName);
                }

                // 如果有多张表，自动为后续表创建可视配置块并填充值（仅设置文本，不强制加载工作表列表）
                if (Array.isArray(config.sheets) && config.sheets.length > 1) {
                    const list = document.getElementById('sheet-config-list');
                    config.sheets.slice(1).forEach(sheetCfg => {
                        if (!list) return;
                        addVisualSheetConfigItem();
                        const items = list.querySelectorAll('.sheet-config-item');
                        const item = items[items.length - 1];
                        if (!item) return;

                        const textInputs = item.querySelectorAll('input[type="text"]');
                        const spreadsheetInputEl = textInputs[0];
                        const customInputEl = textInputs[1] || null;

                        if (spreadsheetInputEl && sheetCfg.spreadsheet_id) {
                            spreadsheetInputEl.value = sheetCfg.spreadsheet_id;
                        }
                        if (customInputEl && sheetCfg.sheet_name) {
                            customInputEl.value = sheetCfg.sheet_name;
                        }
                    });
                }
                
                if (config.token_type) {
                    document.getElementById('token_type').value = config.token_type;
                    document.getElementById('token_type').dispatchEvent(new Event('change'));
                }
                
                if (config.token_file) {
                    document.getElementById('token_file').value = config.token_file;
                }
                
                if (config.token_json) {
                    document.getElementById('token_json').value = config.token_json;
                }
                
                if (config.proxy_url) {
                    document.getElementById('proxy_url').value = config.proxy_url;
                }

                if (config.market_type) {
                    const mtInput = document.querySelector(`input[name="market_type"][value="${config.market_type}"]`);
                    if (mtInput) {
                        mtInput.checked = true;
                    }
                }

                if (config.date_range_mode !== undefined) {
                    applyDateRangeModes(config.date_range_mode);
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
                calculateCombinations();
                showNotification('已加载模板配置', 'success');
                
                // 更新页面标题和提示
                const urlTemplateId = new URLSearchParams(window.location.search).get('template_id');
                if (urlTemplateId) {
                    document.title = '从模板创建任务 - Google Sheet 参数批量校验';
                    const cardHeader = document.querySelector('.card-header h4');
                    if (cardHeader) {
                        cardHeader.innerHTML = '<i class="bi bi-file-earmark-text"></i> 从模板创建任务';
                    }
                }
            }
        } catch (error) {
            console.error('加载模板失败:', error);
            showError('加载模板配置失败: ' + error.message);
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

    // 获取单个配置块的工作表列表
    function loadWorksheetsForItem(item, isManualRefresh = false) {
        if (!item) return;

        // 当前配置块内的元素
        const spreadsheetInputEl = item.querySelector('input[type="text"]');
        const sheetSelect = item.querySelector('select');
        const refreshBtn = item.querySelector('button.btn-outline-secondary');
        const helpText = item.querySelector('.form-text');

        if (!spreadsheetInputEl || !sheetSelect || !refreshBtn || !helpText) {
            return;
        }

        const spreadsheetInput = spreadsheetInputEl.value;
        const spreadsheetId = extractSpreadsheetId(spreadsheetInput);
        const tokenType = document.getElementById('token_type').value;
        const tokenFile = document.getElementById('token_file').value;
        const proxyUrl = document.getElementById('proxy_url').value;

        if (!spreadsheetId) {
            sheetSelect.innerHTML = '<option value="">请先输入电子表格ID</option>';
            helpText.textContent = '选择要操作的工作表';
            refreshBtn.disabled = true;
            return;
        }

        // 显示加载状态
        sheetSelect.disabled = true;
        refreshBtn.disabled = true;
        if (isManualRefresh) {
            const icon = refreshBtn.querySelector('i');
            if (icon) {
                icon.classList.add('spin');
            }
        }
        sheetSelect.innerHTML = '<option value="">正在加载工作表列表...</option>';
        helpText.textContent = '正在从Google Sheet获取工作表列表...';

        // 准备请求数据
        const requestData = {
            spreadsheet_id: spreadsheetId,
            token_file: tokenType === 'file' ? tokenFile : undefined,
            proxy_url: proxyUrl || undefined
        };

        // 发送请求获取工作表列表
        fetch('/api/google-sheet/worksheets', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(requestData)
        })
        .then(response => response.json())
        .then(data => {
            if (data.status === 'success' && Array.isArray(data.worksheets)) {
                if (data.worksheets.length === 0) {
                    throw new Error('未找到任何工作表');
                }

                // 如果接口返回了表标题，自动写入标题输入框（仅当前配置块）
                const titleInput = item.querySelector('#spreadsheet_title');
                if (titleInput && typeof data.title === 'string' && data.title.trim() !== '') {
                    titleInput.value = data.title.trim();
                }

                // 清空并重新填充下拉列表
                sheetSelect.innerHTML = '';
                data.worksheets.forEach(worksheet => {
                    const option = document.createElement('option');
                    option.value = worksheet;
                    option.textContent = worksheet;
                    sheetSelect.appendChild(option);
                });

                // 添加自定义选项
                const customOption = document.createElement('option');
                customOption.value = '自定义';
                customOption.textContent = '自定义';
                sheetSelect.appendChild(customOption);

                // 如果有保存的值，恢复它（仅对主配置块适用，其它块不使用 data-saved-value）
                const savedValue = sheetSelect.getAttribute('data-saved-value');
                if (savedValue) {
                    if (data.worksheets.includes(savedValue)) {
                        sheetSelect.value = savedValue;
                        helpText.textContent = `已选择工作表: ${savedValue}`;
                    } else if (savedValue === '自定义') {
                        sheetSelect.value = '自定义';
                        const customContainer = document.getElementById('custom-sheet-container');
                        if (customContainer) {
                            customContainer.style.display = 'block';
                        }
                        helpText.textContent = '使用自定义工作表名称';
                    }
                } else {
                    // 默认选择第一个工作表
                    const defaultSheet = data.worksheets[0];
                    sheetSelect.value = defaultSheet;
                    helpText.textContent = `已自动选择第一个工作表: ${defaultSheet}`;
                }

                if (!isManualRefresh) {
                    showNotification('工作表列表已自动加载', 'success');
                } else {
                    showNotification('工作表列表已刷新', 'success');
                }
            } else {
                throw new Error(data.message || '获取工作表列表失败');
            }
        })
        .catch(error => {
            console.error('获取工作表列表失败:', error);
            sheetSelect.innerHTML = '<option value="">加载失败</option>';
            helpText.textContent = '加载失败，请检查电子表格ID是否正确';
            showError('获取工作表列表失败: ' + error.message);
        })
        .finally(() => {
            sheetSelect.disabled = false;
            refreshBtn.disabled = false;
            if (isManualRefresh) {
                const icon = refreshBtn.querySelector('i');
                if (icon) {
                    icon.classList.remove('spin');
                }
            }
        });
    }

    // 保持原有接口，默认针对第一组主配置块
    function loadWorksheets(isManualRefresh = false) {
        const firstItem = document.querySelector('#sheet-config-list .sheet-config-item');
        if (firstItem) {
            loadWorksheetsForItem(firstItem, isManualRefresh);
        }
    }

    // 页面加载完成后绑定事件
    document.addEventListener('DOMContentLoaded', function() {
        bindEvents();
        loadTemplates(); // 加载模板列表

        // URL 参数驱动的数据加载：
        // - ?template_id=xxx -> /api/templates/xxx
        // - ?restart_task_id=xxx -> /api/tasks/xxx
        // - 其它 -> loadSavedFormData()
        initFromUrlParams();

        // 初始化日期默认值（如果未从模板/重启/本地恢复）
        initDefaultDatesIfEmpty();

        // 初始化产品代码chips（基于隐藏的param1值）
        initProductCodeChipsFromParam1();

        calculateCombinations();

        // 创建防抖版本的函数
        const debouncedLoadWorksheets = debounce(loadWorksheets, 500);
        const debouncedCalculateCombinations = debounce(calculateCombinations, 300);
        const debouncedSaveFormData = debounce(saveFormData, 300);

        // 监听spreadsheet输入变化
        const spreadsheetInput = document.getElementById('spreadsheet');
        spreadsheetInput.addEventListener('input', debouncedLoadWorksheets);

        // 为参数输入添加防抖
        document.querySelectorAll('textarea[id^="param"]').forEach(function(textarea) {
            textarea.addEventListener('input', function() {
                debouncedCalculateCombinations();
                debouncedSaveFormData();
            });
        });

        // 为其他输入字段添加防抖的自动保存
        const inputFields = [
            'task_name', 'task_description', 'custom_sheet_name', 
            'token_file', 'token_json', 'proxy_url'
        ];
        
        inputFields.forEach(function(fieldId) {
            const field = document.getElementById(fieldId);
            if (field) {
                field.addEventListener('input', debouncedSaveFormData);
                field.addEventListener('change', debouncedSaveFormData);
            }
        });
    });

    function initFromUrlParams() {
        const params = new URLSearchParams(window.location.search);
        const templateId = params.get('template_id');
        const restartTaskId = params.get('restart_task_id');

        if (templateId) {
            fillFormWithTemplate(templateId);
            return;
        }

        if (restartTaskId) {
            fillFormWithRestartTask(restartTaskId);
            return;
        }

        loadSavedFormData();
    }

    function fillFormWithRestartTask(taskId) {
        fetch(`/api/tasks/${encodeURIComponent(taskId)}`)
            .then(resp => resp.json())
            .then(data => {
                const task = (data && data.task) ? data.task : null;
                const configRaw = task ? task.config : null;
                if (!configRaw) {
                    showNotification('加载原任务配置失败：config为空', 'error');
                    return;
                }
                loadRestartConfig(configRaw, taskId);
            })
            .catch(err => {
                console.error('加载原任务失败:', err);
                showNotification('加载原任务失败', 'error');
            });
    }

    // 加载模板列表
    function loadTemplates() {
        // 只加载 C4 类型的模板
        fetch('/api/templates?task_type=google_sheet_C4')
            .then(response => response.json())
            .then(data => {
                if (!data || !data.status === 'success' || !Array.isArray(data.templates)) {
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
                showError('加载模板列表失败');
            });
    }

    // 使用模板填充表单
    function fillFormWithTemplate(templateId) {
        if (!templateId) {
            return;
        }

        fetch(`/api/templates/${templateId}`)
            .then(response => response.json())
            .then(template => {
                let config = template.config;
                if (typeof config === 'string') {
                    try {
                        config = JSON.parse(config);
                    } catch (e) {
                        console.error('解析模板配置失败:', e);
                        return;
                    }
                }

                // 填充Google Sheet配置（优先使用新版 sheets 数组，兼容旧字段）
                let primarySpreadsheetId = '';
                let primarySheetName = '';

                if (Array.isArray(config.sheets) && config.sheets.length > 0) {
                    const firstSheet = config.sheets[0] || {};
                    primarySpreadsheetId = firstSheet.spreadsheet_id || '';
                    primarySheetName = firstSheet.sheet_name || '';
                } else {
                    primarySpreadsheetId = config.spreadsheet_id || '';
                    primarySheetName = config.sheet_name || '';
                }

                if (primarySpreadsheetId) {
                    document.getElementById('spreadsheet').value = primarySpreadsheetId;
                }
                if (primarySheetName) {
                    const sheetSelect = document.getElementById('sheet_name');
                    sheetSelect.setAttribute('data-saved-value', primarySheetName);
                }

                // 多张表：为后续表创建可视配置块
                if (Array.isArray(config.sheets) && config.sheets.length > 1) {
                    const list = document.getElementById('sheet-config-list');
                    config.sheets.slice(1).forEach(sheetCfg => {
                        if (!list) return;
                        addVisualSheetConfigItem();
                        const items = list.querySelectorAll('.sheet-config-item');
                        const item = items[items.length - 1];
                        if (!item) return;

                        const textInputs = item.querySelectorAll('input[type="text"]');
                        const spreadsheetInputEl = textInputs[0];
                        const customInputEl = textInputs[1] || null;

                        if (spreadsheetInputEl && sheetCfg.spreadsheet_id) {
                            spreadsheetInputEl.value = sheetCfg.spreadsheet_id;
                        }
                        if (customInputEl && sheetCfg.sheet_name) {
                            customInputEl.value = sheetCfg.sheet_name;
                        }
                    });
                }
                if (config.token_type) {
                    document.getElementById('token_type').value = config.token_type;
                    document.getElementById('token_type').dispatchEvent(new Event('change'));
                }
                if (config.token_file) {
                    document.getElementById('token_file').value = config.token_file;
                }
                if (config.token_json) {
                    document.getElementById('token_json').value = config.token_json;
                }
                if (config.proxy_url) {
                    document.getElementById('proxy_url').value = config.proxy_url;
                }
                if (config.count_mode) {
                    const modeInput = document.querySelector(`input[name="count_mode"][value="${config.count_mode}"]`);
                    if (modeInput) {
                        modeInput.checked = true;
                    }
                }
                if (config.date_range_mode !== undefined) {
                    applyDateRangeModes(config.date_range_mode);
                }
                if (config.market_type) {
                    const mtInput = document.querySelector(`input[name="market_type"][value="${config.market_type}"]`);
                    if (mtInput) {
                        mtInput.checked = true;
                    }
                }
                if (config.start_date) {
                    const sd = document.getElementById('start_date');
                    if (sd) sd.value = config.start_date;
                }
                if (config.end_date) {
                    const ed = document.getElementById('end_date');
                    if (ed) ed.value = config.end_date;
                }

                // 填充产品代码参数
                if (config.parameters && Array.isArray(config.parameters)) {
                    const firstParam = config.parameters[0];
                    const paramElement = document.getElementById('param1');
                    if (paramElement && Array.isArray(firstParam)) {
                        paramElement.value = JSON.stringify(firstParam);
                        initProductCodeChipsFromParam1();
                    }
                }

                // 更新组合计算
                calculateCombinations();
                showNotification('已加载模板配置', 'success');
            })
            .catch(error => {
                console.error('加载模板详情失败:', error);
                showNotification('加载模板失败', 'error');
            });
    }

    // 初始化日期默认值：结束=昨天，开始=结束往前推5年（仅在两者都为空时）
    function initDefaultDatesIfEmpty() {
        const startInput = document.getElementById('start_date');
        const endInput = document.getElementById('end_date');
        if (!startInput || !endInput) return;

        // 已有值（来自模板/重启/本地存储），不覆盖
        if (startInput.value || endInput.value) {
            return;
        }

        const today = new Date();
        // 昨天
        const end = new Date(today.getFullYear(), today.getMonth(), today.getDate() - 1);
        // 五年前同一天
        const start = new Date(end.getFullYear() - 5, end.getMonth(), end.getDate());

        const toISODate = (d) => {
            const m = (d.getMonth() + 1).toString().padStart(2, '0');
            const day = d.getDate().toString().padStart(2, '0');
            return `${d.getFullYear()}-${m}-${day}`;
        };

        endInput.value = toISODate(end);
        startInput.value = toISODate(start);
    }

    function getSelectedDateRangeModes() {
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

    function bindEvents() {
        // 创建防抖版本的函数
        const debouncedLoadWorksheets = debounce(loadWorksheets, 500);
        const debouncedCalculateCombinations = debounce(calculateCombinations, 300);
        const debouncedSaveFormData = debounce(saveFormData, 300);

        // 统计方式与时间范围类型联动
        const countModeRadios = document.querySelectorAll('input[name="count_mode"]');
        const drmFull = document.getElementById('date_range_full');
        const drmRecent = document.getElementById('date_range_recent');
        function updateDateRangeModeAvailability() {
            const current = document.querySelector('input[name="count_mode"]:checked')?.value || 'total';
            const enable = current === 'n_plus_1';
            if (drmFull) {
                drmFull.disabled = !enable;
                if (!enable) drmFull.checked = false;
            }
            if (drmRecent) {
                drmRecent.disabled = !enable;
                if (!enable) drmRecent.checked = false;
            }
        }
        countModeRadios.forEach(r => {
            r.addEventListener('change', updateDateRangeModeAvailability);
        });
        updateDateRangeModeAvailability();

        // 模板选择变化事件
        document.getElementById('task_template').addEventListener('change', function() {
            fillFormWithTemplate(this.value);
        });

        // 任务名称和描述变化事件
        document.getElementById('task_name').addEventListener('input', debouncedSaveFormData);
        document.getElementById('task_description').addEventListener('input', debouncedSaveFormData);
        
        // 工作表名称选择变化事件
        document.getElementById('sheet_name').addEventListener('change', function() {
            const customContainer = document.getElementById('custom-sheet-container');
            const helpText = document.getElementById('sheet-name-help');
            
            if (this.value === '自定义') {
                customContainer.style.display = 'block';
                helpText.textContent = '使用自定义工作表名称';
            } else {
                customContainer.style.display = 'none';
                if (this.value) {
                    helpText.textContent = `已选择工作表: ${this.value}`;
                }
            }
            debouncedSaveFormData();
        });

        // 认证方式选择变化事件
        document.getElementById('token_type').addEventListener('change', function() {
            const fileContainer = document.getElementById('token_file_container');
            const jsonContainer = document.getElementById('token_json_container');
            if (this.value === 'file') {
                fileContainer.style.display = 'block';
                jsonContainer.style.display = 'none';
            } else {
                fileContainer.style.display = 'none';
                jsonContainer.style.display = 'block';
            }
            debouncedSaveFormData();
        });

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
            'spreadsheet', 'custom_sheet_name', 'token_file', 'token_json', 'proxy_url',
            'start_date', 'end_date'
        ];
        
        inputFields.forEach(function(fieldId) {
            const field = document.getElementById(fieldId);
            if (field) {
                field.addEventListener('input', debouncedSaveFormData);
                field.addEventListener('change', debouncedSaveFormData);
            }
        });

        // 监听spreadsheet输入变化
        const spreadsheetInput = document.getElementById('spreadsheet');
        spreadsheetInput.addEventListener('input', function() {
            const refreshBtn = document.getElementById('refresh-sheets');
            if (this.value.trim()) {
                refreshBtn.disabled = false;
            } else {
                refreshBtn.disabled = true;
            }
            debouncedLoadWorksheets(false);
        });

        // 刷新按钮点击事件
        document.getElementById('refresh-sheets').addEventListener('click', function() {
            debouncedLoadWorksheets(true); // 使用防抖，避免与输入触发的请求叠加
        });

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
                const isHidden = advanced.style.display === 'none' || advanced.style.display === '';
                advanced.style.display = isHidden ? 'block' : 'none';
                textSpan.textContent = isHidden ? '收起' : '展开';
                icon.classList.toggle('bi-chevron-down', !isHidden);
                icon.classList.toggle('bi-chevron-up', isHidden);
            });
        }

        // 表单提交事件
        document.getElementById('parameter-form').addEventListener('submit', function(e) {
            e.preventDefault();
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
        const help = clone.querySelector('#sheet-name-help');
        if (help) {
            help.removeAttribute('id');
        }

        // 为克隆出来的配置块绑定独立的事件
        const spreadsheetInputEl = clone.querySelector('input[type="text"]');
        const refreshBtn = clone.querySelector('button.btn-outline-secondary');

        if (spreadsheetInputEl && refreshBtn) {
            const debouncedLoadForItem = debounce(function() {
                loadWorksheetsForItem(clone, false);
            }, 500);

            spreadsheetInputEl.addEventListener('input', function() {
                const value = (this.value || '').trim();
                refreshBtn.disabled = !value;
                debouncedLoadForItem();
            });

            refreshBtn.addEventListener('click', function() {
                loadWorksheetsForItem(clone, true);
            });

            // 初始禁用刷新按钮
            refreshBtn.disabled = true;
        }

        list.appendChild(clone);
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
        showNotification('已移除最后一组表格配置', 'success');
    }

    // ==== 产品代码 chips 管理，基于隐藏的 param1 ====

    // 从隐藏的 param1 初始化 productCodes 和 chips 展示
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
        syncProductCodesToParam1();
    }

    // 将 productCodes 数组同步到隐藏的 param1 文本域（JSON 字符串）
    function syncProductCodesToParam1() {
        const param1El = document.getElementById('param1');
        if (!param1El) return;
        try {
            param1El.value = JSON.stringify(productCodes);
        } catch (e) {
            console.warn('同步产品代码到 param1 失败:', e);
        }
        // 每次变更后更新组合数量
        calculateCombinations();
    }

    // 渲染产品代码 chips
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

        syncProductCodesToParam1();
    }

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
        renderProductCodeChips();
        showNotification(`已添加 ${parts.length} 个产品代码`, 'success');
    }

    // 删除单个产品代码
    function removeProductCode(code) {
        if (!code) return;
        productCodes = productCodes.filter(c => c !== code);
        renderProductCodeChips();
        showNotification(`已移除产品代码 ${code}`, 'info');
    }

    // 计算参数组合数量
    function calculateCombinations() {
        const param1 = parseJsonArray(document.getElementById('param1').value) || [];
        const spreadsheetInput = document.getElementById('spreadsheet');
        const spreadsheetId = spreadsheetInput ? extractSpreadsheetId(spreadsheetInput.value) : null;

        // 组合方式：电子表格ID或URL * 产品代码数量
        const count = spreadsheetId ? param1.length : 0;
        
        const infoDiv = document.getElementById('combination-info');
        const countSpan = document.getElementById('combination-count');
        
        if (count > 0) {
            infoDiv.style.display = 'block';
            countSpan.textContent = count;
        } else {
            infoDiv.style.display = 'none';
        }
        
        return count;
    }

    // 显示参数组合预览
    function showCombinationPreview() {
        const param1 = parseJsonArray(document.getElementById('param1').value) || [];
        const parameters = [param1];
        const combinations = generateCombinations(parameters);
        
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
    function generateCombinations(parameters) {
        const combinations = [];
        const param1 = parameters[0] || [];
        for (const p1 of param1) {
            combinations.push([p1]);
        }
        return combinations;
    }

    function clearAllParameters() {
        if (confirm('确定要清空所有配置吗？')) {
            const param1El = document.getElementById('param1');
            if (param1El) {
                param1El.value = '';
            }
            productCodes = [];
            renderProductCodeChips();
            calculateCombinations();
            showNotification('已清空所有配置', 'warning');
        }
    }

    // 提交任务
    function submitTask() {
        // 计算参数组合数量
        const combinationCount = calculateCombinations();
        if (combinationCount === 0) {
            showNotification('请至少输入一个参数', 'error');
            return;
        }
        
        // 获取Google Sheet配置
        const spreadsheetInput = document.getElementById('spreadsheet').value;
        const spreadsheetId = extractSpreadsheetId(spreadsheetInput);
        const sheetNameSelect = document.getElementById('sheet_name').value;
        const customSheetName = document.getElementById('custom_sheet_name').value;
        const sheetName = sheetNameSelect === '自定义' ? customSheetName : sheetNameSelect;
        const tokenType = document.getElementById('token_type').value;
        const tokenFile = document.getElementById('token_file').value;
        const tokenJson = document.getElementById('token_json').value;
        const proxyUrl = document.getElementById('proxy_url').value;
        const countMode = document.querySelector('input[name="count_mode"]:checked')?.value || 'total';
        const marketType = document.querySelector('input[name="market_type"]:checked')?.value || 'cn';
        const dateRangeModes = getSelectedDateRangeModes();
        const startDate = document.getElementById('start_date')?.value || null;
        const endDate = document.getElementById('end_date')?.value || null;
        
        // 验证必要字段
        if (!spreadsheetId) {
            showNotification('请输入电子表格ID或URL', 'error');
            return;
        }
        
        if (sheetNameSelect === '自定义' && !customSheetName) {
            showNotification('请输入自定义工作表名称', 'error');
            return;
        }
        
        if (tokenType === 'file' && !tokenFile) {
            showNotification('请输入Token文件路径', 'error');
            return;
        }
        
        if (tokenType === 'json' && !tokenJson) {
            showNotification('请输入Token JSON字符串', 'error');
            return;
        }
        
        // 获取产品代码参数
        const param1 = parseJsonArray(document.getElementById('param1').value);
        
        // 检查是否有解析错误
        if (param1 === null) {
            showNotification('参数格式错误，请检查JSON格式', 'error');
            return;
        }
        
        // 构造参数列表（仅产品代码）
        const parameters = [param1];

        // 收集所有表格配置（主配置 + 其他可视配置）
        const sheets = [];
        const sheetConfigList = document.getElementById('sheet-config-list');
        if (sheetConfigList) {
            const items = sheetConfigList.querySelectorAll('.sheet-config-item');
            items.forEach((item, index) => {
                let sid = '';
                let sname = '';

                const spreadsheetTitle = document.getElementById('spreadsheet_title')?.value.trim() || null;

                if (index === 0) {
                    // 主配置使用当前计算好的值
                    sid = spreadsheetId;
                    sname = sheetName;
                } else {
                    // 其他配置块：通过输入/下拉推导
                    const textInputs = item.querySelectorAll('input[type="text"]');
                    const spreadsheetInputEl = textInputs[0];
                    const customInputEl = textInputs[1] || null;
                    const selectEl = item.querySelector('select');

                    if (spreadsheetInputEl) {
                        sid = extractSpreadsheetId(spreadsheetInputEl.value || '');
                    }

                    if (selectEl) {
                        if (selectEl.value === '自定义' && customInputEl) {
                            sname = (customInputEl.value || '').trim();
                        } else if (selectEl.value) {
                            sname = selectEl.value;
                        } else if (customInputEl) {
                            // 下拉无有效值时，允许直接用自定义输入
                            sname = (customInputEl.value || '').trim();
                        }
                    } else if (customInputEl) {
                        sname = (customInputEl.value || '').trim();
                    }
                }

                if (sid && sname) {
                    const sheetConfig = {
                        spreadsheet_id: sid,
                        sheet_name: sname
                    };
                    if (index === 0 && spreadsheetTitle) {
                        sheetConfig.title = spreadsheetTitle;
                    }
                    sheets.push(sheetConfig);
                }
            });
        }

        // 构造任务配置（C4 任务仅使用 sheets 数组，不再重复顶层 spreadsheet_id/sheet_name）
        const taskConfig = {
            token_type: tokenType,
            token_file: tokenFile,
            token_json: tokenJson,
            proxy_url: proxyUrl || null,
            count_mode: countMode,
            market_type: marketType,
            date_range_mode: dateRangeModes,
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
            task_type: 'google_sheet_C4',
            config: taskConfig
        };
        
        ajaxRequest('/api/tasks', 'POST', taskData, function(err, data) {
            executeBtn.disabled = false;
            executeBtn.innerHTML = '<i class="bi bi-play-circle"></i> 创建任务并执行';
            
            if (!err && data && data.status === 'success') {
                currentTaskId = data.task_id;
                showNotification('任务创建成功，正在跳转到详情页面...', 'success');
                
                // 清空表单
                document.getElementById('parameter-form').reset();
                // 隐藏组合信息
                document.getElementById('combination-info').style.display = 'none';
                // 清除保存的表单数据
                clearSavedFormData();
                
                // 延迟1秒后跳转到详情页面（C4 模式）
                setTimeout(function() {
                    window.location.href = `/google-sheet/detail?task_id=${currentTaskId}&version=c4`;
                }, 1000);
            } else {
                showNotification('创建任务失败: ' + (data ? data.message : '未知错误'), 'error');
            }
        });
    }

    // SSE相关功能已移除，任务创建后直接跳转到详情页面

    // 处理任务事件（保留以备将来使用）
    function handleTaskEvent(event) {
        if (event.type === 'log_update') {
            // 处理实时日志更新
            console.log('收到日志更新:', event.data);
        } else if (event.type === 'heartbeat') {
            // 心跳包，无需处理
        } else if (event.type === 'error') {
            showNotification('任务执行出错: ' + event.data, 'error');
        }
    }
    
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
            custom_sheet_name: document.getElementById('custom_sheet_name').value,
            token_type: document.getElementById('token_type').value,
            token_file: document.getElementById('token_file').value,
            token_json: document.getElementById('token_json').value,
            proxy_url: document.getElementById('proxy_url').value,
            market_type: document.querySelector('input[name="market_type"]:checked')?.value || 'cn',
            date_range_mode: getSelectedDateRangeModes(),
            param1: document.getElementById('param1').value
        };
        
        try {
            localStorage.setItem('google_sheet_c4_form_data', JSON.stringify(formData));
            // 静默保存，不显示提示
        } catch (e) {
            console.warn('无法保存表单数据到localStorage:', e);
        }
    }

    // 从localStorage加载表单数据
    function loadSavedFormData() {
        try {
            const savedData = localStorage.getItem('google_sheet_c4_form_data');
            if (savedData) {
                const formData = JSON.parse(savedData);
                
                // 恢复表单字段
                if (formData.task_name) document.getElementById('task_name').value = formData.task_name;
                if (formData.task_description) document.getElementById('task_description').value = formData.task_description;
                if (formData.spreadsheet) document.getElementById('spreadsheet').value = formData.spreadsheet;
                if (formData.spreadsheet_title) document.getElementById('spreadsheet_title').value = formData.spreadsheet_title;
                if (formData.sheet_name) {
                    const sheetSelect = document.getElementById('sheet_name');
                    sheetSelect.setAttribute('data-saved-value', formData.sheet_name);
                }
                if (formData.custom_sheet_name) document.getElementById('custom_sheet_name').value = formData.custom_sheet_name;
                if (formData.token_type) document.getElementById('token_type').value = formData.token_type;
                if (formData.token_file) document.getElementById('token_file').value = formData.token_file;
                if (formData.token_json) document.getElementById('token_json').value = formData.token_json;
                if (formData.proxy_url) document.getElementById('proxy_url').value = formData.proxy_url;
                const param1El = document.getElementById('param1');
                if (formData.param1 && param1El) param1El.value = formData.param1;

                if (formData.market_type) {
                    const mtInput = document.querySelector(`input[name="market_type"][value="${formData.market_type}"]`);
                    if (mtInput) {
                        mtInput.checked = true;
                    }
                }

                if (formData.date_range_mode !== undefined) {
                    applyDateRangeModes(formData.date_range_mode);
                }
                
                // 触发相关事件以更新UI状态
                document.getElementById('sheet_name').dispatchEvent(new Event('change'));
                document.getElementById('token_type').dispatchEvent(new Event('change'));
                initProductCodeChipsFromParam1();
                
                console.log('表单数据已恢复');
                
                // 显示恢复状态
                showNotification('表单数据已恢复', 'info');
            }
        } catch (e) {
            console.warn('无法从localStorage加载表单数据:', e);
        }
    }

    // 清除保存的表单数据
    function clearSavedFormData() {
        try {
            localStorage.removeItem('google_sheet_c4_form_data');
            // 重置表单
            document.getElementById('parameter-form').reset();
            // 隐藏组合信息
            document.getElementById('combination-info').style.display = 'none';
            // 重新计算组合数量
            calculateCombinations();
            console.log('已清除保存的表单数据');
            showNotification('已清除保存的表单数据', 'success');
        } catch (e) {
            console.warn('无法清除localStorage数据:', e);
        }
    }

    // 保存为模板
    function saveAsTemplate() {
        // 获取当前配置
        const config = getCurrentConfig();
        if (!config) {
            return;
        }

        // 预填充模板名称（如果有任务名称）
        const taskName = document.getElementById('task_name').value.trim();
        if (taskName) {
            document.getElementById('templateName').value = taskName + ' 模板';
        }

        // 显示保存模板对话框
        const modal = new bootstrap.Modal(document.getElementById('saveTemplateModal'));
        modal.show();
    }

    // 获取当前配置
    function getCurrentConfig() {
        try {
            const spreadsheetInput = document.getElementById('spreadsheet').value;
            const spreadsheetId = extractSpreadsheetId(spreadsheetInput);
            const sheetNameSelect = document.getElementById('sheet_name').value;
            const customSheetName = document.getElementById('custom_sheet_name').value;
            const sheetName = sheetNameSelect === '自定义' ? customSheetName : sheetNameSelect;
            const tokenType = document.getElementById('token_type').value;
            const tokenFile = document.getElementById('token_file').value;
            const tokenJson = document.getElementById('token_json').value;
            const proxyUrl = document.getElementById('proxy_url').value;
            const countMode = document.querySelector('input[name="count_mode"]:checked')?.value || 'total';
            const marketType = document.querySelector('input[name="market_type"]:checked')?.value || 'cn';
            const startDate = document.getElementById('start_date')?.value || null;
            const endDate = document.getElementById('end_date')?.value || null;

            // 验证必要字段
            if (!spreadsheetId) {
                showError('请输入电子表格ID或URL');
                return null;
            }

            if (sheetNameSelect === '自定义' && !customSheetName) {
                showError('请输入自定义工作表名称');
                return null;
            }

            if (tokenType === 'file' && !tokenFile) {
                showError('请输入Token文件路径');
                return null;
            }

            if (tokenType === 'json' && !tokenJson) {
                showError('请输入Token JSON字符串');
                return null;
            }

            // 获取产品代码参数
            const param1 = parseJsonArray(document.getElementById('param1').value);

            // 检查是否有解析错误
            if (param1 === null) {
                showError('参数格式错误，请检查JSON格式');
                return null;
            }

            // 收集所有表格配置
            const sheets = [];
            const sheetConfigList = document.getElementById('sheet-config-list');
            if (sheetConfigList) {
                const items = sheetConfigList.querySelectorAll('.sheet-config-item');
                items.forEach((item, index) => {
                    let sid = '';
                    let sname = '';

                    if (index === 0) {
                        sid = spreadsheetId;
                        sname = sheetName;
                    } else {
                        const textInputs = item.querySelectorAll('input[type="text"]');
                        const spreadsheetInputEl = textInputs[0];
                        const customInputEl = textInputs[1] || null;
                        const selectEl = item.querySelector('select');

                        if (spreadsheetInputEl) {
                            sid = extractSpreadsheetId(spreadsheetInputEl.value || '');
                        }

                        if (selectEl) {
                            if (selectEl.value === '自定义' && customInputEl) {
                                sname = (customInputEl.value || '').trim();
                            } else if (selectEl.value) {
                                sname = selectEl.value;
                            } else if (customInputEl) {
                                sname = (customInputEl.value || '').trim();
                            }
                        } else if (customInputEl) {
                            sname = (customInputEl.value || '').trim();
                        }
                    }

                    if (sid && sname) {
                        sheets.push({
                            spreadsheet_id: sid,
                            sheet_name: sname
                        });
                    }
                });
            }

            // 构造配置对象（C4 专用结构）
            return {
                task_type: 'google_sheet_C4',
                token_type: tokenType,
                token_file: tokenFile,
                token_json: tokenJson,
                proxy_url: proxyUrl || null,
                count_mode: countMode,
                market_type: marketType,
                start_date: startDate,
                end_date: endDate,
                parameters: [param1],
                sheets: sheets
            };
        } catch (error) {
            console.error('获取当前配置失败:', error);
            showError('获取当前配置失败: ' + error.message);
            return null;
        }
    }

    // 提交模板
    function submitTemplate() {
        const config = getCurrentConfig();
        if (!config) {
            return;
        }

        const name = document.getElementById('templateName').value.trim();
        const description = document.getElementById('templateDescription').value.trim();

        if (!name) {
            showError('请输入模板名称');
            return;
        }

        const templateData = {
            name: name,
            description: description,
            config: config
        };

        fetch('/api/templates', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(templateData)
        })
        .then(response => response.json())
        .then(data => {
            if (data.status === 'success') {
                const modal = document.getElementById('saveTemplateModal');
                const modalInstance = bootstrap.Modal.getInstance(modal);
                if (modalInstance) {
                    modalInstance.hide();
                }
                showNotification('模板保存成功', 'success');
                
                // 重新加载模板列表
                loadTemplates();
            } else {
                showError(data.message || '保存模板失败');
            }
        })
        .catch(error => {
            console.error('保存模板失败:', error);
            showError('保存模板失败: ' + error.message);
        });
    }

    // 将可能的旧结构配置转换为 C4 统一结构
    function normalizeC4Config(raw) {
        if (!raw || typeof raw !== 'object') {
            return {};
        }

        // 已经是 C4 新结构（有 sheets 数组）则直接返回
        if (Array.isArray(raw.sheets) && raw.sheets.length > 0) {
            return raw;
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
            count_mode: raw.count_mode || 'total',
            start_date: raw.start_date || null,
            end_date: raw.end_date || null,
            market_type: raw.market_type || 'cn',
            token_type: raw.token_type || 'file',
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
            const restartConfig = normalizeC4Config(restartConfigRaw);
            
            console.log('加载重启配置:', restartConfig);
            
            // 填充基本信息（添加重启标识）
            if (restartConfig.name) {
                document.getElementById('task_name').value = restartConfig.name + ' (重启)';
            }
            
            // 填充Google Sheet配置（优先使用 sheets 数组）
            let primarySpreadsheetId = '';
            let primarySheetName = '';

            if (Array.isArray(restartConfig.sheets) && restartConfig.sheets.length > 0) {
                const firstSheet = restartConfig.sheets[0] || {};
                primarySpreadsheetId = firstSheet.spreadsheet_id || '';
                primarySheetName = firstSheet.sheet_name || '';
            } else {
                primarySpreadsheetId = restartConfig.spreadsheet_id || '';
                primarySheetName = restartConfig.sheet_name || '';
            }

            if (primarySpreadsheetId) {
                document.getElementById('spreadsheet').value = primarySpreadsheetId;
            }
            if (primarySheetName) {
                // 与模板加载逻辑保持一致：先保存到 data-saved-value
                // 等 loadWorksheetsForItem 拉取到工作表列表后再真正选中
                const sheetSelect = document.getElementById('sheet_name');
                if (sheetSelect) {
                    sheetSelect.setAttribute('data-saved-value', primarySheetName);
                }
                // 不在这里强制切换为“自定义工作表名称”，避免在还没加载下拉列表时进入错误状态
            }

            // 多张表：为后续表创建可视配置块
            if (Array.isArray(restartConfig.sheets) && restartConfig.sheets.length > 1) {
                const list = document.getElementById('sheet-config-list');
                restartConfig.sheets.slice(1).forEach(sheetCfg => {
                    if (!list) return;
                    addVisualSheetConfigItem();
                    const items = list.querySelectorAll('.sheet-config-item');
                    const item = items[items.length - 1];
                    if (!item) return;

                    const textInputs = item.querySelectorAll('input[type="text"]');
                    const spreadsheetInputEl = textInputs[0];
                    const customInputEl = textInputs[1] || null;

                    if (spreadsheetInputEl && sheetCfg.spreadsheet_id) {
                        spreadsheetInputEl.value = sheetCfg.spreadsheet_id;
                    }
                    if (customInputEl && sheetCfg.sheet_name) {
                        customInputEl.value = sheetCfg.sheet_name;
                    }
                });
            }
            if (restartConfig.token_type) {
                document.getElementById('token_type').value = restartConfig.token_type;
                // 触发change事件来显示对应的输入框
                document.getElementById('token_type').dispatchEvent(new Event('change'));
            }
            if (restartConfig.token_file) {
                document.getElementById('token_file').value = restartConfig.token_file;
            }
            if (restartConfig.token_json) {
                document.getElementById('token_json').value = restartConfig.token_json;
            }
            if (restartConfig.proxy_url) {
                document.getElementById('proxy_url').value = restartConfig.proxy_url;
            }
            if (restartConfig.market_type) {
                const mtInput = document.querySelector(`input[name="market_type"][value="${restartConfig.market_type}"]`);
                if (mtInput) {
                    mtInput.checked = true;
                }
            }

            if (restartConfig.date_range_mode) {
                const drmInput = document.querySelector(`input[name="date_range_mode"][value="${restartConfig.date_range_mode}"]`);
                if (drmInput) {
                    drmInput.checked = true;
                }
            }
            
            // 填充参数配置
            if (restartConfig.parameters && Array.isArray(restartConfig.parameters)) {
                const firstParam = restartConfig.parameters[0];
                const paramElement = document.getElementById('param1');
                if (paramElement && Array.isArray(firstParam)) {
                    paramElement.value = JSON.stringify(firstParam);
                    initProductCodeChipsFromParam1();
                }
            }
            
            // 更新页面标题
            document.title = '重启任务 - Google Sheet 参数批量校验';
            
            // 在页面顶部添加提示
            const cardHeader = document.querySelector('.card-header h4');
            if (cardHeader) {
                cardHeader.innerHTML = '<i class="bi bi-arrow-clockwise"></i> 重启任务 (基于原任务: ' + originalTaskId + ')';
            }
            
            // 计算参数组合
            calculateCombinations();
            
            showNotification('已加载原任务配置', 'info');
        } catch (e) {
            console.warn('加载重启配置失败:', e);
        }
    }
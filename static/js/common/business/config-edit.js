// ------------------------------
// c4/c5/c7 详情页三胞胎共享：编辑配置弹窗（02 §3.6，F3 收敛 pass）。
// 来源：static/js/pages/google_sheet_c{4,5,7}_detail.js（三版规范化后逐字相同，正本取自 c4）。
// 页面差异逻辑仍留在 pages 层；页面调用点经 Biz.configEdit.* 访问。
// ------------------------------
(function () {
    window.Biz = window.Biz || {};

    function openEditConfigModal() {
        if (!currentTaskData) {
            showNotification('任务数据未加载', 'error');
            return;
        }
    
        // 解析任务配置（必须是包含 sheets / parameters 结构的对象）
        var config = currentTaskData.config || {};
        if (typeof config === 'string') {
            try {
                config = JSON.parse(config);
            } catch (e) {
                console.warn('解析任务配置失败，将按原始字符串展示', e);
            }
        }
    
        // 任务基本信息
        const editTaskNameEl = document.getElementById('edit-task-name');
        if (editTaskNameEl) {
            editTaskNameEl.value = currentTaskData.name || '';
        }
        const editTaskDescEl = document.getElementById('edit-task-description');
        if (editTaskDescEl) {
            editTaskDescEl.value = currentTaskData.description || '';
        }
    
        // 主参数：parameters[0] 渲染为 chips
        var mainParams = Array.isArray(config.parameters && config.parameters[0])
            ? config.parameters[0].slice()
            : [];
        renderEditProductCodeChips(mainParams);
    
        // 完整 parameters 只读展示
        const paramsRawEl = document.getElementById('edit-parameters-raw');
        if (paramsRawEl) {
            try {
                paramsRawEl.value = config.parameters
                    ? JSON.stringify(config.parameters, null, 2)
                    : '';
            } catch (e) {
                paramsRawEl.value = '';
            }
        }
    
        // sheets 多行输入
        const sheets = Array.isArray(config.sheets) ? config.sheets : [];
        renderEditSheetsRows(sheets);
    
        // 更多参数区域
        const countModeEl = document.getElementById('edit-count-mode');
        if (countModeEl) {
            countModeEl.value = config.count_mode || 'n_plus_1';
        }
    
        const fullModeEl = document.getElementById('edit-date-range-full');
        const recentModeEl = document.getElementById('edit-date-range-recent');
        let drmList = [];
        if (Array.isArray(config.date_range_mode)) {
            drmList = config.date_range_mode;
        } else if (typeof config.date_range_mode === 'string' && config.date_range_mode) {
            drmList = [config.date_range_mode];
        }
        if (drmList.length === 0) {
            drmList = ['full'];
        }
    
        function applyEditDateRangeModes(enableOnly) {
            const currentMode = (countModeEl && countModeEl.value) || 'n_plus_1';
            const enable = currentMode === 'n_plus_1';
            if (fullModeEl) {
                fullModeEl.disabled = !enable;
                if (!enable) {
                    fullModeEl.checked = false;
                } else if (!enableOnly) {
                    fullModeEl.checked = drmList.includes('full');
                }
            }
            if (recentModeEl) {
                recentModeEl.disabled = !enable;
                if (!enable) {
                    recentModeEl.checked = false;
                } else if (!enableOnly) {
                    recentModeEl.checked = drmList.includes('recent');
                }
            }
        }
    
        applyEditDateRangeModes(false);
        if (countModeEl) {
            countModeEl.addEventListener('change', function () {
                applyEditDateRangeModes(true);
            });
        }
    
        const startDateEl = document.getElementById('edit-start-date');
        if (startDateEl) {
            startDateEl.value = config.start_date || '';
        }
    
        const endDateEl = document.getElementById('edit-end-date');
        if (endDateEl) {
            endDateEl.value = config.end_date || '';
        }
    
        const marketTypeEl = document.getElementById('edit-market-type');
        if (marketTypeEl) {
            marketTypeEl.value = config.market_type || '';
        }
    
        // 认证方式 / Token
        var tokenType = config.token_type || 'file';
        var tokenTypeSelect = document.getElementById('edit-token-type');
        var fileContainer = document.getElementById('edit-token-file-container');
        var jsonContainer = document.getElementById('edit-token-json-container');
    
        if (tokenTypeSelect) {
            tokenTypeSelect.value = tokenType;
    
            // 绑定切换事件（只绑定一次）
            if (!tokenTypeSelect._bindedForToggle) {
                tokenTypeSelect.addEventListener('change', function () {
                    const t = this.value || 'file';
                    if (fileContainer) fileContainer.classList.toggle('d-none', t !== 'file');
                    if (jsonContainer) jsonContainer.classList.toggle('d-none', t !== 'json');
                });
                tokenTypeSelect._bindedForToggle = true;
            }
        }
    
        if (fileContainer) fileContainer.classList.toggle('d-none', tokenType !== 'file');
        if (jsonContainer) jsonContainer.classList.toggle('d-none', tokenType !== 'json');
    
        const editTokenFileEl = document.getElementById('edit-token-file');
        if (editTokenFileEl) {
            editTokenFileEl.value = config.token_file || 'data/token.json';
        }
        const editTokenJsonEl = document.getElementById('edit-token-json');
        if (editTokenJsonEl) {
            editTokenJsonEl.value = config.token_json || '';
        }
    
        const editProxyUrlEl = document.getElementById('edit-proxy-url');
        if (editProxyUrlEl) {
            editProxyUrlEl.value = config.proxy_url || '';
        }
    
        // 打开模态框
        if (editConfigModal) {
            editConfigModal.show();
        }
    }

    function renderEditProductCodeChips(codes) {
        const container = document.getElementById('edit-product-code-chips');
        if (!container) return;
        container.innerHTML = '';
    
        const unique = [];
        const seen = new Set();
        (codes || []).forEach(c => {
            const val = String(c).trim();
            if (!val || seen.has(val)) return;
            seen.add(val);
            unique.push(val);
        });
    
        unique.forEach(code => {
            const chip = document.createElement('span');
            chip.className = 'badge bg-primary d-flex align-items-center me-1 mb-1';
            chip.style.cursor = 'default';
            chip.dataset.value = code;
            chip.innerHTML = `
                <span class="me-1">${code}</span>
                <button type="button" class="btn btn-sm btn-light btn-close p-0 ms-1" aria-label="删除" style="font-size: 0.5rem;"></button>
            `;
            const closeBtn = chip.querySelector('button');
            if (closeBtn) {
                closeBtn.addEventListener('click', function (e) {
                    e.stopPropagation();
                    chip.remove();
                });
            }
            container.appendChild(chip);
        });
    }

    function renderEditSheetsRows(sheets) {
        const list = document.getElementById('edit-sheets-list');
        if (!list) return;
        list.innerHTML = '';
        const data = Array.isArray(sheets) && sheets.length > 0 ? sheets : [{}];
    
        data.forEach(s => {
            const row = document.createElement('div');
            row.className = 'row g-2 align-items-end mb-2 edit-sheet-row';
            row.innerHTML = `
                <div class="col-md-4">
                    <label class="form-label small mb-1">spreadsheet_id</label>
                    <input type="text" class="form-control form-control-sm edit-sheet-spreadsheet-id" value="${s.spreadsheet_id || ''}">
                </div>
                <div class="col-md-4">
                    <label class="form-label small mb-1">title</label>
                    <input type="text" class="form-control form-control-sm edit-sheet-title" value="${s.title || ''}">
                </div>
                <div class="col-md-4">
                    <label class="form-label small mb-1">sheet_name</label>
                    <input type="text" class="form-control form-control-sm edit-sheet-name" value="${s.sheet_name || ''}">
                </div>
            `;
            list.appendChild(row);
        });
    }

    function collectEditProductCodesFromChips() {
        const container = document.getElementById('edit-product-code-chips');
        if (!container) return [];
        const vals = [];
        const seen = new Set();
        container.querySelectorAll('[data-value]').forEach(el => {
            const v = (el.dataset.value || '').trim();
            if (v && !seen.has(v)) {
                seen.add(v);
                vals.push(v);
            }
        });
        return vals;
    }

    function createConfigGridItem(item) {
        const col = document.createElement('div');
        col.className = 'detail-config-item d-flex align-items-start';
        col.innerHTML = `
            <i class="${item.icon} text-muted me-3 mt-1"></i>
            <div class="flex-grow-1 min-w-0">
                <div class="detail-config-label">${item.label}</div>
                <div class="detail-config-value">${item.value}</div>
            </div>
        `;
        return col;
    }

    function formatConfigDisplayValue(value, mapping) {
        if (Array.isArray(value)) {
            const formatted = value
                .map(item => formatConfigDisplayValue(item, mapping))
                .filter(Boolean);
            return formatted.length ? formatted.join('、') : '-';
        }
    
        if (value === null || value === undefined || value === '') {
            return '-';
        }
    
        const normalized = String(value);
        return mapping && mapping[normalized] ? mapping[normalized] : normalized;
    }

    function formatCountMode(value) {
        return formatConfigDisplayValue(value, {
            total: '总数',
            n_plus_1: 'N+1'
        });
    }

    function formatDateRangeMode(value) {
        return formatConfigDisplayValue(value, {
            full: '整年',
            recent: '近年'
        });
    }

    function formatMarketType(value) {
        return formatConfigDisplayValue(value, {
            cn: 'A股',
            us: '美股'
        });
    }

    function formatTokenType(value) {
        return formatConfigDisplayValue(value, {
            file: 'Token 文件',
            json: 'Token JSON'
        });
    }

    Biz.configEdit = {
        openEditConfigModal: openEditConfigModal,
        renderEditProductCodeChips: renderEditProductCodeChips,
        renderEditSheetsRows: renderEditSheetsRows,
        collectEditProductCodesFromChips: collectEditProductCodesFromChips,
        createConfigGridItem: createConfigGridItem,
        formatConfigDisplayValue: formatConfigDisplayValue,
        formatCountMode: formatCountMode,
        formatDateRangeMode: formatDateRangeMode,
        formatMarketType: formatMarketType,
        formatTokenType: formatTokenType
    };
})();

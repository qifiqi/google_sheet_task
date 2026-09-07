// Google Sheet 任务详情页（C7）（templates/google_sheet_c7/detail.html 的页面逻辑）。
// 批内收敛：同名函数已提升至 static/js/common/business/（Biz.*），见 F3 收敛 pass。
// 自 templates/google_sheet_c7/detail.html 内联脚本原样抽离；接口调用经 common/api.js。

// ── 原 Jinja 服务端渲染点的前端等价实现（静态化，docs/design/frontend-refactor/03 §5）──
// 原 `url_for('google_sheet.index', version=request.args.get('version', 'c7'))`
const versionParam = new URLSearchParams(location.search).get('version');
if (versionParam && versionParam !== 'c7') {
    const backLink = document.querySelector('a[href="/google-sheet/?version=c7"]');
    if (backLink) {
        backLink.href = '/google-sheet/?version=' + encodeURIComponent(versionParam);
    }
}

// 原 JS 模板字符串内的 `{{ version }}`（docs/design/frontend-refactor/03 §5）：
// 静态化后改为运行时读取 query 参数（原服务端渲染值）
const CURRENT_VERSION = new URLSearchParams(location.search).get('version');
    // 全局变量
    let currentTaskId = null;
    let statusInterval = null;
    let refreshInterval = null;
    let allResults = [];
    let groupedResults = [];
    let flattenedResults = [];
    let filteredResults = [];
    let currentResultsPage = 1;
    let resultsPerPage = 10;
    let resultsTotalPages = 1;
    let resultsTotalCount = 0;
    let resultsTotalSuccess = null;
    let resultsTotalFailed = null;
    let currentResultsFilter = 'all';
    let currentRefreshFrequency = 60000; // 固定1分钟刷新
    let taskStartTime = null; // 存储任务开始时间
    let currentTaskData = null; // 存储当前任务数据
    let editConfigModal = null; // 编辑配置模态框实例

    // 页面加载完成后获取任务详情
    document.addEventListener('DOMContentLoaded', function () {
        console.log('页面加载完成');
        currentTaskId = Biz.taskPolling.getTaskIdFromUrl();
        console.log('获取到的任务ID:', currentTaskId);

        // 初始化编辑配置模态框
        const modalElement = document.getElementById('editConfigModal');
        if (modalElement && typeof bootstrap !== 'undefined') {
            editConfigModal = new bootstrap.Modal(modalElement);
        }

        // 绑定编辑弹窗内的事件（chips & sheets）
        const addCodeBtn = document.getElementById('edit-add-product-code-btn');
        const codeInput = document.getElementById('edit-product-code-input');
        if (addCodeBtn && codeInput) {
            const addCodes = function () {
                const raw = (codeInput.value || '').trim();
                if (!raw) return;
                const parts = raw.split(/[\s,，]+/).map(v => v.trim()).filter(v => v);
                const existing = Biz.configEdit.collectEditProductCodesFromChips();
                Biz.configEdit.renderEditProductCodeChips(existing.concat(parts));
                codeInput.value = '';
            };
            addCodeBtn.addEventListener('click', addCodes);
            codeInput.addEventListener('keydown', function (e) {
                if (e.key === 'Enter') {
                    e.preventDefault();
                    addCodes();
                }
            });
        }

        const addSheetBtn = document.getElementById('edit-add-sheet-btn');
        const removeSheetBtn = document.getElementById('edit-remove-sheet-btn');
        if (addSheetBtn) {
            addSheetBtn.addEventListener('click', function () {
                const list = document.getElementById('edit-sheets-list');
                if (!list) return;
                const row = document.createElement('div');
                row.className = 'row g-2 align-items-end mb-2 edit-sheet-row';
                row.innerHTML = `
                    <div class="col-md-4">
                        <label class="form-label small mb-1">spreadsheet_id</label>
                        <input type="text" class="form-control form-control-sm edit-sheet-spreadsheet-id" value="">
                    </div>
                    <div class="col-md-4">
                        <label class="form-label small mb-1">title</label>
                        <input type="text" class="form-control form-control-sm edit-sheet-title" value="">
                    </div>
                    <div class="col-md-4">
                        <label class="form-label small mb-1">sheet_name</label>
                        <input type="text" class="form-control form-control-sm edit-sheet-name" value="">
                    </div>
                `;
                list.appendChild(row);
            });
        }
        if (removeSheetBtn) {
            removeSheetBtn.addEventListener('click', function () {
                const list = document.getElementById('edit-sheets-list');
                if (!list) return;
                const rows = list.querySelectorAll('.edit-sheet-row');
                // 导出排序规则：
                // 1) 按 stock_code 降序
                // 2) 按 kline_range 的完整日期区间排序：先结束日期，再开始日期，都是降序
                // 3) 同一完整日期区间内按 xm 升序，空值和 0 排最前
                // 4) 同一 xm 内按 ReturnBeats 降序
                if (rows.length > 1) {
                    list.removeChild(rows[rows.length - 1]);
                }
            });
        }

        if (currentTaskId) {
            // 从配置加载默认刷新频率
            Api.endpoints.config.get().then(function(data) {
                if (data && data.config && data.config.detail_refresh_interval) {
                    currentRefreshFrequency = data.config.detail_refresh_interval;
                    // 更新下拉框的默认选择
                    const frequencySelect = document.getElementById('refresh-frequency');
                    if (frequencySelect) {
                        frequencySelect.value = currentRefreshFrequency;
                    }
                }

                loadTaskDetail();
                // 启动自动刷新
                startAutoRefresh();
            }).catch(function() {
                // 原 ajaxRequest 失败分支：仍按默认频率加载并启动自动刷新
                loadTaskDetail();
                startAutoRefresh();
            });
        } else {
            showNotification('任务ID无效', 'error');
        }
    });

    // 页面卸载时清理定时器
    window.addEventListener('beforeunload', function () {
        stopAutoRefresh();
    });

    // 获取频率文本
    // 手动刷新
    // 获取URL中的任务ID
    // 加载任务详情
    function loadTaskDetail() {
        console.log('开始加载任务详情，任务ID:', currentTaskId);
        Api.endpoints.task.detail(currentTaskId).then(function(data) {
            console.log('API响应:', data);
            if (data && data.task) {
                const task = data.task;
                console.log('任务数据:', task);

                // 保存任务数据供编辑使用
                currentTaskData = task;

                // 填充基本信息
                document.getElementById('task-id').textContent = task.id;
                document.getElementById('task-name').textContent = task.name;
                document.getElementById('task-status').innerHTML = `<span class="badge ${getStatusClass(task.status)}">${getStatusText(task.status)}</span>`;

                // 更新进度显示（增强对比度和可见性）
                const progressPercent = task.total_steps > 0 ? Math.round((task.current_step / task.total_steps) * 100) : 0;
                const visiblePercent = progressPercent > 0 ? Math.max(progressPercent, 5) : 0;
                const progressBarClass = getProgressBarClass(task.status) + (task.status === 'running' ? ' progress-bar-striped progress-bar-animated' : '');
                let progress_html = null
                progress_html = `
                    <div class="progress" style="height: 20px; background-color: #e9ecef; position: relative;">
                        <div class="progress-bar ${progressBarClass}" role="progressbar"
                             style="width: ${visiblePercent}%;">
                        </div>
                        <span style="position: absolute; top: 0; left: 0; right: 0; bottom: 0;
                               display: flex; align-items: center; justify-content: center;
                               color: black;  z-index: 10; font-size: 12px;">
                            ${task.current_step}/${task.total_steps} (${progressPercent}%)
                        </span>
                    </div>
                `;
                     /*
                     *
                     *
                     *                      progress_html= ` <div class="progress" style="height: 20px; background-color: #e9ecef;">
                            <div class="progress-bar ${progressBarClass}" role="progressbar"
                                 style="width: ${visiblePercent}%;">
                                ${task.current_step}/${total_steps} (${progressPercent}%)
                            </div>
                        </div>
                    `;
                     * */

                document.getElementById('task-progress').innerHTML = progress_html;

                // 更新时间信息
                document.getElementById('start-time').textContent = formatTime(task.start_time);
                document.getElementById('end-time').textContent = formatTime(task.end_time);
                document.getElementById('create-time').textContent = formatTime(task.created_at);

                // 保存任务开始时间用于计算耗时
                if (task.start_time) {
                    taskStartTime = new Date(task.start_time);
                }

                // 计算执行时长
                let duration = 0;
                if (task.created_at) {
                    const cTime = new Date(task.created_at);
                    const endTime = task.end_time ? new Date(task.end_time) : new Date();
                    duration = Math.max(0, Math.round((endTime - cTime) / 1000)); // 确保不为负数
                }
                document.getElementById('execution-duration').textContent = formatDuration(duration);

                // 显示/隐藏错误信息
                const errorInfo = document.getElementById('error-info');
                if (task.error_message) {
                    document.getElementById('error-message').textContent = task.error_message;
                    errorInfo.classList.remove('d-none');
                } else {
                    errorInfo.classList.add('d-none');
                }

                // 显示/隐藏取消按钮
                const cancelBtn = document.getElementById('cancel-task-btn');
                if (task.status === 'running') {
                    cancelBtn.classList.remove('d-none');
                    cancelBtn.setAttribute('data-task-id', task.id);
                } else {
                    cancelBtn.classList.add('d-none');
                }

                // 显示/隐藏重启按钮（包括pending状态）
                const restartBtn = document.getElementById('restart-dropdown-btn');
                if (task.status === 'pending' || task.status === 'completed' || task.status === 'error' || task.status === 'cancelled') {
                    restartBtn.classList.remove('d-none');
                } else {
                    restartBtn.classList.add('d-none');
                }

                // 显示/隐藏编辑按钮（只有非运行状态才能编辑）
                const editBtn = document.getElementById('edit-config-btn');
                if (task.status !== 'running') {
                    editBtn.classList.remove('d-none');
                } else {
                    editBtn.classList.add('d-none');
                }

                // 填充配置信息（兼容 config 为字符串或对象的情况）
                let cfg = task.config;
                if (typeof cfg === 'string') {
                    try {
                        cfg = JSON.parse(cfg);
                    } catch (e) {
                        console.warn('解析任务配置失败，将按原始字符串展示', e);
                    }
                }

                loadTaskConfig(cfg);
                loadTaskParameters(cfg);

                // 加载任务日志
                Biz.taskPolling.loadTaskLogs();

                // 加载任务结果
                Biz.taskPolling.loadTaskResults();

                // 更新页面标题
                document.title = `任务详情 - ${task.name}`;

                // 如果任务还在运行，启动定时刷新
                if (task.status === 'running') {
                    startAutoRefresh();
                } else {
                    stopAutoRefresh();
                }
            } else {
                showNotification('获取任务详情失败: ' + (data ? data.message : '未知错误'), 'error');
            }
        }).catch(function(err) {
            showNotification('获取任务详情失败: ' + (err && err.message ? err.message : '未知错误'), 'error');
        });
    }

    // ===== 编辑配置模态框辅助函数 =====
    window.openEditConfigModal = Biz.configEdit.openEditConfigModal;

    // 加载任务配置
    function formatPriceMode(value) {
        return Biz.configEdit.formatConfigDisplayValue(value, {
            kp_price: '开盘价',
            sp_price: '收盘价',
            vwap_price: '加权平均价'
        });
    }

    function formatExcludedYears(value) {
        if (!value || !Array.isArray(value) || value.length === 0) {
            return '<span class="text-muted">无</span>';
        }
        const years = value.map(y => `近${y}年`).join('、');
        return `<span class="text-danger">${years}</span>`;
    }



    function formatTokenSelectionMode(value) {
        return Biz.configEdit.formatConfigDisplayValue(value, {
            '__random__': '\u968f\u673a Token'
        });
    }

    function loadTaskConfig(config) {
        const container = document.getElementById('config-container');
        const moreContainer = document.getElementById('more-config-container');
        container.innerHTML = '';
        if (moreContainer) {
            moreContainer.innerHTML = '';
        }

        if (!config) {
            container.innerHTML = '<div class="text-muted">无配置信息</div>';
            if (moreContainer) {
                moreContainer.innerHTML = '<div class="text-muted">无更多参数</div>';
            }
            return;
        }

        // C4 专用渲染：按 sheets + 汇总信息展示
        const sheets = Array.isArray(config.sheets) ? config.sheets : [];
        const dateRange = `${config.start_date || '-'} ~ ${config.end_date || '-'}`;
        const dateRangeModeDisplay = Biz.configEdit.formatDateRangeMode(config.date_range_mode || 'full');

        // 工作表列表：每个表一行（表N + ID + 名称）
        const sheetsBlock = document.createElement('div');
        sheetsBlock.className = 'mb-2';
        sheetsBlock.innerHTML = '<strong class="d-block mb-2">工作表配置</strong>';

        if (sheets.length > 0) {
            sheets.forEach((s, idx) => {
                const row = document.createElement('div');
                row.className = 'detail-sheet-item small text-muted mb-2';
                const titleText = s.title || '';
                row.innerHTML = `
                    <div class="d-flex flex-wrap align-items-center gap-2">
                        <span class="badge bg-secondary">表 ${idx + 1}</span>
                        <span>表格 ID：${s.spreadsheet_id || '-'}</span>
                        <span>工作表：${s.sheet_name || '-'}</span>
                        <span class="text-muted">标题：${titleText || '-'}</span>
                    </div>
                `;
                sheetsBlock.appendChild(row);
            });
        } else {
            const empty = document.createElement('div');
            empty.className = 'text-muted small';
            empty.textContent = '无工作表配置';
            sheetsBlock.appendChild(empty);
        }

        container.appendChild(sheetsBlock);

        // 汇总信息折叠显示（只在需要时展开查看）
        const details = document.createElement('details');
        details.className = 'mt-2 small';

        const summary = document.createElement('summary');
        summary.className = 'text-muted';
        summary.textContent = '更多参数';
        details.appendChild(summary);

        const list = document.createElement('div');
        list.className = 'detail-config-grid mt-3';

        const configItems = [
            {label: '统计方式', value: Biz.configEdit.formatCountMode(config.count_mode || 'total'), icon: 'bi-calculator'},
            {label: '价格类型', value: formatPriceMode(config.price_mode || 'vwap_price'), icon: 'bi-currency-exchange'},
            {label: '市场类型', value: Biz.configEdit.formatMarketType(config.market_type || 'cn'), icon: 'bi-graph-up-arrow'},
            {label: '市场代码', value: config.exchange_market || config.market || '-', icon: 'bi-building'},
            {label: '数据源', value: config.kline_data_source || config.data_source || '-', icon: 'bi-database'},
            {label: '时间范围类型', value: dateRangeModeDisplay, icon: 'bi-clock-history'},
            {label: '数据时间范围', value: dateRange, icon: 'bi-calendar-range'},
            {label: '移除的近年区间', value: formatExcludedYears(config.exclude_recent_years), icon: 'bi-x-circle'},
            {label: '认证方式', value: Biz.configEdit.formatTokenType(config.token_type || 'file'), icon: 'bi-shield-lock'},
            {label: 'Token \u540d\u79f0', value: config.token_name || '-', icon: 'bi-tag'},
            {label: 'Token \u9009\u62e9\u6a21\u5f0f', value: formatTokenSelectionMode(config.token_selection_mode), icon: 'bi-shuffle'},
            {label: 'Token 路径', value: config.token_file || '-', icon: 'bi-file-earmark-text'},
            {label: '代理地址', value: config.proxy_url || '-', icon: 'bi-globe'}
        ];

        configItems.forEach(item => {
            list.appendChild(Biz.configEdit.createConfigGridItem(item));
        });

        details.appendChild(list);
        if (moreContainer) {
            moreContainer.appendChild(details);
        } else {
            container.appendChild(details);
        }
    }

    // 加载任务日志
    // 加载任务参数
    function loadTaskParameters(config) {
        const container = document.getElementById('parameters-container');
        container.innerHTML = '';

        if (!config || !Array.isArray(config.parameters) || config.parameters.length === 0) {
            container.innerHTML = '<div class="text-muted">无参数配置</div>';
            return;
        }

        // 样式与 google_sheet/detail.html 一致：badge + code(JSON.stringify)
        const paramsArr = config.parameters;

        paramsArr.forEach((paramGroup, index) => {
            const paramDiv = document.createElement('div');
            paramDiv.className = 'mb-2';
            paramDiv.innerHTML = `
                <div class="d-flex align-items-center">
                    <span class="badge bg-primary me-2">参数${index + 1}</span>
                    <code class="text-dark">${JSON.stringify(paramGroup)}</code>
                </div>
            `;
            container.appendChild(paramDiv);
        });
    }

    // 加载任务结果（后端分页）
    function isC7V03Task() {
        let config = currentTaskData?.config || {};
        if (typeof config === 'string') {
            try {
                config = JSON.parse(config);
            } catch (_error) {
                return false;
            }
        }
        return Array.isArray(config.sheets)
            && config.sheets.some(sheet => sheet?.c7_model_version === 'c7_0_3');
    }

    function adaptC7ResultMetrics(metrics) {
        if (!Biz.taskPolling.isPlainObject(metrics) || !isC7V03Task()) {
            return metrics;
        }

        const adapted = {...metrics};
        for (let row = 2; row <= 20; row += 1) {
            delete adapted[`D${row}`];
        }
        for (let offset = 0; offset <= 18; offset += 1) {
            const sourceKey = `D${offset + 2}`;
            if (metrics[sourceKey] != null) {
                adapted[`D${offset + 8}`] = metrics[sourceKey];
            }
        }
        return adapted;
    }

    // 按每条 result（参数组合）分组，内部包含多个模型结果
    function groupResults(resultsArray) {
        const list = [];

        if (!Array.isArray(resultsArray)) {
            return list;
        }

        resultsArray.forEach((item) => {
            const params = item.parameters || {};
            const stockCode = params.stock_code || '-';

            let klineRange = '-';
            if (Array.isArray(params.kline) && params.kline.length > 0) {
                const sortedKline = params.kline
                        .filter(r => r && r.stock_date)
                        .slice()
                        .sort((a, b) => (a.stock_date > b.stock_date ? 1 : -1));
                if (sortedKline.length > 0) {
                    const first = sortedKline[0];
                    const last = sortedKline[sortedKline.length - 1];
                    klineRange = `${first.stock_date || '-'} ~ ${last.stock_date || '-'}`;
                }
            }

            const a1 = params.A1 != null ? params.A1 : null;
            const b1 = params.B1 != null ? params.B1 : null;

            const resultObj = item.result && typeof item.result === 'object' ? item.result : {};
            const models = [];

            Object.keys(resultObj).forEach((keyName) => {
                const metrics = adaptC7ResultMetrics(resultObj[keyName] || {});

                const d2 = Biz.taskPolling.getPreferredMetricValue(metrics, 'D8');
                const d3 = Biz.taskPolling.getPreferredMetricValue(metrics, 'D9');
                const d4 = Biz.taskPolling.getPreferredMetricValue(metrics, 'D10');
                const d5 = Biz.taskPolling.getPreferredMetricValue(metrics, 'D11');
                const d6 = Biz.taskPolling.getPreferredMetricValue(metrics, 'D12');
                const d7 = Biz.taskPolling.getPreferredMetricValue(metrics, 'D13');

                const startSharpe = Biz.taskPolling.getModelSharpeValue(metrics, 'start');
                const indexSharpe = Biz.taskPolling.getModelSharpeValue(metrics, 'index');

                const keyParts = String(keyName).split('__');
                const modelCode = keyParts[0] || String(keyName);
                const modelTitle = keyParts.slice(1).join('__');

                models.push({
                    modelKey: keyName,
                    modelCode: modelCode,
                    modelTitle: modelTitle,
                    d2: d2,
                    d3: d3,
                    d4: d4,
                    d5: d5,
                    d6: d6,
                    d7: d7,
                    startSharpe: startSharpe,
                    indexSharpe: indexSharpe,
                    rawMetrics: metrics
                });
            });

            list.push({
                stepIndex: item.step_index,
                success: !!item.success,
                errorMessage: item.error_message || null,
                timestamp: item.timestamp || null,
                taskId: item.task_id || null,
                rowId: item.id != null ? item.id : null,
                parameters: params,
                stockCode: stockCode,
                a1: a1,
                b1: b1,
                klineRange: klineRange,
                models: models
            });
        });

        return list;
    }

    // 将后端返回的 results 扁平化为按 result-key 展示的列表
    function flattenResults(resultsArray) {
        const list = [];

        if (!Array.isArray(resultsArray)) {
            return list;
        }

        resultsArray.forEach((item) => {
            const params = item.parameters || {};
            const stockCode = params.stock_code || '-';

            let klineRange = '-';
            if (Array.isArray(params.kline) && params.kline.length > 0) {
                const sortedKline = params.kline
                        .filter(r => r && r.stock_date)
                        .slice()
                        .sort((a, b) => (a.stock_date > b.stock_date ? 1 : -1));
                if (sortedKline.length > 0) {
                    const first = sortedKline[0];
                    const last = sortedKline[sortedKline.length - 1];
                    klineRange = `${first.stock_date || '-'} ~ ${last.stock_date || '-'}`;
                }
            }

            const resultObj = item.result && typeof item.result === 'object' ? item.result : {};
            Object.keys(resultObj).forEach((keyName) => {
                const metrics = adaptC7ResultMetrics(resultObj[keyName] || {});
                const d2 = Biz.taskPolling.getPreferredMetricValue(metrics, 'D8');
                const d3 = Biz.taskPolling.getPreferredMetricValue(metrics, 'D9');

                const startSharpe = Biz.taskPolling.getModelSharpeValue(metrics, 'start');
                const indexSharpe = Biz.taskPolling.getModelSharpeValue(metrics, 'index');

                const keyParts = String(keyName).split('__');
                const modelCode = keyParts[0] || String(keyName);
                const modelTitle = keyParts.slice(1).join('__');

                list.push({
                    stepIndex: item.step_index,
                    success: !!item.success,
                    errorMessage: item.error_message || null,
                    timestamp: item.timestamp || null,
                    taskId: item.task_id || null,
                    rowId: item.id != null ? item.id : null,
                    parameters: params,
                    stockCode: stockCode,
                    klineRange: klineRange,
                    modelKey: keyName,
                    modelCode: modelCode,
                    modelTitle: modelTitle,
                    d2: d2,
                    d3: d3,
                    startSharpe: startSharpe,
                    indexSharpe: indexSharpe,
                    rawMetrics: metrics
                });
            });
        });

        return list;
    }

    // 应用结果筛选（以分组为单位）
    // 筛选结果
    // 渲染结果列表（按参数组合分组的卡片视图）
    function renderResults() {
        const listContainer = document.getElementById('results-list');
        const summaryEl = document.getElementById('results-summary');
        listContainer.innerHTML = '';

        // 后端分页：filteredResults 已经是当前页的数据，直接使用
        const pageResults = filteredResults;

        // 统计总数优先使用后端返回的全局统计
        let totalCount;
        let successCount;
        let failedCount;

        if (typeof resultsTotalSuccess === 'number' && typeof resultsTotalFailed === 'number') {
            successCount = resultsTotalSuccess;
            failedCount = resultsTotalFailed;
            totalCount = resultsTotalCount || (resultsTotalSuccess + resultsTotalFailed);
        } else {
            totalCount = resultsTotalCount || groupedResults.length;
            successCount = groupedResults.filter(r => r.success).length;
            failedCount = totalCount - successCount;
        }

        if (summaryEl) {
            summaryEl.textContent = `共 ${totalCount} 条模型结果，其中成功 ${successCount} 条，失败 ${failedCount} 条。`;
        }

        if (!Array.isArray(pageResults) || pageResults.length === 0) {
            const emptyDiv = document.createElement('div');
            emptyDiv.className = 'text-muted text-center py-3';
            emptyDiv.textContent = '暂无执行结果';
            listContainer.appendChild(emptyDiv);
        } else {
            pageResults.forEach((group, idx) => {
                const col = document.createElement('div');
                col.className = 'col-12';
                const groupIndex = idx; // 当前页内的索引

                const modelsRows = (group.models || []).map((model, mIndex) => {
                    const rawMetrics = model.rawMetrics || {};
                    const d2Text = formatMetricText(rawMetrics.D8, 6, 'D8');
                    const d3Text = formatMetricText(rawMetrics.D9, 6, 'D9');
                    const d4Text = formatMetricText(rawMetrics.D10, 6, 'D10');
                    const d5Text = formatMetricText(rawMetrics.D11, 6, 'D11');
                    const d6Text = formatMetricText(rawMetrics.D12, 6, 'D12');
                    const d7Text = formatMetricText(rawMetrics.D13, 6, 'D13');
                    let iXplText = '-';
                    if (model.indexSharpe != null) {
                        const v = Number(model.indexSharpe);
                        iXplText = Number.isFinite(v) ? v.toFixed(6) : String(model.indexSharpe);
                    }

                    let sXplText = '-';
                    if (model.startSharpe != null) {
                        const v2 = Number(model.startSharpe);
                        sXplText = Number.isFinite(v2) ? v2.toFixed(6) : String(model.startSharpe);
                    }

                    const titleText = model.modelTitle && model.modelTitle.length > 0
                            ? escapeHtml(model.modelTitle)
                            : escapeHtml(model.modelKey || '');

                    return `
                        <tr>
                            <td class="small">${titleText}</td>
                            <td class="small text-center">${d2Text}</td>
                            <td class="small text-center">${d3Text}</td>
                            <td class="small text-center">${d4Text}</td>
                            <td class="small text-center">${d5Text}</td>
                            <td class="small text-center">${d6Text}</td>
                            <td class="small text-center">${d7Text}</td>
                            <td class="small text-center">${iXplText}</td>
                            <td class="small text-center">${sXplText}</td>
                            <td class="small text-end">
                                <button type="button" class="btn btn-link btn-sm p-0" onclick="showResultDetail(${groupIndex}, ${mIndex})">更多</button>
                            </td>
                        </tr>
                    `;
                }).join('') || '<tr><td colspan="10" class="text-muted small text-center">无模型结果</td></tr>';

                col.innerHTML = `
                    <div class="card h-100">
                        <div class="card-header d-flex justify-content-between align-items-center">
                            <div>
                                <div class="small text-muted result-header-meta">
                                    <span>股票代码：</span>
                                    <span class="fw-semibold">${group.stockCode}</span>
                                    <span> · K线区间：${group.klineRange}</span>
                                    <span> · 步骤 ${group.stepIndex + 1}</span>
                                    <span> · A1：${group.a1 != null ? group.a1 : '-'}</span>
                                    <span> · B1：${group.b1 != null ? group.b1 : '-'}</span>
                                    <span> · 执行时间：${formatTime(group.timestamp) || '-'}</span>
                                </div>
                            </div>
                            <div class="text-end small result-header-status">
                                <span class="badge ${group.success ? 'bg-success' : 'bg-danger'} me-2">
                                    <i class="bi ${group.success ? 'bi-check-circle' : 'bi-x-circle'}"></i>
                                    ${group.success ? '成功' : '失败'}
                                </span>
                                <span class="text-muted">ID: ${group.rowId != null ? group.rowId : '-'}</span>
                            </div>
                        </div>
                        <div class="card-body p-2">
                            <div class="table-responsive mb-0">
                                <table class="table table-sm table-bordered mb-0">
                                    <thead>
                                        <tr class="small text-center align-middle">
                                            <th style="width: 25%;">模型标题</th>
                                            <th style="width: 10%;">Return</th>
                                            <th style="width: 10%;">Annualized</th>
                                            <th style="width: 10%;">Max DD%</th>
                                            <th style="width: 10%;">Index Return</th>
                                            <th style="width: 10%;">Annualized</th>
                                            <th style="width: 10%;">Index max dd</th>
                                            <th style="width: 10%;">i xpl</th>
                                            <th style="width: 10%;">s xpl</th>
                                            <th style="width: 5%;">操作</th>
                                        </tr>
                                    </thead>
                                    <tbody>
                                        ${modelsRows}
                                    </tbody>
                                </table>
                            </div>
                            ${group.errorMessage ? `<div class="small text-danger mt-2">错误：${group.errorMessage}</div>` : ''}
                        </div>
                    </div>
            `;

                listContainer.appendChild(col);
            });
        }

        // 渲染分页
        Biz.taskPolling.renderResultsPagination();
    }

    // 渲染结果分页
    // 切换结果页面
        // 刷新结果
        function refreshResults() {
            Biz.taskPolling.loadTaskResults(currentResultsPage || 1);
            showNotification('结果列表已刷新', 'info');
        }

        // 导出所有结果为 Excel：通过 fetch 走统一认证封装，确保携带 Authorization。
        async function exportResultsToCSV() {
            if (!currentTaskId) {
                showNotification('任务ID为空，无法导出', 'error');
                return;
            }

            try {
                const defaultFilename = ensureExcelExtension(`${currentTaskData?.name || currentTaskId}.xlsx`);
                const saveTarget = await prepareExcelSaveTarget(defaultFilename);
                const response = await Api.endpoints.export.task(encodeURIComponent(currentTaskId));
                if (!response.ok) {
                    const text = await response.text();
                    let message = `导出失败，状态码 ${response.status}`;
                    try {
                        const payload = JSON.parse(text);
                        message = payload.message || message;
                    } catch (_error) {
                        if (text) message = text;
                    }
                    showNotification(message, 'error');
                    return;
                }

                const blob = await response.blob();
                await saveExcelBlob(blob, saveTarget, getExportFilenameFromResponse(response) || defaultFilename);
            } catch (error) {
                if (error.name === 'AbortError') {
                    showNotification('已取消保存操作', 'info');
                    return;
                }
                showNotification(`导出失败: ${error.message || error}`, 'error');
            }
        }

        async function exportResultsByStockCode() {
            if (!currentTaskId) {
                showNotification('任务ID为空，无法导出', 'error');
                return;
            }

            try {
                const defaultFilename = ensureZipExtension(`${currentTaskData?.name || currentTaskId}_按股票代码导出.zip`);
                const saveTarget = await prepareZipSaveTarget(defaultFilename);
                const response = await Api.endpoints.export.taskStocks(encodeURIComponent(currentTaskId));
                if (!response.ok) {
                    const text = await response.text();
                    let message = `导出失败，状态码 ${response.status}`;
                    try {
                        const payload = JSON.parse(text);
                        message = payload.message || message;
                    } catch (_error) {
                        if (text) message = text;
                    }
                    showNotification(message, 'error');
                    return;
                }

                const blob = await response.blob();
                await saveZipBlob(blob, saveTarget, getExportFilenameFromResponse(response) || defaultFilename);
            } catch (error) {
                if (error.name === 'AbortError') {
                    showNotification('已取消保存操作', 'info');
                    return;
                }
                showNotification(`导出失败: ${error.message || error}`, 'error');
            }
        }

        async function prepareExcelSaveTarget(defaultFilename) {
            if (window.showSaveFilePicker && window.isSecureContext) {
                try {
                    const fileHandle = await window.showSaveFilePicker({
                        suggestedName: defaultFilename,
                        types: [{
                            description: 'Excel 工作簿',
                            accept: {
                                'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': ['.xlsx']
                            }
                        }]
                    });
                    return {type: 'fileHandle', fileHandle};
                } catch (error) {
                    if (error.name === 'AbortError') {
                        throw error;
                    }
                    console.warn('文件保存窗口不可用，回退到浏览器下载:', error);
                }
            }

            const userFilename = prompt('请输入导出的 Excel 文件名:', defaultFilename);
            if (userFilename === null) {
                const abortError = new Error('用户取消了保存操作');
                abortError.name = 'AbortError';
                throw abortError;
            }

            return {type: 'download', filename: ensureExcelExtension(userFilename.trim() || defaultFilename)};
        }

        async function prepareZipSaveTarget(defaultFilename) {
            if (window.showSaveFilePicker && window.isSecureContext) {
                try {
                    const fileHandle = await window.showSaveFilePicker({
                        suggestedName: defaultFilename,
                        types: [{
                            description: 'ZIP 压缩包',
                            accept: {
                                'application/zip': ['.zip']
                            }
                        }]
                    });
                    return {type: 'fileHandle', fileHandle};
                } catch (error) {
                    if (error.name === 'AbortError') {
                        throw error;
                    }
                    console.warn('文件保存窗口不可用，回退到浏览器下载:', error);
                }
            }

            const userFilename = prompt('请输入导出的 ZIP 文件名:', defaultFilename);
            if (userFilename === null) {
                const abortError = new Error('用户取消了保存操作');
                abortError.name = 'AbortError';
                throw abortError;
            }

            return {type: 'download', filename: ensureZipExtension(userFilename.trim() || defaultFilename)};
        }

        async function saveExcelBlob(blob, saveTarget, fallbackFilename) {
            if (saveTarget?.type === 'fileHandle') {
                const writable = await saveTarget.fileHandle.createWritable();
                await writable.write(blob);
                await writable.close();
                showNotification('Excel 文件已保存', 'success');
                return;
            }

            downloadBlob(blob, saveTarget?.filename || ensureExcelExtension(fallbackFilename));
            showNotification('Excel 导出已开始下载', 'success');
        }

        async function saveZipBlob(blob, saveTarget, fallbackFilename) {
            if (saveTarget?.type === 'fileHandle') {
                const writable = await saveTarget.fileHandle.createWritable();
                await writable.write(blob);
                await writable.close();
                showNotification('按股票代码导出文件已保存', 'success');
                return;
            }

            downloadBlob(blob, saveTarget?.filename || ensureZipExtension(fallbackFilename));
            showNotification('按股票代码导出已开始下载', 'success');
        }

        function downloadBlob(blob, filename) {
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = filename;
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            URL.revokeObjectURL(url);
        }

        function ensureExcelExtension(filename) {
            const safeName = String(filename || 'export.xlsx').trim() || 'export.xlsx';
            return safeName.toLowerCase().endsWith('.xlsx') ? safeName : `${safeName}.xlsx`;
        }

        function ensureZipExtension(filename) {
            const safeName = String(filename || 'export.zip').trim() || 'export.zip';
            return safeName.toLowerCase().endsWith('.zip') ? safeName : `${safeName}.zip`;
        }

        function getExportFilenameFromResponse(response) {
            const disposition = response.headers.get('Content-Disposition') || '';
            const utf8Match = disposition.match(/filename\*=UTF-8''([^;]+)/i);
            if (utf8Match) {
                return decodeURIComponent(utf8Match[1]);
            }
            const asciiMatch = disposition.match(/filename="?([^";]+)"?/i);
            return asciiMatch ? asciiMatch[1] : '';
        }

        // 更新结果统计
        function updateResultsStatistics() {
            let successCount;
            let failedCount;
            let totalCount;

            if (typeof resultsTotalSuccess === 'number' && typeof resultsTotalFailed === 'number') {
                successCount = resultsTotalSuccess;
                failedCount = resultsTotalFailed;
                totalCount = resultsTotalCount || (resultsTotalSuccess + resultsTotalFailed);
            } else {
                successCount = groupedResults.filter(result => result.success).length;
                failedCount = groupedResults.filter(result => !result.success).length;
                totalCount = groupedResults.length;
            }
            const successRate = totalCount > 0 ? Math.round((successCount / totalCount) * 100) : 0;

            document.getElementById('success-count').textContent = successCount;
            document.getElementById('failed-count').textContent = failedCount;
            document.getElementById('success-progress').style.width = successRate + '%';
        }

        // 显示单条结果详情（指定分组和模型索引）
        function showResultDetail(groupIndex, modelIndex) {
            if (!Array.isArray(groupedResults) || groupIndex < 0 || groupIndex >= groupedResults.length) {
                return;
            }

            const group = groupedResults[groupIndex];
            const models = group.models || [];
            if (modelIndex < 0 || modelIndex >= models.length) {
                return;
            }

            const result = models[modelIndex];
            const modalTitle = document.getElementById('resultDetailModalLabel');
            const metaEl = document.getElementById('result-detail-meta');
            const tbody = document.getElementById('result-detail-body');

            if (!modalTitle || !metaEl || !tbody) {
                return;
            }

            if (result.modelTitle && result.modelTitle.length > 0) {
                modalTitle.textContent = `${result.modelTitle}`;
            } else {
                modalTitle.textContent = `${result.modelKey || ''}`;
            }

            metaEl.textContent = `股票代码：${group.stockCode || '-'} · K线区间：${group.klineRange || '-'} · 步骤 ${group.stepIndex + 1} · A1：${group.a1 != null ? group.a1 : '-'} · B1：${group.b1 != null ? group.b1 : '-'} · 执行时间：${formatTime(group.timestamp) || '-'}`;

            const metrics = result.rawMetrics || {};
            const detailMetrics = Biz.taskPolling.getDetailMetricSource(metrics);
            const hasFlatResult = !!Biz.taskPolling.getFlatResult(metrics);

            // 专门处理 start_return_xpl 和 index_return_xpl，两者为字典，显示为卡片
            const startReturn = hasFlatResult ? null : (metrics.start_return_xpl || null);
            const indexReturn = hasFlatResult ? null : (metrics.index_return_xpl || null);

            const cards = [];

            if (startReturn) {
                cards.push(`
                <div class="col-md-6 mb-2">
                    <div class="card border-secondary">
                        <div class="card-header py-1 px-2 small fw-semibold">模型收益分析</div>
                        <div class="card-body py-2 px-2 small">
                            ${renderStatLine('起始日期', startReturn.start_date)}
                            ${renderStatLine('结束日期', startReturn.end_date)}
                            ${renderStatLine('月份数', startReturn.month_count)}
                            ${renderStatLine('平均月收益', formatMetricRawValue(startReturn.avg_monthly_return, 6))}
                            ${renderStatLine('月度波动率', formatMetricRawValue(startReturn.monthly_std_dev, 6))}
                            ${renderStatLine('年化波动率', formatMetricRawValue(startReturn.annual_std_dev, 6))}
                            ${renderStatLine('夏普率', formatMetricRawValue(startReturn.sharpe_ratio, 6))}
                        </div>
                    </div>
                </div>
            `);
            }

            if (indexReturn) {
                cards.push(`
                <div class="col-md-6 mb-2">
                    <div class="card border-secondary">
                        <div class="card-header py-1 px-2 small fw-semibold">指数收益分析</div>
                        <div class="card-body py-2 px-2 small">
                            ${renderStatLine('起始日期', indexReturn.start_date)}
                            ${renderStatLine('结束日期', indexReturn.end_date)}
                            ${renderStatLine('月份数', indexReturn.month_count)}
                            ${renderStatLine('平均月收益', formatMetricRawValue(indexReturn.avg_monthly_return, 6))}
                            ${renderStatLine('月度波动率', formatMetricRawValue(indexReturn.monthly_std_dev, 6))}
                            ${renderStatLine('年化波动率', formatMetricRawValue(indexReturn.annual_std_dev, 6))}
                            ${renderStatLine('夏普率', formatMetricRawValue(indexReturn.sharpe_ratio, 6))}
                        </div>
                    </div>
                </div>
            `);
            }

            // 剩余字段进入通用两列表格（剔除字典字段），并按排序规则排
            const metricKeys = Object.keys(detailMetrics).filter(Biz.taskPolling.shouldShowDetailMetric);
            const keys = sortMetricKeys(metricKeys);
            const rows = [];

            for (let i = 0; i < keys.length; i += 2) {
                const k1 = keys[i];
                const k2 = keys[i + 1];

                const v1 = detailMetrics[k1];
                const v2 = k2 != null ? detailMetrics[k2] : undefined;

                const display1 = formatMetricDisplayValue(v1, k1);
                const display2 = k2 != null ? formatMetricDisplayValue(v2, k2) : '<span class="text-muted small">-</span>';

                rows.push(`
                <tr>
                    <td class="small fw-semibold">${getMetricDisplayLabel(k1)}</td>
                    <td>${display1}</td>
                    <td class="small fw-semibold">${k2 != null ? getMetricDisplayLabel(k2) : ''}</td>
                    <td>${k2 != null ? display2 : ''}</td>
                </tr>
            `);
            }

            // 先渲染统计卡片，再渲染表格行
            const cardsHtml = cards.length > 0
                    ? `<tr><td colspan="4" class="p-0"><div class="row g-2 m-0">${cards.join('')}</div></td></tr>`
                    : '';

            if (rows.length === 0 && !cardsHtml) {
                tbody.innerHTML = '<tr><td colspan="4" class="text-muted text-center small">无详细指标</td></tr>';
            } else {
                tbody.innerHTML = cardsHtml + rows.join('');
            }

            if (typeof bootstrap !== 'undefined') {
                const modalEl = document.getElementById('resultDetailModal');
                const modal = bootstrap.Modal.getOrCreateInstance(modalEl);
                modal.show();
            }
        }

        // 在统计卡片中渲染一行 label + value
        function renderStatLine(label, value) {
            const safeLabel = escapeHtml(String(label));
            let safeValue;

            if (value == null || value === '') {
                safeValue = '<span class="text-muted">-</span>';
            } else if (typeof value === 'number') {
                safeValue = formatMetricRawValue(value, 6);
            } else {
                safeValue = escapeHtml(String(value));
            }

            return `
            <div class="d-flex justify-content-between mb-1">
                <span class="text-muted me-2">${safeLabel}</span>
                <span class="text-end">${safeValue}</span>
            </div>
        `;
        }

        // HTML 转义
        function escapeHtml(str) {
            return str
                    .replace(/&/g, '&amp;')
                    .replace(/</g, '&lt;')
                    .replace(/>/g, '&gt;')
                    .replace(/"/g, '&quot;')
                    .replace(/'/g, '&#39;');
        }

        // C7 汇总指标位于 D8-D26。
        const metricDisplayNameMap = {
            D8: 'Return%',
            D9: 'Annualized',
            D10: 'Max DD%',
            D11: 'Index Return',
            D12: 'Annualized',
            D13: 'Index max dd',
            D14: 'Fee total',
            D15: 'Fee annualized',
            D16: '年换手率',
            D17: 'return beats',
            D18: 'ddBeats',
            D19: 'max(1y beats%)',
            D20: 'min(1y beats%)',
            D21: '最大理论杠杆率',
            D22: '平均理论杠杆率',
            D23: '单位理论杠杆率收益',
            D24: '最大实际杠杆率',
            D25: '平均实际杠杆率',
            D26: '单位实际杠杆率收益',
            annualized_return_diff: '年化超额收益',
            avg_monthly_excess_returns: '平均月超额',
            excess_drawdown_winning_rate: '超额回撤胜率',
            excess_maximum_number_of_backtest_repair_days: '超额最大修复天数',
            excess_sortino: '超额索提诺',
            excess_sharpe: '超额夏普',
            index_annual_std_dev: '指数年化波动率',
            index_annualized_return: '指数年化收益',
            index_avg_monthly_return: '指数平均月收益率',
            index_avg_monthly_return_common: '指数平均月收益率',
            index_kama_ratio: '指数卡玛比率',
            index_monthly_return_volatility: '指数月收益率波动率',
            index_monthly_std_dev: '指数月度标准差',
            index_profit_annual: '指数盈利年份百分比',
            index_profit_monthly_percentage: '指数月盈利百分比',
            index_sharpe_ratio: '指数夏普比率',
            index_sortino_ratio: '指数索提诺比率',
            max_drawdown: '年最大超额回撤',
            monthly_excess_return_percentage_last_return: '月超额收益胜率',
            monthly_excess_volatility: '月超额波动率',
            outperform_year: '跑赢年份(百分比)',
            start_annual_std_dev: '模型年化波动率',
            start_annualized_return: '模型年化收益',
            start_avg_monthly_return: '模型平均月收益率',
            start_avg_monthly_return_common: '模型平均月收益率',
            start_drawdown: '年最大回撤',
            start_kama_ratio: '模型卡玛比率',
            start_maximum_number_of_backtest_repair_days: '最大修复天数',
            start_monthly_return_volatility: '模型月收益率波动率',
            start_monthly_std_dev: '模型月度标准差',
            start_profit_annual: '模型盈利年份百分比',
            start_profit_monthly_percentage: '模型月盈利百分比',
            start_sharpe_ratio: '模型夏普比率',
            start_sortino_ratio: '模型索提诺比率'
        };

        function getMetricDisplayLabel(key) {
            const rawKey = String(key);
            const mapped = metricDisplayNameMap[rawKey];
            return escapeHtml(mapped || rawKey);
        }

        // 指标 key 排序：D* 优先，其次按首字母分组和数字顺序
        function sortMetricKeys(keys) {
            return keys.slice().sort((a, b) => {
                const pa = parseMetricKey(a);
                const pb = parseMetricKey(b);

                // 先把以 D 开头的放在最前面
                const aIsD = pa.prefix === 'D';
                const bIsD = pb.prefix === 'D';
                if (aIsD && !bIsD) return -1;
                if (!aIsD && bIsD) return 1;

                // 其余按前缀再按数字
                if (pa.prefix !== pb.prefix) {
                    return pa.prefix.localeCompare(pb.prefix);
                }
                if (pa.num !== null && pb.num !== null) {
                    return pa.num - pb.num;
                }
                return a.localeCompare(b);
            });
        }

        function parseMetricKey(key) {
            const m = String(key).match(/^([A-Za-z_]+)(\d+)?$/);
            if (m) {
                return {prefix: m[1], num: m[2] != null ? parseInt(m[2], 10) : null};
            }
            return {prefix: String(key), num: null};
        }

        function formatMetricRawValue(value, digits) {
            if (value == null || value === '') {
                return null;
            }

            const numericValue = Number(value);
            if (Number.isFinite(numericValue)) {
                return typeof digits === 'number' ? numericValue.toFixed(digits) : String(numericValue);
            }
            return value;
        }

        const c7RawPercentMetricKeys = new Set(['D10', 'D15', 'D18', 'D19']);
        const c7LeveragePercentMetricKeys = new Set(['D22', 'D24', 'D25']);

        function normalizeLegacyC7MetricValue(value, key) {
            const metricKey = String(key || '');
            if (value == null || value === '') {
                return value;
            }

            const text = String(value).trim();
            if (c7RawPercentMetricKeys.has(metricKey) && !text.endsWith('%')) {
                const numericValue = Number(text.replace(/,/g, ''));
                return Number.isFinite(numericValue) ? `${(numericValue * 100).toFixed(2)}%` : value;
            }
            if (c7LeveragePercentMetricKeys.has(metricKey) && text.endsWith('%')) {
                const numericValue = Number(text.slice(0, -1));
                return Number.isFinite(numericValue) ? numericValue / 100 : value;
            }
            return value;
        }

        function formatMetricText(value, digits, key) {
            const formatted = formatMetricRawValue(normalizeLegacyC7MetricValue(value, key), digits);
            if (formatted == null) {
                return '-';
            }
            return String(formatted);
        }

        function formatMetricDisplayValue(value, key) {
            if (value == null) {
                return '<span class="text-muted small">-</span>';
            }
            if (Array.isArray(value)) {
                return `<pre class="mb-0 small text-muted">${escapeHtml(JSON.stringify(value, null, 2))}</pre>`;
            }
            if (typeof value === 'object') {
                const rows = sortMetricKeys(Object.keys(value).filter(Biz.taskPolling.shouldShowDetailMetric))
                    .map(key => `
                        <div class="d-flex justify-content-between gap-2 border-bottom py-1">
                            <span class="text-muted">${getMetricDisplayLabel(key)}</span>
                            <span class="text-end">${formatMetricDisplayValue(value[key], key)}</span>
                        </div>
                    `)
                    .join('');
                return rows ? `<div class="small">${rows}</div>` : '<span class="text-muted small">-</span>';
            }
            return escapeHtml(formatMetricText(value, 6, key));
        }

        // 取消任务
        function cancelTask() {
            if (confirm('确定要取消这个任务吗？')) {
                Api.endpoints.task.cancel(currentTaskId).then(function (data) {
                    showNotification('任务已取消', 'success');
                    loadTaskDetail(); // 刷新任务详情
                }).catch(function (err) {
                    showNotification('取消任务失败: ' + (err && err.message ? err.message : '未知错误'), 'error');
                });
            }
        }

        // 自动刷新相关变量（已在全局变量中声明）

        // 启动自动刷新
        function startAutoRefresh() {
            if (refreshInterval) {
                clearInterval(refreshInterval);
            }

            console.log(`启动自动刷新，每${Biz.taskPolling.getFrequencyText(currentRefreshFrequency)}刷新一次`);
            refreshInterval = setInterval(function () {
                console.log('自动刷新任务详情和日志...');
                loadTaskDetail(); // 这会重新加载所有信息，包括日志
            }, currentRefreshFrequency);
        }

        // 停止自动刷新
        function stopAutoRefresh() {
            if (refreshInterval) {
                console.log('停止自动刷新');
                clearInterval(refreshInterval);
                refreshInterval = null;
            }
        }

        // 页面卸载时清理定时器
        window.addEventListener('beforeunload', function () {
            stopAutoRefresh();
        });

        // 绑定取消任务按钮事件
        document.addEventListener('click', function (e) {
            if (e.target.id === 'cancel-task-btn') {
                cancelTask();
            }
        });

        // 辅助函数
        function formatDuration(seconds) {
            if (seconds < 60) {
                return `${seconds}秒`;
            } else if (seconds < 3600) {
                const minutes = Math.floor(seconds / 60);
                const remainingSeconds = seconds % 60;
                return `${minutes}分${remainingSeconds}秒`;
            } else {
                const hours = Math.floor(seconds / 3600);
                const minutes = Math.floor((seconds % 3600) / 60);
                return `${hours}小时${minutes}分钟`;
            }
        }

        function getProgressBarClass(status) {
            switch (status) {
                case 'completed':
                    return 'bg-success';
                case 'error':
                    return 'bg-danger';
                case 'running':
                    return 'bg-primary';
                default:
                    return 'bg-secondary';
            }
        }

        // 检查任务状态
        function checkTaskStatus() {
            const btn = document.getElementById('check-status-btn');
            const icon = btn.querySelector('i');

            // 添加旋转动画
            icon.style.animation = 'spin 1s linear infinite';
            btn.disabled = true;

            Api.endpoints.task.statusCheck(currentTaskId).then(function (data) {
                icon.style.animation = '';
                btn.disabled = false;

                if (data && data.status_check) {
                    const statusCheck = data.status_check;
                    let message = `状态检查结果:\n`;
                    message += `数据库状态: ${statusCheck.db_status}\n`;
                    message += `内存运行状态: ${statusCheck.memory_running ? '运行中' : '未运行'}\n`;
                    message += `当前步骤: ${statusCheck.current_step}/${statusCheck.total_steps}\n`;

                    if (statusCheck.latest_log_time) {
                        message += `最新日志时间: ${formatTime(statusCheck.latest_log_time)}\n`;
                    }

                    if (statusCheck.can_restart) {
                        message += `\n⚠️ 检测到问题: ${statusCheck.restart_reason}\n`;
                        message += `建议重启任务`;

                        if (confirm(message + '\n\n是否立即重启任务？')) {
                            restartTask(true);
                        }
                    } else {
                        message += `\n✅ 任务状态正常`;
                        showNotification(message, 'info');
                    }
                } else {
                showNotification('检查任务状态失败: 未知错误', 'error');
                }
            }).catch(function (err) {
                icon.style.animation = '';
                btn.disabled = false;
                showNotification('检查任务状态失败: ' + (err && err.message ? err.message : '未知错误'), 'error');
            });
        }

        // 重启任务
        function restartTask(resumeFromCheckpoint) {
            const action = resumeFromCheckpoint ? '从断点重启' : '从头重启';

            if (!confirm(`确定要${action}任务吗？`)) {
                return;
            }

            const requestData = {
                resume_from_checkpoint: resumeFromCheckpoint
            };

            Api.endpoints.task.restart(currentTaskId, requestData).then(function (data) {
                showNotification(`任务${action}成功`, 'success');
                // 刷新任务详情
                loadTaskDetail();
            }).catch(function (err) {
                // 处理错误情况 - err.message 即原信封 message
                const errorMessage = (err && err.message) ? err.message : '未知错误';
                showNotification(`${action}失败: ${errorMessage}`, 'error');
            });
        }

        // 跳转到创建重启任务页面（c7 模式）
        function goToCreateRestartTask() {
            window.location.href = `/google-sheet/create?version=${CURRENT_VERSION}&restart_task_id=${encodeURIComponent(currentTaskId || '')}`;
        }

        // 创建新的重启任务
        function createRestartTask() {
            if (!confirm('确定要创建新的重启任务吗？这将基于当前任务的配置创建一个新任务。')) {
                return;
            }

            Api.endpoints.task.createRestart(currentTaskId, {}).then(function (data) {
                showNotification(`新重启任务创建成功`, 'success');

                // 询问是否跳转到新任务
                if (confirm('是否跳转到新任务的详情页面？')) {
                    window.location.href = `/google-sheet/detail?task_id=${data.new_task_id}&version=${CURRENT_VERSION}`;
                }
            }).catch(function (err) {
                const errorMessage = (err && err.message) ? err.message : '未知错误';
                showNotification(`创建重启任务失败: ${errorMessage}`, 'error');
            });
        }

        // 保存任务配置
        function saveTaskConfig() {
            try {
                // 收集基本信息
                const name = document.getElementById('edit-task-name').value.trim();
                const description = document.getElementById('edit-task-description').value.trim();

                if (!name) {
                    showNotification('请输入任务名称', 'error');
                    return;
                }

                // 主参数：从 chips 收集 parameters[0]
                const params0 = Biz.configEdit.collectEditProductCodesFromChips();
                if (!params0 || params0.length === 0) {
                    showNotification('请至少添加一个产品代码（parameters[0]）', 'error');
                    return;
                }

                // sheets：从多行输入收集
                const list = document.getElementById('edit-sheets-list');
                const sheets = [];
                if (list) {
                    list.querySelectorAll('.edit-sheet-row').forEach(row => {
                        const sidEl = row.querySelector('.edit-sheet-spreadsheet-id');
                        const titleEl = row.querySelector('.edit-sheet-title');
                        const nameEl = row.querySelector('.edit-sheet-name');
                        const sid = sidEl ? sidEl.value.trim() : '';
                        const sname = nameEl ? nameEl.value.trim() : '';
                        const title = titleEl ? titleEl.value.trim() : '';
                        if (sid || sname || title) {
                            const item = {
                                spreadsheet_id: sid || null,
                                sheet_name: sname || null
                            };
                            if (title) item.title = title;
                            sheets.push(item);
                        }
                    });
                }

                // 其它参数
                const countMode = document.getElementById('edit-count-mode').value || 'n_plus_1';
                const fullModeEl = document.getElementById('edit-date-range-full');
                const recentModeEl = document.getElementById('edit-date-range-recent');
                const dateRangeModeList = [];
                if (fullModeEl && fullModeEl.checked) {
                    dateRangeModeList.push('full');
                }
                if (recentModeEl && recentModeEl.checked) {
                    dateRangeModeList.push('recent');
                }
                if (dateRangeModeList.length === 0) {
                    dateRangeModeList.push('full');
                    if (fullModeEl) {
                        fullModeEl.checked = true;
                    }
                }
                const startDate = document.getElementById('edit-start-date').value || null;
                const endDate = document.getElementById('edit-end-date').value || null;
                const marketType = document.getElementById('edit-market-type').value.trim() || null;

                const tokenType = document.getElementById('edit-token-type').value;
                const tokenFile = document.getElementById('edit-token-file').value.trim();
                const tokenJson = document.getElementById('edit-token-json').value.trim();
                const proxyUrl = document.getElementById('edit-proxy-url').value.trim();

                if (tokenType === 'file' && !tokenFile) {
                    showNotification('请输入 Token 文件路径', 'error');
                    return;
                }
                if (tokenType === 'json' && !tokenJson) {
                    showNotification('请输入 Token JSON 字符串', 'error');
                    return;
                }

                const config = {
                    count_mode: countMode,
                    date_range_mode: dateRangeModeList,
                    start_date: startDate,
                    end_date: endDate,
                    market_type: marketType,
                    parameters: [params0],
                    sheets: sheets,
                    proxy_url: proxyUrl || null,
                    token_type: tokenType,
                    token_file: tokenFile,
                    token_json: tokenJson
                };

                const requestData = {
                    name: name,
                    description: description,
                    config: config
                };

                Api.endpoints.task.updateConfig(currentTaskId, requestData).then(function (data) {
                    showNotification('配置更新成功', 'success');

                    // 关闭模态框
                    if (editConfigModal) {
                        editConfigModal.hide();
                    }

                    // 刷新任务详情
                    loadTaskDetail();
                }).catch(function (err) {
                    const errorMessage = (err && err.message) ? err.message : '未知错误';
                    showNotification(`配置更新失败: ${errorMessage}`, 'error');
                });
            } catch (e) {
                showNotification(`保存配置时出错: ${e.message}`, 'error');
                console.error('保存配置错误:', e);
            }
        }
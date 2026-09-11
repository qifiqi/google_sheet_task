// Weight Combination Analysis Page with Tabulator
(function() {
    'use strict';

    let table = null;
    let allData = [];
    let isAnalyzing = false;
    let abortController = null;

    // 当前筛选值缓存：field -> { min, max }
    // 弹窗打开时回填用户输入的值；按钮激活态也由此判断
    const headerFilterValues = {};

    // 表头筛选控件：field -> { btn: 漏斗按钮, success: Tabulator 应用筛选回调 }
    // 编辑器在 clearHeaderFilter 后会被 Tabulator 重建，此表随编辑器初始化刷新
    const filterControls = {};

    // 筛选弹窗（懒创建，挂在 body 下 fixed 定位）
    let filterPopup = null;
    let filterPopupCtx = null; // { field, title, btn }

    function hasActiveRangeFilter(field) {
        const v = headerFilterValues[field];
        return !!(v && ((v.min !== null && v.min !== undefined) || (v.max !== null && v.max !== undefined)));
    }

    function setFilterButtonIcon(btn, active) {
        btn.classList.toggle('is-active', active);
        btn.innerHTML = `<i class="bi bi-funnel${active ? '-fill' : ''}"></i>`;
    }

    function refreshFilterButton(field) {
        const ctrl = filterControls[field];
        if (ctrl && ctrl.btn) setFilterButtonIcon(ctrl.btn, hasActiveRangeFilter(field));
    }

    // ============ 范围筛选：漏斗按钮编辑器（点击弹出筛选弹窗） ============
    function filterButtonEditor(column, onRendered, success, cancel, editorParams) {
        // 注意：Tabulator 表头筛选编辑器的第一个参数不是完整 Cell/Column 组件，
        // 只有 getField/getColumn/getElement 等方法，列标题须经 getColumn().getDefinition() 获取
        const field = column.getField();
        const colComp = column.getColumn ? column.getColumn() : null;
        const title = (colComp && colComp.getDefinition ? colComp.getDefinition().title : null) || field;

        const btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'wc-filter-btn';
        btn.title = '范围筛选';
        btn.setAttribute('aria-label', `范围筛选：${title}`);
        setFilterButtonIcon(btn, hasActiveRangeFilter(field));

        btn.addEventListener('click', function(e) {
            // 阻止冒泡到列头，避免误触发排序；stopImmediatePropagation 连同
            // Tabulator 在同一元素上附加的 focus 抢占监听一并拦下
            e.stopPropagation();
            e.preventDefault();
            e.stopImmediatePropagation();
            toggleFilterPopup(field, title, btn);
        });

        filterControls[field] = { btn: btn, success: success };
        return btn;
    }

    // ============ 范围筛选弹窗 ============
    function getPopupInputs() {
        return {
            min: filterPopup.querySelector('[data-role="min"]'),
            max: filterPopup.querySelector('[data-role="max"]')
        };
    }

    function ensureFilterPopup() {
        if (filterPopup) return filterPopup;

        filterPopup = document.createElement('div');
        filterPopup.className = 'wc-filter-popup';
        filterPopup.setAttribute('role', 'dialog');
        filterPopup.setAttribute('aria-label', '范围筛选');
        filterPopup.innerHTML = `
            <div class="wc-filter-popup__header">
                <span class="wc-filter-popup__title"></span>
                <button type="button" class="wc-filter-popup__close" aria-label="关闭"><i class="bi bi-x-lg"></i></button>
            </div>
            <div class="wc-filter-popup__body">
                <div class="wc-filter-popup__field">
                    <label for="wc-filter-min">最小值</label>
                    <input type="number" id="wc-filter-min" class="form-control form-control-sm wc-filter-popup__input" data-role="min" placeholder="不限">
                </div>
                <div class="wc-filter-popup__field">
                    <label for="wc-filter-max">最大值</label>
                    <input type="number" id="wc-filter-max" class="form-control form-control-sm wc-filter-popup__input" data-role="max" placeholder="不限">
                </div>
                <p class="wc-filter-popup__hint">最小值不能大于最大值</p>
            </div>
            <div class="wc-filter-popup__footer">
                <button type="button" class="btn btn-sm btn-outline-secondary" data-role="clear">
                    <i class="bi bi-x-circle me-1"></i>清除
                </button>
                <button type="button" class="btn btn-sm btn-primary" data-role="apply">
                    <i class="bi bi-check-lg me-1"></i>应用
                </button>
            </div>`;
        document.body.appendChild(filterPopup);

        filterPopup.querySelector('.wc-filter-popup__close').addEventListener('click', closeFilterPopup);
        filterPopup.querySelector('[data-role="clear"]').addEventListener('click', clearRangeFilter);
        filterPopup.querySelector('[data-role="apply"]').addEventListener('click', applyRangeFilter);

        const inputs = getPopupInputs();
        [inputs.min, inputs.max].forEach(function(input) {
            input.addEventListener('keydown', function(e) {
                if (e.key === 'Enter') applyRangeFilter();
                if (e.key === 'Escape') closeFilterPopup();
            });
        });

        // 点击弹窗与漏斗按钮之外的区域关闭
        document.addEventListener('mousedown', function(e) {
            if (!filterPopup.classList.contains('show')) return;
            if (filterPopup.contains(e.target)) return;
            if (filterPopupCtx && filterPopupCtx.btn.contains(e.target)) return;
            closeFilterPopup();
        });
        // 页面/表格滚动、窗口缩放时关闭，避免弹窗飘离锚点
        window.addEventListener('resize', closeFilterPopup);
        window.addEventListener('scroll', closeFilterPopup, true);

        return filterPopup;
    }

    function toggleFilterPopup(field, title, btn) {
        if (filterPopupCtx && filterPopupCtx.field === field && filterPopup.classList.contains('show')) {
            closeFilterPopup();
            return;
        }
        openFilterPopup(field, title, btn);
    }

    function openFilterPopup(field, title, btn) {
        ensureFilterPopup();
        filterPopupCtx = { field: field, title: title, btn: btn };

        filterPopup.querySelector('.wc-filter-popup__title').textContent = title;
        filterPopup.querySelector('.wc-filter-popup__hint').classList.remove('is-visible');

        const inputs = getPopupInputs();
        const v = headerFilterValues[field] || {};
        inputs.min.value = v.min !== null && v.min !== undefined ? v.min : '';
        inputs.max.value = v.max !== null && v.max !== undefined ? v.max : '';
        inputs.min.classList.remove('is-invalid');
        inputs.max.classList.remove('is-invalid');

        filterPopup.classList.add('show');
        positionFilterPopup(btn);
        // Tabulator 会在同一点击事件里把焦点抢回按钮，延迟聚焦保证输入框拿到焦点
        setTimeout(function() { inputs.min.focus(); }, 0);
    }

    function positionFilterPopup(btn) {
        const rect = btn.getBoundingClientRect();
        const pw = filterPopup.offsetWidth;
        const ph = filterPopup.offsetHeight;

        let left = rect.right - pw; // 默认右对齐到按钮
        left = Math.max(8, Math.min(left, window.innerWidth - pw - 8));

        let top = rect.bottom + 6;
        if (top + ph > window.innerHeight - 8) {
            top = rect.top - ph - 6; // 下方空间不足时弹到按钮上方
        }

        filterPopup.style.left = left + 'px';
        filterPopup.style.top = Math.max(8, top) + 'px';
    }

    function closeFilterPopup() {
        if (!filterPopup) return;
        filterPopup.classList.remove('show');
        filterPopupCtx = null;
    }

    function updateStats() {
        setStats(table.getDataCount('active'), allData.length);
    }

    function setStats(filteredCount, totalCount) {
        const filteredEl = document.getElementById('filtered-count');
        const totalEl = document.getElementById('total-count');
        if (filteredEl) filteredEl.textContent = `${filteredCount} 条显示`;
        if (totalEl) totalEl.textContent = `${totalCount} 条总计`;
    }

    // Tabulator 的 refreshData 管线分帧异步提交 activeRows，事件派发瞬间计数可能还是旧值；
    // 从下一帧起持续刷新统计，直到计数稳定
    function refreshStatsDeferred() {
        let last = null;
        let ticks = 0;
        const tick = function() {
            const active = table.getDataCount('active');
            if (active !== last) {
                last = active;
                setStats(active, allData.length);
            }
            if (++ticks < 15) requestAnimationFrame(tick);
        };
        requestAnimationFrame(tick);
    }

    function applyRangeFilter() {
        if (!filterPopupCtx) return;
        const field = filterPopupCtx.field;
        const inputs = getPopupInputs();
        const minRaw = inputs.min.value.trim();
        const maxRaw = inputs.max.value.trim();
        const min = minRaw === '' ? null : parseFloat(minRaw);
        const max = maxRaw === '' ? null : parseFloat(maxRaw);

        if (min !== null && max !== null && min > max) {
            inputs.min.classList.add('is-invalid');
            inputs.max.classList.add('is-invalid');
            filterPopup.querySelector('.wc-filter-popup__hint').classList.add('is-visible');
            return;
        }

        headerFilterValues[field] = { min: min, max: max };
        const ctrl = filterControls[field];
        if (ctrl) ctrl.success(headerFilterValues[field]);
        refreshFilterButton(field);
        refreshStatsDeferred();
        closeFilterPopup();
    }

    function clearRangeFilter() {
        if (!filterPopupCtx) return;
        const field = filterPopupCtx.field;
        const inputs = getPopupInputs();
        inputs.min.value = '';
        inputs.max.value = '';
        inputs.min.classList.remove('is-invalid');
        inputs.max.classList.remove('is-invalid');

        headerFilterValues[field] = { min: null, max: null };
        const ctrl = filterControls[field];
        if (ctrl) ctrl.success({ min: null, max: null });
        refreshFilterButton(field);
        refreshStatsDeferred();
        closeFilterPopup();
    }

    // ============ 自定义范围筛选函数 ============
    function minMaxFilterFunction(headerValue, rowValue, rowData, filterParams) {
        if (!headerValue || (headerValue.min === null && headerValue.max === null)) {
            return true;
        }

        // 空值放行
        if (rowValue === null || rowValue === undefined || rowValue === '') {
            return true;
        }

        const value = parseFloat(rowValue);
        if (isNaN(value)) {
            return true;
        }

        if (headerValue.min !== null && headerValue.min !== undefined && value < headerValue.min) {
            return false;
        }

        if (headerValue.max !== null && headerValue.max !== undefined && value > headerValue.max) {
            return false;
        }

        return true;
    }

    // ============ 列工厂 ============
    function numberFormatter(digits, suffix = '') {
        return function(cell) {
            const val = cell.getValue();
            return val != null && val !== '' ? Number(val).toFixed(digits) + suffix : '-';
        };
    }

    function rangeColumn(title, field, opts = {}) {
        const digits = opts.digits ?? 2;
        const suffix = opts.suffix || '';
        const width = opts.width || 160;

        return {
            title: title,
            field: field,
            width: width,
            sorter: 'number',
            headerFilter: filterButtonEditor,
            headerFilterFunc: minMaxFilterFunction,
            headerTooltip: true,
            formatter: numberFormatter(digits, suffix)
        };
    }

    // DOM elements
    const form = document.getElementById('weight-combination-form');
    const taskIdInput = document.getElementById('task-id');
    const stepInput = document.getElementById('step');
    const maxWeightInput = document.getElementById('max-weight');
    const minWeightInput = document.getElementById('min-weight');
    const singleCapInput = document.getElementById('single-cap');
    const btnAnalyze = document.getElementById('btn-analyze');
    const btnCancel = document.getElementById('btn-cancel');
    const progressCard = document.getElementById('progress-card');
    const progressBar = document.getElementById('progress-bar');
    const progressInfo = document.getElementById('progress-info');
    const resultsCard = document.getElementById('results-card');

    // Initialize
    document.addEventListener('DOMContentLoaded', function() {
        setupEventListeners();
        initializeTable();
        prefillTaskIdFromUrl();
    });

    function setupEventListeners() {
        form.addEventListener('submit', handleAnalyze);
        btnCancel.addEventListener('click', handleCancel);
    }

    function prefillTaskIdFromUrl() {
        const params = new URLSearchParams(window.location.search);
        const taskId = params.get('task_id');
        if (taskId) {
            taskIdInput.value = taskId;
        }
    }

    /**
     * 初始化 Tabulator 表格
     */
    function initializeTable() {
        table = new Tabulator('#results-table', {
            height: '600px',
            layout: 'fitColumns',
            placeholder: '暂无数据，请先进行分析',
            pagination: false,
            virtualDom: true,
            virtualDomBuffer: 300,

            columns: [
                {
                    title: '#',
                    formatter: 'rownum',
                    width: 60,
                    hozAlign: 'center',
                    headerSort: false
                },
                {
                    title: '股票组合',
                    field: 'stocks_display',
                    minWidth: 300,
                    headerSort: false,
                    formatter: 'textarea',
                    tooltip: true,
                    variableHeight: false
                },
                rangeColumn('年化收益率(指数)', 'index_rate_disp', { width: 185, digits: 2, suffix: '%' }),
                rangeColumn('年化收益率(策略)', 'start_rate_disp', { width: 185, digits: 2, suffix: '%' }),
                rangeColumn('最大回撤(指数)', 'index_dd_disp', { width: 180, digits: 2, suffix: '%' }),
                rangeColumn('最大回撤(策略)', 'start_dd_disp', { width: 180, digits: 2, suffix: '%' }),
                rangeColumn('权重和(%)', 'weight_sum', { width: 150, digits: 0, suffix: '%' })
            ],

            initialSort: [],
            responsiveLayout: 'collapse',

            renderComplete: function() {
                updateStats();
            }
        });

        // ✅ 不再设置默认筛选，加载后显示全部数据

        table.on('dataFiltered', function() {
            updateStats();
        });

        document.getElementById('export-csv-btn').onclick = exportCSV;
        document.getElementById('clear-filter-btn').onclick = function() {
            closeFilterPopup();
            Object.keys(headerFilterValues).forEach(k => delete headerFilterValues[k]);
            table.clearHeaderFilter();
            // clearHeaderFilter 会重建编辑器，这里兜底刷新一遍按钮激活态
            Object.keys(filterControls).forEach(refreshFilterButton);
            refreshStatsDeferred();
        };
    }

    /**
     * 处理分析表单提交
     */
    async function handleAnalyze(e) {
        e.preventDefault();
        if (isAnalyzing) return;

        const taskId = taskIdInput.value.trim();
        if (!taskId) {
            alert('请输入任务 ID');
            return;
        }

        const step = parseInt(stepInput.value);
        const maxWeight = parseInt(maxWeightInput.value);
        const minWeight = parseInt(minWeightInput.value);
        const singleCap = parseInt(singleCapInput.value);

        if (step < 1 || step > 100) { alert('权重步长必须在 1-100 之间'); return; }
        if (100 % step !== 0) { alert('权重步长必须能整除 100'); return; }
        if (maxWeight < 1 || maxWeight > 100) { alert('组合总权重上限必须在 1-100 之间'); return; }
        if (minWeight < 0 || minWeight > 100) { alert('组合总权重下限必须在 0-100 之间'); return; }
        if (minWeight > maxWeight) { alert('组合总权重下限不能大于上限'); return; }
        if (singleCap < 1 || singleCap > 100) { alert('单只股票权重上限必须在 1-100 之间'); return; }
        if (maxWeight % step !== 0 || minWeight % step !== 0 || singleCap % step !== 0) {
            alert('所有权重参数必须是步长的整数倍');
            return;
        }
        if (singleCap < step) { alert('单只股票权重上限不能小于步长'); return; }

        startAnalysis({
            task_id: taskId,
            step: step,
            max_weight: maxWeight,
            min_weight: minWeight,
            single_cap: singleCap
        });
    }

    /**
     * 开始分析
     */
    async function startAnalysis(payload) {
        isAnalyzing = true;
        allData = [];

        btnAnalyze.disabled = true;
        btnCancel.style.display = 'inline-block';
        progressCard.style.display = 'block';
        resultsCard.style.display = 'none';

        // 清空数据 + 筛选缓存
        closeFilterPopup();
        Object.keys(headerFilterValues).forEach(k => delete headerFilterValues[k]);
        table.clearData();
        table.clearHeaderFilter();

        updateProgress(0, '正在发送请求...');

        try {
            abortController = new AbortController();

            const response = await fetch('/performance_analysis/v1/weight_combination', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload),
                signal: abortController.signal
            });

            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(errorData.message || `请求失败: ${response.status}`);
            }

            const reader = response.body.getReader();
            const decoder = new TextDecoder();
            let buffer = '';
            let processedCount = 0;
            let renderedCount = 0;

            updateProgress(0, '正在接收数据...');

            while (true) {
                const { done, value } = await reader.read();
                if (done) break;

                buffer += decoder.decode(value, { stream: true });

                const lines = buffer.split('\n');
                buffer = lines.pop();

                for (const line of lines) {
                    if (line.trim()) {
                        try {
                            const data = JSON.parse(line);
                            if (data.error) throw new Error(data.message || '服务端返回错误');

                            const transformed = transformData(data);
                            allData.push(transformed);
                            processedCount++;

                            if (processedCount % 20 === 0) {
                                updateProgress(null, `已接收 ${processedCount} 条组合...`);

                                const newRows = allData.slice(renderedCount);
                                if (renderedCount === 0) {
                                    table.setData(allData);
                                    resultsCard.style.display = 'block';
                                } else if (newRows.length) {
                                    table.addData(newRows);
                                }
                                renderedCount = allData.length;
                            }
                        } catch (err) {
                            console.error('解析 JSON 失败:', line, err);
                            if (err.message.includes('服务端返回错误')) throw err;
                        }
                    }
                }
            }

            if (buffer.trim()) {
                try {
                    const data = JSON.parse(buffer);
                    if (data.error) throw new Error(data.message || '服务端返回错误');
                    const transformed = transformData(data);
                    allData.push(transformed);
                    processedCount++;
                } catch (err) {
                    console.error('解析最后的 JSON 失败:', buffer, err);
                    if (err.message.includes('服务端返回错误')) throw err;
                }
            }

            // 最终补差量
            const finalNewRows = allData.slice(renderedCount);
            if (finalNewRows.length) {
                if (renderedCount === 0) {
                    table.setData(allData);
                } else {
                    table.addData(finalNewRows);
                }
                renderedCount = allData.length;
            } else {
                table.setData(allData);
            }

            updateProgress(100, `分析完成！共生成 ${allData.length} 个组合`);
            resultsCard.style.display = 'block';

            // ✅ 只更新统计，不再应用默认筛选
            setTimeout(function() {
                updateStats();
            }, 0);

            setTimeout(() => {
                progressCard.style.display = 'none';
            }, 2000);

        } catch (error) {
            if (error.name === 'AbortError') {
                updateProgress(0, '分析已取消');
                setTimeout(() => {
                    progressCard.style.display = 'none';
                }, 1500);
            } else {
                console.error('分析失败:', error);
                alert('分析失败: ' + error.message);
                updateProgress(0, '分析失败');
            }
        } finally {
            isAnalyzing = false;
            btnAnalyze.disabled = false;
            btnCancel.style.display = 'none';
            abortController = null;
        }
    }

    /**
     * 数据转换：生成 *_disp 字段（原始值 × 100）
     */
    function transformData(item) {
        item.weight_sum = item.stocks.reduce((sum, stock) => sum + stock.ratio, 0);

        const indexRate = item.annualized_rates?.index;
        const startRate = item.annualized_rates?.start;
        const indexDd = item.year_max_drawdown?.index;
        const startDd = item.year_max_drawdown?.start;

        item.index_rate = indexRate;
        item.start_rate = startRate;
        item.index_dd = indexDd;
        item.start_dd = startDd;

        item.index_rate_disp = indexRate != null ? Number(indexRate) * 100 : null;
        item.start_rate_disp = startRate != null ? Number(startRate) * 100 : null;
        item.index_dd_disp = indexDd != null ? Number(indexDd) * 100 : null;
        item.start_dd_disp = startDd != null ? Number(startDd) * 100 : null;

        item.stocks_display = item.stocks
            .filter(s => s.ratio > 0)
            .map(s => `${s.stock_name || s.stock_code || 'N/A'} (${s.ratio}%)`)
            .join(', ');

        return item;
    }

    function handleCancel() {
        if (abortController) abortController.abort();
    }

    function updateProgress(percentage, message) {
        if (percentage !== null) {
            progressBar.style.width = percentage + '%';
            progressBar.setAttribute('aria-valuenow', percentage);
            progressBar.textContent = percentage + '%';
        }
        if (message) progressInfo.textContent = message;
    }

    function exportCSV() {
        table.download('csv', `weight_combination_${Date.now()}.csv`, {
            bom: true,
            delimiter: ','
        });
    }

})();
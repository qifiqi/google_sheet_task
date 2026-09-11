// Weight Combination Analysis Page with Tabulator
(function() {
    'use strict';

    let table = null;
    let allData = [];
    let isAnalyzing = false;
    let abortController = null;

    // 当前筛选值缓存：field -> { min, max }
    // 用于编辑器初始化时回填用户输入的值
    const headerFilterValues = {};

    // ============ 自定义范围筛选编辑器 ============
    function minMaxFilterEditor(cell, onRendered, success, cancel, editorParams) {
        const container = document.createElement("span");
        container.style.display = "flex";
        container.style.gap = "2px";
        container.style.fontSize = "12px";

        const minInput = document.createElement("input");
        minInput.setAttribute("type", "number");
        minInput.setAttribute("placeholder", "最小");
        minInput.style.padding = "2px 4px";
        minInput.style.width = "50px";
        minInput.style.fontSize = "11px";

        const maxInput = document.createElement("input");
        maxInput.setAttribute("type", "number");
        maxInput.setAttribute("placeholder", "最大");
        maxInput.style.padding = "2px 4px";
        maxInput.style.width = "50px";
        maxInput.style.fontSize = "11px";

        container.appendChild(minInput);
        container.appendChild(maxInput);

        // 只从缓存读当前筛选值，避免调 getHeaderFilterValue 触发 Tabulator 内部报错
        const field = cell.getField ? cell.getField() : null;
        const currentValue = field ? headerFilterValues[field] : null;

        if (currentValue && typeof currentValue === 'object') {
            if (currentValue.min !== null && currentValue.min !== undefined && currentValue.min !== '') {
                minInput.value = currentValue.min;
            }
            if (currentValue.max !== null && currentValue.max !== undefined && currentValue.max !== '') {
                maxInput.value = currentValue.max;
            }
        }

        function buildValues() {
            const value = {
                min: minInput.value !== "" ? parseFloat(minInput.value) : null,
                max: maxInput.value !== "" ? parseFloat(maxInput.value) : null
            };
            if (field) {
                headerFilterValues[field] = value;
            }
            success(value);
        }

        minInput.addEventListener("change", buildValues);
        minInput.addEventListener("blur", buildValues);
        maxInput.addEventListener("change", buildValues);
        maxInput.addEventListener("blur", buildValues);

        function handleEnter(e) {
            if (e.key === "Enter") {
                buildValues();
            }
        }
        minInput.addEventListener("keydown", handleEnter);
        maxInput.addEventListener("keydown", handleEnter);

        return container;
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
        const width = opts.width || 150;

        return {
            title: title,
            field: field,
            width: width,
            sorter: 'number',
            headerFilter: minMaxFilterEditor,
            headerFilterFunc: minMaxFilterFunction,
            headerFilterLiveFilter: false,
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
                rangeColumn('年化收益率(指数)', 'index_rate_disp', { width: 160, digits: 2, suffix: '%' }),
                rangeColumn('年化收益率(策略)', 'start_rate_disp', { width: 160, digits: 2, suffix: '%' }),
                rangeColumn('最大回撤(指数)', 'index_dd_disp', { width: 150, digits: 2, suffix: '%' }),
                rangeColumn('最大回撤(策略)', 'start_dd_disp', { width: 150, digits: 2, suffix: '%' }),
                rangeColumn('权重和(%)', 'weight_sum', { width: 120, digits: 0, suffix: '%' })
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
            Object.keys(headerFilterValues).forEach(k => delete headerFilterValues[k]);
            table.clearHeaderFilter();
            updateStats();
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

    function updateStats() {
        const filteredCount = table.getDataCount('active');
        const totalCount = allData.length;

        const filteredEl = document.getElementById('filtered-count');
        const totalEl = document.getElementById('total-count');

        if (filteredEl) filteredEl.textContent = `${filteredCount} 条显示`;
        if (totalEl) totalEl.textContent = `${totalCount} 条总计`;
    }

    function exportCSV() {
        table.download('csv', `weight_combination_${Date.now()}.csv`, {
            bom: true,
            delimiter: ','
        });
    }

})();
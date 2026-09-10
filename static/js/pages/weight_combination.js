// Weight Combination Analysis Page with Tabulator
(function() {
    'use strict';

    let table = null;
    let allData = [];
    let isAnalyzing = false;
    let abortController = null;

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
    });

    function setupEventListeners() {
        form.addEventListener('submit', handleAnalyze);
        btnCancel.addEventListener('click', handleCancel);
    }

    /**
     * 初始化 Tabulator 表格
     */
    function initializeTable() {
        table = new Tabulator('#results-table', {
            height: '600px',
            layout: 'fitColumns',
            placeholder: '暂无数据，请先进行分析',
            pagination: false,  // 使用虚拟滚动而非分页
            virtualDom: true,   // 启用虚拟滚动
            virtualDomBuffer: 300,  // 缓冲区大小

            // 列定义
            columns: [
                {
                    title: '#',
                    field: 'rowNum',
                    width: 60,
                    hozAlign: 'center',
                    headerSort: false,
                    formatter: function(cell) {
                        return cell.getRow().getPosition();
                    }
                },
                {
                    title: '年化收益率(指数)',
                    field: 'index_rate',
                    width: 150,
                    sorter: 'number',
                    headerFilter: 'number',
                    headerFilterPlaceholder: '筛选...',
                    headerFilterFunc: 'range',
                    formatter: function(cell) {
                        const val = cell.getValue();
                        return val != null ? val.toFixed(4) : '-';
                    }
                },
                {
                    title: '年化收益率(起始)',
                    field: 'start_rate',
                    width: 150,
                    sorter: 'number',
                    headerFilter: 'number',
                    headerFilterPlaceholder: '筛选...',
                    headerFilterFunc: 'range',
                    formatter: function(cell) {
                        const val = cell.getValue();
                        return val != null ? val.toFixed(4) : '-';
                    }
                },
                {
                    title: '最大回撤(指数)',
                    field: 'index_dd',
                    width: 140,
                    sorter: 'number',
                    headerFilter: 'number',
                    headerFilterPlaceholder: '筛选...',
                    headerFilterFunc: 'range',
                    formatter: function(cell) {
                        const val = cell.getValue();
                        return val != null ? val.toFixed(4) : '-';
                    }
                },
                {
                    title: '最大回撤(起始)',
                    field: 'start_dd',
                    width: 140,
                    sorter: 'number',
                    headerFilter: 'number',
                    headerFilterPlaceholder: '筛选...',
                    headerFilterFunc: 'range',
                    formatter: function(cell) {
                        const val = cell.getValue();
                        return val != null ? val.toFixed(4) : '-';
                    }
                },
                {
                    title: '权重和(%)',
                    field: 'weight_sum',
                    width: 110,
                    sorter: 'number',
                    headerFilter: 'number',
                    headerFilterPlaceholder: '筛选...',
                    headerFilterFunc: 'range',
                    formatter: function(cell) {
                        const val = cell.getValue();
                        return val != null ? val.toFixed(0) + '%' : '-';
                    }
                },
                {
                    title: '股票组合',
                    field: 'stocks_display',
                    minWidth: 300,
                    headerSort: false,
                    formatter: 'textarea',
                    tooltip: true
                }
            ],

            // 初始排序
            initialSort: [],

            // 响应式列
            responsiveLayout: 'collapse',

            // 深色模式适配
            renderComplete: function() {
                updateStats();
            }
        });

        // 导出按钮
        const exportBtn = document.createElement('button');
        exportBtn.className = 'btn btn-sm btn-success mt-2 ms-2';
        exportBtn.innerHTML = '<i class="bi bi-filetype-csv me-1"></i>导出 CSV';
        exportBtn.onclick = exportCSV;
        document.querySelector('#results-card .card-header').appendChild(exportBtn);

        // 清除筛选按钮
        const clearBtn = document.createElement('button');
        clearBtn.className = 'btn btn-sm btn-outline-secondary mt-2 ms-2';
        clearBtn.innerHTML = '<i class="bi bi-x-circle me-1"></i>清除筛选';
        clearBtn.onclick = () => table.clearHeaderFilter();
        document.querySelector('#results-card .card-header').appendChild(clearBtn);

        // 统计信息容器
        const statsDiv = document.createElement('div');
        statsDiv.id = 'table-stats';
        statsDiv.className = 'mt-2 small text-muted';
        statsDiv.innerHTML = '<span class="badge bg-success me-2" id="filtered-count">0 条显示</span><span class="badge bg-primary" id="total-count">0 条总计</span>';
        document.querySelector('#results-card .card-header').appendChild(statsDiv);
    }

    /**
     * 处理分析表单提交
     */
    async function handleAnalyze(e) {
        e.preventDefault();

        if (isAnalyzing) {
            return;
        }

        // 参数验证
        const taskId = taskIdInput.value.trim();
        if (!taskId) {
            alert('请输入任务 ID');
            return;
        }

        const step = parseInt(stepInput.value);
        const maxWeight = parseInt(maxWeightInput.value);
        const minWeight = parseInt(minWeightInput.value);
        const singleCap = parseInt(singleCapInput.value);

        // 基础验证
        if (step < 1 || step > 100) {
            alert('权重步长必须在 1-100 之间');
            return;
        }

        if (100 % step !== 0) {
            alert('权重步长必须能整除 100');
            return;
        }

        if (maxWeight < 1 || maxWeight > 100) {
            alert('组合总权重上限必须在 1-100 之间');
            return;
        }

        if (minWeight < 0 || minWeight > 100) {
            alert('组合总权重下限必须在 0-100 之间');
            return;
        }

        if (minWeight > maxWeight) {
            alert('组合总权重下限不能大于上限');
            return;
        }

        if (singleCap < 1 || singleCap > 100) {
            alert('单只股票权重上限必须在 1-100 之间');
            return;
        }

        if (maxWeight % step !== 0 || minWeight % step !== 0 || singleCap % step !== 0) {
            alert('所有权重参数必须是步长的整数倍');
            return;
        }

        if (singleCap < step) {
            alert('单只股票权重上限不能小于步长');
            return;
        }

        // 开始分析
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

        // UI 更新
        btnAnalyze.disabled = true;
        btnCancel.style.display = 'inline-block';
        progressCard.style.display = 'block';
        resultsCard.style.display = 'none';

        // 清空表格
        table.clearData();

        updateProgress(0, '正在发送请求...');

        try {
            abortController = new AbortController();

            const response = await fetch('/performance_analysis/v1/weight_combination', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify(payload),
                signal: abortController.signal
            });

            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(errorData.message || `请求失败: ${response.status}`);
            }

            // 流式处理
            const reader = response.body.getReader();
            const decoder = new TextDecoder();
            let buffer = '';
            let processedCount = 0;

            updateProgress(0, '正在接收数据...');

            while (true) {
                const { done, value } = await reader.read();

                if (done) break;

                buffer += decoder.decode(value, { stream: true });

                // 处理完整的 JSON 对象
                const lines = buffer.split('\n');
                buffer = lines.pop();

                for (const line of lines) {
                    if (line.trim()) {
                        try {
                            const data = JSON.parse(line);

                            // 检查错误
                            if (data.error) {
                                throw new Error(data.message || '服务端返回错误');
                            }

                            // 数据转换和扁平化
                            const transformed = transformData(data);
                            allData.push(transformed);
                            processedCount++;

                            // 批量更新表格（每 100 条）
                            if (processedCount % 100 === 0) {
                                updateProgress(null, `已接收 ${processedCount} 条组合...`);

                                // 实时更新表格
                                if (processedCount === 100) {
                                    table.setData(allData);
                                    resultsCard.style.display = 'block';
                                } else {
                                    table.addData(allData.slice(-100));
                                }
                            }
                        } catch (err) {
                            console.error('解析 JSON 失败:', line, err);
                            if (err.message.includes('服务端返回错误')) {
                                throw err;
                            }
                        }
                    }
                }
            }

            // 处理剩余数据
            if (buffer.trim()) {
                try {
                    const data = JSON.parse(buffer);
                    if (data.error) {
                        throw new Error(data.message || '服务端返回错误');
                    }
                    const transformed = transformData(data);
                    allData.push(transformed);
                    processedCount++;
                } catch (err) {
                    console.error('解析最后的 JSON 失败:', buffer, err);
                    if (err.message.includes('服务端返回错误')) {
                        throw err;
                    }
                }
            }

            // 最终更新表格
            table.setData(allData);
            updateProgress(100, `分析完成！共生成 ${allData.length} 个组合`);

            resultsCard.style.display = 'block';

        } catch (error) {
            if (error.name === 'AbortError') {
                updateProgress(0, '分析已取消');
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
     * 数据转换和扁平化
     */
    function transformData(item) {
        // 计算权重和
        item.weight_sum = item.stocks.reduce((sum, stock) => sum + stock.ratio, 0);

        // 扁平化嵌套字段（加速筛选和排序）
        item.index_rate = item.annualized_rates?.index;
        item.start_rate = item.annualized_rates?.start;
        item.index_dd = item.year_max_drawdown?.index;
        item.start_dd = item.year_max_drawdown?.start;

        // 生成股票组合显示文本
        item.stocks_display = item.stocks
            .filter(s => s.ratio > 0)
            .map(s => `${s.stock_name || s.stock_code || 'N/A'} (${s.ratio}%)`)
            .join(', ');

        return item;
    }

    /**
     * 取消分析
     */
    function handleCancel() {
        if (abortController) {
            abortController.abort();
        }
    }

    /**
     * 更新进度
     */
    function updateProgress(percentage, message) {
        if (percentage !== null) {
            progressBar.style.width = percentage + '%';
            progressBar.setAttribute('aria-valuenow', percentage);
            progressBar.textContent = percentage + '%';
        }
        if (message) {
            progressInfo.textContent = message;
        }
    }

    /**
     * 更新统计信息
     */
    function updateStats() {
        const filteredCount = table.getDataCount('active');
        const totalCount = allData.length;

        const filteredEl = document.getElementById('filtered-count');
        const totalEl = document.getElementById('total-count');

        if (filteredEl) filteredEl.textContent = `${filteredCount} 条显示`;
        if (totalEl) totalEl.textContent = `${totalCount} 条总计`;
    }

    /**
     * 导出 CSV
     */
    function exportCSV() {
        table.download('csv', `weight_combination_${Date.now()}.csv`, {
            bom: true,  // UTF-8 BOM for Excel
            delimiter: ','
        });
    }

    // 监听表格筛选事件
    if (table) {
        table.on('dataFiltered', function(filters, rows) {
            updateStats();
        });
    }

})();

// 页面脚本（templates/xpl/index.html 内联脚本原样抽离，F5 de-jinja）。
    // 全局变量
    let chart = null;
    let drawdownChart = null;
    let sharpePastChart = null;
    let sharpeYearChart = null;
    let rawData = [];
    let processedData = [];
    let currentResults = null;

    function normalizeApiResponse(payload) {
        const isStandard = payload
            && typeof payload === 'object'
            && Object.prototype.hasOwnProperty.call(payload, 'code')
            && Object.prototype.hasOwnProperty.call(payload, 'data');
        const body = isStandard && payload.data && typeof payload.data === 'object'
            ? payload.data
            : payload;
        return {
            ok: isStandard ? payload.code === 0 : body?.status === 'success',
            message: payload?.message || body?.message || '',
            body,
            data: isStandard ? payload.data : body
        };
    }

    function getAnalyzeResults(api) {
        return api.body?.results ?? api.data?.results ?? api.data;
    }

    function formatPercent(value, digits = 2) {
        if (value === undefined || value === null || value === '') {
            return '-';
        }
        const num = Number(value);
        return Number.isFinite(num) ? `${(num * 100).toFixed(digits)}%` : '-';
    }

    function formatNumber(value, digits = 4) {
        if (value === undefined || value === null || value === '') {
            return '-';
        }
        const num = Number(value);
        return Number.isFinite(num) ? num.toFixed(digits) : '-';
    }

    function getReturnRateValue(item) {
        return item?.annual_return ?? item?.monthly_return ?? item?.daily_return ?? item?.return;
    }

    function isDualResults(results) {
        return results?.analysis_mode === 'dual'
            || Boolean(results?.start_returns_rate || results?.index_returns_rate);
    }

    function getPrimaryResults(results) {
        if (!isDualResults(results)) {
            return results;
        }

        return {
            maximum_drawdown: results.start_maximum_drawdown,
            returns_rate: results.start_returns_rate,
            sharpe_ratios: results.start_sharpe_ratios,
            analysis_mode: results.analysis_mode
        };
    }

    function getSecondaryResults(results) {
        if (!isDualResults(results)) {
            return null;
        }

        return {
            maximum_drawdown: results.index_maximum_drawdown,
            returns_rate: results.index_returns_rate,
            sharpe_ratios: results.index_sharpe_ratios,
            analysis_mode: results.analysis_mode
        };
    }

    function formatSharpePeriodLabel(key) {
        if (key === 'all') {
            return '全部';
        }

        const pastMatch = key.match(/^past_(\d+)_years_since_(\d{4})$/);
        if (pastMatch) {
            return `近${pastMatch[1]}年（${pastMatch[2]}起）`;
        }

        const yearMatch = key.match(/^year_(\d+)_(\d{4})$/);
        if (yearMatch) {
            return `第${yearMatch[1]}年（${yearMatch[2]}）`;
        }

        return key;
    }

    // 页面加载完成
    document.addEventListener('DOMContentLoaded', () => {
        initEventListeners();
        showAlert('欢迎使用收益率分析工具！请从Excel复制数据并粘贴到上方区域。', 'info');
        
        // 不初始化默认图表，等待数据加载后再创建
    });
    
    // 刷新数据
    function refreshData() {
        if (rawData.length > 0) {
            parseExcelData();
        } else {
            showAlert('没有可刷新的数据', 'warning');
        }
    }

    // 从剪贴板粘贴
    async function pasteFromClipboard() {
        try {
            const text = await navigator.clipboard.readText();
            document.getElementById('data-input').value = text;
            showAlert('已从剪贴板粘贴数据', 'success');
        } catch (err) {
            console.error('无法访问剪贴板:', err);
            showAlert('无法访问剪贴板，请手动粘贴', 'danger');
        }
    }

    // 全局变量用于取消请求
    let abortController = null;

    // 取消加载
    document.getElementById('cancel-loading')?.addEventListener('click', () => {
        if (abortController) {
            abortController.abort();
            hideLoading();
            showAlert('已取消操作', 'info');
        }
    });

    // 显示加载中
    function showLoading() {
        const overlay = document.getElementById('loading-overlay');
        if (overlay) {
            overlay.style.display = 'flex';
            // 禁用页面滚动
            document.body.style.overflow = 'hidden';
        }
    }

    // 隐藏加载中
    function hideLoading() {
        const overlay = document.getElementById('loading-overlay');
        if (overlay) {
            overlay.style.display = 'none';
            // 恢复页面滚动
            document.body.style.overflow = '';
        }
    }

    // 解析Excel数据并发送到后端处理
    function parseExcelData() {
        const inputText = document.getElementById('data-input').value.trim();
        
        // 添加更严格的输入验证
        if (!inputText) {
            showAlert('请输入要分析的数据', 'warning');
            return;
        }

        // 检查是否只有空白行
        const nonEmptyLines = inputText.split('\n').filter(line => line.trim().length > 0);
        if (nonEmptyLines.length === 0) {
            showAlert('请输入有效的分析数据', 'warning');
            return;
        }
        rawData = nonEmptyLines;

        // 显示加载中
        showLoading();
        
        // 准备请求数据
        const requestData = {
            data: inputText,
            time_format: document.getElementById('time-format').value
        };

        // 创建新的AbortController
        abortController = new AbortController();
        const signal = abortController.signal;
        
        // 设置超时
        const timeoutId = setTimeout(() => {
            if (abortController) {
                abortController.abort('请求超时，请稍后重试');
            }
        }, 30000); // 30秒超时

        // 发送数据到后端API
        fetch('/xpl/analyze', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': document.querySelector('meta[name="csrf-token"]')?.content || ''
            },
            body: JSON.stringify(requestData),
            signal: signal
        })
        .then(async response => {
            clearTimeout(timeoutId);
            if (!response.ok) {
                const error = await response.json().catch(() => ({}));
                const api = normalizeApiResponse(error);
                throw new Error(api.message || `HTTP error! status: ${response.status}`);
            }
            return response.json();
        })
        .then(data => {
            const api = normalizeApiResponse(data);
            const results = getAnalyzeResults(api);
            if (api.ok) {
                showAlert('数据分析完成', 'success');
                console.log('API Response:', data); // 调试日志
                
                // 保存当前结果用于导出
                currentResults = {results};
                
                // 更新所有数据
                if (results) {
                    updateMetrics(results);
                    updateAllTables(results);
                }
            } else {
                throw new Error(api.message || '处理数据时出错');
            }
        })
        .catch(error => {
            console.error('请求出错:', error);
            if (error.name === 'AbortError') {
                showAlert(error.message || '操作已取消', 'info');
            } else {
                showAlert('请求出错: ' + (error.message || '未知错误'), 'danger');
            }
        })
        .finally(() => {
            hideLoading();
            abortController = null;
            clearTimeout(timeoutId);
        });
    }
    // 更新数据预览
    function updateDataPreview(data) {
        const tbody = document.getElementById('data-preview');
        tbody.innerHTML = '';
        
        if (!data || data.length === 0) {
            tbody.innerHTML = '<tr><td colspan="4" class="text-center text-muted py-4">暂无数据</td></tr>';
            return;
        }
        
        data.forEach((item, index) => {
            const row = document.createElement('tr');
            row.innerHTML = `
                <td>${index + 1}</td>
                <td>${item.date || '-'}</td>
                <td class="${(item.return || 0) >= 0 ? 'text-success' : 'text-danger'}">
                    ${((item.return || 0) * 100).toFixed(2)}%
                </td>
                <td>${((item.cumulative_return || 0) * 100).toFixed(2)}%</td>
            `;
            tbody.appendChild(row);
        });
        
        document.getElementById('data-count').textContent = data.length;
    }
    
    // 更新指标
    function updateMetrics(results) {
        if (!results) return;
        const primaryResults = getPrimaryResults(results);

        // 更新核心指标
        if (Array.isArray(primaryResults.returns_rate) && primaryResults.returns_rate.length > 0) {
            const latestReturn = primaryResults.returns_rate[primaryResults.returns_rate.length - 1];
            const totalReturn = latestReturn.net_value !== undefined ? latestReturn.net_value - 1 : getReturnRateValue(latestReturn);
            document.getElementById('total-return').textContent = `${formatNumber(totalReturn, 2)}%`;
            document.getElementById('annual-return').textContent = formatPercent(latestReturn.annual_return);
        }
        
        if (primaryResults.maximum_drawdown !== undefined) {
            document.getElementById('max-drawdown').textContent = formatPercent(primaryResults.maximum_drawdown.total_maximum_drawdown?.drawdown);
        }
        if (primaryResults.sharpe_ratios !== undefined) {
            document.getElementById('sharpe-ratio').textContent = formatNumber(primaryResults.sharpe_ratios.all?.sharpe_ratio);
        }
        
        // // 更新其他指标
        // if (results.data_points !== undefined) {
        //     document.getElementById('data-points').textContent = results.data_points;
        // }
        // if (results.date_range) {
        //     document.getElementById('date-range').textContent = results.date_range;
        // }
        // if (results.annual_volatility !== undefined) {
        //     document.getElementById('annual-volatility').textContent = (results.annual_volatility * 100).toFixed(2) + '%';
        // }
        // if (results.win_rate !== undefined) {
        //     document.getElementById('win-rate').textContent = (results.win_rate * 100).toFixed(2) + '%';
        // }
    }

    // 加载示例数据
    function loadSampleData() {
        const sampleData = `2025-01-01 0.0234
2025-01-02 -0.0156
2025-01-03 0.0089
2025-01-04 0.0123
2025-01-05 -0.0078
2025-01-06 0.0189
2025-01-07 -0.0056
2025-01-08 0.0098
2025-01-09 0.0145
2025-01-10 -0.0032`;
        
        document.getElementById('data-input').value = sampleData;
        showAlert('已加载示例数据', 'info');
    }

    // 清空所有数据
    function clearAllData() {
        if (confirm('确定要清空所有数据吗？此操作不可恢复。')) {
            document.getElementById('data-input').value = '';
            document.getElementById('data-preview').innerHTML = '<tr><td colspan="4" class="text-center text-muted py-4">暂无数据</td></tr>';
            document.getElementById('results-tbody').innerHTML = '<tr><td colspan="5" class="text-center text-muted py-3">分析后将显示数据预览</td></tr>';
            document.getElementById('data-count').textContent = '0';
            
            // 重置图表
            if (chart) {
                chart.data.labels = [];
                chart.data.datasets[0].data = [];
                chart.update();
            }
            
            // 重置指标
            ['total-return', 'annual-return', 'max-drawdown', 'sharpe-ratio', 
             'data-points', 'date-range', 'annual-volatility', 'win-rate'].forEach(id => {
                const el = document.getElementById(id);
                if (el) el.textContent = '-';
            });
            
            showAlert('已清空所有数据', 'success');
        }
    }

    // 导出结果
    function exportResults() {
        if (!currentResults) {
            showAlert('没有可导出的结果', 'warning');
            return;
        }
        
        // 直接导出接口响应的数据
        const exportData = {
            meta: {
                generatedAt: new Date().toISOString(),
                dataPoints: rawData.length
            },
            results: currentResults.results
        };
        
        document.getElementById('export-data').value = JSON.stringify(exportData, null, 2);
        const exportModal = new bootstrap.Modal(document.getElementById('exportModal'));
        exportModal.show();
    }

    // 复制到剪贴板
    async function copyToClipboard() {
        const exportData = document.getElementById('export-data');
        try {
            await navigator.clipboard.writeText(exportData.value);
            showAlert('已复制到剪贴板', 'success');
        } catch (err) {
            console.error('复制失败:', err);
            showAlert('复制失败: ' + err.message, 'danger');
        }
    }

    // 下载JSON文件
    function downloadJSON() {
        const exportData = document.getElementById('export-data');
        const blob = new Blob([exportData.value], { type: 'application/json' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `analysis-${new Date().toISOString().slice(0, 10)}.json`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
    }

    // 显示提示信息
    function showAlert(message, type = 'info') {
        const alert = document.createElement('div');
        alert.className = `alert alert-${type} alert-dismissible fade show`;
        alert.role = 'alert';
        alert.innerHTML = `
            ${message}
            <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>
        `;
        
        const container = document.createElement('div');
        container.className = 'position-fixed top-0 end-0 p-3';
        container.style.zIndex = '9999';
        container.appendChild(alert);
        
        document.body.appendChild(container);
        
        // 2秒后自动移除
        setTimeout(() => {
            const bsAlert = new bootstrap.Alert(alert);
            bsAlert.close();
            setTimeout(() => container.remove(), 150);
        }, 2000);
    }

    // 初始化事件监听器
    function initEventListeners() {
        // 监听键盘快捷键
        document.addEventListener('keydown', (e) => {
            // Ctrl+Enter 触发计算
            if (e.ctrlKey && e.key === 'Enter') {
                e.preventDefault();
                parseExcelData();
            }
            
            // Esc 清空输入
            if (e.key === 'Escape') {
                clearAllData();
            }
        });
        
        // 监听输入框变化
        document.getElementById('data-input').addEventListener('input', function() {
            this.style.height = 'auto';
            this.style.height = (this.scrollHeight) + 'px';
        });
    }

    // 添加行数统计功能
    document.addEventListener('DOMContentLoaded', function() {
        const textarea = document.getElementById('data-input');
        const lineCount = document.getElementById('line-count');
        
        function updateLineCount() {
            const lines = textarea.value.split('\n').filter(line => line.trim() !== '');
            lineCount.textContent = `${lines.length} 行数据`;
        }
        
        textarea.addEventListener('input', updateLineCount);
        
        // 初始化工具提示
        const tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
        tooltipTriggerList.map(function (tooltipTriggerEl) {
            return new bootstrap.Tooltip(tooltipTriggerEl);
        });
    });

    // 更新最大回撤表格
    function updateDrawdownTable(data) {
        const table = document.getElementById('drawdown-table');
        if (!table) {
            console.error('Drawdown table not found');
            return;
        }

        const tbody = table.querySelector('tbody');
        if (!tbody) {
            console.error('Drawdown table body not found');
            return;
        }

        tbody.innerHTML = ''; // 清空现有内容

        const primaryResults = getPrimaryResults(data);
        const secondaryResults = getSecondaryResults(data);
        if (!primaryResults.maximum_drawdown || !primaryResults.maximum_drawdown.year_maximum_drawdown) {
            tbody.innerHTML = '<tr><td colspan="5" class="text-center text-muted">没有可用的回撤数据</td></tr>';
            return;
        }

        // 添加数据行
        primaryResults.maximum_drawdown.year_maximum_drawdown.forEach((item, index) => {
            const secondaryItem = secondaryResults?.maximum_drawdown?.year_maximum_drawdown?.[index];
            const row = document.createElement('tr');
            row.innerHTML = `
                <td>${item.date}</td>
                <td>${item.year}</td>
                <td class="${item.drawdown >= 0 ? 'text-danger' : 'text-success'}">
                    ${isDualResults(data) ? '模型 ' : ''}${formatPercent(item.drawdown)}
                    ${secondaryItem ? `<div class="small text-muted">指数 ${formatPercent(secondaryItem.drawdown)}</div>` : ''}
                </td>
                <td>${formatNumber(item.daily_return, 2)}%${secondaryItem ? `<div class="small text-muted">指数 ${formatNumber(secondaryItem.daily_return, 2)}%</div>` : ''}</td>
                <td>${formatNumber(item.net_value)}${secondaryItem ? `<div class="small text-muted">指数 ${formatNumber(secondaryItem.net_value)}</div>` : ''}</td>
            `;
            tbody.appendChild(row);
        });
    }

    // 更新主收益率曲线图表
    function updateMainReturnsChart(results) {
        const ctx = document.getElementById('return-chart');
        if (!ctx) {
            console.error('Main return chart canvas not found');
            return;
        }

        const primaryResults = Array.isArray(results) ? { returns_rate: results } : getPrimaryResults(results);
        const secondaryResults = Array.isArray(results) ? null : getSecondaryResults(results);
        const returnsData = primaryResults?.returns_rate;
        if (!returnsData || !Array.isArray(returnsData)) {
            console.error('Invalid returns data for main chart');
            return;
        }

        // 准备图表数据
        const labels = returnsData.map(item => {
            const date = new Date(item.date);
            return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}`;
        });

        const data = returnsData.map(item => getReturnRateValue(item) * 100);
        const datasets = [{
            label: isDualResults(results) ? '模型年度收益率 (%)' : '年度收益率 (%)',
            data: data,
            borderColor: '#007bff',
            backgroundColor: 'rgba(0, 123, 255, 0.1)',
            borderWidth: 2,
            fill: true,
            tension: 0.1
        }];
        if (secondaryResults?.returns_rate) {
            datasets.push({
                label: '指数年度收益率 (%)',
                data: secondaryResults.returns_rate.map(item => getReturnRateValue(item) * 100),
                borderColor: '#6c757d',
                backgroundColor: 'rgba(108, 117, 125, 0.08)',
                borderWidth: 2,
                fill: false,
                tension: 0.1
            });
        }

        // 创建或更新图表
        if (chart) {
            chart.data.labels = labels;
            chart.data.datasets = datasets;
            chart.update();
        } else {
            chart = new Chart(ctx, {
                type: 'line',
                data: {
                    labels: labels,
                    datasets: datasets
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    scales: {
                        y: {
                            beginAtZero: true,
                            title: {
                                display: true,
                                text: '收益率 (%)'
                            },
                            ticks: {
                                callback: function(value) {
                                    return value + '%';
                                }
                            }
                        },
                        x: {
                            title: {
                                display: true,
                                text: '日期'
                            }
                        }
                    }
                }
            });
        }
    }

    // 更新收益率表格和图表
    function updateReturnsData(data) {
        const table = document.getElementById('returns-table');
        if (!table) {
            console.error('Returns table not found');
            return;
        }

        const tbody = table.querySelector('tbody');
        if (!tbody) {
            console.error('Returns table body not found');
            return;
        }

        tbody.innerHTML = ''; // 清空现有内容

        const primaryResults = getPrimaryResults(data);
        const secondaryResults = getSecondaryResults(data);
        if (!primaryResults.returns_rate || !Array.isArray(primaryResults.returns_rate)) {
            tbody.innerHTML = '<tr><td colspan="4" class="text-center text-muted">没有可用的收益率数据</td></tr>';
            return;
        }

        // 添加数据行
        primaryResults.returns_rate.forEach((item, index) => {
            const secondaryItem = secondaryResults?.returns_rate?.[index];
            const row = document.createElement('tr');
            // const date = new Date(item.date);
            // const year = date.getFullYear();
            // const month = String(date.getMonth() + 1).padStart(2, '0');
            
            row.innerHTML = `
                <td>${item.date}</td>
                <td>${item.year}</td>
                <td class="${getReturnRateValue(item) >= 0 ? 'text-success' : 'text-danger'}">
                    ${formatPercent(getReturnRateValue(item))}
                    ${secondaryItem ? `<div class="small text-muted">指数 ${formatPercent(getReturnRateValue(secondaryItem))}</div>` : ''}
                </td>
                <td>${formatNumber(item.net_value)}</td>
            `;
            tbody.appendChild(row);
        });

        // 更新图表到主收益率曲线区域
        if (primaryResults.returns_rate && Array.isArray(primaryResults.returns_rate)) {
            updateMainReturnsChart(data);
        }
    }

    // 更新夏普比率表格
    function updateSharpeTable(data) {
        const table = document.getElementById('sharpe-table');
        if (!table) {
            console.error('Sharpe table not found');
            return;
        }

        const tbody = table.querySelector('tbody');
        if (!tbody) {
            console.error('Sharpe table body not found');
            return;
        }

        tbody.innerHTML = ''; // 清空现有内容

        const primaryResults = getPrimaryResults(data);
        const secondaryResults = getSecondaryResults(data);
        if (!primaryResults.sharpe_ratios) {
            tbody.innerHTML = '<tr><td colspan="7" class="text-center text-muted">没有可用的夏普比率数据</td></tr>';
            return;
        }

        // 添加数据行
        Object.entries(primaryResults.sharpe_ratios).forEach(([key, value]) => {
            if (typeof value === 'object' && value !== null) {
                const secondaryValue = secondaryResults?.sharpe_ratios?.[key];
                const row = document.createElement('tr');
                row.innerHTML = `
                    <td>${formatSharpePeriodLabel(key)}</td>
                    <td>${formatNumber(value.sharpe_ratio)}${secondaryValue ? `<div class="small text-muted">指数 ${formatNumber(secondaryValue.sharpe_ratio)}</div>` : ''}</td>
                    <td>${formatPercent(value.avg_monthly_return)}${secondaryValue ? `<div class="small text-muted">指数 ${formatPercent(secondaryValue.avg_monthly_return)}</div>` : ''}</td>
                    <td>${formatPercent(value.monthly_std_dev)}${secondaryValue ? `<div class="small text-muted">指数 ${formatPercent(secondaryValue.monthly_std_dev)}</div>` : ''}</td>
                    <td>${formatPercent(value.annual_std_dev)}${secondaryValue ? `<div class="small text-muted">指数 ${formatPercent(secondaryValue.annual_std_dev)}</div>` : ''}</td>
                    <td>${value.start_date || '-'}</td>
                    <td>${value.end_date || '-'}</td>
                `;
                tbody.appendChild(row);
            }
        });
    }

    // 更新最大回撤图表
    function updateDrawdownChart(data) {
        const ctx = document.getElementById('drawdown-chart');
        if (!ctx) {
            console.error('Drawdown chart canvas not found');
            return;
        }

        const primaryResults = getPrimaryResults(data);
        const secondaryResults = getSecondaryResults(data);
        if (!primaryResults || !primaryResults.maximum_drawdown || !primaryResults.maximum_drawdown.year_maximum_drawdown) {
            console.error('Invalid drawdown data for chart');
            return;
        }

        const drawdownData = primaryResults.maximum_drawdown.year_maximum_drawdown;
        const labels = drawdownData.map(item => item.year);
        const drawdownValues = drawdownData.map(item => item.drawdown * 100);
        const datasets = [{
            label: isDualResults(data) ? '模型最大回撤 (%)' : '最大回撤 (%)',
            data: drawdownValues,
            borderColor: '#dc3545',
            backgroundColor: 'rgba(220, 53, 69, 0.1)',
            borderWidth: 2,
            fill: true,
            tension: 0.1
        }];
        if (secondaryResults?.maximum_drawdown?.year_maximum_drawdown) {
            datasets.push({
                label: '指数最大回撤 (%)',
                data: secondaryResults.maximum_drawdown.year_maximum_drawdown.map(item => item.drawdown * 100),
                borderColor: '#6c757d',
                backgroundColor: 'rgba(108, 117, 125, 0.08)',
                borderWidth: 2,
                fill: false,
                tension: 0.1
            });
        }

        if (drawdownChart) {
            drawdownChart.data.labels = labels;
            drawdownChart.data.datasets = datasets;
            drawdownChart.update();
        } else {
            drawdownChart = new Chart(ctx, {
                type: 'line',
                data: {
                    labels: labels,
                    datasets: datasets
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    scales: {
                        y: {
                            beginAtZero: true,
                            title: {
                                display: true,
                                text: '回撤 (%)'
                            }
                        },
                        x: {
                            title: {
                                display: true,
                                text: '年份'
                            }
                        }
                    }
                }
            });
        }
    }

    // 更新夏普率图表（过去期间）
    function updateSharpePastChart(data) {
        const ctx = document.getElementById('sharpe-past-chart');
        if (!ctx) {
            console.error('Sharpe past chart canvas not found');
            return;
        }

        const primaryResults = getPrimaryResults(data);
        const secondaryResults = getSecondaryResults(data);
        if (!primaryResults || !primaryResults.sharpe_ratios) {
            console.error('Invalid sharpe data for past chart');
            return;
        }

        // 过滤出past_开头的数据
        const pastData = Object.entries(primaryResults.sharpe_ratios)
            .filter(([key]) => key.includes('past_'))
            .map(([key, value]) => ({
                key,
                label: formatSharpePeriodLabel(key),
                sharpe: value.sharpe_ratio
            }));

        const labels = pastData.map(item => item.label);
        const sharpeValues = pastData.map(item => item.sharpe);
        const datasets = [{
            label: isDualResults(data) ? '模型夏普比率' : '夏普比率',
            data: sharpeValues,
            backgroundColor: sharpeValues.map(value => value >= 1 ? 'rgba(40, 167, 69, 0.5)' : 'rgba(255, 193, 7, 0.5)'),
            borderColor: sharpeValues.map(value => value >= 1 ? '#28a745' : '#ffc107'),
            borderWidth: 1
        }];
        if (secondaryResults?.sharpe_ratios) {
            datasets.push({
                label: '指数夏普比率',
                data: pastData.map(item => secondaryResults.sharpe_ratios[item.key]?.sharpe_ratio ?? null),
                backgroundColor: 'rgba(108, 117, 125, 0.35)',
                borderColor: '#6c757d',
                borderWidth: 1
            });
        }

        if (sharpePastChart) {
            sharpePastChart.data.labels = labels;
            sharpePastChart.data.datasets = datasets;
            sharpePastChart.update();
        } else {
            sharpePastChart = new Chart(ctx, {
                type: 'bar',
                data: {
                    labels: labels,
                    datasets: datasets
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    scales: {
                        y: {
                            beginAtZero: true,
                            title: {
                                display: true,
                                text: '夏普比率'
                            }
                        }
                    }
                }
            });
        }
    }

    // 更新夏普率图表（按年度）
    function updateSharpeYearChart(data) {
        const ctx = document.getElementById('sharpe-year-chart');
        if (!ctx) {
            console.error('Sharpe year chart canvas not found');
            return;
        }

        const primaryResults = getPrimaryResults(data);
        const secondaryResults = getSecondaryResults(data);
        if (!primaryResults || !primaryResults.sharpe_ratios) {
            console.error('Invalid sharpe data for year chart');
            return;
        }

        // 过滤出year_开头的数据
        const yearData = Object.entries(primaryResults.sharpe_ratios)
            .filter(([key]) => key.includes('year_'))
            .map(([key, value]) => ({
                key,
                label: formatSharpePeriodLabel(key),
                sharpe: value.sharpe_ratio
            }));

        const labels = yearData.map(item => item.label);
        const sharpeValues = yearData.map(item => item.sharpe);
        const datasets = [{
            label: isDualResults(data) ? '模型夏普比率' : '夏普比率',
            data: sharpeValues,
            backgroundColor: sharpeValues.map(value => value >= 1 ? 'rgba(40, 167, 69, 0.5)' : 'rgba(220, 53, 69, 0.5)'),
            borderColor: sharpeValues.map(value => value >= 1 ? '#28a745' : '#dc3545'),
            borderWidth: 1
        }];
        if (secondaryResults?.sharpe_ratios) {
            datasets.push({
                label: '指数夏普比率',
                data: yearData.map(item => secondaryResults.sharpe_ratios[item.key]?.sharpe_ratio ?? null),
                backgroundColor: 'rgba(108, 117, 125, 0.35)',
                borderColor: '#6c757d',
                borderWidth: 1
            });
        }

        if (sharpeYearChart) {
            sharpeYearChart.data.labels = labels;
            sharpeYearChart.data.datasets = datasets;
            sharpeYearChart.update();
        } else {
            sharpeYearChart = new Chart(ctx, {
                type: 'bar',
                data: {
                    labels: labels,
                    datasets: datasets
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    scales: {
                        y: {
                            beginAtZero: true,
                            title: {
                                display: true,
                                text: '夏普比率'
                            }
                        }
                    }
                }
            });
        }
    }

    // 更新所有表格和图表
    function updateAllTables(results) {
        updateDrawdownTable(results);
        updateReturnsData(results);
        updateSharpeTable(results);
        
        // 更新所有图表
        updateMainReturnsChart(results);
        updateDrawdownChart(results);
        updateSharpePastChart(results);
        updateSharpeYearChart(results);
    }

// 全局变量
    let currentTaskId = null;
    let statusInterval = null;
    let refreshInterval = null;
    let allResults = [];  // 当前页的结果数据
    let currentResultsPage = 1;
    let resultsPerPage = 20;  // 每页显示数量
    let resultsTotal = 0;  // 总结果数
    let resultsPages = 0;  // 总页数
    let resultsTotalSuccess = 0;  // 总成功数
    let resultsTotalFailed = 0;  // 总失败数
    let currentRefreshFrequency = 60000; // 默认1分钟，将从配置加载
    let taskStartTime = null; // 存储任务开始时间
    let currentTaskData = null; // 存储当前任务数据
    let editConfigModal = null; // 编辑配置模态框实例

    // 页面加载完成后获取任务详情
    document.addEventListener('DOMContentLoaded', function() {
        console.log('页面加载完成');
        currentTaskId = getTaskIdFromUrl();
        console.log('获取到的任务ID:', currentTaskId);
        
        // 初始化编辑配置模态框
        const modalElement = document.getElementById('editConfigModal');
        if (modalElement && typeof bootstrap !== 'undefined') {
            editConfigModal = new bootstrap.Modal(modalElement);
        }
        
        if (currentTaskId) {
            // 从配置加载默认刷新频率
            ajaxRequest('/api/config', 'GET', null, function(err, data) {
                if (!err && data && data.config && data.config.detail_refresh_interval) {
                    currentRefreshFrequency = data.config.detail_refresh_interval;
                    // 更新下拉框的默认选择
                    const frequencySelect = document.getElementById('refresh-frequency');
                    if (frequencySelect) {
                        frequencySelect.value = currentRefreshFrequency;
                    }
                }
                
                loadTaskDetail();
                initializeRefreshControls();
                // 启动自动刷新
                startAutoRefresh();
            });
        } else {
            showNotification('任务ID无效', 'error');
        }
    });

    // 页面卸载时清理定时器
    window.addEventListener('beforeunload', function() {
        stopAutoRefresh();
    });

    // 初始化刷新控制
    function initializeRefreshControls() {
        const frequencySelect = document.getElementById('refresh-frequency');
        const manualRefreshBtn = document.getElementById('manual-refresh-btn');
        
        // 刷新频率选择事件
        frequencySelect.addEventListener('change', function() {
            currentRefreshFrequency = parseInt(this.value);
            console.log('刷新频率更改为:', currentRefreshFrequency + 'ms');
            startAutoRefresh(); // 重新启动自动刷新
            showNotification(`自动刷新频率已设置为 ${getFrequencyText(currentRefreshFrequency)}`, 'info');
        });
        
        // 手动刷新按钮事件
        manualRefreshBtn.addEventListener('click', function() {
            manualRefresh();
        });
    }

    // 获取频率文本
    function getFrequencyText(milliseconds) {
        const seconds = milliseconds / 1000;
        if (seconds < 60) {
            return `${seconds}秒`;
        } else {
            const minutes = seconds / 60;
            return `${minutes}分钟`;
        }
    }

    // 手动刷新
    function manualRefresh() {
        const btn = document.getElementById('manual-refresh-btn');
        const icon = btn.querySelector('i');
        
        // 添加旋转动画
        icon.style.animation = 'spin 1s linear infinite';
        btn.disabled = true;
        
        console.log('执行手动刷新...');
        loadTaskDetail();
        
        // 1秒后恢复按钮
        setTimeout(() => {
            icon.style.animation = '';
            btn.disabled = false;
        }, 1000);
        
        showNotification('手动刷新完成', 'success');
    }

    // 获取URL中的任务ID
    function getTaskIdFromUrl() {
        const urlParams = new URLSearchParams(window.location.search);
        return urlParams.get('task_id');
    }

    // 加载任务详情
    function loadTaskDetail() {
        console.log('开始加载任务详情，任务ID:', currentTaskId);
        ajaxRequest(`/api/tasks/${currentTaskId}`, 'GET', null, function(err, data) {
            console.log('API响应:', err, data);
            if (!err && data && data.task) {
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
                // 进度条至少展示为 5% 宽，避免进度很低时几乎看不见
                const visiblePercent = progressPercent > 0 ? Math.max(progressPercent, 5) : 0;
                const progressBarClass = getProgressBarClass(task.status) + (task.status === 'running' ? ' progress-bar-striped progress-bar-animated' : '');

                document.getElementById('task-progress').innerHTML = `
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
                
                // 更新时间信息
                document.getElementById('start-time').textContent = formatTime(task.start_time);
                document.getElementById('end-time').textContent = formatTime(task.end_time);
                
                // 保存任务开始时间用于计算耗时
                if (task.start_time) {
                    taskStartTime = new Date(task.start_time);
                }
                
                // 计算执行时长
                let duration = 0;
                if (task.start_time) {
                    const startTime = new Date(task.start_time);
                    const endTime = task.end_time ? new Date(task.end_time) : new Date();
                    duration = Math.max(0, Math.round((endTime - startTime) / 1000)); // 确保不为负数
                }
                document.getElementById('execution-duration').textContent = formatDuration(duration);
                
                // 显示/隐藏错误信息
                const errorInfo = document.getElementById('error-info');
                if (task.error_message) {
                    document.getElementById('error-message').textContent = task.error_message;
                    errorInfo.style.display = 'block';
                } else {
                    errorInfo.style.display = 'none';
                }
                
                // 显示/隐藏取消按钮
                const cancelBtn = document.getElementById('cancel-task-btn');
                if (task.status === 'running') {
                    cancelBtn.style.display = 'inline-block';
                    cancelBtn.setAttribute('data-task-id', task.id);
                } else {
                    cancelBtn.style.display = 'none';
                }
                
                // 显示/隐藏重启按钮（包括pending状态）
                const restartBtn = document.getElementById('restart-dropdown-btn');
                if (task.status === 'pending' || task.status === 'completed' || task.status === 'error' || task.status === 'cancelled') {
                    restartBtn.style.display = 'inline-block';
                } else {
                    restartBtn.style.display = 'none';
                }
                
                // 显示/隐藏编辑按钮（只有非运行状态才能编辑）
                const editBtn = document.getElementById('edit-config-btn');
                if (task.status !== 'running') {
                    editBtn.style.display = 'inline-block';
                } else {
                    editBtn.style.display = 'none';
                }
                
                // 填充配置信息
                loadTaskConfig(task.config);
                loadTaskParameters(task.config);
                
                // 加载任务日志
                loadTaskLogs();
                
                // 加载任务结果
                loadTaskResults();
                
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
        });
    }

    // 加载任务配置
    function loadTaskConfig(config) {
        const container = document.getElementById('config-container');
        container.innerHTML = '';
        
        if (config) {
            const configItems = [
                { label: '电子表格ID', value: config.spreadsheet_id || '-', icon: 'bi-link-45deg' },
                { label: '工作表名称', value: config.sheet_name || '-', icon: 'bi-file-spreadsheet' },
                { label: '认证方式', value: config.token_type || '-', icon: 'bi-shield-lock' },
                { label: '代理URL', value: config.proxy_url || '无', icon: 'bi-globe' },
                { label: '参数数量', value: config.parameters ? config.parameters.length : 0, icon: 'bi-list-ul' }
            ];
            
            configItems.forEach(item => {
                const itemDiv = document.createElement('div');
                itemDiv.className = 'mb-2 d-flex align-items-center';
                itemDiv.innerHTML = `
                    <i class="${item.icon} text-muted me-2"></i>
                    <strong class="me-2">${item.label}:</strong>
                    <span class="text-muted">${item.value}</span>
                `;
                container.appendChild(itemDiv);
            });
        } else {
            container.innerHTML = '<div class="text-muted">无配置信息</div>';
        }
    }

    // 加载任务日志
    function loadTaskLogs() {
        console.log('开始加载任务日志...');
        ajaxRequest(`/api/tasks/${currentTaskId}/logs`, 'GET', null, function(err, data) {
            console.log('日志API响应:', err, data);
            if (!err && data && data.logs) {
                const logContainer = document.getElementById('log-container');
                console.log('找到日志容器:', logContainer);
                console.log('日志数量:', data.logs.length);
                
                if (data.logs.length > 0) {
                    // 保存当前滚动位置
                    const wasAtBottom = logContainer.scrollTop + logContainer.clientHeight >= logContainer.scrollHeight - 5;
                    
                    // 更新日志内容
                    logContainer.innerHTML = data.logs.map(log => {
                        const level = log.level || 'info';
                        const levelClass = level === 'error' ? 'text-danger' : 
                                         level === 'warning' ? 'text-warning' : 
                                         level === 'info' ? 'text-info' : 'text-light';
                        return `<div class="${levelClass}">[${formatTime(log.timestamp)}] ${log.message}</div>`;
                    }).join('');
                    
                    // 如果之前在底部，保持滚动到底部
                    if (wasAtBottom) {
                logContainer.scrollTop = logContainer.scrollHeight;
                    }
                    
                    console.log('日志已显示');
                } else {
                    logContainer.innerHTML = '<div class="text-muted">暂无日志</div>';
                    console.log('没有日志数据');
                }
            } else {
                console.error('加载日志失败:', err, data);
                const logContainer = document.getElementById('log-container');
                logContainer.innerHTML = '<div class="text-danger">加载日志失败</div>';
            }
        });
    }

    // 加载任务参数
    function loadTaskParameters(config) {
        const container = document.getElementById('parameters-container');
        container.innerHTML = '';
        
        if (config && config.parameters) {
            config.parameters.forEach((param, index) => {
                const paramDiv = document.createElement('div');
                paramDiv.className = 'mb-2';
                paramDiv.innerHTML = `
                    <div class="d-flex align-items-center">
                        <span class="badge bg-primary me-2">参数${index + 1}</span>
                        <code class="text-dark">${JSON.stringify(param)}</code>
                    </div>
                `;
                container.appendChild(paramDiv);
            });
        } else {
            container.innerHTML = '<div class="text-muted">无参数配置</div>';
        }
    }

    // 加载任务结果（使用翻页接口）
    function loadTaskResults(page = currentResultsPage) {
        currentResultsPage = page;
        const url = `/api/tasks/${currentTaskId}/results?page=${page}&per_page=${resultsPerPage}`;
        ajaxRequest(url, 'GET', null, function(err, data) {
            if (!err && data) {
                // 检查是否有分页数据
                if (data.results !== undefined && data.total !== undefined) {
                    // 分页接口返回的数据
                    allResults = data.results;
                    resultsTotal = data.total || 0;
                    resultsPages = data.pages || 0;
                    resultsTotalSuccess = data.total_success || 0;
                    resultsTotalFailed = data.total_failed || 0;
                    updateResultsStatistics();
                    renderResults();
                } else if (data.results && Array.isArray(data.results)) {
                    // 兼容旧接口（无分页参数时返回全部数据）
                    allResults = data.results;
                    resultsTotal = data.results.length;
                    resultsPages = 1;
                    resultsTotalSuccess = data.results.filter(r => r.success).length;
                    resultsTotalFailed = data.results.filter(r => !r.success).length;
                    updateResultsStatistics();
                    renderResults();
                } else {
                    showNotification('加载结果失败：数据格式错误', 'error');
                }
            } else {
                showNotification('加载结果失败：' + (err ? err.message : '未知错误'), 'error');
            }
        });
    }

    // 筛选结果（暂时保留，但不实现，因为需要后端支持）
    function filterResults(filter) {
        showNotification('筛选功能需要后端支持，暂时无法使用', 'info');
        // TODO: 实现后端筛选功能
    }

    // 渲染结果列表
    function renderResults() {
        const tbody = document.getElementById('results-table-body');
        tbody.innerHTML = '';
        
        if (allResults.length === 0) {
            const row = document.createElement('tr');
            row.innerHTML = '<td colspan="6" class="text-center text-muted">暂无结果数据</td>';
            tbody.appendChild(row);
            renderResultsPagination();
            return;
        }
        
        // 填充结果列表
        allResults.forEach((result, index) => {
            const row = document.createElement('tr');
            
            // 计算耗时：当前结果时间与上一个结果时间比较
            let executionTime = '-';
            if (result.timestamp) {
                const currentResultTime = new Date(result.timestamp);
                if (!isNaN(currentResultTime.getTime())) {
                    let previousTime = taskStartTime; // 默认使用任务开始时间
                    
                    // 如果有上一个结果，使用上一个结果的时间
                    if (index > 0) {
                        const prevResult = allResults[index - 1];
                        if (prevResult && prevResult.timestamp) {
                            previousTime = new Date(prevResult.timestamp);
                        }
                    }
                    
                    const durationMs = currentResultTime - previousTime;
                    const durationSeconds = Math.round(durationMs / 1000);
                    if (durationSeconds >= 0) {
                        executionTime = formatDuration(durationSeconds);
                    }
                }
            }
            
            row.innerHTML = `
                <td>${result.step_index + 1}</td>
                <td>
                    <div class="d-flex flex-wrap gap-1">
                        ${result.parameters.map((param, i) => 
                            `<span class="badge bg-secondary" style="font-size: 0.75rem;">${param}</span>`
                        ).join('')}
                    </div>
                </td>
                <td>
                    <div class="result-content">
                        ${result.result ? `<pre class="mb-0 small text-dark">${JSON.stringify(result.result, null, 2)}</pre>` : '<span class="text-muted">-</span>'}
                    </div>
                </td>
                <td>
                    <span class="badge ${result.success ? 'bg-success' : 'bg-danger'}">
                        <i class="bi ${result.success ? 'bi-check-circle' : 'bi-x-circle'}"></i>
                        ${result.success ? '成功' : '失败'}
                    </span>
                </td>
                <td>${formatTime(result.timestamp)}</td>
                <td>${executionTime}</td>
            `;
            tbody.appendChild(row);
        });
        
        // 渲染分页
        renderResultsPagination();
    }

    // 渲染结果分页
    function renderResultsPagination() {
        const pagination = document.getElementById('results-pagination');
        pagination.innerHTML = '';
        
        if (resultsPages <= 1) {
            // 如果只有一页或没有数据，显示总数信息
            if (resultsTotal > 0) {
                const infoLi = document.createElement('li');
                infoLi.className = 'page-item disabled';
                infoLi.innerHTML = `<span class="page-link">共 ${resultsTotal} 条结果</span>`;
                pagination.appendChild(infoLi);
            }
            return;
        }
        
        // 上一页
        const prevLi = document.createElement('li');
        prevLi.className = `page-item ${currentResultsPage === 1 ? 'disabled' : ''}`;
        prevLi.innerHTML = `<a class="page-link" href="#" onclick="event.preventDefault(); changeResultsPage(${currentResultsPage - 1});">上一页</a>`;
        pagination.appendChild(prevLi);
        
        // 页码
        const startPage = Math.max(1, currentResultsPage - 2);
        const endPage = Math.min(resultsPages, currentResultsPage + 2);
        
        // 如果起始页不是第一页，显示第一页和省略号
        if (startPage > 1) {
            const firstLi = document.createElement('li');
            firstLi.className = 'page-item';
            firstLi.innerHTML = `<a class="page-link" href="#" onclick="event.preventDefault(); changeResultsPage(1);">1</a>`;
            pagination.appendChild(firstLi);
            if (startPage > 2) {
                const ellipsisLi = document.createElement('li');
                ellipsisLi.className = 'page-item disabled';
                ellipsisLi.innerHTML = '<span class="page-link">...</span>';
                pagination.appendChild(ellipsisLi);
            }
        }
        
        for (let i = startPage; i <= endPage; i++) {
            const li = document.createElement('li');
            li.className = `page-item ${i === currentResultsPage ? 'active' : ''}`;
            li.innerHTML = `<a class="page-link" href="#" onclick="event.preventDefault(); changeResultsPage(${i});">${i}</a>`;
            pagination.appendChild(li);
        }
        
        // 如果结束页不是最后一页，显示省略号和最后一页
        if (endPage < resultsPages) {
            if (endPage < resultsPages - 1) {
                const ellipsisLi = document.createElement('li');
                ellipsisLi.className = 'page-item disabled';
                ellipsisLi.innerHTML = '<span class="page-link">...</span>';
                pagination.appendChild(ellipsisLi);
            }
            const lastLi = document.createElement('li');
            lastLi.className = 'page-item';
            lastLi.innerHTML = `<a class="page-link" href="#" onclick="event.preventDefault(); changeResultsPage(${resultsPages});">${resultsPages}</a>`;
            pagination.appendChild(lastLi);
        }
        
        // 下一页
        const nextLi = document.createElement('li');
        nextLi.className = `page-item ${currentResultsPage === resultsPages ? 'disabled' : ''}`;
        nextLi.innerHTML = `<a class="page-link" href="#" onclick="event.preventDefault(); changeResultsPage(${currentResultsPage + 1});">下一页</a>`;
        pagination.appendChild(nextLi);
        
        // 显示总数信息
        const infoLi = document.createElement('li');
        infoLi.className = 'page-item disabled';
        infoLi.innerHTML = `<span class="page-link">共 ${resultsTotal} 条结果</span>`;
        pagination.appendChild(infoLi);
    }

    // 切换结果页面
    function changeResultsPage(page) {
        if (page >= 1 && page <= resultsPages) {
            loadTaskResults(page);
        }
    }

    // 刷新结果
    function refreshResults() {
        loadTaskResults();
        showNotification('结果列表已刷新', 'info');
    }

    // 更新结果统计（使用后端返回的统计数据）
    function updateResultsStatistics() {
        const successCount = resultsTotalSuccess;
        const failedCount = resultsTotalFailed;
        const totalCount = resultsTotal;
        const successRate = totalCount > 0 ? Math.round((successCount / totalCount) * 100) : 0;

        document.getElementById('success-count').textContent = successCount;
        document.getElementById('failed-count').textContent = failedCount;
        document.getElementById('success-progress').style.width = successRate + '%';
    }

    // 取消任务
    function cancelTask() {
        if (confirm('确定要取消这个任务吗？')) {
            ajaxRequest(`/api/tasks/${currentTaskId}/cancel`, 'POST', null, function(err, data) {
                if (!err && data && data.status === 'success') {
                    showNotification('任务已取消', 'success');
                    loadTaskDetail(); // 刷新任务详情
                } else {
                    showNotification('取消任务失败: ' + (data ? data.message : '未知错误'), 'error');
                }
            });
        }
    }

    // 自动刷新相关变量（已在全局变量中声明）
    
    // 启动自动刷新
    function startAutoRefresh() {
        if (refreshInterval) {
            clearInterval(refreshInterval);
        }
        
        console.log(`启动自动刷新，每${getFrequencyText(currentRefreshFrequency)}刷新一次`);
        refreshInterval = setInterval(function() {
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
    window.addEventListener('beforeunload', function() {
        stopAutoRefresh();
    });

    // 绑定取消任务按钮事件
    document.addEventListener('click', function(e) {
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
        switch(status) {
            case 'completed': return 'bg-success';
            case 'error': return 'bg-danger';
            case 'running': return 'bg-primary';
            default: return 'bg-secondary';
        }
    }

    // 检查任务状态
    function checkTaskStatus() {
        const btn = document.getElementById('check-status-btn');
        const icon = btn.querySelector('i');
        
        // 添加旋转动画
        icon.style.animation = 'spin 1s linear infinite';
        btn.disabled = true;
        
        ajaxRequest(`/api/tasks/${currentTaskId}/status-check`, 'GET', null, function(err, data) {
            icon.style.animation = '';
            btn.disabled = false;
            
            if (!err && data && data.status === 'success') {
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
                showNotification('检查任务状态失败: ' + (data ? data.message : '未知错误'), 'error');
            }
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
        
        ajaxRequest(`/api/tasks/${currentTaskId}/restart`, 'POST', requestData, function(err, data) {
            if (data && data.status === 'success') {
                showNotification(`任务${action}成功`, 'success');
                // 刷新任务详情
                loadTaskDetail();
            } else {
                // 处理错误情况 - data可能包含错误信息，即使err存在
                const errorMessage = (data && data.message) ? data.message : (err ? err.message : '未知错误');
                showNotification(`${action}失败: ${errorMessage}`, 'error');
            }
        });
    }

    // 跳转到创建重启任务页面
    function goToCreateRestartTask() {
        const version = new URLSearchParams(window.location.search).get('version');
        const versionParam = version ? `&version=${encodeURIComponent(version)}` : '';
        window.location.href = `/google-sheet/create?restart_task_id=${encodeURIComponent(currentTaskId || '')}${versionParam}`;
    }

    // 创建新的重启任务
    function createRestartTask() {
        if (!confirm('确定要创建新的重启任务吗？这将基于当前任务的配置创建一个新任务。')) {
            return;
        }
        
        ajaxRequest(`/api/tasks/${currentTaskId}/create-restart`, 'POST', {}, function(err, data) {
            if (data && data.status === 'success') {
                showNotification(`新重启任务创建成功`, 'success');
                
                // 询问是否跳转到新任务
                if (confirm('是否跳转到新任务的详情页面？')) {
                    const version = new URLSearchParams(window.location.search).get('version');
                    const versionParam = version ? `&version=${encodeURIComponent(version)}` : '';
                    window.location.href = `/google-sheet/detail?task_id=${data.new_task_id}${versionParam}`;
                }
            } else {
                // 处理错误情况 - data可能包含错误信息，即使err存在
                const errorMessage = (data && data.message) ? data.message : (err ? err.message : '未知错误');
                showNotification(`创建重启任务失败: ${errorMessage}`, 'error');
            }
        });
    }

    // ========== 编辑配置相关函数 ==========
    
    // 打开编辑配置模态框
    function openEditConfigModal() {
        if (!currentTaskData) {
            showNotification('任务数据未加载', 'error');
            return;
        }
        
        const config = currentTaskData.config || {};
        
        // 填充基本信息
        document.getElementById('edit-task-name').value = currentTaskData.name || '';
        document.getElementById('edit-task-description').value = currentTaskData.description || '';
        
        // 填充Google Sheet配置
        document.getElementById('edit-spreadsheet-id').value = config.spreadsheet_id || '';
        document.getElementById('edit-sheet-name').value = config.sheet_name || '';
        document.getElementById('edit-token-file').value = config.token_file || 'data/token.json';
        document.getElementById('edit-proxy-url').value = config.proxy_url || '';
        
        // 填充位置配置
        document.getElementById('edit-param-positions').value = JSON.stringify(config.parameter_positions || []);
        document.getElementById('edit-check-positions').value = JSON.stringify(config.check_positions || []);
        document.getElementById('edit-result-positions').value = JSON.stringify(config.result_positions || []);
        
        // 填充参数配置
        loadParametersEditor(config.parameters || []);
        
        // 显示模态框
        if (editConfigModal) {
            editConfigModal.show();
        }
    }
    
    // 加载参数编辑器
    function loadParametersEditor(parameters) {
        const container = document.getElementById('parameters-editor');
        container.innerHTML = '';
        
        parameters.forEach((paramGroup, index) => {
            addParameterGroupToEditor(paramGroup, index);
        });
        
        // 如果没有参数，添加一个空组
        if (parameters.length === 0) {
            addParameterGroupToEditor([], 0);
        }
    }
    
    // 添加参数组到编辑器
    function addParameterGroupToEditor(paramValues = [], index = null) {
        const container = document.getElementById('parameters-editor');
        const actualIndex = index !== null ? index : container.children.length;
        
        const paramGroupDiv = document.createElement('div');
        paramGroupDiv.className = 'card mb-3';
        paramGroupDiv.setAttribute('data-param-index', actualIndex);
        
        const valuesStr = Array.isArray(paramValues) ? paramValues.join(', ') : '';
        
        paramGroupDiv.innerHTML = `
            <div class="card-body">
                <div class="d-flex justify-content-between align-items-center mb-2">
                    <h6 class="mb-0">参数组 ${actualIndex + 1}</h6>
                    <button type="button" class="btn btn-sm btn-danger" onclick="removeParameterGroup(${actualIndex})">
                        <i class="bi bi-trash"></i> 删除
                    </button>
                </div>
                <div class="mb-2">
                    <label class="form-label">参数值（用逗号分隔）</label>
                    <input type="text" class="form-control param-values" 
                           placeholder="例如: 1, 2, 3, 4, 5" 
                           value="${valuesStr}">
                    <small class="text-muted">这些值会组合生成多个参数组合</small>
                </div>
            </div>
        `;
        
        container.appendChild(paramGroupDiv);
    }
    
    // 添加参数组
    function addParameterGroup() {
        addParameterGroupToEditor([], null);
    }
    
    // 移除参数组
    function removeParameterGroup(index) {
        const container = document.getElementById('parameters-editor');
        const paramGroups = container.querySelectorAll('[data-param-index]');
        
        if (paramGroups.length <= 1) {
            showNotification('至少需要保留一个参数组', 'warning');
            return;
        }
        
        paramGroups.forEach(group => {
            if (parseInt(group.getAttribute('data-param-index')) === index) {
                group.remove();
            }
        });
        
        // 重新索引
        reindexParameterGroups();
    }
    
    // 重新索引参数组
    function reindexParameterGroups() {
        const container = document.getElementById('parameters-editor');
        const paramGroups = container.querySelectorAll('[data-param-index]');
        
        paramGroups.forEach((group, index) => {
            group.setAttribute('data-param-index', index);
            const title = group.querySelector('h6');
            if (title) {
                title.textContent = `参数组 ${index + 1}`;
            }
            const deleteBtn = group.querySelector('button[onclick^="removeParameterGroup"]');
            if (deleteBtn) {
                deleteBtn.setAttribute('onclick', `removeParameterGroup(${index})`);
            }
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
            
            // 收集Google Sheet配置
            const spreadsheetId = document.getElementById('edit-spreadsheet-id').value.trim();
            const sheetName = document.getElementById('edit-sheet-name').value.trim();
            const tokenFile = document.getElementById('edit-token-file').value.trim();
            const proxyUrl = document.getElementById('edit-proxy-url').value.trim();
            
            if (!spreadsheetId) {
                showNotification('请输入电子表格ID', 'error');
                return;
            }
            
            // 收集参数配置
            const parameters = [];
            const paramGroups = document.querySelectorAll('.param-values');
            paramGroups.forEach(input => {
                const valuesStr = input.value.trim();
                if (valuesStr) {
                    const values = valuesStr.split(',').map(v => {
                        const trimmed = v.trim();
                        // 尝试转换为数字
                        const num = parseFloat(trimmed);
                        return isNaN(num) ? trimmed : num;
                    });
                    parameters.push(values);
                }
            });
            
            if (parameters.length === 0) {
                showNotification('请至少添加一组参数', 'error');
                return;
            }
            
            // 解析位置配置
            let parameterPositions, checkPositions, resultPositions;
            try {
                parameterPositions = JSON.parse(document.getElementById('edit-param-positions').value || '[]');
                checkPositions = JSON.parse(document.getElementById('edit-check-positions').value || '[]');
                resultPositions = JSON.parse(document.getElementById('edit-result-positions').value || '[]');
            } catch (e) {
                showNotification('位置配置格式错误，请使用JSON数组格式', 'error');
                return;
            }
            
            // 构建完整配置
            const config = {
                spreadsheet_id: spreadsheetId,
                sheet_name: sheetName,
                token_file: tokenFile,
                proxy_url: proxyUrl,
                parameters: parameters,
                parameter_positions: parameterPositions,
                check_positions: checkPositions,
                result_positions: resultPositions
            };
            
            // 发送更新请求
            const requestData = {
                name: name,
                description: description,
                config: config
            };
            
            ajaxRequest(`/api/tasks/${currentTaskId}/config`, 'PUT', requestData, function(err, data) {
                if (!err && data && data.status === 'success') {
                    showNotification('配置更新成功', 'success');
                    
                    // 关闭模态框
                    if (editConfigModal) {
                        editConfigModal.hide();
                    }
                    
                    // 刷新任务详情
                    loadTaskDetail();
                } else {
                    const errorMessage = (data && data.message) ? data.message : (err ? err.message : '未知错误');
                    showNotification(`配置更新失败: ${errorMessage}`, 'error');
                }
            });
            
        } catch (e) {
            showNotification(`保存配置时出错: ${e.message}`, 'error');
            console.error('保存配置错误:', e);
        }
    }
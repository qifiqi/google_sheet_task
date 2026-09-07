// 页面脚本（templates/admin/logs.html 内联脚本原样抽离，F5 de-jinja）。
    let allLogs = [];
    let filteredLogs = [];
    let autoRefresh = true;
    let refreshInterval;

    // 页面加载完成后获取日志
    document.addEventListener('DOMContentLoaded', function() {
        // 延迟加载，确保DOM完全准备好
        setTimeout(function() {
            loadLogs();
        }, 100);
        
        // 从配置获取日志刷新间隔
        ajaxRequest('/api/config', 'GET', null, function(err, data) {
            const interval = (data && data.data.config && data.data.config.log_polling_interval) ? 
                            data.data.config.log_polling_interval : 5000;
            
            refreshInterval = setInterval(function() {
                if (autoRefresh) {
                    loadLogs();
                }
            }, interval);
        });
    });

    // 页面卸载时清理定时器
    window.addEventListener('beforeunload', function() {
        if (refreshInterval) {
            clearInterval(refreshInterval);
        }
        stopRealtimeUpdate();
    });

    function loadLogs() {
        // 显示加载状态
        showLoadingState();
        
        // 构建查询参数
        const params = new URLSearchParams();
        const levelFilterEl = document.getElementById('level-filter');
        const searchInputEl = document.getElementById('search-input');
        const dateFilterEl = document.getElementById('date-filter');
        
        const levelFilter = levelFilterEl ? levelFilterEl.value : '';
        const searchInput = searchInputEl ? searchInputEl.value : '';
        const dateFilter = dateFilterEl ? dateFilterEl.value : '';
        
        if (levelFilter) params.append('level', levelFilter);
        if (searchInput) params.append('search', searchInput);
        if (dateFilter) params.append('date', dateFilter);
        params.append('limit', '200'); // 获取更多日志
        
        // 调用真实的日志API
        console.log('开始加载日志，API URL:', `/api/logs?${params.toString()}`);
        
        ajaxRequest(`/api/logs?${params.toString()}`, 'GET', null, function(err, data) {
            hideLoadingState();
            
            console.log('日志API响应:', err, data);
            
            if (!err && data && data.status === 'success') {
                allLogs = (data.data && data.data.logs) || [];
                filteredLogs = allLogs; // 服务端已经过滤，直接使用
                console.log('加载到的日志数量:', allLogs.length);
                renderLogs();
                
                // 更新最后更新时间
                const lastUpdateEl = document.getElementById('last-update');
                if (lastUpdateEl) {
                    lastUpdateEl.textContent = formatTime(new Date().toISOString());
                }
            } else {
                console.error('日志加载失败:', err, data);
                showNotification('加载日志失败: ' + (data ? data.message : '未知错误'), 'error');
                
                // 如果API失败，显示空状态
                allLogs = [];
                filteredLogs = [];
                renderLogs();
            }
        });
    }

    function filterLogs() {
        // 重新加载数据，服务端处理过滤
        loadLogs();
    }

    function clearFilters() {
        document.getElementById('level-filter').value = '';
        document.getElementById('search-input').value = '';
        document.getElementById('date-filter').value = '';
        filterLogs();
    }

    function renderLogs() {
        const container = document.getElementById('log-container');
        const countBadge = document.getElementById('log-count');
        
        if (!container) {
            console.error('日志容器未找到');
            return;
        }
        
        if (countBadge) {
            countBadge.textContent = filteredLogs.length;
        }
        
        if (filteredLogs.length === 0) {
            container.innerHTML = '<div class="text-center text-muted">暂无日志</div>';
            return;
        }

        const logHtml = filteredLogs.map(log => {
            const time = formatTime(log.timestamp);
            const levelClass = getLevelClass(log.level);
            const level = (log.level || 'info').toUpperCase();
            const source = log.source ? `[${log.source}] ` : '';
            const lineText = `[${time}] [${level}] ${source}${log.message || ''}`;
            
            return `<div class="${levelClass}">${escapeHtml(lineText)}</div>`;
        }).join('');

        // 保存当前滚动位置
        const wasAtBottom = container.scrollTop + container.clientHeight >= container.scrollHeight - 5;
        
        container.innerHTML = logHtml;
        
        // 如果之前在底部，保持滚动到底部
        if (wasAtBottom) {
            container.scrollTop = container.scrollHeight;
        }
    }

    function getLevelClass(level) {
        switch (level) {
            case 'warning': return 'log-line-warning';
            case 'error': return 'log-line-error';
            case 'info': return 'log-line-info';
            default: return '';
        }
    }

    function escapeHtml(value) {
        return String(value)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;');
    }

    function refreshLogs() {
        loadLogs();
        showNotification('日志已刷新', 'success');
    }

    function clearLogs() {
        if (confirm('确定要清空所有日志吗？此操作不可恢复。')) {
            showNotification('清空日志功能暂未实现', 'warning');
            // TODO: 实现清空日志的API调用
            // 目前只是展示功能，不实际清空文件日志
        }
    }

    function downloadLogs() {
        if (filteredLogs.length === 0) {
            showNotification('没有日志可下载', 'warning');
            return;
        }

        const logText = filteredLogs.map(log => 
            `[${formatTime(log.timestamp)}] [${log.level.toUpperCase()}] [${log.source}] ${log.message}`
        ).join('\n');

        const blob = new Blob([logText], { type: 'text/plain' });
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `system_logs_${new Date().toISOString().split('T')[0]}.txt`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        window.URL.revokeObjectURL(url);

        showNotification('日志下载完成', 'success');
    }

    // 切换自动刷新
    function toggleAutoRefresh() {
        autoRefresh = !autoRefresh;
        const btn = document.getElementById('auto-refresh-btn');
        if (autoRefresh) {
            btn.innerHTML = '<i class="bi bi-pause-circle"></i> 暂停自动刷新';
            btn.className = 'btn btn-sm btn-outline-warning';
            startRealtimeUpdate();
        } else {
            btn.innerHTML = '<i class="bi bi-play-circle"></i> 开始自动刷新';
            btn.className = 'btn btn-sm btn-outline-success';
            stopRealtimeUpdate();
        }
    }

    // 实时更新相关变量
    let realtimeInterval = null;
    let lastLogTimestamp = null;

    // 开始实时更新
    function startRealtimeUpdate() {
        if (realtimeInterval) {
            clearInterval(realtimeInterval);
        }
        
        // 记录当前最新日志的时间戳
        if (filteredLogs.length > 0) {
            lastLogTimestamp = filteredLogs[0].timestamp;
        }
        
        // 从配置获取实时更新间隔
        ajaxRequest('/api/config', 'GET', null, function(err, data) {
            const interval = (data && data.data.config && data.data.config.log_realtime_interval) ? 
                            data.data.config.log_realtime_interval : 3000;
            
            realtimeInterval = setInterval(function() {
                fetchLatestLogs();
            }, interval);
        });
    }

    // 停止实时更新
    function stopRealtimeUpdate() {
        if (realtimeInterval) {
            clearInterval(realtimeInterval);
            realtimeInterval = null;
        }
    }

    // 获取最新日志
    function fetchLatestLogs() {
        const params = new URLSearchParams();
        if (lastLogTimestamp) {
            params.append('since', lastLogTimestamp);
        }
        params.append('limit', '20');
        
        ajaxRequest(`/api/logs/latest?${params.toString()}`, 'GET', null, function(err, data) {
            const apiLogs = (data && data.data && data.data.logs) || [];
            if (!err && data && data.status === 'success' && apiLogs.length > 0) {
                // 添加新日志到现有列表的顶部
                const newLogs = apiLogs;
                
                // 更新最新时间戳
                if (newLogs.length > 0) {
                    lastLogTimestamp = newLogs[newLogs.length - 1].timestamp;
                }
                
                // 将新日志添加到列表开头（因为我们是倒序显示）
                filteredLogs = newLogs.reverse().concat(filteredLogs);
                
                // 限制总数以避免内存占用过多
                if (filteredLogs.length > 500) {
                    filteredLogs = filteredLogs.slice(0, 500);
                }
                
                // 重新渲染
                renderLogs();
                
                // 显示新日志通知
                if (newLogs.length > 0) {
                    showNotification(`收到 ${newLogs.length} 条新日志`, 'info');
                }
            }
        });
    }

    // 显示加载状态
    function showLoadingState() {
        const container = document.getElementById('log-container');
        if (container) {
            container.innerHTML = `
                <div class="text-center py-5">
                    <div class="spinner-border text-primary" role="status">
                        <span class="visually-hidden">加载中...</span>
                    </div>
                    <div class="mt-2 text-muted">正在加载日志...</div>
                </div>
            `;
        } else {
            console.error('日志容器未找到: log-container');
        }
    }

    // 隐藏加载状态
    function hideLoadingState() {
        // 加载状态会被renderLogs覆盖，这里不需要特殊处理
    }

    // 格式化时间
    function formatTime(dateString) {
        if (!dateString) return '-';
        try {
            const date = new Date(dateString);
            return date.toLocaleString('zh-CN', {
                year: 'numeric',
                month: '2-digit',
                day: '2-digit',
                hour: '2-digit',
                minute: '2-digit',
                second: '2-digit'
            });
        } catch (e) {
            return dateString;
        }
    }

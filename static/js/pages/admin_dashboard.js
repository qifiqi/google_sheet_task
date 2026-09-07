// 页面脚本（templates/admin/dashboard.html 内联脚本原样抽离，F5 de-jinja）。
    let dashboardCharts = {};
    let dashboardRefreshTimer = null;

    function upsertChart(key, canvasId, config) {
        if (dashboardCharts[key]) {
            dashboardCharts[key].destroy();
        }
        const ctx = document.getElementById(canvasId).getContext('2d');
        dashboardCharts[key] = new Chart(ctx, config);
    }

    function normalizeTaskType(taskType) {
        const normalizedType = String(taskType || '').trim().toLowerCase();
        if (['google_sheet', 'google_sheet_c3', 'google_sheet_c31'].includes(normalizedType)) {
            return 'google_sheet';
        }
        if (normalizedType === 'google_sheet_c4') {
            return 'google_sheet_c4';
        }
        if (normalizedType === 'google_sheet_c5') {
            return 'google_sheet_c5';
        }
        if (['backtest_training', 'backtest'].includes(normalizedType)) {
            return 'backtest_training';
        }
        if (['backtest_multi_product', 'multi_product_backtest', 'backtest_multi'].includes(normalizedType)) {
            return 'backtest_multi_product';
        }
        return normalizedType;
    }

    function getGoogleSheetVersion(taskType) {
        const normalizedType = normalizeTaskType(taskType);
        if (normalizedType === 'google_sheet_c5') {
            return 'c5';
        }
        if (normalizedType === 'google_sheet_c4') {
            return 'c4';
        }
        if (normalizedType === 'google_sheet') {
            return 'c3';
        }
        return '';
    }

    function buildTaskDetailUrl(task) {
        const taskId = task && task.id ? task.id : '';
        const normalizedType = normalizeTaskType(task && task.task_type);

        if (normalizedType === 'backtest_training') {
            return `/backtest-training/detail/${encodeURIComponent(taskId)}`;
        }
        if (normalizedType === 'backtest_multi_product') {
            return `/backtest-multi-product/detail/${encodeURIComponent(taskId)}`;
        }

        const params = new URLSearchParams({ task_id: taskId });
        const version = getGoogleSheetVersion(normalizedType);
        if (version) {
            params.set('version', version);
        }
        return `/google-sheet/detail?${params.toString()}`;
    }

    function renderSummary(summary) {
        document.getElementById('summary-total').textContent = summary.total_tasks || 0;
        document.getElementById('summary-completed').textContent = summary.completed_tasks || 0;
        document.getElementById('summary-running').textContent = summary.running_tasks || 0;
        document.getElementById('summary-error').textContent = summary.error_tasks || 0;
        document.getElementById('summary-cancelled').textContent = summary.cancelled_tasks || 0;
        document.getElementById('summary-pending').textContent = summary.pending_tasks || 0;
    }

    function renderTrendChart(items) {
        upsertChart('trend', 'taskTrendChart', {
            type: 'line',
            data: {
                labels: items.map(item => item.date),
                datasets: [
                    {
                        label: '创建任务',
                        data: items.map(item => item.created),
                        borderColor: '#0d6efd',
                        backgroundColor: 'rgba(13, 110, 253, 0.15)',
                        fill: true,
                        tension: 0.3
                    },
                    {
                        label: '完成任务',
                        data: items.map(item => item.completed),
                        borderColor: '#198754',
                        backgroundColor: 'rgba(25, 135, 84, 0.12)',
                        fill: true,
                        tension: 0.3
                    }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: { legend: { position: 'top' } }
            }
        });
    }

    function renderDoughnutChart() {
        const statusData = window.dashboardData.status_distribution || {};
        upsertChart('status', 'taskStatusChart', {
            type: 'doughnut',
            data: {
                labels: Object.keys(statusData),
                datasets: [{
                    data: Object.values(statusData),
                    backgroundColor: ['#0d6efd', '#198754', '#ffc107', '#dc3545', '#6c757d', '#20c997']
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: { legend: { position: 'bottom' } }
            }
        });
    }

    function renderTypeChart() {
        const typeData = window.dashboardData.task_type_distribution || {};
        upsertChart('type', 'taskTypeChart', {
            type: 'bar',
            data: {
                labels: Object.keys(typeData),
                datasets: [{
                    label: '任务数',
                    data: Object.values(typeData),
                    backgroundColor: '#6f42c1'
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                indexAxis: 'y',
                plugins: { legend: { display: false } }
            }
        });
    }

    function renderActiveTasks(tasks) {
        const container = document.getElementById('active-task-list');
        if (!tasks.length) {
            container.innerHTML = '<div class="col-12 text-muted">当前没有运行中的任务。</div>';
            return;
        }

        container.innerHTML = tasks.map(task => `
            <div class="col-md-6">
                <div class="border rounded p-3 h-100">
                    <div class="d-flex justify-content-between align-items-start mb-2">
                        <div>
                            <div class="fw-semibold">${task.name}</div>
                            <div class="small text-muted">${task.task_type}</div>
                        </div>
                        <span class="${getStatusClass(task.status)}">${getStatusText(task.status)}</span>
                    </div>
                    <div class="small text-muted mb-2">参数组: ${task.config_summary.parameter_groups || 0}</div>
                    <div class="progress mb-2" style="height: 18px;">
                        <div class="progress-bar" style="width:${task.progress_percentage || 0}%">${task.current_step || 0}/${task.total_steps || 0}</div>
                    </div>
                    <div class="small mb-1">停止请求: ${task.stop_confirmation.stop_requested ? '<span class="text-warning">已发出</span>' : '<span class="text-muted">未发出</span>'}</div>
                    <div class="small mb-2">完全停止: ${task.stop_confirmation.stop_confirmed ? '<span class="text-success">是</span>' : '<span class="text-muted">否</span>'}</div>
                    <a class="btn btn-sm btn-outline-primary" href="${buildTaskDetailUrl(task)}">查看详情</a>
                </div>
            </div>
        `).join('');
    }

    function renderRecentTasks(tasks) {
        const tbody = document.getElementById('recent-task-table');
        tbody.innerHTML = tasks.map(task => `
            <tr>
                <td>
                    <div class="fw-semibold">${task.name}</div>
                    <div class="small text-muted">${task.task_type}</div>
                </td>
                <td><span class="${getStatusClass(task.status)}">${getStatusText(task.status)}</span></td>
                <td>
                    ${task.stop_confirmation.stop_confirmed
                        ? '<span class="badge bg-success">已完全停止</span>'
                        : (task.stop_confirmation.stop_requested
                            ? '<span class="badge bg-warning text-dark">停止中</span>'
                            : '<span class="badge bg-secondary">未停止</span>')}
                </td>
                <td>${task.config_summary.parameter_groups || 0}</td>
                <td style="min-width:160px;">
                    <div class="progress" style="height: 18px;">
                        <div class="progress-bar" style="width:${task.progress_percentage || 0}%">${task.current_step || 0}/${task.total_steps || 0}</div>
                    </div>
                </td>
                <td>${task.duration_seconds != null ? task.duration_seconds + 's' : '-'}</td>
                <td>${formatTime(task.created_at)}</td>
                <td><a class="btn btn-sm btn-outline-info" href="${buildTaskDetailUrl(task)}">查看</a></td>
            </tr>
        `).join('');
    }

    function loadDashboard(showToast = false) {
        ajaxRequest('/admin/api/dashboard/overview', 'GET', null, function(err, data) {
            const overview = data && data.data ? data.data : null;
            if (err || !overview || !overview.success) {
                showNotification('加载仪表盘失败', 'error');
                return;
            }

            window.dashboardData = overview;
            renderSummary(overview.summary || {});
            renderTrendChart(overview.daily_trend || []);
            renderDoughnutChart();
            renderTypeChart();
            renderActiveTasks(overview.active_tasks || []);
            renderRecentTasks(overview.recent_tasks || []);
            document.getElementById('dashboard-last-update').textContent = formatTime(overview.checked_at);

            if (showToast) {
                showNotification('仪表盘已刷新', 'success');
            }
        });
    }

    document.addEventListener('DOMContentLoaded', function() {
        loadDashboard(false);
        ajaxRequest('/api/config', 'GET', null, function(err, data) {
            const interval = (data && data.data.config && data.data.config.dashboard_refresh_interval)
                ? data.data.config.dashboard_refresh_interval
                : 30000;
            dashboardRefreshTimer = setInterval(loadDashboard, interval);
        });
    });

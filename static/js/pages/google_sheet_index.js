// Google Sheet 首页（templates/google_sheet/index.html 的页面逻辑）。
// 自 google_sheet/index.html 内联脚本原样抽离；接口调用经 common/api.js。

// ── 原 Jinja 服务端渲染点的前端等价实现（静态化，docs/design/frontend-refactor/03 §5）──
// 原 title：`首页 - Google Sheet {{ request.args.get('version') }}`（缺 version 时渲染字面 "None"）
const versionParam = new URLSearchParams(location.search).get('version');
// 无 version 的「首页」按 C3 列表渲染（下方 version 兜底），标题如实标 C3 而不是 None
const VERSION_LABELS = { c3: 'C3', c4: 'C4', c5: 'C5', c7: 'C7', c1_1: 'C1.1.0' };
const displayVersionParam = VERSION_LABELS[versionParam || 'c3'] || versionParam;
document.title = '首页 - Google Sheet ' + displayVersionParam;
(function () {
    // 原 `<h3>{{ version }} 任务管理</h3>`
    const heading = document.querySelector('h3.text-primary.fw-bold.mb-2');
    if (heading) {
        heading.textContent = displayVersionParam + ' 任务管理';
    }
    const scopeHint = document.getElementById('filter-scope-hint');
    if (scopeHint) {
        scopeHint.textContent = '仅搜 ' + displayVersionParam;
    }
    // 原 `{% if version == 'c3' %}` 包住的「合并导出 / 创建批量任务」两个按钮：
    // 仅 ?version=c3 时保留，其余一律移除（与原服务端条件渲染逐字节一致）。
    if (versionParam !== 'c3') {
        document.querySelectorAll('a[href="/google-sheet/merge-export"], a[href="/google-sheet/create?version=c31"]')
            .forEach(function (a) { a.remove(); });
    }
    // 原 `url_for('google_sheet.create', version=request.args.get('version'))`
    if (versionParam !== null) {
        const createLink = document.querySelector('.col-lg-8 a.btn-primary.btn-lg');
        if (createLink) {
            createLink.href = '/google-sheet/create?version=' + encodeURIComponent(versionParam);
        }
    }
})();

    // 全局变量
    const localUrlObj = new URL(window.location.href);
    let version = localUrlObj.searchParams.get('version') || 'c3';
    let upper_version = version.toUpperCase();
    let display_version = version === 'c1_1' ? 'C1.1.0' : upper_version;
    let allTasks = [];
    let currentPage = 1;
    let tasksPerPage = 10;
    let currentFilter = 'all';
    let task_type = upper_version === "C3" ? "google_sheet" : `google_sheet_${upper_version}`;
    let serverPagination = { page: 1, per_page: 10, total: 0, pages: 0, has_prev: false, has_next: false };
    let serverStatistics = {};
    let isLoadingTasks = false;
    let _previousPendingView = null;
    let advancedFilters = { keyword: '', stock_code: '', token_name: '', start_date: '', end_date: '' };
    console.log(task_type);

    const ADVANCED_FILTER_INPUTS = {
        keyword: 'keyword-filter-input',
        stock_code: 'stock-code-filter-input',
        token_name: 'token-filter-input',
        start_date: 'start-date-filter-input',
        end_date: 'end-date-filter-input',
    };
    // 同一模板服务首页与各单版本页：跨版本提示只覆盖 Sheet 系任务（回测任务有独立页面）
    const SHEET_VERSION_TYPES = [
        { version: 'c3', task_type: 'google_sheet', label: 'C3' },
        { version: 'c4', task_type: 'google_sheet_C4', label: 'C4' },
        { version: 'c5', task_type: 'google_sheet_C5', label: 'C5' },
        { version: 'c7', task_type: 'google_sheet_C7', label: 'C7' },
        { version: 'c1_1', task_type: 'google_sheet_C1_1', label: 'C1.1' },
    ];

    function getTaskVersion(task) {
        const normalizedType = String(task && task.task_type ? task.task_type : '').toLowerCase();
        if (normalizedType === 'google_sheet_c5') return 'c5';
        if (normalizedType === 'google_sheet_c4') return 'c4';
        if (normalizedType === 'google_sheet_c1_1') return 'c1_1';
        if (normalizedType === 'google_sheet') return 'c3';
        return version || 'c3';
    }

    function buildTaskDetailUrl(task) {
        const taskVersion = getTaskVersion(task);
        return `/google-sheet/detail?task_id=${encodeURIComponent(task.id)}&version=${encodeURIComponent(taskVersion)}`;
    }

    // 页面加载完成后启动任务列表轮询
    document.addEventListener('DOMContentLoaded', function() {
        restoreUserPreferences();
        loadStateFromUrl();
        loadTasks(true);

        Api.endpoints.config.get().then(function(data) {
            const interval = (data && data.config && data.config.frontend_polling_interval) ?
                            data.config.frontend_polling_interval : 15000;
            setIntervalVisible(loadTasks, interval);
        }).catch(function() {
            // 原 ajaxRequest 失败回调同样落到默认 15000ms 轮询
            setIntervalVisible(loadTasks, 15000);
        });

        window.addEventListener('popstate', function(event) {
            loadStateFromUrl();
            loadTasks();
        });

        const pageJumpInput = document.getElementById('page-jump-input');
        if (pageJumpInput) {
            pageJumpInput.addEventListener('keypress', function(e) {
                if (e.key === 'Enter') {
                    e.preventDefault();
                    jumpToPage();
                }
            });
            pageJumpInput.addEventListener('input', function(e) {
                this.value = this.value.replace(/[^0-9]/g, '');
            });
        }
    });

    // 从URL参数加载状态
    function loadStateFromUrl() {
        const urlParams = new URLSearchParams(window.location.search);
        const page = urlParams.get('page');
        const filter = urlParams.get('filter');

        if (page && !isNaN(page) && parseInt(page) > 0) {
            currentPage = parseInt(page);
        }
        if (filter && ['all', 'running', 'completed', 'error', 'cancelled', 'pending'].includes(filter)) {
            currentFilter = filter;
        }

        const filterSelect = document.getElementById('filter-select');
        if (filterSelect) {
            filterSelect.value = currentFilter;
        }

        Object.keys(ADVANCED_FILTER_INPUTS).forEach(function(key) {
            const value = urlParams.get(key) || '';
            advancedFilters[key] = value;
            const input = document.getElementById(ADVANCED_FILTER_INPUTS[key]);
            if (input) {
                input.value = value;
            }
        });
    }

    // 更新URL参数（含高级筛选，保证刷新/收藏/跨版本跳转后条件不丢）
    function updateUrl() {
        const url = new URL(window.location);
        url.searchParams.set('page', currentPage);
        url.searchParams.set('filter', currentFilter);
        Object.keys(ADVANCED_FILTER_INPUTS).forEach(function(key) {
            const value = (advancedFilters[key] || '').trim();
            if (value) {
                url.searchParams.set(key, value);
            } else {
                url.searchParams.delete(key);
            }
        });
        window.history.pushState({}, '', url);
    }

    // 高级筛选参数（不含 status/filter，供列表请求与跨版本提示复用）
    function buildAdvancedFilterParams() {
        const params = new URLSearchParams();
        Object.keys(ADVANCED_FILTER_INPUTS).forEach(function(key) {
            const value = (advancedFilters[key] || '').trim();
            if (value) {
                params.set(key, value);
            }
        });
        return params;
    }

    function hasAdvancedFilters() {
        return Array.from(buildAdvancedFilterParams().keys()).length > 0;
    }

    // 从服务端获取任务列表（服务端分页+筛选）
    function loadTasks(checkPending = false) {
        if (isLoadingTasks) return;
        isLoadingTasks = true;

        const params = new URLSearchParams({
            task_type: task_type,
            page: currentPage,
            per_page: tasksPerPage,
        });
        if (currentFilter !== 'all') {
            params.set('status', currentFilter);
        }
        buildAdvancedFilterParams().forEach(function(value, key) {
            params.set(key, value);
        });

        Api.endpoints.task.list(params.toString()).then(function(data) {
            isLoadingTasks = false;
            if (data && data.items) {
                allTasks = data.items;
                const pg = data;
                serverPagination = {
                    page: pg.current_page, per_page: pg.per_page, total: pg.total,
                    pages: pg.pages, has_prev: pg.current_page > 1, has_next: pg.current_page < pg.pages,
                };
                serverStatistics = data.statistics || {};

                updateStatisticsFromServer(serverStatistics);
                renderTasks();

                if (checkPending) {
                    checkPendingTasks();
                }
            }
        }).catch(function() {
            // 原 ajaxRequest 错误回调：静默忽略，等待下一轮轮询
            isLoadingTasks = false;
        });
    }

    // 筛选任务（服务端筛选，重置到第一页）
    function filterTasks(filter) {
        currentFilter = filter;
        currentPage = 1;
        updateUrl();
        loadTasks();
    }

    // 高级筛选（关键字/股票代码/Token/创建日期）：服务端过滤，重置到第一页
    function readAdvancedFilterInputs() {
        return {
            keyword: document.getElementById('keyword-filter-input').value || '',
            stock_code: document.getElementById('stock-code-filter-input').value || '',
            token_name: document.getElementById('token-filter-input').value || '',
            start_date: document.getElementById('start-date-filter-input').value || '',
            end_date: document.getElementById('end-date-filter-input').value || ''
        };
    }

    function applyAdvancedFilters() {
        advancedFilters = readAdvancedFilterInputs();
        currentPage = 1;
        updateUrl();
        loadTasks();
    }

    function resetAdvancedFilters() {
        document.getElementById('keyword-filter-input').value = '';
        document.getElementById('stock-code-filter-input').value = '';
        document.getElementById('token-filter-input').value = '';
        document.getElementById('start-date-filter-input').value = '';
        document.getElementById('end-date-filter-input').value = '';
        advancedFilters = { keyword: '', stock_code: '', token_name: '', start_date: '', end_date: '' };
        currentPage = 1;
        updateUrl();
        loadTasks();
    }

    // 渲染任务列表
    function renderTasks() {
        const tbody = document.getElementById('tasks-table-body');
        tbody.innerHTML = '';

        allTasks.forEach(function(task) {
            const row = document.createElement('tr');
            const typeLabel = task.task_type === task_type ? display_version : '默认';
            const typeBadgeClass = task.task_type === task_type ? 'bg-warning' : 'bg-secondary';
            const tokenName = getTaskTokenName(task);

            row.innerHTML = `
                <td>
                    <div class="fw-bold">
                        ${task.name}
                        <span class="badge ${typeBadgeClass} ms-1">${typeLabel}</span>
                    </div>
                    ${tokenName ? `<div><small class="text-muted">Token: ${escapeHtml(tokenName)}</small></div>` : ''}
                    ${task.description ? `<small class="text-muted">${task.description}</small>` : ''}
                </td>
                <td><span class="badge ${getStatusClass(task.status)}">${getStatusText(task.status)}</span></td>
                <td>${task.current_step}/${task.total_steps}</td>
                <td>${formatTime(task.start_time)}</td>
                <td>${formatTime(task.end_time)}</td>
                <td>
                    <div class="btn-group" role="group">
                        <a href="${buildTaskDetailUrl(task)}" class="btn btn-sm btn-info">
                            <i class="bi bi-eye"></i> 查看
                        </a>
                        ${task.status === 'running' ? `
                            <button class="btn btn-sm btn-warning cancel-task" data-task-id="${task.id}">
                                <i class="bi bi-stop-circle"></i> 停止
                            </button>
                        ` : (task.status === 'completed' || task.status === 'error') ? `
                            <button class="btn btn-sm btn-danger delete-task" data-task-id="${task.id}">
                                <i class="bi bi-trash"></i> 删除
                            </button>
                        ` : ''}
                    </div>
                </td>
            `;
            tbody.appendChild(row);
        });

        if (allTasks.length === 0) {
            renderEmptyState(tbody);
        }

        bindTaskEvents();
        renderPagination();
    }

    // 空结果提示：说明列表只覆盖当前版本，并在其他版本有匹配时给出直达链接
    function renderEmptyState(tbody) {
        const row = document.createElement('tr');
        const cell = document.createElement('td');
        cell.colSpan = 6;
        cell.className = 'text-center text-muted py-4';
        cell.textContent = (hasAdvancedFilters() || currentFilter !== 'all')
            ? `当前 ${display_version} 视图下没有匹配的任务`
            : `当前 ${display_version} 视图暂无任务`;

        if (hasAdvancedFilters()) {
            const hint = document.createElement('div');
            hint.className = 'small mt-2';
            cell.appendChild(hint);
            fillCrossVersionHint(hint);
        }

        row.appendChild(cell);
        tbody.appendChild(row);
    }

    function fillCrossVersionHint(container) {
        const targets = SHEET_VERSION_TYPES.filter(function(item) {
            return item.task_type !== task_type;
        });
        const filterParams = buildAdvancedFilterParams();

        Promise.all(targets.map(function(item) {
            const query = new URLSearchParams(filterParams);
            query.set('task_type', item.task_type);
            if (currentFilter !== 'all') {
                query.set('status', currentFilter);
            }
            query.set('page', '1');
            query.set('per_page', '1');
            return Api.endpoints.task.list(query.toString()).then(function(data) {
                return { item: item, total: (data && data.total) || 0 };
            }).catch(function() {
                return { item: item, total: 0 };
            });
        })).then(function(results) {
            if (!container.isConnected) return;
            const hits = results.filter(function(result) { return result.total > 0; });
            if (hits.length === 0) {
                container.textContent = '其他版本也没有匹配';
                return;
            }
            container.textContent = '其他版本有匹配：';
            hits.forEach(function(hit, index) {
                if (index > 0) {
                    container.appendChild(document.createTextNode(' · '));
                }
                const link = document.createElement('a');
                const linkQuery = new URLSearchParams(filterParams);
                linkQuery.set('version', hit.item.version);
                linkQuery.set('filter', currentFilter);
                link.href = '/google-sheet/?' + linkQuery.toString();
                link.textContent = hit.item.label + '（' + hit.total + ' 条）';
                container.appendChild(link);
            });
        });
    }

    function getTaskTokenName(task) {
        if (!task || !task.config || typeof task.config !== 'object') return '';
        return task.config.token_name || '';
    }

    function bindTaskEvents() {
        document.querySelectorAll('.cancel-task').forEach(function(btn) {
            btn.addEventListener('click', function() {
                cancelTask(this.getAttribute('data-task-id'));
            });
        });
        document.querySelectorAll('.delete-task').forEach(function(btn) {
            btn.addEventListener('click', function() {
                deleteTask(this.getAttribute('data-task-id'));
            });
        });
    }

    // 渲染分页（基于服务端 pagination 数据）
    function renderPagination() {
        const pagination = document.getElementById('pagination');
        const paginationInfo = document.getElementById('pagination-info');
        const pageJumpInput = document.getElementById('page-jump-input');

        pagination.innerHTML = '';

        const p = serverPagination;
        const totalPages = p.pages || 0;
        const total = p.total || 0;
        const startIndex = total > 0 ? (p.page - 1) * p.per_page + 1 : 0;
        const endIndex = Math.min(p.page * p.per_page, total);

        if (total === 0) {
            paginationInfo.textContent = '暂无数据';
        } else {
            paginationInfo.textContent = `显示第 ${startIndex}-${endIndex} 条，共 ${total} 条记录`;
        }

        if (pageJumpInput) {
            pageJumpInput.max = totalPages;
            pageJumpInput.value = '';
            pageJumpInput.placeholder = totalPages > 0 ? `1-${totalPages}` : '页';
        }

        if (totalPages <= 1) {
            pagination.parentElement.style.display = totalPages === 0 ? 'none' : 'block';
            return;
        }

        pagination.parentElement.style.display = 'block';

        // 上一页
        const prevLi = document.createElement('li');
        prevLi.className = `page-item ${!p.has_prev ? 'disabled' : ''}`;
        prevLi.innerHTML = `<a class="page-link" href="#" onclick="changePage(${currentPage - 1})">上页</a>`;
        pagination.appendChild(prevLi);

        // 页码范围
        const maxVisiblePages = 7;
        let startPage, endPage;
        if (totalPages <= maxVisiblePages) {
            startPage = 1;
            endPage = totalPages;
        } else {
            const halfVisible = Math.floor(maxVisiblePages / 2);
            if (currentPage <= halfVisible) {
                startPage = 1;
                endPage = maxVisiblePages;
            } else if (currentPage + halfVisible >= totalPages) {
                startPage = totalPages - maxVisiblePages + 1;
                endPage = totalPages;
            } else {
                startPage = currentPage - halfVisible;
                endPage = currentPage + halfVisible;
            }
        }

        if (startPage > 1) {
            const firstLi = document.createElement('li');
            firstLi.className = 'page-item';
            firstLi.innerHTML = `<a class="page-link" href="#" onclick="changePage(1)">1</a>`;
            pagination.appendChild(firstLi);
            if (startPage > 2) {
                const ellipsisLi = document.createElement('li');
                ellipsisLi.className = 'page-item disabled';
                ellipsisLi.innerHTML = `<span class="page-link">...</span>`;
                pagination.appendChild(ellipsisLi);
            }
        }

        for (let i = startPage; i <= endPage; i++) {
            const li = document.createElement('li');
            li.className = `page-item ${i === currentPage ? 'active' : ''}`;
            li.innerHTML = `<a class="page-link" href="#" onclick="changePage(${i})">${i}</a>`;
            pagination.appendChild(li);
        }

        if (endPage < totalPages) {
            if (endPage < totalPages - 1) {
                const ellipsisLi = document.createElement('li');
                ellipsisLi.className = 'page-item disabled';
                ellipsisLi.innerHTML = `<span class="page-link">...</span>`;
                pagination.appendChild(ellipsisLi);
            }
            const lastLi = document.createElement('li');
            lastLi.className = 'page-item';
            lastLi.innerHTML = `<a class="page-link" href="#" onclick="changePage(${totalPages})">${totalPages}</a>`;
            pagination.appendChild(lastLi);
        }

        // 下一页
        const nextLi = document.createElement('li');
        nextLi.className = `page-item ${!p.has_next ? 'disabled' : ''}`;
        nextLi.innerHTML = `<a class="page-link" href="#" onclick="changePage(${currentPage + 1})">下页</a>`;
        pagination.appendChild(nextLi);
    }

    // 切换页面（服务端分页）
    function changePage(page) {
        const totalPages = serverPagination.pages || 1;
        if (page >= 1 && page <= totalPages) {
            currentPage = page;
            updateUrl();
            loadTasks();
        }
    }

    // 改变每页显示数量
    function changePageSize() {
        const pageSizeSelect = document.getElementById('page-size-select');
        const newPageSize = parseInt(pageSizeSelect.value);
        const currentFirstRecord = (currentPage - 1) * tasksPerPage + 1;
        const newPage = Math.ceil(currentFirstRecord / newPageSize);

        tasksPerPage = newPageSize;
        currentPage = newPage;

        updateUrl();
        loadTasks();
        localStorage.setItem('tasksPerPage', tasksPerPage);
    }

    // 跳转到指定页面
    function jumpToPage() {
        const pageJumpInput = document.getElementById('page-jump-input');
        const targetPage = parseInt(pageJumpInput.value);
        const totalPages = serverPagination.pages || 1;

        if (isNaN(targetPage)) {
            showNotification('请输入有效的页码', 'warning');
            return;
        }
        if (targetPage < 1 || targetPage > totalPages) {
            showNotification(`页码必须在 1 到 ${totalPages} 之间`, 'warning');
            return;
        }

        changePage(targetPage);
        pageJumpInput.value = '';
    }

    // 从localStorage恢复用户偏好
    function restoreUserPreferences() {
        const savedPageSize = localStorage.getItem('tasksPerPage');
        if (savedPageSize) {
            tasksPerPage = parseInt(savedPageSize);
            const pageSizeSelect = document.getElementById('page-size-select');
            if (pageSizeSelect) {
                pageSizeSelect.value = tasksPerPage;
            }
        }
    }

    // 刷新任务
    function refreshTasks() {
        loadTasks();
        showNotification('任务列表已刷新', 'info');
    }

    // 使用后端统计数据更新统计卡片
    function updateStatisticsFromServer(stats) {
        if (!stats) return;

        safeUpdateElement('total-tasks', stats.total_tasks || 0);
        safeUpdateElement('completed-tasks', stats.completed_tasks || 0);
        safeUpdateElement('running-tasks', stats.running_tasks || 0);
        safeUpdateElement('error-tasks', stats.error_tasks || 0);
        safeUpdateElement('today-new', stats.today_new_tasks || 0);
        safeUpdateElement('success-rate', `${stats.success_rate || 0}%`);
        safeUpdateElement('error-rate', `${stats.error_rate || 0}%`);

        const avg = stats.avg_duration_minutes || 0;
        safeUpdateElement('avg-duration', avg > 60
            ? `${Math.round(avg / 60)}小时${avg % 60}分钟`
            : `${avg}分钟`);

        updateProgressBars(stats);
    }

    function safeUpdateElement(id, value) {
        const element = document.getElementById(id);
        if (element) {
            element.textContent = value;
        }
    }

    // 更新进度条（使用后端统计数据 + 正确的卡片ID选择器）
    function updateProgressBars(stats) {
        const total = stats.total_tasks || 0;
        const completed = stats.completed_tasks || 0;
        const running = stats.running_tasks || 0;
        const error = stats.error_tasks || 0;

        const progressBars = [
            {selector: '#total-tasks-card .progress-bar', progress: total > 0 ? (completed / total * 100) : 0},
            {selector: '#completed-tasks-card .progress-bar', progress: (completed + error) > 0 ? (completed / (completed + error) * 100) : 0},
            {selector: '#running-tasks-card .progress-bar', progress: total > 0 ? (running / total * 100) : 0},
            {selector: '#error-tasks-card .progress-bar', progress: total > 0 ? (error / total * 100) : 0}
        ];

        progressBars.forEach(({selector, progress}) => {
            const element = document.querySelector(selector);
            if (element) {
                const safeProgress = Math.min(Math.max(progress, 0), 100);
                element.style.width = `${safeProgress}%`;
                element.setAttribute('aria-valuenow', safeProgress.toFixed(1));
                element.style.transition = 'width 0.6s ease';
            }
        });
    }

    // 取消任务
    function cancelTask(taskId) {
        if (confirm('确定要停止这个任务吗？')) {
            Api.endpoints.task.cancel(taskId).then(function() {
                showNotification('任务已停止', 'success');
                loadTasks();
            }).catch(function(err) {
                showNotification('停止任务失败: ' + (err && err.message ? err.message : '未知错误'), 'error');
                loadTasks(); // 任务可能已被结束（竞态），刷新列表消除过期的取消入口
            });
        }
    }

    // 删除任务
    function deleteTask(taskId) {
        if (confirm('确定要删除这个任务吗？删除后无法恢复！')) {
            Api.endpoints.task.remove(taskId).then(function() {
                showNotification('任务已删除', 'success');
                loadTasks();
            }).catch(function(err) {
                showNotification('删除任务失败: ' + (err && err.message ? err.message : '未知错误'), 'error');
            });
        }
    }

    // 检查待重启的任务（使用后端统计数据）
    function checkPendingTasks() {
        const pendingCount = serverStatistics.pending_tasks || 0;
        if (pendingCount > 0) {
            const alertDiv = document.getElementById('pending-tasks-alert');
            const messageSpan = document.getElementById('pending-tasks-message');
            messageSpan.textContent = `检测到 ${pendingCount} 个任务可能因应用重启而中断，建议检查并重新启动。`;
            alertDiv.classList.remove('d-none');
        }
    }

    // 查看所有待重启任务详情（筛选出 pending 状态，保存当前浏览上下文以便恢复）
    function checkAllPendingTasks() {
        // 保存当前浏览状态，便于用户返回
        _previousPendingView = { filter: currentFilter, page: currentPage };

        currentFilter = 'pending';
        currentPage = 1;

        const filterSelect = document.getElementById('filter-select');
        if (filterSelect) {
            filterSelect.value = 'pending';
        }

        updateUrl();
        loadTasks();

        const alertDiv = document.getElementById('pending-tasks-alert');
        alertDiv.classList.add('d-none');

        showNotification('已筛选出所有待处理的任务（点击筛选下拉框可切换回其他视图）', 'info');
    }

    // 从待重启视图返回之前的浏览状态
    function restorePreviousView() {
        if (!_previousPendingView) return;
        currentFilter = _previousPendingView.filter;
        currentPage = _previousPendingView.page;
        _previousPendingView = null;

        const filterSelect = document.getElementById('filter-select');
        if (filterSelect) {
            filterSelect.value = currentFilter;
        }
        updateUrl();
        loadTasks();
    }


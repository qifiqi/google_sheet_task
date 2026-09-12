// 任务列表页面逻辑（templates 页面脚本原样抽离，F4 de-jinja）。
// 批内收敛（F4 dedupe pass）：bt/multi 规范化后逐字相同的函数已提升至 common/business/（Biz.*）。
// 接口调用经 common/api.js。
const TASK_API_BASE = '/api/tasks';
const BACKTEST_TASK_TYPE = 'backtest_multi_product';
const BATCH_EXPORT_API = '/api/exports/global-previews/batch';
const DEFAULT_PAGE_SIZE = 20;
const BATCH_EXPORT_MAX_TASKS = 10;
const LIST_PAGINATION_STORAGE_KEY = 'backtest_multi_product:list_pagination';
let paginationState = {
    page: 1,
    per_page: DEFAULT_PAGE_SIZE,
    pages: 0,
    total: 0,
    has_prev: false,
    has_next: false,
    prev_num: null,
    next_num: null
};
let isLoadingTasks = false;
let currentPageTasks = [];
const selectedBatchExportTaskIds = new Set();

function readStoredListPaginationState() {
    try {
        return JSON.parse(localStorage.getItem(LIST_PAGINATION_STORAGE_KEY) || '{}') || {};
    } catch (error) {
        return {};
    }
}

function getInitialListPaginationState() {
    const params = new URLSearchParams(window.location.search);
    const stored = readStoredListPaginationState();
    return {
        page: Biz.parsePositiveInt(params.get('page'), Biz.parsePositiveInt(stored.page, 1)),
        per_page: Biz.parsePositiveInt(params.get('per_page'), Biz.parsePositiveInt(stored.per_page, DEFAULT_PAGE_SIZE))
    };
}

function persistListPaginationState() {
    const state = {
        page: paginationState.page,
        per_page: paginationState.per_page
    };
    localStorage.setItem(LIST_PAGINATION_STORAGE_KEY, JSON.stringify(state));

    const url = new URL(window.location.href);
    url.searchParams.set('page', String(state.page));
    url.searchParams.set('per_page', String(state.per_page));
    window.history.replaceState({}, '', url);
}

function buildDetailHref(taskId) {
    const params = new URLSearchParams({
        list_page: String(paginationState.page || 1),
        list_per_page: String(paginationState.per_page || DEFAULT_PAGE_SIZE)
    });
    return `/backtest-multi-product/detail/${encodeURIComponent(taskId)}?${params.toString()}`;
}

// 按 config 内各产品 sheet 标题提取模型版本（与后端 get_backtest_model_version 同口径）。
function extractModelVersionLabel(title) {
    const normalized = String(title || '').toUpperCase();
    if (normalized.includes('C7.0.3')) return 'C7.0.3';
    if (normalized.includes('C7')) return 'C7';
    if (normalized.includes('C5')) return 'C5';
    if (normalized.includes('C4')) return 'C4';
    if (normalized.includes('C3') || normalized.includes('CHARTING:3')) return 'C3';
    return '';
}

function inferModelVersion(task) {
    const products = Array.isArray(task.config?.products) ? task.config.products : [];
    const versions = [...new Set(products
        .map((product) => extractModelVersionLabel(product.sheet?.title))
        .filter(Boolean))];
    const versionText = versions.join('-') || '-';
    return products.length ? `${versionText} · ${products.length}品` : versionText;
}

function buildKlineRangeText(task) {
    const config = task.config || {};
    if (!config.start_date && !config.end_date) {
        return '-';
    }
    return `${config.start_date || '-'} ~ ${config.end_date || '-'}`;
}

// 执行参数跨产品去重：参数行完全相同只展示一次。
function buildExecutionParamsText(task) {
    const products = Array.isArray(task.config?.products) ? task.config.products : [];
    const seen = new Set();
    const uniqueRows = [];
    products.forEach((product) => {
        (Array.isArray(product.parameters) ? product.parameters : []).forEach((row) => {
            const key = JSON.stringify(row);
            if (seen.has(key)) {
                return;
            }
            seen.add(key);
            uniqueRows.push((Array.isArray(row) ? row : [row]).join('/'));
        });
    });
    return uniqueRows.join('；');
}

function renderTaskCell(task) {
    const shortId = String(task.id || '').slice(0, 8);
    const taskName = task.name || '未命名任务';
    const products = Array.isArray(task.config?.products) ? task.config.products : [];
    const productNames = products.map((item) => item.product_name || item.stock_code).filter(Boolean).join(' / ') || '-';

    return `
        <div class="fw-semibold" title="${Biz.escapeHtml(task.id || '')}">${Biz.escapeHtml(taskName)}</div>
        <div class="task-meta text-body-secondary">ID: ${Biz.escapeHtml(shortId)} · 产品: ${Biz.escapeHtml(productNames)}</div>
    `;
}

function getTaskSecondaryText(task) {
    const shortId = String(task.id || '').slice(0, 8);
    const products = Array.isArray(task.config?.products) ? task.config.products : [];
    const productNames = products.map((item) => item.product_name || item.stock_code).filter(Boolean).join(' / ') || '-';
    return `ID: ${shortId} · 产品: ${productNames}`;
}

function getExportableTasks() {
    return currentPageTasks.filter((task) => task.status === 'completed');
}

function updateBatchExportSummary() {
    const summary = document.getElementById('batchExportSummary');
    const confirmButton = document.getElementById('confirmBatchExportBtn');
    const exportableCount = getExportableTasks().length;
    const selectedCount = selectedBatchExportTaskIds.size;
    if (summary) {
        summary.textContent = `当前页 ${currentPageTasks.length} 个任务，可导出 ${exportableCount} 个，已选 ${selectedCount} 个`;
    }
    if (confirmButton) {
        confirmButton.disabled = selectedCount < 1;
    }
}

function renderBatchExportTaskList() {
    const container = document.getElementById('batchExportTaskList');
    if (!container) {
        return;
    }

    if (!currentPageTasks.length) {
        container.innerHTML = '<div class="batch-export-empty">当前页暂无可展示任务</div>';
        updateBatchExportSummary();
        return;
    }

    const knownIds = new Set(currentPageTasks.map((task) => String(task.id || '')));
    [...selectedBatchExportTaskIds].forEach((taskId) => {
        if (!knownIds.has(taskId)) {
            selectedBatchExportTaskIds.delete(taskId);
        }
    });

    container.innerHTML = currentPageTasks.map((task) => {
        const taskId = String(task.id || '');
        const isCompleted = task.status === 'completed';
        const isSelected = selectedBatchExportTaskIds.has(taskId);
        const cardClass = [
            'batch-export-task-card',
            isSelected ? 'is-selected' : '',
            isCompleted ? '' : 'is-disabled'
        ].filter(Boolean).join(' ');
        const statusText = Biz.getStatusText(task.status);
        const statusClass = isCompleted ? 'text-bg-success' : 'text-bg-secondary';
        const disabledReason = isCompleted ? '' : '<div class="small text-body-secondary mt-1">尚未完成，不可导出</div>';

        return `
            <div class="${cardClass}" role="button" tabindex="${isCompleted ? '0' : '-1'}" data-task-id="${Biz.escapeHtml(taskId)}" data-disabled="${isCompleted ? 'false' : 'true'}" aria-disabled="${isCompleted ? 'false' : 'true'}">
                <input class="form-check-input mt-1" type="checkbox" tabindex="-1" ${isSelected ? 'checked' : ''} ${isCompleted ? '' : 'disabled'} aria-label="选择任务">
                <span class="text-start">
                    <span class="d-block fw-semibold batch-export-task-title">${Biz.escapeHtml(task.name || '未命名任务')}</span>
                    <span class="d-block small text-body-secondary mt-1">${Biz.escapeHtml(getTaskSecondaryText(task))}</span>
                    <span class="d-block small text-body-secondary mt-1">模型版本：${Biz.escapeHtml(inferModelVersion(task))} · 创建：${Biz.escapeHtml(Biz.formatTime(task.created_at))}</span>
                    ${disabledReason}
                </span>
                <span class="badge ${statusClass} rounded-pill px-3 py-2">${Biz.escapeHtml(statusText)}</span>
            </div>
        `;
    }).join('');
    updateBatchExportSummary();
}

function selectAllExportableTasks() {
    selectedBatchExportTaskIds.clear();
    getExportableTasks().slice(0, BATCH_EXPORT_MAX_TASKS).forEach((task) => {
        selectedBatchExportTaskIds.add(String(task.id));
    });
    renderBatchExportTaskList();
}

function clearBatchExportSelection() {
    selectedBatchExportTaskIds.clear();
    renderBatchExportTaskList();
}

async function exportSelectedBatchTasks() {
    const button = document.getElementById('confirmBatchExportBtn');
    const originalHtml = button.innerHTML;
    const taskIds = [...selectedBatchExportTaskIds];
    if (!taskIds.length) {
        return;
    }

    button.disabled = true;
    button.innerHTML = '<span class="spinner-border spinner-border-sm me-1" aria-hidden="true"></span>导出中';
    try {
        const response = await Api.endpoints.export.globalPreviewsBatch(taskIds);
        if (!response.ok) {
            const text = await response.text();
            let message = '导出失败';
            try {
                const payload = JSON.parse(text);
                message = payload.message || message;
            } catch (_error) {
                message = text || message;
            }
            throw new Error(message);
        }

        const blob = await response.blob();
        const filename = Biz.resolveDownloadFilename(
            response.headers.get('Content-Disposition') || '',
            'backtest_multi_product_global_preview_batch.zip'
        );
        const url = URL.createObjectURL(blob);
        const link = document.createElement('a');
        link.href = url;
        link.download = filename;
        document.body.appendChild(link);
        link.click();
        link.remove();
        URL.revokeObjectURL(url);
        bootstrap.Modal.getOrCreateInstance(document.getElementById('batchExportModal')).hide();
    } catch (error) {
        alert(error.message || '导出失败');
    } finally {
        button.innerHTML = originalHtml;
        updateBatchExportSummary();
    }
}

async function deleteTask(taskId) {
    if (!confirm(`确认删除任务 ${taskId} 吗？`)) {
        return;
    }

    const data = await Api.envelope('DELETE', `${TASK_API_BASE}/${encodeURIComponent(taskId)}`);

    if (data.status === 'success') {
        const nextPage = paginationState.total > 1 && paginationState.page > 1 && document.querySelectorAll('#taskTableBody tr').length <= 1
            ? paginationState.page - 1
            : paginationState.page;
        loadTasks({ page: nextPage });
        return;
    }

    alert(`删除失败：${data.message || '未知错误'}`);
}

function renderPagination() {
    const summary = document.getElementById('paginationSummary');
    const pagination = document.getElementById('taskPagination');
    const pageSizeSelect = document.getElementById('pageSizeSelect');
    if (!summary || !pagination || !pageSizeSelect) {
        return;
    }

    const { page, per_page, pages, total, has_prev, has_next, prev_num, next_num } = paginationState;
    pageSizeSelect.value = String(per_page || DEFAULT_PAGE_SIZE);

    if (!total) {
        summary.textContent = '共 0 条任务';
        pagination.innerHTML = '';
        return;
    }

    const start = (page - 1) * per_page + 1;
    const end = Math.min(page * per_page, total);
    summary.textContent = `显示 ${start}-${end} 条，共 ${total} 条任务`;

    const items = [];
    items.push(`
        <li class="page-item ${has_prev ? '' : 'disabled'}">
            <button class="page-link" type="button" data-page="${has_prev ? prev_num : ''}" ${has_prev ? '' : 'disabled'}>上一页</button>
        </li>
    `);

    Biz.buildPaginationPages(page, pages).forEach((item) => {
        if (typeof item !== 'number') {
            items.push('<li class="page-item disabled"><span class="page-link">...</span></li>');
            return;
        }
        items.push(`
            <li class="page-item ${item === page ? 'active' : ''}">
                <button class="page-link" type="button" data-page="${item}">${item}</button>
            </li>
        `);
    });

    items.push(`
        <li class="page-item ${has_next ? '' : 'disabled'}">
            <button class="page-link" type="button" data-page="${has_next ? next_num : ''}" ${has_next ? '' : 'disabled'}>下一页</button>
        </li>
    `);

    pagination.innerHTML = items.join('');
}

function updateStatistics(statistics, fallbackTasks) {
    const tasks = Array.isArray(fallbackTasks) ? fallbackTasks : [];
    const total = Number(statistics?.total_tasks ?? paginationState.total ?? tasks.length);
    const running = Number(statistics?.running_tasks ?? tasks.filter((task) => task.status === 'running').length);
    const completed = Number(statistics?.completed_tasks ?? tasks.filter((task) => task.status === 'completed').length);
    const failed = Number(statistics?.error_tasks ?? tasks.filter((task) => task.status === 'error' || task.status === 'failed').length);

    document.getElementById('totalTasks').textContent = total;
    document.getElementById('runningTasks').textContent = running;
    document.getElementById('completedTasks').textContent = completed;
    document.getElementById('failedTasks').textContent = failed;
    Biz.setMetricProgress('totalTasksBar', total, total);
    Biz.setMetricProgress('runningTasksBar', running, total);
    Biz.setMetricProgress('completedTasksBar', completed, total);
    Biz.setMetricProgress('failedTasksBar', failed, total);
}

async function loadTasks(options = {}) {
    if (isLoadingTasks) {
        return;
    }

    const nextPage = Math.max(Number(options.page || paginationState.page || 1), 1);
    const nextPerPage = Math.max(Number(options.perPage || paginationState.per_page || DEFAULT_PAGE_SIZE), 1);
    const query = new URLSearchParams({
        task_type: BACKTEST_TASK_TYPE,
        page: String(nextPage),
        per_page: String(nextPerPage)
    });
    isLoadingTasks = true;
    try {
        const data = await Api.endpoints.task.list(query.toString());
        const tasks = Array.isArray(data && data.items) ? data.items : [];
        currentPageTasks = tasks;
        const pagination = data || {};

        const tbody = document.getElementById('taskTableBody');
        tbody.innerHTML = '';

        const total = Number(pagination.total || 0);
        const totalPages = Number(pagination.pages || 0);
        if (!tasks.length && total > 0 && nextPage > Math.max(totalPages, 1)) {
            isLoadingTasks = false;
            loadTasks({ page: Math.max(totalPages, 1), perPage: nextPerPage });
            return;
        }

        tasks.forEach((task) => {
            const detailHref = buildDetailHref(task.id);
            const row = `
                <tr>
                    <td class="ps-4 task-name-cell">${renderTaskCell(task)}</td>
                    <td><span class="badge rounded-pill text-bg-light border">${Biz.escapeHtml(inferModelVersion(task))}</span></td>
                    <td>${Biz.escapeHtml(buildKlineRangeText(task))}</td>
                    <td class="param-preview-cell" title="${Biz.escapeHtml(buildExecutionParamsText(task))}">${Biz.escapeHtml(buildExecutionParamsText(task)) || '-'}</td>
                    <td>${Biz.renderStatus(task.status)}</td>
                    <td>${Biz.renderTimeCell(task.created_at)}</td>
                    <td>${Biz.renderTimeCell(task.start_time)}</td>
                    <td>${Biz.renderTimeCell(task.end_time)}</td>
                    <td class="pe-4 text-end">
                        <a href="${detailHref}" class="btn btn-sm btn-outline-primary">查看详情</a>
                        <button type="button" class="btn btn-sm btn-outline-danger delete-task-btn ms-2" data-task-id="${Biz.escapeHtml(task.id)}">删除</button>
                    </td>
                </tr>
            `;
            tbody.insertAdjacentHTML('beforeend', row);
        });

        paginationState = {
            page: Number(pagination.current_page || nextPage),
            per_page: Number(pagination.per_page || nextPerPage),
            pages: Number(pagination.pages || 0),
            total: Number(pagination.total || tasks.length),
            has_prev: Number(pagination.current_page || 1) > 1,
            has_next: Number(pagination.current_page || 1) < Number(pagination.pages || 0),
            prev_num: null,
            next_num: null
        };

        if (!tasks.length) {
            tbody.innerHTML = `
                <tr>
                    <td colspan="9" class="text-center text-body-secondary py-5">
                        当前还没有数据回测任务，点击右上角“创建新任务”开始。
                    </td>
                </tr>
            `;
        }

        updateStatistics(data.statistics, tasks);
        renderPagination();
        renderBatchExportTaskList();
        persistListPaginationState();
        document.getElementById('lastUpdated').textContent = Biz.formatTime(new Date().toISOString());
    } catch (error) {
        console.error(error);
    } finally {
        isLoadingTasks = false;
    }
}

document.addEventListener('click', (event) => {
    const exportCard = event.target.closest('.batch-export-task-card');
    if (exportCard && exportCard.dataset.disabled !== 'true') {
        event.preventDefault();
        const taskId = exportCard.dataset.taskId;
        if (selectedBatchExportTaskIds.has(taskId)) {
            selectedBatchExportTaskIds.delete(taskId);
        } else if (selectedBatchExportTaskIds.size < BATCH_EXPORT_MAX_TASKS) {
            selectedBatchExportTaskIds.add(taskId);
        } else {
            alert(`批量导出最多支持 ${BATCH_EXPORT_MAX_TASKS} 个任务`);
        }
        renderBatchExportTaskList();
        return;
    }

    const button = event.target.closest('.delete-task-btn');
    if (!button) {
        return;
    }
    deleteTask(button.dataset.taskId);
});

document.addEventListener('keydown', (event) => {
    if (event.key !== 'Enter' && event.key !== ' ') {
        return;
    }
    const exportCard = event.target.closest('.batch-export-task-card');
    if (!exportCard || exportCard.dataset.disabled === 'true') {
        return;
    }
    event.preventDefault();
    exportCard.click();
});

document.getElementById('taskPagination').addEventListener('click', (event) => {
    const target = event.target.closest('[data-page]');
    if (!target || target.disabled) {
        return;
    }
    const nextPage = Number(target.getAttribute('data-page'));
    if (!nextPage || nextPage === paginationState.page) {
        return;
    }
    loadTasks({ page: nextPage });
});

document.getElementById('pageSizeSelect').addEventListener('change', (event) => {
    const nextPerPage = Number(event.target.value) || DEFAULT_PAGE_SIZE;
    loadTasks({ page: 1, perPage: nextPerPage });
});

document.getElementById('openBatchExportBtn').addEventListener('click', () => {
    renderBatchExportTaskList();
    bootstrap.Modal.getOrCreateInstance(document.getElementById('batchExportModal')).show();
});

document.getElementById('selectAllExportableBtn').addEventListener('click', selectAllExportableTasks);
document.getElementById('selectCompletedOnlyBtn').addEventListener('click', selectAllExportableTasks);
document.getElementById('clearBatchExportSelectionBtn').addEventListener('click', clearBatchExportSelection);
document.getElementById('confirmBatchExportBtn').addEventListener('click', () => {
    exportSelectedBatchTasks();
});

const initialListPagination = getInitialListPaginationState();
paginationState.page = initialListPagination.page;
paginationState.per_page = initialListPagination.per_page;
loadTasks();
setInterval(loadTasks, 5000);

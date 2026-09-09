// C3 合并导出页（templates/google_sheet/merge_export.html 的页面逻辑）。
// 自 google_sheet/merge_export.html 内联脚本原样抽离；接口调用经 common/api.js。
'use strict';

// ── 全局状态 ──
const taskType = 'google_sheet';
let allTasks = [];
let currentPage = 1;
let tasksPerPage = 20;
let totalTasks = 0;
let totalPages = 0;
let selectedTaskIds = new Set();
let sortField = 'created_at';
let sortDir = 'desc';
let isLoading = false;

document.addEventListener('DOMContentLoaded', function() {
    const input = document.getElementById('search-keyword');
    if (input) {
        input.addEventListener('keypress', function(e) {
            if (e.key === 'Enter') { e.preventDefault(); doSearch(); }
        });
    }
    doSearch();
});

// ── 搜索 ──
function doSearch(page) {
    if (isLoading) return;
    isLoading = true;
    if (page) currentPage = page;

    const keyword = (document.getElementById('search-keyword').value || '').trim();
    const status = document.getElementById('search-status').value;

    const params = new URLSearchParams({
        task_type: taskType,
        page: currentPage,
        per_page: tasksPerPage,
    });
    if (keyword) params.set('keyword', keyword);
    if (status) params.set('status', status);

    Api.endpoints.task.list(params.toString()).then(function (pdata) {
        isLoading = false;
        if (!pdata || !pdata.items) {
            showNotification('搜索失败', 'error');
            return;
        }
        allTasks = pdata.items;
        totalTasks = pdata.total || 0;
        totalPages = pdata.pages || 0;
        currentPage = pdata.current_page || currentPage;
        renderTable();
        renderPagination();
    }).catch(function () {
        isLoading = false;
        showNotification('搜索失败', 'error');
    });
}

function resetSearch() {
    document.getElementById('search-keyword').value = '';
    document.getElementById('search-status').value = '';
    currentPage = 1;
    doSearch();
}

// ── 表格渲染 ──
function renderTable() {
    const tbody = document.getElementById('tasks-table-body');
    tbody.innerHTML = '';

    if (!allTasks.length) {
        tbody.innerHTML = '<tr><td colspan="8" class="text-center text-muted py-4">未找到匹配任务</td></tr>';
        return;
    }

    allTasks.forEach(function(task) {
        const checked = selectedTaskIds.has(String(task.id));
        const row = document.createElement('tr');
        row.innerHTML = `
            <td class="text-center ps-3">
                <input class="form-check-input" type="checkbox" value="${task.id}"
                       ${checked ? 'checked' : ''} onchange="onRowCheckChange(this)">
            </td>
            <td><small class="text-muted">${escapeHtml(String(task.id).substring(0, 8))}</small></td>
            <td>
                <div class="fw-bold">${escapeHtml(task.name)}</div>
                ${task.description ? `<small class="text-muted">${escapeHtml(task.description)}</small>` : ''}
            </td>
            <td><small>${formatTime(task.created_at)}</small></td>
            <td><span class="badge ${getStatusClass(task.status)}">${getStatusText(task.status)}</span></td>
            <td>${task.current_step}/${task.total_steps}</td>
            <td><small>${formatTime(task.start_time)}</small></td>
            <td><small>${formatTime(task.end_time)}</small></td>
        `;
        tbody.appendChild(row);
    });

    updateSelectedCount();
    updateSortIcons();
}

// ── 分页 ──
function renderPagination() {
    const el = document.getElementById('pagination');
    const info = document.getElementById('pagination-info');
    el.innerHTML = '';

    const start = totalTasks > 0 ? (currentPage - 1) * tasksPerPage + 1 : 0;
    const end = Math.min(currentPage * tasksPerPage, totalTasks);
    info.textContent = `显示第 ${start}-${end} 条，共 ${totalTasks} 条`;

    if (totalPages <= 1) return;

    function addLi(text, page, disabled, active) {
        const li = document.createElement('li');
        li.className = `page-item ${disabled ? 'disabled' : ''} ${active ? 'active' : ''}`;
        li.innerHTML = `<a class="page-link" href="#" onclick="event.preventDefault();doSearch(${page})">${text}</a>`;
        el.appendChild(li);
    }

    addLi('«', 1, currentPage === 1);
    addLi('‹', Math.max(1, currentPage - 1), currentPage === 1);

    let s = Math.max(1, currentPage - 2);
    let e = Math.min(totalPages, currentPage + 2);
    if (s > 1) { addLi('1', 1); if (s > 2) addLi('…', 0, true); }
    for (let i = s; i <= e; i++) addLi(i, i, false, i === currentPage);
    if (e < totalPages) { if (e < totalPages - 1) addLi('…', 0, true); addLi(totalPages, totalPages); }

    addLi('›', Math.min(totalPages, currentPage + 1), currentPage === totalPages);
    addLi('»', totalPages, currentPage === totalPages);
}

function changePageSize() {
    tasksPerPage = parseInt(document.getElementById('page-size-select').value) || 20;
    currentPage = 1;
    doSearch();
}

// ── 多选 ──
function onRowCheckChange(cb) {
    const id = String(cb.value);
    cb.checked ? selectedTaskIds.add(id) : selectedTaskIds.delete(id);
    updateSelectedCount();
}

function onHeaderCheckChange(cb) {
    const checked = cb.checked;
    document.querySelectorAll('#tasks-table-body input[type=checkbox]').forEach(c => {
        c.checked = checked;
        const id = String(c.value);
        checked ? selectedTaskIds.add(id) : selectedTaskIds.delete(id);
    });
    updateSelectedCount();
}

function selectAll() {
    allTasks.forEach(t => selectedTaskIds.add(String(t.id)));
    document.querySelectorAll('#tasks-table-body input[type=checkbox]').forEach(c => c.checked = true);
    updateSelectedCount();
}

function deselectAll() {
    selectedTaskIds.clear();
    document.querySelectorAll('#tasks-table-body input[type=checkbox],#header-check').forEach(c => c.checked = false);
    updateSelectedCount();
}

function invertSelection() {
    document.querySelectorAll('#tasks-table-body input[type=checkbox]').forEach(c => {
        c.checked = !c.checked;
        const id = String(c.value);
        c.checked ? selectedTaskIds.add(id) : selectedTaskIds.delete(id);
    });
    updateSelectedCount();
}

function updateSelectedCount() {
    const count = selectedTaskIds.size;
    const badge = document.getElementById('selected-count');
    badge.textContent = count;
    // 超过最大限制时变色提示并禁用导出按钮
    const overLimit = count > MAX_EXPORT_TASKS;
    badge.className = 'badge ' + (overLimit ? 'bg-danger' : 'bg-primary');
    const btn = document.getElementById('export-btn');
    btn.disabled = count === 0 || overLimit;
    btn.title = overLimit ? `最多支持 ${MAX_EXPORT_TASKS} 个任务` : '';
    const headerCheck = document.getElementById('header-check');
    if (headerCheck) {
        const bodyChecks = document.querySelectorAll('#tasks-table-body input[type=checkbox]');
        headerCheck.checked = bodyChecks.length > 0 && Array.from(bodyChecks).every(c => c.checked);
        headerCheck.indeterminate = !headerCheck.checked && Array.from(bodyChecks).some(c => c.checked);
    }
}

// ── 列排序 ──
function toggleSort(field) {
    if (sortField === field) {
        sortDir = sortDir === 'asc' ? 'desc' : 'asc';
    } else {
        sortField = field;
        sortDir = 'desc';
    }
    allTasks.sort(function(a, b) {
        let va = a[field] || '', vb = b[field] || '';
        if (field === 'created_at' || field === 'start_time' || field === 'end_time') {
            va = va ? new Date(va).getTime() : 0;
            vb = vb ? new Date(vb).getTime() : 0;
        } else {
            va = String(va).toLowerCase();
            vb = String(vb).toLowerCase();
        }
        if (va < vb) return sortDir === 'asc' ? -1 : 1;
        if (va > vb) return sortDir === 'asc' ? 1 : -1;
        return 0;
    });
    renderTable();
}

function updateSortIcons() {
    document.querySelectorAll('.sort-icon').forEach(el => el.textContent = '');
    const icon = document.getElementById('sort-icon-' + sortField);
    if (icon) icon.textContent = sortDir === 'asc' ? ' ↑' : ' ↓';
}

const MAX_EXPORT_TASKS = 10;

// ── 流式下载工具 ──────────────────────────────────────────
// 使用 ReadableStream 实时接收数据块并显示进度
function streamingDownload(responsePromise, onProgress) {
    return Promise.resolve(responsePromise).then(async resp => {
        if (!resp.ok) {
            const errData = await resp.json().catch(() => ({}));
            throw new Error(errData.message || `请求失败 (${resp.status})`);
        }

        const contentLength = parseInt(resp.headers.get('Content-Length') || '0', 10);
        const disposition = resp.headers.get('Content-Disposition') || '';
        const filenameMatch = disposition.match(/filename\*?=(?:UTF-8''|"?)([^";]+)/i);
        const filename = filenameMatch
            ? decodeURIComponent(filenameMatch[1].replace(/"/g, ''))
            : 'export.xlsx';

        // 无 body 时直接读 blob
        if (!resp.body) {
            const blob = await resp.blob();
            onProgress && onProgress({ received: blob.size, total: blob.size, percent: 100 });
            return { blob, filename };
        }

        const reader = resp.body.getReader();
        const chunks = [];
        let received = 0;

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            chunks.push(value);
            received += value.length;
            onProgress && onProgress({
                received,
                total: contentLength || 0,
                percent: contentLength ? Math.round((received / contentLength) * 100) : -1,
            });
        }

        const blob = new Blob(chunks, {
            type: resp.headers.get('Content-Type') || 'application/octet-stream',
        });
        return { blob, filename };
    });
}

// 触发浏览器下载
function triggerDownload(blob, filename) {
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    window.URL.revokeObjectURL(url);
    a.remove();
}

// 进度条 UI 控制
function showProgress(statusText, percent) {
    const wrap = document.getElementById('download-progress');
    const bar = document.getElementById('progress-bar');
    const pct = document.getElementById('progress-pct');
    const status = document.getElementById('progress-status');
    wrap.style.display = 'block';
    status.textContent = statusText;
    if (percent < 0) {
        // 未知长度：持续动画
        bar.classList.add('progress-bar-animated');
        bar.style.width = '100%';
        pct.textContent = formatBytes(receivedBytes);
    } else {
        bar.classList.remove('progress-bar-animated');
        bar.style.width = percent + '%';
        pct.textContent = percent + '%';
    }
}
function hideProgress() {
    document.getElementById('download-progress').style.display = 'none';
    document.getElementById('progress-bar').style.width = '0%';
}
function formatBytes(bytes) {
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1048576) return (bytes / 1024).toFixed(1) + ' KB';
    return (bytes / 1048576).toFixed(1) + ' MB';
}
let receivedBytes = 0;

// ── 导出 ──
function doExport() {
    if (selectedTaskIds.size === 0) return;
    if (selectedTaskIds.size > MAX_EXPORT_TASKS) {
        showNotification(`合并导出最多支持 ${MAX_EXPORT_TASKS} 个任务，当前已选 ${selectedTaskIds.size} 个`, 'warning');
        return;
    }
    const btn = document.getElementById('export-btn');
    const originalText = btn.innerHTML;
    btn.innerHTML = '<i class="bi bi-hourglass-split"></i> 生成中…';
    btn.disabled = true;
    receivedBytes = 0;
    showProgress('正在生成文件，请稍候…', 0);

    streamingDownload(
        Api.endpoints.export.batchTasks(Array.from(selectedTaskIds)),
        function onProgress(info) {
            receivedBytes = info.received;
            if (info.percent < 0) {
                showProgress('下载中… ' + formatBytes(info.received), -1);
            } else {
                showProgress(
                    '下载中… ' + formatBytes(info.received) + ' / ' + formatBytes(info.total),
                    info.percent
                );
            }
        }
    )
    .then(({ blob, filename }) => {
        triggerDownload(blob, filename);
        showProgress('下载完成', 100);
        setTimeout(hideProgress, 2000);
        showNotification(`合并导出成功（${selectedTaskIds.size} 个任务）`, 'success');
    })
    .catch(err => {
        hideProgress();
        showNotification('合并导出失败: ' + err.message, 'error');
    })
    .finally(() => {
        btn.innerHTML = originalText;
        btn.disabled = selectedTaskIds.size === 0 || selectedTaskIds.size > MAX_EXPORT_TASKS;
    });
}


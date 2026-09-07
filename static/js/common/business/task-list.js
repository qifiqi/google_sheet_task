// backtest 任务列表页（backtest 双胞胎）批内收敛：bt/multi 两页规范化后逐字相同的函数提升至此（F4 dedupe pass，
// docs/design/frontend-refactor/02 §3.6）。函数体为页面原实现逐字节搬移；
// 页面调用点已改写为 Biz.*，页面差异（路径前缀、数据列、存储键、导出上限）保留在 pages JS。
window.Biz = window.Biz || {};
(function (Biz) {
'use strict';

function parsePositiveInt(value, fallback) {
    const parsed = Number.parseInt(value, 10);
    return Number.isFinite(parsed) && parsed > 0 ? parsed : fallback;
}

function buildPaginationPages(currentPage, totalPages) {
    const pages = [];
    if (totalPages <= 7) {
        for (let page = 1; page <= totalPages; page += 1) {
            pages.push(page);
        }
        return pages;
    }

    pages.push(1);
    if (currentPage > 3) {
        pages.push('ellipsis-left');
    }

    const start = Math.max(2, currentPage - 1);
    const end = Math.min(totalPages - 1, currentPage + 1);
    for (let page = start; page <= end; page += 1) {
        pages.push(page);
    }

    if (currentPage < totalPages - 2) {
        pages.push('ellipsis-right');
    }
    pages.push(totalPages);
    return pages;
}

function escapeHtml(value) {
    return String(value ?? '')
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
}

function formatTime(value) {
    if (!value) return '-';

    const date = new Date(value);
    if (Number.isNaN(date.getTime())) {
        return value;
    }

    return date.toLocaleString('zh-CN', {
        year: 'numeric',
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
        hour12: false
    });
}

function getStatusText(status) {
    const labels = {
        pending: '待执行',
        running: '运行中',
        completed: '已完成',
        cancelled: '已取消',
        error: '失败',
        failed: '失败'
    };
    return labels[status] || status || '-';
}

function renderTimeCell(value) {
    if (!value) {
        return '<span class="text-body-secondary">-</span>';
    }

    const date = new Date(value);
    if (Number.isNaN(date.getTime())) {
        return `<span class="fw-medium">${escapeHtml(value)}</span>`;
    }

    const main = date.toLocaleDateString('zh-CN');
    const sub = date.toLocaleTimeString('zh-CN', { hour12: false });
    return `<div class="fw-medium">${main}</div><div class="time-sub text-body-secondary">${sub}</div>`;
}

function renderStatus(status) {
    const normalized = status || 'pending';
    const classMap = {
        pending: 'text-bg-secondary',
        running: 'text-bg-primary',
        completed: 'text-bg-success',
        cancelled: 'text-bg-info',
        error: 'text-bg-danger',
        failed: 'text-bg-danger'
    };
    const badgeClass = classMap[normalized] || 'text-bg-secondary';
    return `<span class="badge ${badgeClass} rounded-pill px-3 py-2">${escapeHtml(getStatusText(normalized))}</span>`;
}

function resolveDownloadFilename(disposition, fallback) {
    const utf8Match = disposition.match(/filename\*=UTF-8''([^;]+)/i);
    if (utf8Match) {
        try {
            return decodeURIComponent(utf8Match[1]);
        } catch (_error) {
            return utf8Match[1];
        }
    }
    const asciiMatch = disposition.match(/filename="?([^"]+)"?/i);
    return asciiMatch ? asciiMatch[1] : fallback;
}

function setMetricProgress(id, value, total) {
    const bar = document.getElementById(id);
    if (!bar) {
        return;
    }
    const safeTotal = Math.max(Number(total) || 0, 0);
    const safeValue = Math.max(Number(value) || 0, 0);
    const percent = safeTotal ? Math.min((safeValue / safeTotal) * 100, 100) : 0;
    bar.style.width = `${percent}%`;
}

Biz.parsePositiveInt = parsePositiveInt;
Biz.buildPaginationPages = buildPaginationPages;
Biz.escapeHtml = escapeHtml;
Biz.formatTime = formatTime;
Biz.getStatusText = getStatusText;
Biz.renderTimeCell = renderTimeCell;
Biz.renderStatus = renderStatus;
Biz.resolveDownloadFilename = resolveDownloadFilename;
Biz.setMetricProgress = setMetricProgress;
})(window.Biz);

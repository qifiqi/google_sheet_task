
let currentTaskId = '';
let previewPayload = null;
let activeStockCode = '';
let activeGroupKey = '';
let groupMode = 'year';
let previewGroups = [];
const previewCache = new Map();

// Word 导出按“股票×年份×参数方案”逐个调用 Word 报告接口，前端限速避免拥挤。
const WORD_EXPORT_INTERVAL_MS = 2000;
// 结果列表索引（按任务缓存）：result_id → 收益序列/股票/年份，供 Word 导出循环使用。
let taskResultIndex = null;
let taskResultIndexTaskId = '';
// Word 导出弹窗的勾选集合（result_id 字符串）。
let wordExportSelection = new Set();

function showMessage(message, type = 'danger') {
    const box = document.getElementById('messageBox');
    box.className = `alert alert-${type} mb-0`;
    box.textContent = message;
}

function hideResults() {
    ['filterCard', 'previewCard', 'loadingCard'].forEach((id) => document.getElementById(id).classList.add('d-none'));
    document.getElementById('exportBtn').disabled = true;
    document.getElementById('exportWordBtn').disabled = true;
}

function setLoading(message, visible = true) {
    document.getElementById('loadingText').textContent = message;
    document.getElementById('loadingCard').classList.toggle('d-none', !visible);
}

function groupsForActiveStock() {
    return (previewPayload?.groups || []).filter((group) => group.stock_code === activeStockCode);
}

function renderStockOptions() {
    document.getElementById('stockSelectWrap').classList.toggle('d-none', groupMode !== 'stock');
    if (groupMode !== 'stock') return;
    const stocks = groupMode === 'stock'
        ? previewGroups.map((group) => group.key)
        : [...new Set((previewPayload.groups || []).map((group) => group.stock_code))];
    if (!stocks.includes(activeStockCode)) activeStockCode = stocks[0] || '';
    document.getElementById('stockSelect').innerHTML = stocks.map((stock) => `<option value="${escapeHtml(stock)}">${escapeHtml(stock)}</option>`).join('');
    document.getElementById('stockSelect').value = activeStockCode;
}

function renderYearOptions() {
    const groups = groupMode === 'year' ? previewGroups : groupsForActiveStock();
    const valueKey = groupMode === 'year' ? 'key' : 'group_key';
    if (!groups.some((group) => group[valueKey] === activeGroupKey)) activeGroupKey = groups[0]?.[valueKey] || '';
    document.getElementById('yearSelect').innerHTML = groups.map((group) => {
        const key = group[valueKey];
        const label = groupMode === 'year'
            ? `${group.label} (${group.result_ids.length} 组参数)`
            : `${group.group_label} (${group.column_count || 0} 组参数)`;
        return `<option value="${escapeHtml(key)}">${escapeHtml(label)}</option>`;
    }).join('');
    document.getElementById('yearSelect').value = activeGroupKey;
}

function renderTable() {
    const group = groupMode === 'year'
        ? (previewPayload?.groups || []).find((item) => item.year === activeGroupKey)
        : groupsForActiveStock().find((item) => item.group_key === activeGroupKey);
    const container = document.getElementById('previewContainer');
    if (!group || !group.rows?.length || !group.columns?.length) {
        container.innerHTML = '<div class="empty-state">该股票年份下没有成功结果</div>';
        return;
    }
    document.getElementById('groupMeta').textContent = group.period || '';
    const headers = group.columns.map((column) => `<th><div>${escapeHtml(column.header || `结果 ${column.result_id}`)}</div><small class="fw-normal">结果 ID: ${escapeHtml(column.result_id)}</small></th>`).join('');
    const rows = group.rows.map((row) => `<tr><td class="fw-semibold">${escapeHtml(row.category || '-')}</td><td>${escapeHtml(row.metric || '-')}</td><td>${escapeHtml(row.index_value || '-')}</td>${group.columns.map((column) => `<td>${escapeHtml(row.values?.[column.column_key] || '-')}</td>`).join('')}</tr>`).join('');
    container.innerHTML = `<table class="table table-bordered align-middle preview-table"><thead><tr><th>指标类型</th><th>指标</th><th>指数</th>${headers}</tr></thead><tbody>${rows}</tbody></table>`;
}

function renderPreview() {
    renderStockOptions(); renderYearOptions(); renderTable();
    ['filterCard', 'previewCard'].forEach((id) => document.getElementById(id).classList.remove('d-none'));
    document.getElementById('exportBtn').disabled = false;
    document.getElementById('exportWordBtn').disabled = false;
}

function activeMetadataGroup() {
    if (groupMode === 'stock') return previewGroups.find((group) => group.key === activeStockCode);
    return previewGroups.find((group) => group.key === activeGroupKey);
}

async function loadMetadataGroup(group, message) {
    if (!group) return;
    if (previewCache.has(group.key)) {
        previewPayload = previewCache.get(group.key);
        renderPreview();
        return;
    }
    setLoading(message);
    document.getElementById('previewCard').classList.add('d-none');
    try {
        const data = await Api.endpoints.previewHub.previewGroup(encodeURIComponent(currentTaskId), {result_ids: group.result_ids});
        previewPayload = data && data.preview;
        previewCache.set(group.key, previewPayload);
        renderPreview();
    } catch (error) { showMessage(error.message || '分组加载失败'); }
    finally { setLoading('', false); }
}

async function queryTask(event) {
    if (event && event.preventDefault) event.preventDefault();
    currentTaskId = document.getElementById('taskIdInput').value.trim();
    hideResults();
    if (!currentTaskId) return showMessage('请输入任务 ID', 'warning');
    setLoading('正在读取分组…');
    try {
        const data = await Api.endpoints.previewHub.task(encodeURIComponent(currentTaskId));
        if (!data.supported) return showMessage(data.message, 'info');
        groupMode = data.initial?.group_mode || 'year';
        previewGroups = data.initial?.groups || [];
        previewPayload = data.initial?.preview || data.preview;
        previewCache.clear();
        const defaultKey = data.initial?.default_group_key || previewGroups[0]?.key || '';
        previewCache.set(defaultKey, previewPayload);
        activeStockCode = groupMode === 'stock' ? defaultKey : (previewPayload.groups?.[0]?.stock_code || '');
        activeGroupKey = groupMode === 'year' ? defaultKey : '';
        document.getElementById('exportNameInput').value = previewPayload.task?.name || currentTaskId;
        document.getElementById('messageBox').className = 'alert d-none mb-0';
        renderPreview();
    } catch (error) { showMessage(error.message || '查询失败'); }
    finally { setLoading('', false); }
}

async function downloadExportResponse(response, fallbackName) {
    const contentDisposition = response.headers.get('Content-Disposition') || '';
    const utf8Filename = contentDisposition.match(/filename\*=UTF-8''([^;]+)/i);
    const fallbackFilename = contentDisposition.match(/filename="?([^";]+)"?/i);
    const downloadName = utf8Filename ? decodeURIComponent(utf8Filename[1]) : (fallbackFilename?.[1] || fallbackName);
    const blob = await response.blob(); const url = URL.createObjectURL(blob); const link = document.createElement('a');
    link.href = url; link.download = downloadName; document.body.appendChild(link); link.click(); link.remove(); URL.revokeObjectURL(url);
}

async function loadTaskResultIndex() {
    // 结果列表每条自带 return_series_id 与 parameters（股票/年份），是 Word 报告
    // 按结果循环调用的数据源；按任务缓存，重复点击不再拉取。
    // Api.endpoints.task.results 失败直接 throw，成功返回信封 data（{items,...}）。
    if (taskResultIndexTaskId === currentTaskId && taskResultIndex) return taskResultIndex;
    const data = await Api.endpoints.task.results(encodeURIComponent(currentTaskId));
    const items = data?.items || [];
    taskResultIndex = items.map((item) => ({
        resultId: item.id,
        returnSeriesId: item.return_series_id,
        stockCode: String(item.parameters?.stock_code || '').toUpperCase(),
        year: item.parameters?.year != null ? String(item.parameters.year) : '',
        success: item.success !== false,
    }));
    taskResultIndexTaskId = currentTaskId;
    return taskResultIndex;
}

async function openWordExportModal() {
    if (!currentTaskId) return showMessage('请先查询任务', 'warning');
    const button = document.getElementById('exportWordBtn');
    const originalHtml = button.innerHTML;
    button.disabled = true;
    button.innerHTML = '<span class="spinner-border spinner-border-sm me-1"></span>准备中';
    try {
        showMessage('正在读取结果列表…', 'info');
        await loadTaskResultIndex();
        document.getElementById('messageBox').className = 'alert d-none mb-0';
        // 默认全选可导出结果，用户取消勾选即“只导出部分”。
        wordExportSelection = new Set(
            taskResultIndex
                .filter((item) => item.success && item.returnSeriesId)
                .map((item) => String(item.resultId))
        );
        renderWordExportList();
        bootstrap.Modal.getOrCreateInstance(document.getElementById('wordExportModal')).show();
    } catch (error) {
        showMessage(error.message || '读取结果列表失败');
    } finally {
        button.disabled = false;
        button.innerHTML = originalHtml;
    }
}

function wordExportItemLabel(item) {
    return [item.stockCode, item.year, `结果${item.resultId}`].filter(Boolean).join('_');
}

function wordExportEligibleItems() {
    return (taskResultIndex || []).filter((item) => item.success && item.returnSeriesId);
}

function renderWordExportList() {
    const container = document.getElementById('wordExportResultList');
    const items = taskResultIndex || [];
    if (!items.length) {
        container.innerHTML = '<div class="text-center text-body-secondary py-4">该任务下没有结果</div>';
    } else {
        container.innerHTML = items.map((item) => {
            const eligible = item.success && item.returnSeriesId;
            const selected = wordExportSelection.has(String(item.resultId));
            const reason = item.success ? '缺少收益序列，不可导出' : '失败结果，不可导出';
            const boxClass = [
                'd-flex', 'align-items-start', 'gap-2', 'border', 'rounded-1', 'p-2',
                eligible ? '' : 'opacity-50 pe-none',
            ].filter(Boolean).join(' ');
            return `
                <label class="${boxClass}">
                    <input class="form-check-input mt-1" type="checkbox" data-result-id="${escapeHtml(String(item.resultId))}"
                        ${eligible && selected ? 'checked' : ''} ${eligible ? '' : 'disabled'}>
                    <span class="flex-grow-1">
                        <span class="d-block fw-semibold">${escapeHtml(wordExportItemLabel(item))}</span>
                        <span class="d-block small text-body-secondary">${eligible ? '可导出 · RPT-S 文档' : escapeHtml(reason)}</span>
                    </span>
                </label>`;
        }).join('');
    }
    updateWordExportSummary();
}

function updateWordExportSummary() {
    const eligibleCount = wordExportEligibleItems().length;
    const selectedCount = wordExportSelection.size;
    document.getElementById('wordExportSummary').textContent =
        `共 ${(taskResultIndex || []).length} 个结果，可导出 ${eligibleCount} 个，已选 ${selectedCount} 个`;
    document.getElementById('wordExportSelectedCount').textContent = String(selectedCount);
    document.getElementById('confirmWordExportBtn').disabled = selectedCount < 1;
}

async function confirmWordExport() {
    const items = wordExportEligibleItems().filter((item) => wordExportSelection.has(String(item.resultId)));
    if (!items.length) return;
    bootstrap.Modal.getOrCreateInstance(document.getElementById('wordExportModal')).hide();
    await runWordExport(items);
}

async function runWordExport(exportable) {
    const button = document.getElementById('exportWordBtn');
    const originalHtml = button.innerHTML;
    button.disabled = true;
    button.innerHTML = '<span class="spinner-border spinner-border-sm me-1"></span>导出中';
    try {
        // 与多产品全局预览同一个接口（RPT-S），每个结果（股票×年份×参数方案）一个文档，
        // 前端逐个调用、逐个下载；单个失败不中断，最后汇总。
        // 文件名走服务端标准命名（RPT-S-<股票代码>-<k线范围>-<时间戳>），前端不传 filename。
        let done = 0;
        const failed = [];
        for (const item of exportable) {
            done += 1;
            const label = wordExportItemLabel(item);
            showMessage(`正在导出 Word ${done}/${exportable.length}：${label}`, 'info');
            try {
                const response = await Api.endpoints.export.wordReport({
                    report_type: 'RPT-S',
                    task_id: currentTaskId,
                    return_series_id: item.returnSeriesId,
                });
                if (!response.ok) {
                    const errPayload = await response.json().catch(() => ({}));
                    throw new Error(errPayload.message || `HTTP ${response.status}`);
                }
                await downloadExportResponse(response, 'RPT-S.docx');
            } catch (error) {
                failed.push(`${label}：${error.message || '导出失败'}`);
            }
            if (done < exportable.length) {
                await new Promise((resolve) => setTimeout(resolve, WORD_EXPORT_INTERVAL_MS));
            }
        }

        if (failed.length) {
            showMessage(`Word 导出完成：成功 ${exportable.length - failed.length} 个，失败 ${failed.length} 个 —— ${failed.join('；')}`, 'warning');
        } else {
            showMessage(`Word 导出完成：成功导出 ${exportable.length} 个文档`, 'success');
        }
    } catch (error) {
        showMessage(error.message || 'Word 导出失败');
    } finally {
        button.disabled = false;
        button.innerHTML = originalHtml;
    }
}

async function exportPreview() {
    const exportName = document.getElementById('exportNameInput').value.trim();
    const query = exportName ? `?export_name=${encodeURIComponent(exportName)}` : '';
    const button = document.getElementById('exportBtn');
    button.disabled = true; button.innerHTML = '<span class="spinner-border spinner-border-sm me-1"></span>正在导出';
    // 此入口的历史契约始终是“按股票拆 Excel，再合并 ZIP”。
    // 不从首屏预览元数据推断股票数量：首屏只预加载一个年份分组，无法代表整任务。
    const response = await Api.endpoints.export.globalPreviewStocks(encodeURIComponent(currentTaskId), query);
    if (!response.ok) { button.disabled = false; button.innerHTML = '<i class="bi bi-file-earmark-arrow-down me-1"></i>导出'; return showMessage('导出失败'); }
    const contentDisposition = response.headers.get('Content-Disposition') || '';
    const utf8Filename = contentDisposition.match(/filename\*=UTF-8''([^;]+)/i);
    const fallbackFilename = contentDisposition.match(/filename="?([^";]+)"?/i);
    const downloadName = utf8Filename ? decodeURIComponent(utf8Filename[1]) : (fallbackFilename?.[1] || '导出文件');
    const blob = await response.blob(); const url = URL.createObjectURL(blob); const link = document.createElement('a');
    link.href = url; link.download = downloadName; document.body.appendChild(link); link.click(); link.remove(); URL.revokeObjectURL(url);
    button.disabled = false; button.innerHTML = '<i class="bi bi-file-earmark-arrow-down me-1"></i>导出';
}

document.getElementById('queryForm').addEventListener('submit', queryTask);
document.getElementById('stockSelect').addEventListener('change', (event) => {
    activeStockCode = event.target.value; activeGroupKey = '';
    if (groupMode === 'stock') return loadMetadataGroup(activeMetadataGroup(), `正在加载 ${activeStockCode}…`);
    renderYearOptions(); renderTable();
});
document.getElementById('yearSelect').addEventListener('change', (event) => {
    activeGroupKey = event.target.value;
    if (groupMode === 'year') return loadMetadataGroup(activeMetadataGroup(), `正在加载 ${activeGroupKey}…`);
    renderTable();
});
document.getElementById('exportBtn').addEventListener('click', exportPreview);
document.getElementById('exportWordBtn').addEventListener('click', openWordExportModal);
document.getElementById('wordExportResultList').addEventListener('change', (event) => {
    const checkbox = event.target.closest('input[type="checkbox"]');
    if (!checkbox) return;
    const resultId = checkbox.dataset.resultId;
    if (checkbox.checked) {
        wordExportSelection.add(resultId);
    } else {
        wordExportSelection.delete(resultId);
    }
    updateWordExportSummary();
});
document.getElementById('wordExportSelectAllBtn').addEventListener('click', () => {
    wordExportSelection = new Set(wordExportEligibleItems().map((item) => String(item.resultId)));
    renderWordExportList();
});
document.getElementById('wordExportClearBtn').addEventListener('click', () => {
    wordExportSelection = new Set();
    renderWordExportList();
});
document.getElementById('confirmWordExportBtn').addEventListener('click', confirmWordExport);

// 支持 /global-preview/single-product?task_id=<id> 直达（C 系列详情页「全局预览」入口）。
const urlTaskId = new URLSearchParams(window.location.search).get('task_id');
if (urlTaskId) {
    document.getElementById('taskIdInput').value = urlTaskId;
    queryTask();
}

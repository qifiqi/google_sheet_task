
let currentTaskId = '';
let previewPayload = null;
let activeStockCode = '';
let activeGroupKey = '';
let groupMode = 'year';
let previewGroups = [];
const previewCache = new Map();

const escapeHtml = (value) => String(value == null ? '' : value)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;').replace(/'/g, '&#39;');

function showMessage(message, type = 'danger') {
    const box = document.getElementById('messageBox');
    box.className = `alert alert-${type} mb-0`;
    box.textContent = message;
}

function hideResults() {
    ['filterCard', 'previewCard', 'loadingCard'].forEach((id) => document.getElementById(id).classList.add('d-none'));
    document.getElementById('exportBtn').disabled = true;
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
    event.preventDefault();
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

async function exportPreview() {
    const exportName = document.getElementById('exportNameInput').value.trim();
    const query = exportName ? `?export_name=${encodeURIComponent(exportName)}` : '';
    const button = document.getElementById('exportBtn');
    button.disabled = true; button.innerHTML = '<span class="spinner-border spinner-border-sm me-1"></span>正在导出';
    const response = await Api.endpoints.export.globalPreview(encodeURIComponent(currentTaskId), query);
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

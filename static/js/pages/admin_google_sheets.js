// 页面脚本（templates/admin/google_sheets.html 内联脚本原样抽离，F5 de-jinja）。
let googleSheetAdminItems = [];
// F5 de-jinja（03 §3 #7/#8）：原服务端注入的表类型枚举改为 /api/meta/enums 客户端渲染
//（字段名核对自 app/routes/meta_api.py：google_sheet_table_types）。
let GOOGLE_SHEET_TABLE_TYPE_OPTIONS = [];
let DEFAULT_GOOGLE_SHEET_TABLE_TYPE = '';

function renderGoogleSheetTableTypeOptions() {
    [document.getElementById('tableTypeFilter'), document.getElementById('sheetTableType')]
        .forEach(function (select) {
            if (!select) {
                return;
            }
            GOOGLE_SHEET_TABLE_TYPE_OPTIONS.forEach(function (option) {
                const optionEl = document.createElement('option');
                optionEl.value = option.value;
                optionEl.textContent = option.label;
                select.appendChild(optionEl);
            });
        });
}

Api.endpoints.meta.enums().then(function (data) {
    GOOGLE_SHEET_TABLE_TYPE_OPTIONS = data.google_sheet_table_types || [];
    DEFAULT_GOOGLE_SHEET_TABLE_TYPE = GOOGLE_SHEET_TABLE_TYPE_OPTIONS.length
        ? GOOGLE_SHEET_TABLE_TYPE_OPTIONS[0].value
        : '';
    renderGoogleSheetTableTypeOptions();
}).catch(function (error) {
    console.error('加载表类型枚举失败', error);
});


function escapeHtml(value) {
    return String(value || '').replace(/[&<>"']/g, function(char) {
        return ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[char];
    });
}

function buildGoogleSheetUrl(spreadsheetId) {
    const id = String(spreadsheetId || '').trim();
    return id ? `https://docs.google.com/spreadsheets/d/${encodeURIComponent(id)}/edit` : '';
}

function openCreateModal() {
    document.getElementById('sheetModalTitle').textContent = '新增表格';
    document.getElementById('sheetRecordId').value = '';
    document.getElementById('sheetName').value = '';
    document.getElementById('sheetSpreadsheetId').value = '';
    document.getElementById('sheetTableType').value = DEFAULT_GOOGLE_SHEET_TABLE_TYPE;
    document.getElementById('sheetRemark').value = '';
    document.getElementById('sheetIsActive').checked = true;
}

function extractSpreadsheetId(input) {
    if (!input) return '';
    const match = input.match(/\/spreadsheets\/d\/([a-zA-Z0-9-_]+)/);
    return match ? match[1] : input.trim();
}

function openEditModal(id) {
    const item = googleSheetAdminItems.find(function(record) { return record.id === id; });
    if (!item) {
        showNotification('未找到对应记录', 'error');
        return;
    }
    document.getElementById('sheetModalTitle').textContent = '编辑表格';
    document.getElementById('sheetRecordId').value = item.id;
    document.getElementById('sheetName').value = item.name || '';
    document.getElementById('sheetSpreadsheetId').value = item.spreadsheet_id || '';
    document.getElementById('sheetTableType').value = item.table_type || DEFAULT_GOOGLE_SHEET_TABLE_TYPE;
    document.getElementById('sheetRemark').value = item.remark || '';
    document.getElementById('sheetIsActive').checked = !!item.is_active;
    bootstrap.Modal.getOrCreateInstance(document.getElementById('sheetModal')).show();
}

function renderGoogleSheetsAdmin() {
    const keyword = document.getElementById('keyword').value.trim().toLowerCase();
    const activeFilter = document.getElementById('activeFilter').value;
    const usageFilter = document.getElementById('usageFilter').value;
    const tableTypeFilter = document.getElementById('tableTypeFilter').value;
    const tbody = document.getElementById('sheetTableBody');

    const rows = googleSheetAdminItems.filter(function(item) {
        const matchKeyword = !keyword ||
            String(item.name || '').toLowerCase().includes(keyword) ||
            String(item.spreadsheet_id || '').toLowerCase().includes(keyword);
        const matchActive = activeFilter === '' || String(Number(!!item.is_active)) === activeFilter;
        const matchUsage = usageFilter === '' || String(Number(!!item.is_in_use)) === usageFilter;
        const matchTableType = tableTypeFilter === '' || String(item.table_type || '') === tableTypeFilter;
        return matchKeyword && matchActive && matchUsage && matchTableType;
    });

    if (!rows.length) {
        tbody.innerHTML = '<tr><td colspan="8" class="text-center text-muted py-4">暂无数据</td></tr>';
        return;
    }

    tbody.innerHTML = rows.map(function(item) {
        return `
            <tr>
                <td>${escapeHtml(item.name || '-')}</td>
                <td><code>${escapeHtml(item.spreadsheet_id || '-')}</code></td>
                <td><span class="badge bg-info text-dark">${escapeHtml(String(item.table_type || '').toUpperCase() || '-')}</span></td>
                <td>${escapeHtml(item.remark || '-')}</td>
                <td>${item.is_active ? '<span class="badge bg-success">启用</span>' : '<span class="badge bg-secondary">停用</span>'}</td>
                <td>${item.is_in_use ? '<span class="badge bg-warning text-dark">使用中</span>' : '<span class="badge bg-light text-dark">空闲</span>'}</td>
                <td><code>${escapeHtml(item.current_task_id || '-')}</code></td>
                <td class="text-end">
                    ${item.spreadsheet_id
                        ? `<a class="btn btn-sm btn-outline-success me-2" href="${buildGoogleSheetUrl(item.spreadsheet_id)}" target="_blank" rel="noopener noreferrer">跳转到模型</a>`
                        : '<button class="btn btn-sm btn-outline-success me-2" type="button" disabled>跳转到模型</button>'}
                    <button class="btn btn-sm btn-outline-primary me-2" type="button" onclick="openEditModal(${item.id})">编辑</button>
                    <button class="btn btn-sm btn-outline-danger" type="button" onclick="deleteGoogleSheetRecord(${item.id})" ${item.is_in_use ? 'disabled' : ''}>删除</button>
                </td>
            </tr>
        `;
    }).join('');
}

function loadGoogleSheetsAdmin() {
    const tableTypeFilter = document.getElementById('tableTypeFilter').value;
    const params = new URLSearchParams({ include_inactive: '1' });
    if (tableTypeFilter) {
        params.set('table_type', tableTypeFilter);
    }
    Api.endpoints.googleSheet.sheets(params.toString())
        .then(function(data) {
            googleSheetAdminItems = Array.isArray(data.items) ? data.items : [];
            renderGoogleSheetsAdmin();
        })
        .catch(function(error) {
            document.getElementById('sheetTableBody').innerHTML = `<tr><td colspan="8" class="text-center text-danger py-4">${escapeHtml(error.message)}</td></tr>`;
            showNotification('加载表格列表失败：' + error.message, 'error');
        });
}

function submitSheetForm() {
    const id = document.getElementById('sheetRecordId').value;
    const spreadsheetInput = document.getElementById('sheetSpreadsheetId').value.trim();
    const payload = {
        name: document.getElementById('sheetName').value.trim(),
        spreadsheet_id: extractSpreadsheetId(spreadsheetInput),
        table_type: document.getElementById('sheetTableType').value,
        remark: document.getElementById('sheetRemark').value.trim(),
        is_active: document.getElementById('sheetIsActive').checked
    };

    if (!payload.spreadsheet_id) {
        showNotification('请输入 Spreadsheet ID', 'error');
        return;
    }

    (id ? Api.endpoints.adminGoogleSheets.update(id, payload) : Api.endpoints.adminGoogleSheets.create(payload))
        .then(function(envelope) {
            bootstrap.Modal.getOrCreateInstance(document.getElementById('sheetModal')).hide();
            showNotification(envelope.message || '保存成功', 'success');
            loadGoogleSheetsAdmin();
        })
        .catch(function(error) {
            showNotification('保存失败：' + error.message, 'error');
        });
}

function deleteGoogleSheetRecord(id) {
    if (!confirm('确定删除这条 Google Sheet 配置吗？')) {
        return;
    }
    Api.endpoints.adminGoogleSheets.remove(id)
        .then(function(envelope) {
            showNotification(envelope.message || '删除成功', 'success');
            loadGoogleSheetsAdmin();
        })
        .catch(function(error) {
            showNotification('删除失败：' + error.message, 'error');
        });
}

document.addEventListener('DOMContentLoaded', function() {
    ['keyword', 'activeFilter', 'usageFilter', 'tableTypeFilter'].forEach(function(id) {
        document.getElementById(id).addEventListener('input', renderGoogleSheetsAdmin);
        document.getElementById(id).addEventListener('change', renderGoogleSheetsAdmin);
    });
    loadGoogleSheetsAdmin();
});

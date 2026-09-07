// 页面脚本（templates/admin/navigation.html 内联脚本原样抽离，F5 de-jinja）。
let navigationItems = [];

document.addEventListener('DOMContentLoaded', function() {
    ['navigationKeyword', 'navigationParentFilter', 'navigationVisibleFilter'].forEach(function(id) {
        document.getElementById(id)?.addEventListener('input', renderNavigationTable);
        document.getElementById(id)?.addEventListener('change', renderNavigationTable);
    });
    loadNavigationItems();
});

function escapeHtml(value) {
    return String(value ?? '')
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
}

function getParentOptions() {
    return navigationItems.filter(function(item) {
        return !item.path;
    });
}

function parentLabel(parentKey) {
    if (!parentKey) return '-';
    const parent = navigationItems.find(function(item) {
        return item.key === parentKey;
    });
    return parent ? parent.label : parentKey;
}

function refreshParentSelects() {
    const options = ['<option value="">无</option>']
        .concat(getParentOptions().map(function(item) {
            return `<option value="${escapeHtml(item.key)}">${escapeHtml(item.label)} (${escapeHtml(item.key)})</option>`;
        }))
        .join('');
    document.getElementById('navigationParentKey').innerHTML = options;

    const filterOptions = ['<option value="">全部</option>']
        .concat(getParentOptions().map(function(item) {
            return `<option value="${escapeHtml(item.key)}">${escapeHtml(item.label)}</option>`;
        }))
        .join('');
    document.getElementById('navigationParentFilter').innerHTML = filterOptions;
}

function loadNavigationItems() {
    Api.endpoints.adminNavigation.list()
        .then(function(data) {
            navigationItems = (data && Array.isArray(data.items)) ? data.items : [];
            refreshParentSelects();
            renderNavigationTable();
        })
        .catch(function(error) {
            showError(error.message || '加载路由失败');
        });
}

function renderNavigationTable() {
    const keyword = document.getElementById('navigationKeyword').value.trim().toLowerCase();
    const parentFilter = document.getElementById('navigationParentFilter').value;
    const visibleFilter = document.getElementById('navigationVisibleFilter').value;
    const tbody = document.getElementById('navigationTableBody');

    const rows = navigationItems.filter(function(item) {
        const matchKeyword = !keyword || [
            item.label,
            item.key,
            item.path,
            item.permission,
            item.parent_key,
        ].join(' ').toLowerCase().includes(keyword);
        const matchParent = !parentFilter || item.parent_key === parentFilter;
        const matchVisible = !visibleFilter || String(Number(Boolean(item.is_visible))) === visibleFilter;
        return matchKeyword && matchParent && matchVisible;
    });

    if (!rows.length) {
        tbody.innerHTML = '<tr><td colspan="8" class="text-center text-muted py-4">暂无路由记录</td></tr>';
        return;
    }

    tbody.innerHTML = rows.map(function(item) {
        return `
            <tr>
                <td>${escapeHtml(item.label)}</td>
                <td><code>${escapeHtml(item.key)}</code></td>
                <td>${item.path ? `<code>${escapeHtml(item.path)}</code>` : '<span class="text-muted">分组</span>'}</td>
                <td>${item.permission ? `<code>${escapeHtml(item.permission)}</code>` : '<span class="text-muted">无</span>'}</td>
                <td>${escapeHtml(parentLabel(item.parent_key))}</td>
                <td>${Number(item.sort_order || 0)}</td>
                <td>${item.is_visible ? '<span class="badge bg-success">显示</span>' : '<span class="badge bg-secondary">隐藏</span>'}</td>
                <td class="text-end">
                    <button class="btn btn-sm btn-outline-primary" type="button" onclick="openEditNavigationModal(${item.id})">编辑</button>
                </td>
            </tr>
        `;
    }).join('');
}

function openCreateNavigationModal() {
    refreshParentSelects();
    document.getElementById('navigationModalTitle').textContent = '新增路由';
    document.getElementById('navigationRecordId').value = '';
    document.getElementById('navigationLabel').value = '';
    document.getElementById('navigationKey').value = '';
    document.getElementById('navigationPath').value = '';
    document.getElementById('navigationPermission').value = '';
    document.getElementById('navigationParentKey').value = '';
    document.getElementById('navigationSortOrder').value = '0';
    document.getElementById('navigationVisible').checked = false;
    document.getElementById('navigationDeleteBtn').style.display = 'none';
    bootstrap.Modal.getOrCreateInstance(document.getElementById('navigationModal')).show();
}

function openEditNavigationModal(id) {
    const item = navigationItems.find(function(record) {
        return record.id === id;
    });
    if (!item) {
        showError('路由记录不存在');
        return;
    }
    refreshParentSelects();
    document.getElementById('navigationModalTitle').textContent = '编辑路由';
    document.getElementById('navigationRecordId').value = item.id;
    document.getElementById('navigationLabel').value = item.label || '';
    document.getElementById('navigationKey').value = item.key || '';
    document.getElementById('navigationPath').value = item.path || '';
    document.getElementById('navigationPermission').value = item.permission || '';
    document.getElementById('navigationParentKey').value = item.parent_key || '';
    document.getElementById('navigationSortOrder').value = item.sort_order || 0;
    document.getElementById('navigationVisible').checked = !!item.is_visible;
    document.getElementById('navigationDeleteBtn').style.display = '';
    bootstrap.Modal.getOrCreateInstance(document.getElementById('navigationModal')).show();
}

function collectNavigationPayload() {
    return {
        label: document.getElementById('navigationLabel').value.trim(),
        key: document.getElementById('navigationKey').value.trim(),
        path: document.getElementById('navigationPath').value.trim(),
        permission: document.getElementById('navigationPermission').value.trim(),
        parent_key: document.getElementById('navigationParentKey').value,
        sort_order: Number(document.getElementById('navigationSortOrder').value || 0),
        is_visible: document.getElementById('navigationVisible').checked
    };
}

function submitNavigationForm() {
    const id = document.getElementById('navigationRecordId').value;
    const payload = collectNavigationPayload();

    (id ? Api.endpoints.adminNavigation.update(id, payload) : Api.endpoints.adminNavigation.create(payload))
        .then(function(envelope) {
            bootstrap.Modal.getOrCreateInstance(document.getElementById('navigationModal')).hide();
            showNotification(envelope.message || '保存成功', 'success');
            loadNavigationItems();
        })
        .catch(function(error) {
            showError(error.message || '保存失败');
        });
}

function deleteCurrentNavigationItem() {
    const id = document.getElementById('navigationRecordId').value;
    if (!id || !confirm('确定删除这条路由记录吗？')) {
        return;
    }
    Api.endpoints.adminNavigation.remove(id)
        .then(function(envelope) {
            bootstrap.Modal.getOrCreateInstance(document.getElementById('navigationModal')).hide();
            showNotification(envelope.message || '删除成功', 'success');
            loadNavigationItems();
        })
        .catch(function(error) {
            showError(error.message || '删除失败');
        });
}

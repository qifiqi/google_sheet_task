// 页面脚本（templates/admin/roles.html 内联脚本原样抽离，F5 de-jinja）。
let roles = [];
let groupedPermissions = {};
let roleModal = null;
let permissionPreviewModal = null;

function canManageRoles() {
    return Boolean(window.TemplateApp?.isAdmin());
}

function escapeHtml(value) {
    return String(value ?? '')
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
}

function getSelectedPermissionIds() {
    return Array.from(document.querySelectorAll('#permissionGroups input[type="checkbox"]:checked'))
        .map((input) => Number(input.value));
}

function renderPermissionGroups(selectedIds = []) {
    const container = document.getElementById('permissionGroups');
    const groups = Object.entries(groupedPermissions);
    if (!groups.length) {
        container.innerHTML = '<div class="text-muted">暂无可选权限</div>';
        return;
    }

    container.innerHTML = groups.map(([group, permissions]) => `
        <div class="mb-3">
            <div class="fw-semibold mb-2 text-capitalize">${escapeHtml(group)}</div>
            <div class="row g-2">
                ${(permissions || []).map((permission) => `
                    <div class="col-md-6">
                        <label class="border rounded px-3 py-2 w-100">
                            <input class="form-check-input me-2" type="checkbox" value="${permission.id}" ${selectedIds.includes(permission.id) ? 'checked' : ''}>
                            <span class="fw-semibold">${escapeHtml(permission.name)}</span>
                            <div class="small text-muted">${escapeHtml(permission.code)}</div>
                        </label>
                    </div>
                `).join('')}
            </div>
        </div>
    `).join('');
}

function getPermissionSummary(role) {
    const permissions = Array.isArray(role.permissions) ? role.permissions : [];
    if (!permissions.length) {
        return '<span class="text-muted">未分配</span>';
    }

    const preview = permissions.slice(0, 3).map((permission) =>
        `<span class="badge text-bg-light">${escapeHtml(permission.name)}</span>`
    ).join('');
    const remaining = permissions.length - 3;
    const moreBadge = remaining > 0
        ? `<span class="badge bg-secondary-subtle text-secondary-emphasis">+${remaining}</span>`
        : '';

    return `
        <div class="role-permission-summary">
            ${preview}
            ${moreBadge}
            <button type="button" class="btn btn-sm btn-link p-0 text-decoration-none" onclick="openPermissionPreview(${role.id})">
                查看详情
            </button>
        </div>
    `;
}

function renderRoles() {
    const tbody = document.getElementById('rolesTableBody');
    if (!roles.length) {
        tbody.innerHTML = '<tr><td colspan="7" class="text-center text-muted py-4">暂无角色</td></tr>';
        return;
    }

    tbody.innerHTML = roles.map((role) => {
        const actionButtons = canManageRoles()
            ? `
                <button type="button" class="btn btn-sm btn-outline-primary me-2" onclick="openRoleModal(${role.id})">编辑</button>
                ${role.is_system ? '' : `<button type="button" class="btn btn-sm btn-outline-danger" onclick="deleteRole(${role.id})">删除</button>`}
            `
            : '<span class="text-muted">只读</span>';

        return `
            <tr>
                <td>${role.id}</td>
                <td>${escapeHtml(role.name)}</td>
                <td><code>${escapeHtml(role.code)}</code></td>
                <td class="role-description-cell">${escapeHtml(role.description || '-')}</td>
                <td>${getPermissionSummary(role)}</td>
                <td class="text-center">${role.is_system ? '<span class="badge bg-warning text-dark">内置</span>' : '<span class="text-muted">否</span>'}</td>
                <td class="text-end text-nowrap">${actionButtons}</td>
            </tr>
        `;
    }).join('');
}

function openPermissionPreview(roleId) {
    const role = roles.find((item) => item.id === roleId);
    if (!role) {
        showNotification('未找到角色信息', 'error');
        return;
    }

    const title = document.getElementById('permissionPreviewTitle');
    const body = document.getElementById('permissionPreviewBody');
    const permissions = Array.isArray(role.permissions) ? role.permissions : [];

    title.textContent = `${role.name} 权限详情`;
    if (!permissions.length) {
        body.innerHTML = '<div class="text-muted">暂无权限</div>';
        permissionPreviewModal.show();
        return;
    }

    const permissionMap = permissions.reduce((result, permission) => {
        const groupName = permission.group || 'other';
        if (!result[groupName]) {
            result[groupName] = [];
        }
        result[groupName].push(permission);
        return result;
    }, {});

    body.innerHTML = Object.entries(permissionMap).map(([groupName, items]) => `
        <div class="permission-detail-group">
            <div class="fw-semibold mb-2 text-capitalize">${escapeHtml(groupName)} (${items.length})</div>
            <div>
                ${items.map((permission) => `
                    <span class="permission-detail-item" title="${escapeHtml(permission.code)}">
                        ${escapeHtml(permission.name)}
                    </span>
                `).join('')}
            </div>
        </div>
    `).join('');
    permissionPreviewModal.show();
}

function resetRoleForm() {
    document.getElementById('roleId').value = '';
    document.getElementById('roleName').value = '';
    document.getElementById('roleCode').value = '';
    document.getElementById('roleCode').disabled = false;
    document.getElementById('roleDescription').value = '';
    renderPermissionGroups([]);
}

function openRoleModal(roleId = null) {
    if (!canManageRoles()) {
        showNotification('当前账号没有角色管理权限', 'error');
        return;
    }

    const title = document.getElementById('roleModalTitle');
    resetRoleForm();

    if (roleId != null) {
        const role = roles.find((item) => item.id === roleId);
        if (!role) {
            showNotification('未找到角色信息', 'error');
            return;
        }
        title.textContent = '编辑角色';
        document.getElementById('roleId').value = role.id;
        document.getElementById('roleName').value = role.name;
        document.getElementById('roleCode').value = role.code;
        document.getElementById('roleCode').disabled = true;
        document.getElementById('roleDescription').value = role.description || '';
        renderPermissionGroups((role.permissions || []).map((permission) => permission.id));
    } else {
        title.textContent = '新增角色';
    }

    roleModal.show();
}

function loadRoles() {
    ajaxRequest('/api/admin/roles', 'GET', null, function(err, response) {
        if (err) {
            showNotification(`加载角色失败: ${err.message}`, 'error');
            return;
        }
        roles = Array.isArray(response.data) ? response.data : [];
        renderRoles();
    });
}

function loadPermissions() {
    ajaxRequest('/api/admin/permissions', 'GET', null, function(err, response) {
        if (err) {
            showNotification(`加载权限失败: ${err.message}`, 'error');
            return;
        }
        groupedPermissions = response.data || {};
        renderPermissionGroups([]);
    });
}

function saveRole() {
    if (!canManageRoles()) {
        showNotification('当前账号没有角色管理权限', 'error');
        return;
    }

    const roleId = document.getElementById('roleId').value;
    const name = document.getElementById('roleName').value.trim();
    const code = document.getElementById('roleCode').value.trim();
    const payload = {
        name: name,
        description: document.getElementById('roleDescription').value.trim(),
        permission_ids: getSelectedPermissionIds(),
    };

    if (!name) {
        showNotification('请输入角色名称', 'error');
        return;
    }

    if (!roleId) {
        if (!code) {
            showNotification('新增角色时必须填写角色编码', 'error');
            return;
        }
        payload.code = code;
    }

    const url = roleId ? `/api/admin/roles/${roleId}` : '/api/admin/roles';
    const method = roleId ? 'PUT' : 'POST';
    ajaxRequest(url, method, payload, function(err, response) {
        if (err) {
            showNotification(`${roleId ? '更新' : '创建'}角色失败: ${err.message}`, 'error');
            return;
        }
        showNotification(response.message || '保存成功', 'success');
        roleModal.hide();
        loadRoles();
    });
}

function deleteRole(roleId) {
    if (!canManageRoles()) {
        showNotification('当前账号没有角色管理权限', 'error');
        return;
    }

    if (!window.confirm('确认删除这个角色吗？')) {
        return;
    }

    ajaxRequest(`/api/admin/roles/${roleId}`, 'DELETE', null, function(err, response) {
        if (err) {
            showNotification(`删除角色失败: ${err.message}`, 'error');
            return;
        }
        showNotification(response.message || '删除成功', 'success');
        loadRoles();
    });
}

function initRolesPage() {
    roleModal = new bootstrap.Modal(document.getElementById('roleModal'));
    permissionPreviewModal = new bootstrap.Modal(document.getElementById('permissionPreviewModal'));

    const createRoleBtn = document.getElementById('createRoleBtn');
    const saveRoleBtn = document.getElementById('saveRoleBtn');

    if (createRoleBtn) {
        createRoleBtn.addEventListener('click', function() {
            openRoleModal();
        });
    }

    if (saveRoleBtn) {
        saveRoleBtn.hidden = !canManageRoles();
        saveRoleBtn.addEventListener('click', saveRole);
    }

    loadPermissions();
    loadRoles();
}

document.addEventListener('template-auth-ready', initRolesPage, { once: true });

document.addEventListener('DOMContentLoaded', function() {
    if (document.body.classList.contains('template-auth-ready') || document.body.dataset.authEnabled === 'false') {
        initRolesPage();
    }
});

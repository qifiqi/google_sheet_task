// 页面脚本（templates/admin/users.html 内联脚本原样抽离，F5 de-jinja）。
let users = []
let roles = []
let userModal = null
const DEV_ROLE_CODES = ['developer']

function canManageUsers() {
    return Boolean(window.TemplateApp?.isAdmin())
}

function escapeHtml(value) {
    return String(value ?? '')
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;')
}

function getSelectedRoleIds() {
    const value = document.getElementById('roleIds').value
    return value ? [Number(value)] : []
}

function isDeveloperRole(role) {
    return Boolean(role && DEV_ROLE_CODES.includes(role.code))
}

function isDeveloperUser(user) {
    return (user.roles || []).some(isDeveloperRole)
}

function selectedRoleCanOncall() {
    const roleId = getSelectedRoleIds()[0]
    const role = roles.find((item) => Number(item.id) === Number(roleId))
    return isDeveloperRole(role)
}

function syncOncallSwitch() {
    const wrapper = document.getElementById('oncallWrap')
    const checkbox = document.getElementById('isAlertOncall')
    const canOncall = selectedRoleCanOncall()
    wrapper.hidden = !canOncall
    if (!canOncall) {
        checkbox.checked = false
    }
}

function populateRoleOptions(selectedIds = []) {
    const select = document.getElementById('roleIds')
    const selectedId = selectedIds.length ? selectedIds[0] : ''
    select.innerHTML = `
        <option value="">请选择角色</option>
        ${roles.map((role) => `
            <option value="${role.id}" ${Number(selectedId) === Number(role.id) ? 'selected' : ''}>${escapeHtml(role.name)}</option>
        `).join('')}
    `
}

function renderSwitch(checked, onChange) {
    return `
        <div class="form-check form-switch m-0">
            <input class="form-check-input" type="checkbox" ${checked ? 'checked' : ''} onchange="${onChange}">
        </div>
    `
}

function renderUsers() {
    const tbody = document.getElementById('usersTableBody')
    if (!users.length) {
        tbody.innerHTML = '<tr><td colspan="9" class="text-center text-muted py-4">暂无用户</td></tr>'
        return
    }

    tbody.innerHTML = users.map((user) => {
        const roleBadges = (user.roles || []).length
            ? user.roles.map((role) => `<span class="badge text-bg-light me-1">${escapeHtml(role.name)}</span>`).join('')
            : '<span class="text-muted">-</span>'
        const actionButtons = canManageUsers()
            ? `
                <button type="button" class="btn btn-sm btn-outline-primary me-2" onclick="openUserModal(${user.id})">编辑</button>
                <button type="button" class="btn btn-sm btn-outline-danger" onclick="deleteUser(${user.id})">删除</button>
            `
            : '<span class="text-muted">只读</span>'

        return `
            <tr>
                <td>${user.id}</td>
                <td>${escapeHtml(user.username)}</td>
                <td>${roleBadges}</td>
                <td>${escapeHtml(user.mobile || '-')}</td>
                <td><span class="badge ${user.is_active ? 'bg-success' : 'bg-danger'}">${user.is_active ? '启用' : '禁用'}</span></td>
                <td>
                    ${canManageUsers() && isDeveloperUser(user)
                        ? renderSwitch(user.is_alert_oncall, `toggleOncall(${user.id}, this.checked)`)
                        : '-'}
                </td>
                <td>${formatTime(user.created_at)}</td>
                <td>${formatTime(user.last_login)}</td>
                <td class="text-end">${actionButtons}</td>
            </tr>
        `
    }).join('')
}

function resetUserForm() {
    document.getElementById('userId').value = ''
    document.getElementById('username').value = ''
    document.getElementById('username').disabled = false
    document.getElementById('mobile').value = ''
    document.getElementById('password').value = ''
    document.getElementById('isActive').checked = true
    document.getElementById('isAlertOncall').checked = false
    populateRoleOptions([])
    syncOncallSwitch()
}

function openUserModal(userId = null) {
    if (!canManageUsers()) {
        showNotification('当前账号没有用户管理权限', 'error')
        return
    }

    resetUserForm()
    const title = document.getElementById('userModalTitle')

    if (userId != null) {
        const user = users.find((item) => item.id === userId)
        if (!user) {
            showNotification('未找到用户信息', 'error')
            return
        }
        title.textContent = '编辑用户'
        document.getElementById('userId').value = user.id
        document.getElementById('username').value = user.username
        document.getElementById('username').disabled = true
        document.getElementById('mobile').value = user.mobile || ''
        document.getElementById('isActive').checked = Boolean(user.is_active)
        document.getElementById('isAlertOncall').checked = isDeveloperUser(user) && Boolean(user.is_alert_oncall)
        populateRoleOptions((user.roles || []).map((role) => role.id))
    } else {
        title.textContent = '新增用户'
    }

    syncOncallSwitch()
    userModal.show()
}

function loadUsers() {
    ajaxRequest('/api/admin/users', 'GET', null, function(err, response) {
        if (err) {
            showNotification(`加载用户失败: ${err.message}`, 'error')
            return
        }
        users = Array.isArray(response.data) ? response.data : []
        renderUsers()
    })
}

function loadRoles() {
    ajaxRequest('/api/admin/roles', 'GET', null, function(err, response) {
        if (err) {
            showNotification(`加载角色失败: ${err.message}`, 'error')
            return
        }
        roles = Array.isArray(response.data) ? response.data : []
        populateRoleOptions([])
    })
}

function saveUser() {
    if (!canManageUsers()) {
        showNotification('当前账号没有用户管理权限', 'error')
        return
    }

    const userId = document.getElementById('userId').value
    const username = document.getElementById('username').value.trim()
    const password = document.getElementById('password').value
    const payload = {
        mobile: document.getElementById('mobile').value.trim(),
        is_active: document.getElementById('isActive').checked,
        is_alert_oncall: selectedRoleCanOncall() && document.getElementById('isAlertOncall').checked,
        role_ids: getSelectedRoleIds(),
    }

    if (!payload.role_ids.length) {
        showNotification('请选择角色', 'error')
        return
    }

    if (!userId) {
        if (!username || !password) {
            showNotification('新增用户时必须填写用户名和密码', 'error')
            return
        }
        payload.username = username
        payload.password = password
    } else if (password) {
        payload.password = password
    }

    const url = userId ? `/api/admin/users/${userId}` : '/api/admin/users'
    const method = userId ? 'PUT' : 'POST'
    ajaxRequest(url, method, payload, function(err, response) {
        if (err) {
            showNotification(`${userId ? '更新' : '创建'}用户失败: ${err.message}`, 'error')
            return
        }
        showNotification(response.message || '保存成功', 'success')
        userModal.hide()
        loadUsers()
    })
}

function toggleOncall(userId, checked) {
    ajaxRequest(`/api/admin/users/${userId}`, 'PUT', { is_alert_oncall: checked }, function(err, response) {
        if (err) {
            showNotification(`更新值班状态失败: ${err.message}`, 'error')
            loadUsers()
            return
        }
        showNotification(response.message || '值班状态已更新', 'success')
        loadUsers()
    })
}

function toggleActive(userId, checked) {
    ajaxRequest(`/api/admin/users/${userId}`, 'PUT', { is_active: checked }, function(err, response) {
        if (err) {
            showNotification(`更新状态失败: ${err.message}`, 'error')
            loadUsers()
            return
        }
        showNotification(response.message || '状态已更新', 'success')
        loadUsers()
    })
}

function deleteUser(userId) {
    if (!canManageUsers()) {
        showNotification('当前账号没有用户管理权限', 'error')
        return
    }
    if (!window.confirm('确认删除这个用户吗？')) {
        return
    }
    ajaxRequest(`/api/admin/users/${userId}`, 'DELETE', null, function(err, response) {
        if (err) {
            showNotification(`删除用户失败: ${err.message}`, 'error')
            return
        }
        showNotification(response.message || '删除成功', 'success')
        loadUsers()
    })
}

function initUsersPage() {
    userModal = new bootstrap.Modal(document.getElementById('userModal'))

    const createUserBtn = document.getElementById('createUserBtn')
    const saveUserBtn = document.getElementById('saveUserBtn')
    const roleIds = document.getElementById('roleIds')

    if (createUserBtn) {
        createUserBtn.addEventListener('click', function() {
            openUserModal()
        })
    }
    if (saveUserBtn) {
        saveUserBtn.hidden = !canManageUsers()
        saveUserBtn.addEventListener('click', saveUser)
    }
    if (roleIds) {
        roleIds.addEventListener('change', syncOncallSwitch)
    }

    loadRoles()
    loadUsers()
}

document.addEventListener('template-auth-ready', initUsersPage, { once: true })

document.addEventListener('DOMContentLoaded', function() {
    if (document.body.classList.contains('template-auth-ready') || document.body.dataset.authEnabled === 'false') {
        initUsersPage()
    }
})

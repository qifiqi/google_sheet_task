// 页面脚本（templates/admin/config.html 内联脚本原样抽离，F5 de-jinja）。
    let googleSheetTokens = [];

    document.addEventListener('DOMContentLoaded', function() {
        bindEvents();
        reloadAllData();
    });

    function bindEvents() {
        document.getElementById('edit-config-save-btn')?.addEventListener('click', saveEditedConfig);
        document.getElementById('token-import-btn')?.addEventListener('click', importGoogleSheetTokenFromAdmin);
        document.getElementById('save-token-btn')?.addEventListener('click', saveEditedToken);
        document.getElementById('delete-token-btn')?.addEventListener('click', deleteCurrentToken);
    }

    function reloadAllData() {
        loadConfig();
        loadGoogleSheetTokens();
    }

    function escapeHtml(text) {
        if (text === null || text === undefined) {
            return '';
        }
        return String(text)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#039;');
    }

    function formatLimit(value) {
        const num = Number(value || 0);
        return num > 0 ? String(num) : '\u65e0\u9650';
    }

    function formatTime(value) {
        if (!value) {
            return '-';
        }
        try {
            return new Date(value).toLocaleString();
        } catch (e) {
            return value;
        }
    }

    function loadConfig() {
        ajaxRequest('/api/system-configs', 'GET', null, function(err, data) {
            if (!err && data && data.status === 'success') {
                renderConfigTable((data.data && data.data.configs) || []);
            } else {
                showNotification('\u52a0\u8f7d\u914d\u7f6e\u5931\u8d25: ' + (data ? data.message : '\u7f51\u7edc\u9519\u8bef'), 'error');
            }
        });
    }

    function renderConfigTable(configs) {
        const tbody = document.getElementById('configs-table-body');
        tbody.innerHTML = '';

        configs.forEach(function(c) {
            const tr = document.createElement('tr');
            tr.innerHTML = `
                <td><code>${escapeHtml(c.key)}</code></td>
                <td style="white-space: pre-wrap; word-break: break-word;">${escapeHtml(c.value)}</td>
                <td style="white-space: pre-wrap; word-break: break-word;">${escapeHtml(c.description)}</td>
                <td><button type="button" class="btn btn-sm btn-primary">\u7f16\u8f91</button></td>
            `;

            const btn = tr.querySelector('button');
            btn.dataset.key = c.key || '';
            btn.dataset.value = c.value || '';
            btn.dataset.description = c.description || '';
            btn.addEventListener('click', function() {
                openEditConfigModal(btn);
            });

            tbody.appendChild(tr);
        });
    }

    function openEditConfigModal(btn) {
        document.getElementById('edit-config-key').value = btn.dataset.key || '';
        document.getElementById('edit-config-value').value = btn.dataset.value || '';
        document.getElementById('edit-config-description').value = btn.dataset.description || '';
        bootstrap.Modal.getOrCreateInstance(document.getElementById('editConfigModal')).show();
    }

    function saveEditedConfig() {
        const key = document.getElementById('edit-config-key').value;
        const value = document.getElementById('edit-config-value').value;
        const description = document.getElementById('edit-config-description').value;

        ajaxRequest(`/api/system-configs/${encodeURIComponent(key)}`, 'PUT', {
            value: value,
            description: description
        }, function(err, data) {
            if (!err && data && data.status === 'success') {
                bootstrap.Modal.getOrCreateInstance(document.getElementById('editConfigModal')).hide();
                showNotification('\u914d\u7f6e\u66f4\u65b0\u6210\u529f', 'success');
                loadConfig();
            } else {
                showNotification('\u914d\u7f6e\u66f4\u65b0\u5931\u8d25: ' + (data ? data.message : '\u672a\u77e5\u9519\u8bef'), 'error');
            }
        });
    }

    function loadGoogleSheetTokens() {
        Api.endpoints.googleSheet.tokens()
            .then(data => {
                googleSheetTokens = Array.isArray(data.tokens) ? data.tokens : [];
                renderTokenSummary((data && data.summary) || {});
                renderTokenTable(googleSheetTokens);
            })
            .catch(error => {
                showNotification('\u52a0\u8f7d Token \u5931\u8d25: ' + error.message, 'error');
            });
    }

    function renderTokenSummary(summary) {
        document.getElementById('token-summary-in-use').textContent = summary.current_total_in_use ?? 0;
        document.getElementById('token-summary-usage').textContent = summary.current_total_usage ?? 0;
        document.getElementById('token-summary-global-max').textContent = formatLimit(summary.global_max_usage ?? 0);
        document.getElementById('token-summary-available').textContent = summary.available_token_count ?? 0;
    }

    function renderTokenTable(tokens) {
        const tbody = document.getElementById('google-sheet-token-table-body');
        tbody.innerHTML = '';

        tokens.forEach(function(token) {
            const tr = document.createElement('tr');
            const statusBadge = token.is_active
                ? '<span class="badge bg-success">\u542f\u7528</span>'
                : '<span class="badge bg-secondary">\u505c\u7528</span>';
            const availableBadge = token.is_available
                ? '<span class="badge bg-primary">\u53ef\u7528</span>'
                : '<span class="badge bg-warning text-dark">\u5df2\u8fbe\u4e0a\u9650</span>';

            tr.innerHTML = `
                <td>${token.id}</td>
                <td>${escapeHtml(token.name)}</td>
                <td><code>${escapeHtml(token.task_type || 'google_sheet')}</code></td>
                <td>${token.token_context_size || 0}</td>
                <td>${token.current_in_use_count || 0}</td>
                <td>${token.task_usage_count || 0}</td>
                <td>${formatLimit(token.max_usage_count)}</td>
                <td>${statusBadge} ${availableBadge}</td>
                <td>${escapeHtml(formatTime(token.last_used_at))}</td>
                <td><button type="button" class="btn btn-sm btn-primary">\u7f16\u8f91</button></td>
            `;

            tr.querySelector('button').addEventListener('click', function() {
                openEditTokenModal(token.id);
            });

            tbody.appendChild(tr);
        });
    }

    function importGoogleSheetTokenFromAdmin() {
        const tokenContext = document.getElementById('token-import-context').value.trim();
        const name = document.getElementById('token-import-name').value.trim();
        const maxUsageCount = document.getElementById('token-import-max-usage').value.trim();
        const taskType = document.getElementById('token-import-task-type').value;

        if (!tokenContext) {
            showNotification('\u8bf7\u8f93\u5165 Token JSON \u5185\u5bb9', 'warning');
            return;
        }

        Api.endpoints.googleSheet.importTokenEnvelope({
            token_context: tokenContext,
            name: name || null,
            max_usage_count: maxUsageCount === '' ? null : Number(maxUsageCount),
            task_type: taskType || 'google_sheet'
        })
            .then(envelope => {
                showNotification(envelope.message || 'Token \u65b0\u589e\u6210\u529f', 'success');
                document.getElementById('token-import-name').value = '';
                document.getElementById('token-import-max-usage').value = '';
                document.getElementById('token-import-context').value = '';
                loadGoogleSheetTokens();
            })
            .catch(error => {
                showNotification('\u65b0\u589e Token \u5931\u8d25: ' + error.message, 'error');
            });
    }

    function openEditTokenModal(tokenId) {
        Api.endpoints.googleSheet.tokenDetail(tokenId)
            .then(data => {
                const token = (data && data.token) || {};
                document.getElementById('edit-token-id').value = token.id || '';
                document.getElementById('edit-token-name').value = token.name || '';
                document.getElementById('edit-token-task-type').value = token.task_type || 'google_sheet';
                document.getElementById('edit-token-max-usage').value = token.max_usage_count || 0;
                document.getElementById('edit-token-active').value = token.is_active ? 'true' : 'false';
                document.getElementById('edit-token-context').value = token.token_context || '';

                bootstrap.Modal.getOrCreateInstance(document.getElementById('editTokenModal')).show();
            })
            .catch(error => {
                showNotification('\u52a0\u8f7d Token \u8be6\u60c5\u5931\u8d25: ' + error.message, 'error');
            });
    }

    function saveEditedToken() {
        const tokenId = document.getElementById('edit-token-id').value;
        const payload = {
            name: document.getElementById('edit-token-name').value.trim(),
            task_type: document.getElementById('edit-token-task-type').value || 'google_sheet',
            max_usage_count: Number(document.getElementById('edit-token-max-usage').value || 0),
            is_active: document.getElementById('edit-token-active').value === 'true',
            token_context: document.getElementById('edit-token-context').value
        };

        Api.endpoints.googleSheet.updateToken(tokenId, payload)
            .then(data => {
                bootstrap.Modal.getOrCreateInstance(document.getElementById('editTokenModal')).hide();
                showNotification('Token \u66f4\u65b0\u6210\u529f', 'success');
                loadGoogleSheetTokens();
            })
            .catch(error => {
                showNotification('\u4fdd\u5b58 Token \u5931\u8d25: ' + error.message, 'error');
            });
    }

    function deleteCurrentToken() {
        const tokenId = document.getElementById('edit-token-id').value;
        if (!tokenId) {
            return;
        }

        if (!confirm('\u786e\u5b9a\u8981\u5220\u9664\u8fd9\u4e2a Token \u5417\uff1f')) {
            return;
        }

        Api.endpoints.googleSheet.deleteToken(tokenId)
            .then(data => {
                bootstrap.Modal.getOrCreateInstance(document.getElementById('editTokenModal')).hide();
                showNotification('Token \u5220\u9664\u6210\u529f', 'success');
                loadGoogleSheetTokens();
            })
            .catch(error => {
                showNotification('\u5220\u9664 Token \u5931\u8d25: ' + error.message, 'error');
            });
    }

    function validateConfig() {
        ajaxRequest('/api/config/validate', 'GET', null, function(err, data) {
            if (!err && data && data.status === 'success') {
                const validation = data.validation;
                let message = '\u914d\u7f6e\u6821\u9a8c\u7ed3\u679c:\\n';
                message += `\u6570\u636e\u5e93\u914d\u7f6e\u6570\u91cf: ${validation.db_size}\\n`;
                message += `\u7f13\u5b58\u914d\u7f6e\u6570\u91cf: ${validation.cache_size}\\n`;
                message += `Google Sheet \u914d\u7f6e: ${JSON.stringify(validation.google_sheet_config, null, 2)}`;
                alert(message);
                showNotification('\u914d\u7f6e\u6821\u9a8c\u5b8c\u6210\uff0c\u8bf7\u67e5\u770b\u5f39\u7a97\u8be6\u60c5', 'info');
            } else {
                showNotification('\u914d\u7f6e\u6821\u9a8c\u5931\u8d25: ' + (data ? data.message : '\u672a\u77e5\u9519\u8bef'), 'error');
            }
        });
    }

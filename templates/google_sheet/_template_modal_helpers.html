// 模板弹窗公共逻辑：页面只需要提供 getCurrentConfig 和 loadTemplates。
function saveAsTemplate() {
    const config = getCurrentConfig();
    if (!config) {
        return;
    }

    const taskName = document.getElementById('task_name').value.trim();
    if (taskName) {
        document.getElementById('templateName').value = taskName + ' 模板';
    }

    const modal = new bootstrap.Modal(document.getElementById('saveTemplateModal'));
    modal.show();
}

function submitTemplate() {
    const config = getCurrentConfig();
    if (!config) {
        return;
    }

    const name = document.getElementById('templateName').value.trim();
    const description = document.getElementById('templateDescription').value.trim();

    if (!name) {
        showError('请输入模板名称');
        return;
    }

    const templateData = {
        name: name,
        description: description,
        config: config
    };

    fetch('/api/templates', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify(templateData)
    })
    .then(response => response.json())
    .then(data => {
        if (data.status === 'success') {
            const modal = document.getElementById('saveTemplateModal');
            const modalInstance = bootstrap.Modal.getInstance(modal);
            if (modalInstance) {
                modalInstance.hide();
            }
            showNotification('模板保存成功', 'success');
            loadTemplates();
        } else {
            showError(data.message || '保存模板失败');
        }
    })
    .catch(error => {
        console.error('保存模板失败:', error);
        showError('保存模板失败: ' + error.message);
    });
}

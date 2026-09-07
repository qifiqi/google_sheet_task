// 页面脚本（templates/admin/scheduler.html 内联脚本原样抽离，F5 de-jinja）。
let currentTasks = [];

// 页面加载时初始化
document.addEventListener('DOMContentLoaded', function() {
    loadTasks();
    loadStats();
    
    // 定期刷新数据
    setInterval(function() {
        loadTasks();
        loadStats();
    }, 30000); // 30秒刷新一次
});

// 加载任务列表
function loadTasks() {
    ajaxRequest('/api/admin/scheduler/tasks', 'GET', null, function(error, response) {
        if (error) {
            showNotification('加载任务列表失败', 'error');
            return;
        }
        
        currentTasks = (response.data && response.data.items) || [];
        renderTasksTable();
    });
}

// 加载统计信息
function loadStats() {
    ajaxRequest('/api/admin/scheduler/stats', 'GET', null, function(error, response) {
        if (error) {
            console.error('加载统计信息失败:', error);
            return;
        }
        
        const stats = (response.data && response.data.stats) || {};
        document.getElementById('totalTasks').textContent = stats.total_tasks || 0;
        document.getElementById('activeTasks').textContent = stats.active_tasks || 0;
        document.getElementById('inactiveTasks').textContent = stats.inactive_tasks || 0;
        document.getElementById('schedulerStatus').textContent = stats.scheduler_running ? '运行中' : '已停止';
    });
}

// 渲染任务表格
function renderTasksTable() {
    const tbody = document.querySelector('#tasksTable tbody');
    tbody.innerHTML = '';
    
    if (currentTasks.length === 0) {
        tbody.innerHTML = '<tr><td colspan="10" class="text-center">暂无定时任务</td></tr>';
        return;
    }
    
    currentTasks.forEach(task => {
        const row = document.createElement('tr');
        row.innerHTML = `
            <td>${task.id}</td>
            <td>${task.name}</td>
            <td>${task.description || '-'}</td>
            <td><code>${task.cron_expression}</code></td>
            <td><span class="badge bg-info">${getTaskTypeText(task.task_type)}</span></td>
            <td>
                <span class="badge ${task.is_active ? 'bg-success' : 'bg-secondary'}">
                    ${task.is_active ? '启用' : '禁用'}
                </span>
            </td>
            <td>${task.run_count}</td>
            <td>${formatTime(task.last_run_time)}</td>
            <td>${formatTime(task.next_run_time)}</td>
            <td>
                <div class="btn-group btn-group-sm">
                    <button class="btn btn-outline-primary" onclick="editTask(${task.id})" title="编辑">
                        <i class="bi bi-pencil"></i>
                    </button>
                    <button class="btn btn-outline-${task.is_active ? 'warning' : 'success'}" 
                            onclick="toggleTask(${task.id}, ${!task.is_active})" 
                            title="${task.is_active ? '禁用' : '启用'}">
                        <i class="bi bi-${task.is_active ? 'pause' : 'play'}"></i>
                    </button>
                    <button class="btn btn-outline-info" onclick="runTaskNow(${task.id})" title="立即执行">
                        <i class="bi bi-play-fill"></i>
                    </button>
                    <button class="btn btn-outline-danger" onclick="deleteTask(${task.id})" title="删除">
                        <i class="bi bi-trash"></i>
                    </button>
                </div>
            </td>
        `;
        tbody.appendChild(row);
    });
}

// 获取任务类型文本
function getTaskTypeText(taskType) {
    const types = {
        'cleanup': '数据清理',
        'backup': '数据备份',
        'maintenance': '系统维护',
        'custom': '自定义'
    };
    return types[taskType] || taskType;
}

// 添加任务
function addTask() {
    const form = document.getElementById('addTaskForm');
    const formData = new FormData(form);
    
    const taskData = {
        name: document.getElementById('taskName').value,
        description: document.getElementById('taskDescription').value,
        cron_expression: document.getElementById('cronExpression').value,
        task_type: document.getElementById('taskType').value,
        task_function: document.getElementById('taskFunction').value,
        task_params: document.getElementById('taskParams').value,
        is_active: document.getElementById('isActive').checked
    };
    
    // 验证必填字段
    if (!taskData.name || !taskData.cron_expression || !taskData.task_type || !taskData.task_function) {
        showNotification('请填写所有必填字段', 'error');
        return;
    }
    
    // 验证JSON参数
    if (taskData.task_params) {
        try {
            JSON.parse(taskData.task_params);
        } catch (e) {
            showNotification('任务参数必须是有效的JSON格式', 'error');
            return;
        }
    }
    
    ajaxRequest('/api/admin/scheduler/tasks', 'POST', taskData, function(error, response) {
        if (error) {
            showNotification('添加任务失败', 'error');
            return;
        }
        
        showNotification('任务添加成功', 'success');
        bootstrap.Modal.getInstance(document.getElementById('addTaskModal')).hide();
        form.reset();
        loadTasks();
        loadStats();
    });
}

// 编辑任务
function editTask(taskId) {
    const task = currentTasks.find(t => t.id === taskId);
    if (!task) return;
    
    document.getElementById('editTaskId').value = task.id;
    document.getElementById('editTaskName').value = task.name;
    document.getElementById('editTaskDescription').value = task.description || '';
    document.getElementById('editCronExpression').value = task.cron_expression;
    document.getElementById('editTaskType').value = task.task_type;
    document.getElementById('editTaskFunction').value = task.task_function;
    document.getElementById('editTaskParams').value = JSON.stringify(task.task_params, null, 2);
    document.getElementById('editIsActive').checked = task.is_active;
    
    new bootstrap.Modal(document.getElementById('editTaskModal')).show();
}

// 更新任务
function updateTask() {
    const taskId = document.getElementById('editTaskId').value;
    
    const taskData = {
        name: document.getElementById('editTaskName').value,
        description: document.getElementById('editTaskDescription').value,
        cron_expression: document.getElementById('editCronExpression').value,
        task_type: document.getElementById('editTaskType').value,
        task_function: document.getElementById('editTaskFunction').value,
        task_params: document.getElementById('editTaskParams').value,
        is_active: document.getElementById('editIsActive').checked
    };
    
    // 验证JSON参数
    if (taskData.task_params) {
        try {
            JSON.parse(taskData.task_params);
        } catch (e) {
            showNotification('任务参数必须是有效的JSON格式', 'error');
            return;
        }
    }
    
    ajaxRequest(`/api/admin/scheduler/tasks/${taskId}`, 'PUT', taskData, function(error, response) {
        if (error) {
            showNotification('更新任务失败', 'error');
            return;
        }
        
        showNotification('任务更新成功', 'success');
        bootstrap.Modal.getInstance(document.getElementById('editTaskModal')).hide();
        loadTasks();
        loadStats();
    });
}

// 切换任务状态
function toggleTask(taskId, isActive) {
    ajaxRequest(`/api/admin/scheduler/tasks/${taskId}/toggle`, 'POST', {is_active: isActive}, function(error, response) {
        if (error) {
            showNotification('切换任务状态失败', 'error');
            return;
        }
        
        showNotification(`任务已${isActive ? '启用' : '禁用'}`, 'success');
        loadTasks();
        loadStats();
    });
}

// 立即执行任务
function runTaskNow(taskId) {
    if (!confirm('确定要立即执行这个任务吗？')) return;
    
    ajaxRequest(`/api/admin/scheduler/tasks/${taskId}/run`, 'POST', null, function(error, response) {
        if (error) {
            showNotification('执行任务失败', 'error');
            return;
        }
        
        showNotification('任务已开始执行', 'success');
        loadTasks();
    });
}

// 删除任务
function deleteTask(taskId) {
    if (!confirm('确定要删除这个定时任务吗？此操作不可恢复。')) return;
    
    ajaxRequest(`/api/admin/scheduler/tasks/${taskId}`, 'DELETE', null, function(error, response) {
        if (error) {
            showNotification('删除任务失败', 'error');
            return;
        }
        
        showNotification('任务删除成功', 'success');
        loadTasks();
        loadStats();
    });
}

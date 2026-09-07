// 页面脚本（templates/admin/results.html 内联脚本原样抽离，F5 de-jinja）。
let currentPage = 1;
let pageSize = 20;
let currentTaskId = '';
let currentResultPayload = null;

// 显示错误提示
function showError(message) {
    const alertDiv = document.createElement('div');
    alertDiv.className = 'alert alert-danger alert-dismissible fade show';
    alertDiv.innerHTML = `
        ${message}
        <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>
    `;
    document.querySelector('.container-fluid').insertBefore(alertDiv, document.querySelector('.table-responsive'));
    
    // 3秒后自动消失
    setTimeout(() => {
        alertDiv.remove();
    }, 3000);
}

// 显示加载状态
function showLoading(show = true) {
    const resultList = document.getElementById('resultList');
    if (show) {
        resultList.innerHTML = `
            <tr>
                <td colspan="6" class="text-center py-4">
                    <div class="spinner-border text-primary" role="status">
                        <span class="visually-hidden">加载中...</span>
                    </div>
                    <div class="mt-2">加载中...</div>
                </td>
            </tr>
        `;
    }
}

// 加载结果列表
function loadResults(page = 1) {
    currentPage = page;
    showLoading(true);
    const url = new URL('/api/results', window.location.origin);
    url.searchParams.append('page', page);
    url.searchParams.append('per_page', pageSize);
    if (currentTaskId) {
        url.searchParams.append('task_id', currentTaskId);
    }

    Api.endpoints.adminResults.list(url.searchParams.toString())
        .then(data => {
            const resultList = document.getElementById('resultList');
            resultList.innerHTML = '';
            const payload = data || {};

            (payload.items || []).forEach(result => {
                const row = document.createElement('tr');
                row.innerHTML = `
                    <td>${result.id}</td>
                    <td>${result.task_id}</td>
                    <td>${result.step_index}</td>
                    <td>
                        <span class="badge ${result.success ? 'bg-success' : 'bg-danger'}">
                            ${result.success ? '成功' : '失败'}
                        </span>
                    </td>
                    <td>${new Date(result.timestamp).toLocaleString()}</td>
                    <td>
                        <button class="btn btn-sm btn-outline-primary" onclick="viewResult(${result.id})">
                            <i class="bi bi-eye"></i> 查看 JSON
                        </button>
                        <button class="btn btn-sm btn-outline-danger" onclick="deleteResult(${result.id})">
                            <i class="bi bi-trash"></i>
                        </button>
                    </td>
                `;
                resultList.appendChild(row);
            });

            // 更新分页
            updatePagination(payload.total, page);
        })
        .catch(error => console.error('Error:', error));
}

// 更新分页控件
function updatePagination(total, currentPageNum) {
    const totalPages = Math.ceil(total / pageSize);
    const pagination = document.getElementById('pagination');
    pagination.innerHTML = '';
    
    if (totalPages <= 1) return;

    // 上一页
    const prevLi = document.createElement('li');
    prevLi.className = `page-item ${currentPageNum === 1 ? 'disabled' : ''}`;
    prevLi.innerHTML = `<a class="page-link" href="#" onclick="loadResults(${currentPageNum - 1})">上页</a>`;
    pagination.appendChild(prevLi);

    // 计算要显示的页码范围
    const maxVisiblePages = 5;
    let startPage = Math.max(1, currentPageNum - Math.floor(maxVisiblePages / 2));
    let endPage = Math.min(totalPages, startPage + maxVisiblePages - 1);
    
    // 调整起始页，确保显示足够的页码
    if (endPage - startPage + 1 < maxVisiblePages) {
        startPage = Math.max(1, endPage - maxVisiblePages + 1);
    }

    // 第一页
    if (startPage > 1) {
        const li = document.createElement('li');
        li.className = 'page-item';
        li.innerHTML = `<a class="page-link" href="#" onclick="loadResults(1)">1</a>`;
        pagination.appendChild(li);
        
        if (startPage > 2) {
            const ellipsis = document.createElement('li');
            ellipsis.className = 'page-item disabled';
            ellipsis.innerHTML = `<span class="page-link">...</span>`;
            pagination.appendChild(ellipsis);
        }
    }

    // 页码范围
    for (let i = startPage; i <= endPage; i++) {
        const li = document.createElement('li');
        li.className = `page-item ${i === currentPageNum ? 'active' : ''}`;
        li.innerHTML = `<a class="page-link" href="#" onclick="loadResults(${i})">${i}</a>`;
        pagination.appendChild(li);
    }

    // 最后一页
    if (endPage < totalPages) {
        if (endPage < totalPages - 1) {
            const ellipsis = document.createElement('li');
            ellipsis.className = 'page-item disabled';
            ellipsis.innerHTML = `<span class="page-link">...</span>`;
            pagination.appendChild(ellipsis);
        }
        
        const li = document.createElement('li');
        li.className = 'page-item';
        li.innerHTML = `<a class="page-link" href="#" onclick="loadResults(${totalPages})">${totalPages}</a>`;
        pagination.appendChild(li);
    }

    // 下一页
    const nextLi = document.createElement('li');
    nextLi.className = `page-item ${currentPageNum === totalPages ? 'disabled' : ''}`;
    nextLi.innerHTML = `<a class="page-link" href="#" onclick="loadResults(${currentPageNum + 1})">下页</a>`;
    pagination.appendChild(nextLi);
}

// 查看结果详情
function viewResult(id) {
    Api.endpoints.adminResults.detail(id)
        .then(data => {
            const result = data || {};
            currentResultPayload = result;
            document.getElementById('resultDetailId').textContent = result.id ?? '-';
            document.getElementById('resultDetailTaskId').textContent = result.task_id ?? '-';
            document.getElementById('resultDetailStep').textContent = result.step_index ?? '-';
            document.getElementById('resultDetailStatus').innerHTML = `
                <span class="badge ${result.success ? 'bg-success' : 'bg-danger'}">${result.success ? '成功' : '失败'}</span>
                <span class="ms-2">${result.timestamp ? new Date(result.timestamp).toLocaleString() : '-'}</span>
            `;
            document.getElementById('resultParameters').textContent = JSON.stringify(result.parameters, null, 2);
            document.getElementById('resultData').textContent = JSON.stringify(result.result, null, 2);
            document.getElementById('errorMessage').textContent = result.error_message || '无错误信息';

            const firstTab = document.getElementById('result-params-tab');
            if (firstTab) {
                bootstrap.Tab.getOrCreateInstance(firstTab).show();
            }
            bootstrap.Modal.getOrCreateInstance(document.getElementById('viewResultModal')).show();
        })
        .catch(error => console.error('Error:', error));
}

function copyCurrentResultJson() {
    if (!currentResultPayload) {
        return;
    }

    const activePane = document.querySelector('#viewResultModal .tab-pane.active pre');
    const text = activePane ? activePane.textContent : JSON.stringify(currentResultPayload, null, 2);
    navigator.clipboard.writeText(text).catch(error => console.error('复制失败:', error));
}

// 删除结果
function deleteResult(id) {
    if (confirm('确定要删除这条结果记录吗？')) {
        Api.endpoints.adminResults.remove(id)
        .then(() => {
            loadResults(currentPage);
        })
        .catch(error => console.error('Error:', error));
    }
}

// 改变页面大小
function changePageSize() {
    const pageSizeSelect = document.getElementById('page-size-select');
    pageSize = parseInt(pageSizeSelect.value);
    currentPage = 1; // 重置到第一页
    loadResults(1);
}

// 执行筛选
function doFilter() {
    currentTaskId = document.getElementById('taskIdFilter').value.trim();
    currentPage = 1;
    loadResults(1);
}

// 筛选按钮点击事件
document.getElementById('filterButton').addEventListener('click', doFilter);

// 任务ID输入框回车事件
document.getElementById('taskIdFilter').addEventListener('keypress', function(e) {
    if (e.key === 'Enter') {
        e.preventDefault();
        doFilter();
    }
});

// 页面加载时获取结果列表
document.addEventListener('DOMContentLoaded', () => {
    // 从URL参数中获取task_id
    const urlParams = new URLSearchParams(window.location.search);
    const taskId = urlParams.get('task_id');
    if (taskId) {
        document.getElementById('taskIdFilter').value = taskId;
        currentTaskId = taskId;
    }
    loadResults(1);
});

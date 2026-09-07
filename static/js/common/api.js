// 统一接口层（docs/design/frontend-refactor/02 §3.5）。
// 全部 /api/* 请求的唯一出口：端点定义 + 请求 helper + 响应信封解包。
// 鉴权传输不在这里做——template-auth.js 全局拦截 fetch（token 附加、401 刷新重放），
// 本文件只负责调用收敛与信封解包，wire 格式零变化。
//
// 信封格式（app/utils/api_response.py）：{"status","code","message","data"}；
// status !== 'success' 时抛错，message 供调用方展示。
//
// 引入顺序：template-auth.js → navbar.js → api.js → utils.js → 页面 JS。
'use strict';

(function () {
    // options（可选）：fetch 附加项（如 { signal }）；options.envelope=true 时返回完整信封
    //（保留 message 给调用方 toast），默认仍只返回信封 data。
    async function request(method, path, body, options) {
        const fetchOptions = { method: method, headers: {} };
        if (options && typeof options === 'object') {
            Object.keys(options).forEach(function (key) {
                if (key !== 'envelope') {
                    fetchOptions[key] = options[key];
                }
            });
        }
        if (body instanceof FormData) {
            fetchOptions.body = body;
        } else if (body !== undefined && body !== null) {
            fetchOptions.headers['Content-Type'] = 'application/json';
            fetchOptions.body = JSON.stringify(body);
        }

        const response = await fetch(path, fetchOptions);
        let payload = null;
        try {
            payload = await response.json();
        } catch (e) {
            payload = null;
        }

        if (!response.ok || !payload || payload.status !== 'success') {
            const message = (payload && payload.message) || ('请求失败（HTTP ' + response.status + '）');
            const error = new Error(message);
            error.code = payload && payload.code;
            error.data = payload && payload.data;
            throw error;
        }
        return (options && options.envelope) ? payload : payload.data;
    }

    function get(path, options) {
        return request('GET', path, undefined, options);
    }

    function post(path, body, options) {
        return request('POST', path, body, options);
    }

    function put(path, body, options) {
        return request('PUT', path, body, options);
    }

    function del(path, options) {
        return request('DELETE', path, undefined, options);
    }

    // 端点按域分组（对齐 frontend/src/api/*.js 的分域命名）；各批次页面逐个迁入。
    const endpoints = {
        meta: {
            enums: function () { return get('/api/meta/enums'); },
        },
        config: {
            get: function () { return get('/api/config'); },
        },
        task: {
            list: function (query) { return get('/api/tasks' + (query ? '?' + query : '')); },
            detail: function (taskId) { return get('/api/tasks/' + taskId); },
            create: function (payload) { return post('/api/tasks', payload); },
            batchCreate: function (payload) { return post('/api/tasks/batch-create', payload); },
            remove: function (taskId) { return del('/api/tasks/' + taskId); },
            cancel: function (taskId) { return post('/api/tasks/' + taskId + '/cancel'); },
            logs: function (taskId) { return get('/api/tasks/' + taskId + '/logs'); },
            results: function (taskId, query) { return get('/api/tasks/' + taskId + '/results' + (query ? '?' + query : '')); },
            statusCheck: function (taskId) { return get('/api/tasks/' + taskId + '/status-check'); },
            restart: function (taskId, payload) { return post('/api/tasks/' + taskId + '/restart', payload); },
            createRestart: function (taskId, payload) { return post('/api/tasks/' + taskId + '/create-restart', payload); },
            updateConfig: function (taskId, payload) { return put('/api/tasks/' + taskId + '/config', payload); },
        },
        stock: {
            search: function (query, options) { return get('/api/search-stocks' + (query ? '?' + query : ''), options); },
        },
        backtest: {
            // 单品数据回测（/backtest-training 自有 API，信封与 /api/tasks 同一格式）
            importExcel: function (formData) { return post('/backtest-training/api/import-excel', formData); },
            taskResults: function (taskId, query) { return get('/backtest-training/api/task-results/' + taskId + (query ? '?' + query : '')); },
            taskResult: function (resultId, options) { return get('/backtest-training/api/task-result/' + resultId, options); },
            taskResultExportPreview: function (resultId) { return get('/backtest-training/api/task-result/' + resultId + '/export-preview'); },
            taskSummary: function (taskId) { return get('/backtest-training/api/task-summary/' + taskId); },
            globalPreview: function (taskId) { return get('/backtest-training/api/global-preview/' + taskId); },
        },
        backtestMulti: {
            // 多品数据回测（/backtest-multi-product 自有 API）
            taskResults: function (taskId, query) { return get('/backtest-multi-product/api/task-results/' + taskId + (query ? '?' + query : '')); },
            taskResult: function (resultId, options) { return get('/backtest-multi-product/api/task-result/' + resultId, options); },
            taskSummary: function (taskId) { return get('/backtest-multi-product/api/task-summary/' + taskId); },
            globalPreview: function (taskId) { return get('/backtest-multi-product/api/global-preview/' + taskId); },
            calculateRatios: function (taskId, payload) { return post('/backtest-multi-product/api/global-preview/' + taskId + '/calculate-ratios', payload); },
            updateRatios: function (taskId, payload) { return put('/backtest-multi-product/api/global-preview/' + taskId + '/ratios', payload); },
        },
        previewHub: {
            // 独立全局预览中心（/global-preview 自有 API）
            task: function (taskId) { return get('/global-preview/api/tasks/' + taskId); },
            previewGroup: function (taskId, payload) { return post('/global-preview/api/tasks/' + taskId + '/preview-group', payload); },
        },
        template: {
            list: function (query) { return get('/api/templates' + (query ? '?' + query : '')); },
            detail: function (templateId) { return get('/api/templates/' + templateId); },
            create: function (payload) { return post('/api/templates', payload); },
        },
        googleSheet: {
            sheets: function (query) { return get('/api/google-sheets' + (query ? '?' + query : '')); },
            worksheets: function (payload) { return post('/api/google-sheet/worksheets', payload); },
            tokens: function () { return get('/api/google-sheet-tokens'); },
            importToken: function (payload) { return post('/api/google-sheet-tokens/import', payload); },
        },
        export: {
            // 合并导出是流式下载（ReadableStream 读进度），返回原始 Response，
            // 不走信封解包；鉴权拦截由 template-auth.js 的 fetch 拦截照常生效。
            batchTasks: function (taskIds) {
                return fetch('/api/exports/tasks/batch', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ task_ids: taskIds }),
                });
            },
            // 单任务 Excel 导出同样是文件流下载，返回原始 Response。
            task: function (taskId) {
                return fetch('/api/exports/tasks/' + taskId);
            },
            // 单任务按股票代码 ZIP 导出（C7 详情页），文件流下载，返回原始 Response。
            taskStocks: function (taskId) {
                return fetch('/api/exports/tasks/' + taskId + '/stocks');
            },
            // 全局预览 XLSX 导出（backtest 双胞胎 / 全局预览中心），文件流下载，返回原始 Response。
            // query 形如 '?export_name=...' / '?ratios=...'，无参时传空。
            globalPreview: function (taskId, query) {
                return fetch('/api/exports/global-previews/' + taskId + (query || ''));
            },
            // 全局预览批量 ZIP 导出（backtest 列表页），文件流下载，返回原始 Response。
            globalPreviewsBatch: function (taskIds) {
                return fetch('/api/exports/global-previews/batch', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ task_ids: taskIds }),
                });
            },
            // 回测结果 CSV 导出（bt 结果页 / 导出预览页），文件流下载，返回原始 Response。
            backtestResult: function (resultId) {
                return fetch('/api/exports/backtest-results/' + resultId);
            },
            // 多品回测结果 CSV 导出（multi 结果页），文件流下载，返回原始 Response。
            backtestResultXpl: function (payload) {
                return fetch('/api/exports/xpl', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': document.querySelector('meta[name="csrf-token"]')?.content || '',
                    },
                    body: JSON.stringify(payload),
                });
            },
            // 回测 Word 报告导出（RPT-S/RPT-M），文件流下载，返回原始 Response。
            wordReport: function (payload) {
                return fetch('/api/exports/backtest-reports/word', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': document.querySelector('meta[name="csrf-token"]')?.content || '',
                    },
                    body: JSON.stringify(payload),
                });
            },
        },
    };

    window.Api = {
        request: request,
        get: get,
        post: post,
        put: put,
        del: del,
        // 返回完整响应信封（{"status","code","message","data"}）——供需要读取
        // 服务端 message 做成功提示的调用方使用；status !== 'success' 时同样抛错。
        envelope: function (method, path, body) {
            return request(method, path, body, { envelope: true });
        },
        endpoints: endpoints,
    };
})();

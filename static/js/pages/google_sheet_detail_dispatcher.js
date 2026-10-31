// 详情页版本分发器（docs/design/frontend-refactor/03 §4.1）。
// /google-sheet/detail?task_id=…（无 version）由此页查任务补 version 后重定向；
// 映射关系原文抄自 app/routes/google_sheet.py::_version_from_task_type。
'use strict';

(function () {
    function taskTypeToVersion(taskType) {
        const normalized = String(taskType || '').toLowerCase();
        if (normalized === 'google_sheet_c5') return 'c5';
        if (normalized === 'google_sheet_c7') return 'c7';
        if (normalized === 'google_sheet_c1_1') return 'c1_1';
        if (normalized === 'google_sheet_c4') return 'c4';
        if (normalized === 'google_sheet') return 'c3';
        return null;
    }

    const params = new URLSearchParams(window.location.search);
    const taskId = params.get('task_id');
    if (!taskId) {
        // 无 task_id：落回默认 C3 详情页（与原服务端缺省分支一致）。
        window.location.replace('/google-sheet/detail');
        return;
    }

    Api.endpoints.task.detail(taskId).then(function (task) {
        // /api/tasks/<id> 信封 data 形如 {task: {...}}，task_type 在内层。
        const taskInfo = task && task.task ? task.task : task;
        const version = taskTypeToVersion(taskInfo && taskInfo.task_type);
        const sp = new URLSearchParams(window.location.search);
        if (version) {
            sp.set('version', version);
            window.location.replace('/google-sheet/detail?' + sp.toString());
        } else {
            // 未知类型：落服务端缺省分支（version=c3 → C3 详情页）；
            // 不能原样 replace 回自身——无 version 会再次命中 dispatcher 造成刷新循环。
            sp.set('version', 'c3');
            window.location.replace('/google-sheet/detail?' + sp.toString());
        }
    }).catch(function () {
        // 查询失败（任务不存在/网络异常）：落 C3 详情页由页面内报错，同样不可回自身。
        const sp = new URLSearchParams(window.location.search);
        sp.set('version', 'c3');
        window.location.replace('/google-sheet/detail?' + sp.toString());
    });
})();

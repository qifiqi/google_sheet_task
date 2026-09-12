// 详情页版本分发器（docs/design/frontend-refactor/03 §4.1）。
// /google-sheet/detail?task_id=…（无 version）由此页查任务补 version 后重定向；
// 映射关系原文抄自 app/routes/google_sheet.py::_version_from_task_type。
'use strict';

(function () {
    function taskTypeToVersion(taskType) {
        const normalized = String(taskType || '').toLowerCase();
        if (normalized === 'google_sheet_c5') return 'c5';
        if (normalized === 'google_sheet_c7') return 'c7';
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
        const version = taskTypeToVersion(task && task.task_type);
        const sp = new URLSearchParams(window.location.search);
        if (version) {
            sp.set('version', version);
            window.location.replace('/google-sheet/detail?' + sp.toString());
        } else {
            // 未知类型/任务：落回默认 C3 详情页（原服务端缺省分支）。
            window.location.replace('/google-sheet/detail?' + sp.toString());
        }
    }).catch(function () {
        const sp = new URLSearchParams(window.location.search);
        window.location.replace('/google-sheet/detail?' + sp.toString());
    });
})();

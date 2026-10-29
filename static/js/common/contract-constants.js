// 前后端契约镜像常量（docs/design/constants-audit-2026-09/ §5.6 / P5）。
// 这里只放"后端有对应事实、前端需要同值"的契约项；改契约必须两侧同批修改
// （后端源头见各条注释）。纯展示文案/页面私有常量不进本文件。
"use strict";

(function () {
    window.BizConstants = {
        // 后端：app/services/backtest_parameter_utils.py DEFAULT_C3_COMMISSION（C3 默认佣金）
        DEFAULT_C3_COMMISSION: '0.0350%',

        // 后端：app/models.py TaskStatus（DB 存量取值；failed 为历史数据兜底展示）
        TASK_STATUS_LABELS: {
            pending: '待执行',
            running: '运行中',
            completed: '已完成',
            cancelled: '已取消',
            error: '失败',
            failed: '失败',
        },
        TASK_STATUS_BADGE_CLASSES: {
            pending: 'text-bg-secondary',
            running: 'text-bg-primary',
            completed: 'text-bg-success',
            cancelled: 'text-bg-info',
            error: 'text-bg-danger',
            failed: 'text-bg-danger',
        },
    };
})();

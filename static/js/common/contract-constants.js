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

        // 后端：app/services/export_workbook_service.py PRICE_MODE_FILENAME_SLUGS /
        // RANDOM_PRICE_RANGE_FILENAME_SLUGS / KLINE_ADJUSTMENT_FILENAME_SLUGS。
        // 导出文件名价格/复权段 slug（前端拼文件名用，如东财K线页）；随机价段
        // rnd-hl/rnd-oc 由后端任务导出消费，前端查询页暂无该形态。
        EXPORT_PRICE_FILENAME_SLUGS: {
            kp_price: 'open',
            sp_price: 'close',
            vwap_price: 'vwap',
            ohlc_price: 'ohlc',
            random_price: 'rnd',
        },
        EXPORT_RANDOM_RANGE_FILENAME_SLUGS: {
            high_low: 'hl',
            open_close: 'oc',
        },
        EXPORT_ADJUST_FILENAME_SLUGS: {
            forward: 'qfq',
            back: 'hfq',
            none: 'raw',
            // 东财K线页 kline-adjust 下拉的数值词表（0 不复权 / 1 前复权 / 2 后复权）
            0: 'raw',
            1: 'qfq',
            2: 'hfq',
        },
    };
})();

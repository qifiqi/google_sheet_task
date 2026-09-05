"""诊断全局预览缺字段：只读检查 TaskResult 存储的 metrics_payload 键与收益序列。

用法:
    PYTHONPATH=. py -3.11 scripts/diagnose_global_preview.py [task_id] [result_id ...]

不传参数时默认检查任务 ffcffe40-d7da-4776-bac3-bbd7ec750343 的全部结果。
"""

import json
import sys

from app import create_app
from app.extensions import db
from app.models import TaskResult, TaskResultReturn
from app.services.performance_analysis.historical_metrics import extract_core_metrics

DEFAULT_TASK_ID = "ffcffe40-d7da-4776-bac3-bbd7ec750343"

# 全局预览/结果预览读取、且截图显示 "-" 的键。
WATCH_KEYS = [
    "excess_sharpe",
    "excess_sortino",
    "index_sortino_ratio",
    "start_sortino_ratio",
    "year_index_yearly_max_repair_days",
    "year_start_yearly_max_repair_days",
    "index_kama_ratio",
    "start_kama_ratio",
    "index_sharpe_ratios",
    "start_sharpe_ratios",
    "monthly_excess_returns",
    "excess_returns",
]

PREVIEW_KEYS = [
    "excess_sharpe",
    "excess_sortino",
    "year_index_yearly_max_repair_days",
    "year_start_yearly_max_repair_days",
]


def summarize_value(value):
    if isinstance(value, dict):
        return f"dict(keys={list(value.keys())[:6]})"
    if isinstance(value, list):
        if value and isinstance(value[0], dict):
            years = [str(item.get("year")) for item in value[:8] if isinstance(item, dict)]
            return f"list(len={len(value)}, years={years})"
        return f"list(len={len(value)})"
    return repr(value)[:80]


def main():
    args = [arg for arg in sys.argv[1:] if not arg.startswith("-")]
    task_id = args[0] if args else DEFAULT_TASK_ID

    app = create_app()
    with app.app_context():
        query = TaskResult.query.filter_by(task_id=task_id).order_by(TaskResult.id.asc())
        if len(args) > 1:
            query = query.filter(TaskResult.id.in_([int(arg) for arg in args[1:]]))
        results = query.all()
        print(f"任务 {task_id} 共 {len(results)} 条结果\n")

        for task_result in results:
            payload = json.loads(task_result.result) if task_result.result else {}
            core = next(
                (value for value in payload.values() if isinstance(value, dict)),
                {},
            )
            metrics = extract_core_metrics(core)
            metrics_payload = core.get("metrics_payload")
            schema = metrics_payload.get("schema_version") if isinstance(metrics_payload, dict) else None

            print(f"=== result_id={task_result.id} step={task_result.step_index} "
                  f"success={task_result.success} return_series_id={task_result.return_series_id} "
                  f"schema={schema}")
            print(f"    core 顶层键: {list(core.keys())[:10]}")
            print(f"    metrics 键数量: {len(metrics)}")

            for key in WATCH_KEYS:
                value = metrics.get(key)
                marker = "缺失" if key not in metrics else ("None" if value is None else "有值")
                print(f"    [{marker:>2}] {key}: {summarize_value(value) if key in metrics else '-'}")

            # 预览渲染视角：这些键能否被 _safe_all_entry / _max_yearly_repair_days 取到值
            def all_entry(items):
                if not isinstance(items, list):
                    return None
                return next(
                    (item for item in items if isinstance(item, dict) and str(item.get("year")) == "all"),
                    None,
                )

            for side in ("index", "start"):
                entry = all_entry(metrics.get(f"{side}_sortino_ratio"))
                print(f"    预览取值 {side}_sortino(all) = {entry.get('sortino_ratio') if entry else '无 all 条目'}")

            series = db.session.get(TaskResultReturn, task_result.return_series_id) \
                if task_result.return_series_id else None
            if series is not None:
                import json as _json
                dates = _json.loads(series.stock_date) if series.stock_date else []
                print(f"    收益序列: {len(dates)} 行 ({series.start_return_date} ~ {series.end_return_date})")
            else:
                print("    收益序列: 无 TaskResultReturn 记录（无法重算）")
            print()


if __name__ == "__main__":
    main()

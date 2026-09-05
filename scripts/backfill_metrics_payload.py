"""历史 TaskResult 指标回填脚本。

背景：
    2026-08 前后旧版执行代码给 C7.0.3 等任务落库的 result JSON 只有精简版
    ``calculate_metrics``，缺少全局预览/结果预览读取的
    ``excess_sharpe``、``excess_sortino``、``index/start_sortino_ratio``、
    ``year_index/start_yearly_max_repair_days`` 等键，导致预览页显示 "-"。

做法：
    从 TaskResultReturn 里存的累计收益序列（date/index_return/start_return）
    用当前代码重算完整 V1 指标，写回 result JSON 的
    ``metrics_payload = {schema_version, metrics, canonical_metrics}``。
    读取端（extract_core_metrics）优先使用 metrics_payload，旧 legacy 键
    原样保留，不做破坏性修改。必需键齐全的结果自动跳过，可重复执行。

用法（在项目根目录执行；线上库先 set DATABASE_URL=...）：
    :: 单个任务
    .venv\\Scripts\\python scripts\\backfill_metrics_payload.py <task_id> [--apply]
    :: 全库扫描（C3/C4/C5/C7/回测训练五类任务，缺键才补）
    .venv\\Scripts\\python scripts\\backfill_metrics_payload.py --all [--apply]
    可选：--result-id 2855596（限定结果）、--force（齐全也重算）、--verbose（逐键打印）

    默认 dry-run：只打印诊断，不写库；--apply 逐条提交。
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

# 支持直接 `python scripts/backfill_metrics_payload.py` 执行，无需设置 PYTHONPATH。
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import create_app
from app.extensions import db
from app.models import Task, TaskResult, TaskResultReturn
from app.services.performance_analysis.facade import calculate_v1_metrics
from app.services.performance_analysis.historical_metrics import extract_core_metrics
from app.utils.return_series import parse_return_series_fields
from app.utils.task_types import normalize_task_type

# 全局预览/结果预览依赖、且旧精简载荷容易缺失的键；任一缺失即触发重算。
REQUIRED_KEYS = (
    "excess_sharpe",
    "excess_sortino",
    "index_sortino_ratio",
    "start_sortino_ratio",
    "year_index_yearly_max_repair_days",
    "year_start_yearly_max_repair_days",
)

# 全局预览覆盖的任务类型（C3/C4/C5/C7 与回测训练）；多品结果没有 TaskResultReturn，
# 因此不纳入本脚本的收益指标回填范围。
PREVIEW_TASK_TYPES = (
    "backtest_training",
    "google_sheet",
    "google_sheet_c4",
    "google_sheet_c5",
    "google_sheet_c7",
)

CHUNK_SIZE = 100


def _sanitize(value):
    """递归把 NaN/inf 转 None，保证 allow_nan=False 的 JSON 序列化不报错。"""
    if isinstance(value, dict):
        return {key: _sanitize(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_sanitize(item) for item in value]
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def _missing_keys(metrics) -> list[str]:
    if not isinstance(metrics, dict):
        return list(REQUIRED_KEYS)
    return [key for key in REQUIRED_KEYS if metrics.get(key) is None]


def _iter_cores(payload: dict):
    """TaskResult.result 顶层按 sheet 键分组，逐个产出 core 字典。"""
    for core in (payload or {}).values():
        if isinstance(core, dict):
            yield core


def _print_watch_values(new_metrics: dict):
    for key in REQUIRED_KEYS:
        value = new_metrics.get(key)
        if isinstance(value, dict):
            print(f"    {key} = {dict(list(value.items())[:3])}")
        elif isinstance(value, list):
            all_entry = next(
                (item for item in value if isinstance(item, dict) and str(item.get("year")) == "all"),
                None,
            )
            print(f"    {key} = list(len={len(value)}), all={all_entry}")
        else:
            print(f"    {key} = {value!r}")


def backfill_result(task_result: TaskResult, force: bool, recompute: bool = True) -> str:
    """处理单条 TaskResult；返回动作（recomputed / would-recompute / skipped: 原因）。

    ``recompute=False`` 为快速普查模式：只诊断缺键，不做重算（--all dry-run 用）。
    """
    payload = json.loads(task_result.result) if task_result.result else {}
    if not isinstance(payload, dict) or not payload:
        return "skipped: result JSON 为空"

    missing_views = []
    for core in _iter_cores(payload):
        metrics = extract_core_metrics(core)
        missing = _missing_keys(metrics)
        if missing:
            missing_views.append((core, metrics, missing))

    if not missing_views and not force:
        return "skipped: 必需键齐全"

    series = db.session.get(TaskResultReturn, task_result.return_series_id) \
        if task_result.return_series_id else None
    rows = parse_return_series_fields(series) if series is not None else []
    if len(rows) < 2:
        return f"skipped: 无可用收益序列(series_id={task_result.return_series_id})"

    if not recompute:
        return "would-recompute"

    metrics_result = calculate_v1_metrics(rows)
    new_payload = metrics_result.to_json_dict(include_series=False)
    new_metrics = new_payload["metrics"]
    still_missing = _missing_keys(new_metrics)

    for core, _metrics, _missing in missing_views:
        core["metrics_payload"] = dict(new_payload)

    old_count = len(missing_views[0][1]) if missing_views else 0
    print(f"  [重算] 缺失键: {missing_views[0][2] if missing_views else '--force'}, "
          f"指标键数 {old_count} -> {len(new_metrics)}")
    _print_watch_values(new_metrics)
    if still_missing:
        print(f"  [警告] 重算后仍缺失（数据形态导致，如除零）: {still_missing}")

    task_result.result = json.dumps(
        _sanitize(payload), ensure_ascii=False, allow_nan=False, default=str
    )
    return "recomputed"


def _stream_results(result_ids=None, all_tasks: bool = False):
    """按 id 分块流式读取结果，避免一次性加载全表大 JSON。"""
    query = db.session.query(TaskResult.id).order_by(TaskResult.id.asc())
    if result_ids:
        query = query.filter(TaskResult.id.in_(result_ids))
    if all_tasks:
        # 归一化后的预览白名单类型；DB 里存在 backtest/google_sheet_c31 等原始变体，
        # 先取全量去重的 task_type，在 Python 侧归一化后回填过滤条件。
        raw_types = [row[0] for row in db.session.query(Task.task_type).distinct().all()]
        kept = [raw for raw in raw_types if normalize_task_type(raw) in PREVIEW_TASK_TYPES]
        query = query.join(Task, TaskResult.task_id == Task.id).filter(Task.task_type.in_(kept))
    ids = [row[0] for row in query.all()]

    for start in range(0, len(ids), CHUNK_SIZE):
        chunk = ids[start:start + CHUNK_SIZE]
        yield from TaskResult.query.filter(TaskResult.id.in_(chunk)).order_by(TaskResult.id.asc()).all()


def main() -> int:
    parser = argparse.ArgumentParser(description="回填历史 TaskResult 的完整 V1 指标载荷")
    parser.add_argument("task_id", nargs="?", help="限定单个任务 ID")
    parser.add_argument("--all", action="store_true", help="扫描全部 C 系列/回测训练任务")
    parser.add_argument("--result-id", type=int, action="append", default=[], help="限定结果 ID（可重复）")
    parser.add_argument("--force", action="store_true", help="必需键齐全也强制重算")
    parser.add_argument("--apply", action="store_true", help="真正写库（默认 dry-run 只读）")
    args = parser.parse_args()

    if not args.task_id and not args.all and not args.result_id:
        parser.print_help()
        return 1

    app = create_app()
    with app.app_context():
        import re

        url = str(db.engine.url)
        print(f"目标数据库: {re.sub(r':[^:@/]+@', ':***@', url)}")
        mode = "APPLY 写库" if args.apply else "DRY-RUN 只读"
        print(f"模式: {mode}\n")

        stats = {
            "total": 0,
            "recomputed": 0,
            "would_recompute": 0,
            "skipped_complete": 0,
            "skipped_no_series": 0,
            "skipped_other": 0,
        }
        per_type = {}
        # --all 的 dry-run 做快速普查（不重算）；单任务 dry-run 保留完整重算验证。
        recompute = not (args.all and not args.apply)
        results = _stream_results(result_ids=args.result_id or None, all_tasks=args.all)
        for task_result in results:
            stats["total"] += 1
            action = backfill_result(task_result, args.force, recompute=recompute)
            stats_key = (
                "recomputed" if action == "recomputed"
                else "would_recompute" if action == "would-recompute"
                else "skipped_complete" if "齐全" in action
                else "skipped_no_series" if "收益序列" in action
                else "skipped_other"
            )
            stats[stats_key] += 1
            if stats_key in ("recomputed", "would_recompute"):
                task = db.session.get(Task, task_result.task_id)
                task_type = normalize_task_type(task.task_type) if task else "unknown"
                per_type[task_type] = per_type.get(task_type, 0) + 1
                print(f"  result_id={task_result.id} task={task_result.task_id} "
                      f"step={task_result.step_index} type={task_type} -> "
                      f"{'已写库' if args.apply else '待回填'}")
            if args.apply and action == "recomputed":
                db.session.commit()
            else:
                db.session.rollback()

        print(f"\n扫描 {stats['total']} 条：回填 {stats['recomputed']}，"
              f"待回填 {stats['would_recompute']}，键齐全 {stats['skipped_complete']}，"
              f"无收益序列 {stats['skipped_no_series']}，其他跳过 {stats['skipped_other']}")
        if per_type:
            print(f"按任务类型: {per_type}")
        if not args.apply and stats["recomputed"] + stats["would_recompute"]:
            print("当前为 dry-run 未写库；确认后加 --apply 执行。")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())


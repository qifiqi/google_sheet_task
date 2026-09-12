"""Collect latest task logs for currently running tasks.

Usage:
    python scripts/collect_running_task_logs.py
    python scripts/collect_running_task_logs.py --limit 50
    python scripts/collect_running_task_logs.py --output logs/current_running_logs.json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "logs"

METRIC_PATTERNS = {
    "execute_s": re.compile(r"execute=([0-9.]+)s"),
    "rows": re.compile(r'"rows":\s*([0-9]+)'),
    "read_s": re.compile(r'"read":\s*"([0-9.]+)s"'),
    "xpl_s": re.compile(r'"xpl":\s*"([0-9.]+)s"'),
    "save_s": re.compile(r"save=([0-9.]+)s"),
    "push_s": re.compile(r"stock_param_push=([0-9.]+)s"),
}

LOG_TYPE_PATTERNS = {
    "收益率分析摘要": re.compile(r"收益率分析执行完成"),
    "内层成功摘要": re.compile(r"^参数组合执行成功"),
    "外层成功摘要": re.compile(r"第 \d+ 个参数组合执行成功，execute="),
    "后处理耗时": re.compile(r"后处理耗时"),
    "固定等待": re.compile(r"检查执行状态\.\.\. delay"),
    "检查位置": re.compile(r"获取到检查位置"),
    "参数结果": re.compile(r"获取到参数执行结果"),
}

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Collect latest TaskLog rows for active tasks.",
    )
    parser.add_argument(
        "--status",
        default="running",
        help="Task status to collect. Defaults to running.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=20,
        help="Number of latest logs to collect per task. Defaults to 20.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output JSON file path. Defaults to logs/running_task_logs_<timestamp>.json.",
    )
    parser.add_argument(
        "--report-output",
        type=Path,
        default=None,
        help="Output Markdown summary path. Defaults to <json_stem>_summary.md.",
    )
    return parser.parse_args()


def isoformat(value: Any) -> str | None:
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def task_to_dict(task: Any) -> dict[str, Any]:
    return {
        "id": task.id,
        "name": task.name,
        "status": task.status,
        "task_type": task.task_type,
        "current_step": task.current_step,
        "total_steps": task.total_steps,
        "progress_percentage": task.get_progress_percentage(),
        "start_time": isoformat(task.start_time),
        "created_at": isoformat(task.created_at),
        "updated_at": isoformat(task.updated_at),
    }


def log_to_dict(log: Any) -> dict[str, Any]:
    return {
        "id": log.id,
        "level": log.level,
        "timestamp": isoformat(log.timestamp),
        "message": log.message,
    }


def percentile(sorted_values: list[float], ratio: float) -> float:
    if not sorted_values:
        return 0.0
    index = int((len(sorted_values) - 1) * ratio)
    return sorted_values[index]


def metric_stats(values: list[float]) -> dict[str, Any]:
    if not values:
        return {
            "count": 0,
            "min": None,
            "avg": None,
            "max": None,
            "p50": None,
            "p95": None,
        }

    sorted_values = sorted(values)
    return {
        "count": len(values),
        "min": round(sorted_values[0], 3),
        "avg": round(sum(values) / len(values), 3),
        "max": round(sorted_values[-1], 3),
        "p50": round(percentile(sorted_values, 0.50), 3),
        "p95": round(percentile(sorted_values, 0.95), 3),
    }


def get_task_group(task_name: str) -> str:
    if "1y" in task_name:
        return "1y"
    if "3y" in task_name:
        return "3y"
    return "other"


def extract_float(pattern: re.Pattern[str], message: str) -> float | None:
    match = pattern.search(message)
    if not match:
        return None
    return float(match.group(1))


def extract_int(pattern: re.Pattern[str], message: str) -> int | None:
    match = pattern.search(message)
    if not match:
        return None
    return int(match.group(1))


def analyze_payload(payload: dict[str, Any]) -> dict[str, Any]:
    metrics: dict[str, list[float]] = {name: [] for name in METRIC_PATTERNS}
    log_type_counts = {name: 0 for name in LOG_TYPE_PATTERNS}
    level_counts: dict[str, int] = {}
    task_xpl: dict[str, dict[str, Any]] = {}
    group_xpl: dict[str, list[float]] = {}
    non_info_logs = []

    for item in payload["tasks"]:
        task = item["task"]
        task_id = task["id"]
        task_name = task["name"]
        group = get_task_group(task_name)
        task_xpl_values: list[float] = []
        task_rows: set[int] = set()

        for log in item["latest_logs"]:
            level = log["level"]
            message = log["message"] or ""
            level_counts[level] = level_counts.get(level, 0) + 1
            if level != "info":
                non_info_logs.append(
                    {
                        "task_id": task_id,
                        "task_name": task_name,
                        "timestamp": log["timestamp"],
                        "level": level,
                        "message": message,
                    }
                )

            for name, pattern in LOG_TYPE_PATTERNS.items():
                if pattern.search(message):
                    log_type_counts[name] += 1

            for name, pattern in METRIC_PATTERNS.items():
                value = extract_float(pattern, message)
                if value is not None:
                    metrics[name].append(value)

            xpl_value = extract_float(METRIC_PATTERNS["xpl_s"], message)
            if xpl_value is not None:
                task_xpl_values.append(xpl_value)
                group_xpl.setdefault(group, []).append(xpl_value)

            row_value = extract_int(METRIC_PATTERNS["rows"], message)
            if row_value is not None:
                task_rows.add(row_value)

        if task_xpl_values:
            task_xpl[task_id] = {
                "task_id": task_id,
                "task_name": task_name,
                "step": f"{task['current_step']}/{task['total_steps']}",
                "group": group,
                "rows": sorted(task_rows),
                "xpl": metric_stats(task_xpl_values),
                "xpl_values": [round(value, 3) for value in task_xpl_values],
            }

    top_task_xpl = sorted(
        task_xpl.values(),
        key=lambda item: item["xpl"]["max"] or 0,
        reverse=True,
    )[:10]

    return {
        "metric_stats": {
            name: metric_stats(values)
            for name, values in metrics.items()
        },
        "level_counts": level_counts,
        "log_type_counts": log_type_counts,
        "xpl_by_group": {
            group: metric_stats(values)
            for group, values in sorted(group_xpl.items())
        },
        "top_task_xpl": top_task_xpl,
        "non_info_logs": non_info_logs[:20],
    }


def collect_logs(status: str, limit: int) -> dict[str, Any]:
    from app import create_app
    from app.models import Task, TaskLog

    app = create_app()
    with app.app_context():
        tasks = (
            Task.query.filter(Task.status == status)
            .order_by(Task.updated_at.desc(), Task.created_at.desc())
            .all()
        )

        task_items = []
        total_logs = 0
        for task in tasks:
            latest_logs = (
                TaskLog.query.filter(TaskLog.task_id == task.id)
                .order_by(TaskLog.timestamp.desc(), TaskLog.id.desc())
                .limit(limit)
                .all()
            )
            logs = [log_to_dict(log) for log in latest_logs]
            total_logs += len(logs)
            task_items.append(
                {
                    "task": task_to_dict(task),
                    "latest_logs": logs,
                }
            )

        payload = {
            "collected_at": datetime.now().isoformat(timespec="seconds"),
            "status": status,
            "limit_per_task": limit,
            "task_count": len(task_items),
            "total_logs": total_logs,
            "tasks": task_items,
        }
        payload["analysis"] = analyze_payload(payload)
        return payload


def resolve_output_path(output: Path | None) -> Path:
    if output is not None:
        return output if output.is_absolute() else PROJECT_ROOT / output

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return DEFAULT_OUTPUT_DIR / f"running_task_logs_{timestamp}.json"


def resolve_report_path(output_path: Path, report_output: Path | None) -> Path:
    if report_output is not None:
        return report_output if report_output.is_absolute() else PROJECT_ROOT / report_output
    return output_path.with_name(f"{output_path.stem}_summary.md")


def format_value(value: Any) -> str:
    if value is None:
        return "-"
    return str(value)


def render_report(payload: dict[str, Any]) -> str:
    analysis = payload["analysis"]
    metric_stats_map = analysis["metric_stats"]
    lines = [
        "# Running Task Logs Summary",
        "",
        f"- collected_at: {payload['collected_at']}",
        f"- status: {payload['status']}",
        f"- task_count: {payload['task_count']}",
        f"- total_logs: {payload['total_logs']}",
        f"- limit_per_task: {payload['limit_per_task']}",
        "",
        "## Metric Stats",
        "",
        "| metric | count | min | avg | p50 | p95 | max |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]

    for metric in ["execute_s", "rows", "read_s", "xpl_s", "save_s", "push_s"]:
        stats = metric_stats_map[metric]
        lines.append(
            "| {metric} | {count} | {min} | {avg} | {p50} | {p95} | {max} |".format(
                metric=metric,
                count=stats["count"],
                min=format_value(stats["min"]),
                avg=format_value(stats["avg"]),
                p50=format_value(stats["p50"]),
                p95=format_value(stats["p95"]),
                max=format_value(stats["max"]),
            )
        )

    lines.extend(
        [
            "",
            "## XPL By Group",
            "",
            "| group | count | min | avg | p50 | p95 | max |",
            "|---|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for group, stats in analysis["xpl_by_group"].items():
        lines.append(
            "| {group} | {count} | {min} | {avg} | {p50} | {p95} | {max} |".format(
                group=group,
                count=stats["count"],
                min=format_value(stats["min"]),
                avg=format_value(stats["avg"]),
                p50=format_value(stats["p50"]),
                p95=format_value(stats["p95"]),
                max=format_value(stats["max"]),
            )
        )

    lines.extend(
        [
            "",
            "## Top Task XPL",
            "",
            "| task | step | rows | xpl_avg | xpl_max | xpl_values |",
            "|---|---:|---:|---:|---:|---|",
        ]
    )
    for item in analysis["top_task_xpl"]:
        lines.append(
            "| {task_name} | {step} | {rows} | {avg} | {max} | {values} |".format(
                task_name=item["task_name"],
                step=item["step"],
                rows=",".join(str(row) for row in item["rows"]),
                avg=format_value(item["xpl"]["avg"]),
                max=format_value(item["xpl"]["max"]),
                values=", ".join(str(value) for value in item["xpl_values"]),
            )
        )

    lines.extend(
        [
            "",
            "## Log Counts",
            "",
            "### Levels",
            "",
        ]
    )
    for level, count in sorted(analysis["level_counts"].items()):
        lines.append(f"- {level}: {count}")

    lines.extend(["", "### Types", ""])
    for log_type, count in analysis["log_type_counts"].items():
        lines.append(f"- {log_type}: {count}")

    if analysis["non_info_logs"]:
        lines.extend(["", "## Non Info Logs", ""])
        for log in analysis["non_info_logs"]:
            lines.append(
                f"- {log['timestamp']} {log['level']} {log['task_name']}: {log['message']}"
            )

    return "\n".join(lines) + "\n"


def main() -> int:
    args = parse_args()
    if args.limit <= 0:
        raise ValueError("--limit must be greater than 0")

    output_path = resolve_output_path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    payload = collect_logs(status=args.status, limit=args.limit)
    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    report_path = resolve_report_path(output_path, args.report_output)
    report_path.write_text(render_report(payload), encoding="utf-8")

    print(f"已保存: {output_path}")
    print(f"摘要报告: {report_path}")
    print(f"任务数: {payload['task_count']}, 日志数: {payload['total_logs']}")
    xpl_stats = payload["analysis"]["metric_stats"]["xpl_s"]
    execute_stats = payload["analysis"]["metric_stats"]["execute_s"]
    print(
        "execute: "
        f"count={execute_stats['count']}, avg={execute_stats['avg']}s, "
        f"p95={execute_stats['p95']}s, max={execute_stats['max']}s"
    )
    print(
        "xpl: "
        f"count={xpl_stats['count']}, avg={xpl_stats['avg']}s, "
        f"p95={xpl_stats['p95']}s, max={xpl_stats['max']}s"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

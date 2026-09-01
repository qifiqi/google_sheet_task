"""Create five-year-window rerun tasks for recent single backtest tasks.

默认 dry-run，不会创建任务。确认预览无误后加 --execute。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app import create_app
from app.extensions import db
from app.models import Task, TaskResult
from app.services.task import task_manager


MARKER_KEY = "recent_five_year_source_task_id"
DEFAULT_START_DATE = "2026-04-23"
DEFAULT_RECENT_YEARS = 5


@dataclass(frozen=True)
class BuildResult:
    source_task: Task
    config: dict[str, Any] | None
    end_date: str | None
    recent_years: list[int]
    skip_reason: str = ""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="为指定日期之后的单回测任务创建近五年截至日期重跑任务。"
    )
    parser.add_argument(
        "--from-date",
        default=DEFAULT_START_DATE,
        help=f"筛选任务创建日期，格式 YYYY-MM-DD，默认 {DEFAULT_START_DATE}",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="真正创建并启动任务；不加时只预览。",
    )
    parser.add_argument(
        "--start",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="创建后是否尝试启动任务，默认 true；可用 --no-start 只创建 pending 任务。",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="最多处理多少个源任务，调试用。",
    )
    parser.add_argument(
        "--name-suffix",
        default="(近5年重跑)",
        help="新任务名称后缀。",
    )
    parser.add_argument(
        "--include-status",
        action="append",
        default=None,
        help="只处理指定状态，可重复传；默认处理所有状态。",
    )
    parser.add_argument(
        "--allow-duplicate",
        action="store_true",
        help="允许为同一个源任务重复创建近五年任务。",
    )
    parser.add_argument(
        "--app-env",
        choices=("development", "production", "testing"),
        default=os.environ.get("APP_ENV"),
        help="设置 APP_ENV 后再加载 Flask 应用；也可直接设置环境变量 APP_ENV。",
    )
    parser.add_argument(
        "--database-url",
        default=os.environ.get("DATABASE_URL"),
        help="覆盖 DATABASE_URL；也可直接设置环境变量 DATABASE_URL。",
    )
    return parser.parse_args()


def parse_from_date(value: str) -> datetime:
    try:
        return datetime.strptime(value, "%Y-%m-%d")
    except ValueError as exc:
        raise SystemExit(f"--from-date 格式无效，应为 YYYY-MM-DD: {value}") from exc


def load_json(raw: Any, default: Any) -> Any:
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return default
    return raw if raw is not None else default


def normalize_years(values: Any) -> list[int]:
    years: list[int] = []
    for value in values or []:
        if value is None or str(value).strip() == "":
            continue
        years.append(int(value))
    return sorted(set(years))


def extract_stock_date(item: Any) -> str | None:
    if isinstance(item, dict):
        value = item.get("stock_date") or item.get("date")
        return str(value).strip() if value else None
    return None


def find_latest_result_end_date(task_id: str) -> str | None:
    results = (
        TaskResult.query.filter_by(task_id=task_id, success=True)
        .order_by(TaskResult.step_index.asc(), TaskResult.timestamp.asc(), TaskResult.id.asc())
        .all()
    )
    latest: str | None = None
    for result in results:
        parameters = load_json(result.parameters, {})
        if not isinstance(parameters, dict):
            continue
        kline = parameters.get("kline")
        if not isinstance(kline, list) or not kline:
            continue
        end_date = extract_stock_date(kline[-1])
        if end_date and (latest is None or end_date > latest):
            latest = end_date
    return latest


def has_existing_generated_task(source_task_id: str) -> bool:
    pattern = f'%"{MARKER_KEY}": "{source_task_id}"%'
    return (
        db.session.query(Task.id)
        .filter(Task.task_type == "backtest_training", Task.config.like(pattern))
        .first()
        is not None
    )


def build_recent_five_year_config(task: Task, allow_duplicate: bool) -> BuildResult:
    if not allow_duplicate and has_existing_generated_task(task.id):
        return BuildResult(task, None, None, [], "已存在由该源任务创建的近五年任务")

    config = load_json(task.config, {})
    if not isinstance(config, dict):
        return BuildResult(task, None, None, [], "任务配置不是 JSON 对象")

    end_date = find_latest_result_end_date(task.id)
    if not end_date:
        return BuildResult(task, None, None, [DEFAULT_RECENT_YEARS], "历史结果中找不到 parameters.kline 结束日期")

    new_config = deepcopy(config)
    new_config["recent_years"] = [DEFAULT_RECENT_YEARS]
    new_config["full_years"] = []
    new_config.pop("include_full_year_range", None)
    new_config["end_date"] = end_date
    new_config[MARKER_KEY] = task.id
    new_config["recent_five_year_source_task_name"] = task.name

    return BuildResult(task, new_config, end_date, [DEFAULT_RECENT_YEARS])


def query_source_tasks(from_date: datetime, statuses: list[str] | None, limit: int | None) -> list[Task]:
    query = Task.query.filter(
        Task.task_type == "backtest_training",
        Task.created_at >= from_date,
    ).order_by(Task.created_at.asc(), Task.id.asc())
    if statuses:
        query = query.filter(Task.status.in_(statuses))
    if limit:
        query = query.limit(limit)
    return query.all()


def create_task_from_result(result: BuildResult, name_suffix: str, start: bool) -> tuple[str, str]:
    source = result.source_task
    name = f"{source.name} {name_suffix}".strip()
    description = (
        f"{source.description or ''}\n"
        f"基于源任务 {source.id} 创建近5年重跑任务；recent_years=[5]；end_date={result.end_date}"
    ).strip()
    if start:
        response, _status_code = task_manager.create_and_start_task(
            name,
            description,
            "backtest_training",
            result.config or {},
            created_by_user_id=source.created_by_user_id,
        )
        return str(response.get("task_id") or ""), str(response.get("message") or response)

    task_id = task_manager.create_task(
        name,
        description,
        "backtest_training",
        result.config or {},
        created_by_user_id=source.created_by_user_id,
    )
    return task_id, "任务已创建，状态 pending"


def main() -> int:
    args = parse_args()
    from_date = parse_from_date(args.from_date)
    if args.app_env:
        os.environ["APP_ENV"] = args.app_env
    if args.database_url:
        os.environ["DATABASE_URL"] = args.database_url
    app = create_app()

    with app.app_context():
        source_tasks = query_source_tasks(from_date, args.include_status, args.limit)
        build_results = [
            build_recent_five_year_config(task, allow_duplicate=args.allow_duplicate)
            for task in source_tasks
        ]
        ready = [item for item in build_results if item.config]
        skipped = [item for item in build_results if not item.config]

        print(f"筛选任务: task_type=backtest_training, created_at >= {args.from_date}")
        print(f"APP_ENV: {os.environ.get('APP_ENV', 'development')}")
        print(f"DATABASE: {app.config.get('SQLALCHEMY_DATABASE_URI')}")
        print(f"源任务数: {len(source_tasks)}，可创建: {len(ready)}，跳过: {len(skipped)}")
        print(f"模式: {'执行创建' if args.execute else '预览 dry-run'}，创建后启动: {args.start}")
        print()

        for item in ready:
            years_label = ",".join(str(year) for year in item.recent_years)
            print(
                f"[READY] {item.source_task.created_at:%Y-%m-%d %H:%M:%S} "
                f"{item.source_task.id} | {item.source_task.name} | "
                f"recent_years=[{years_label}], end_date={item.end_date}"
            )

        for item in skipped:
            print(
                f"[SKIP]  {item.source_task.created_at:%Y-%m-%d %H:%M:%S} "
                f"{item.source_task.id} | {item.source_task.name} | {item.skip_reason}"
            )

        if not args.execute:
            print()
            print("当前是 dry-run；确认无误后执行：")
            env_arg = f" --app-env {args.app_env}" if args.app_env else ""
            print(
                f"python scripts/create_backtest_full_year_range_tasks.py"
                f"{env_arg} --from-date {args.from_date} --execute"
            )
            return 0

        created = 0
        failed = 0
        print()
        for item in ready:
            try:
                task_id, message = create_task_from_result(item, args.name_suffix, args.start)
                db.session.commit()
                created += 1
                print(f"[CREATED] source={item.source_task.id} new={task_id} | {message}")
            except Exception as exc:
                db.session.rollback()
                failed += 1
                print(f"[ERROR]   source={item.source_task.id} | {exc}")

        print()
        print(f"完成：创建 {created} 个，失败 {failed} 个，跳过 {len(skipped)} 个")
        return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())

"""规范化任务/模板配置；默认只预览，--apply 必须指定新的 --backup-file。"""

from __future__ import annotations

import argparse
from copy import deepcopy
import os
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pydantic import ValidationError
from sqlalchemy import update

from app import create_app
from app.extensions import db
from app.models import Task, TaskTemplate
from app.schemas.task_configs import TASK_CONFIG_MODELS, get_task_config_model, validate_task_config_shape
from app.utils.json_utils import dumps, loads
from app.utils.logger import get_logger

logger = get_logger("scripts.migrate_task_config_schema")
_C3_FLAT_SHEET_KEYS = ("spreadsheet_id", "sheet_name", "title", "spreadsheet_title")
_SHEET_EXTRA_KEYS = ("google_sheet_id", "model_version")


def _build_single_sheet(source: dict[str, Any]) -> dict[str, Any] | None:
    nested = source.get("sheet")
    ref = dict(nested) if isinstance(nested, dict) else {}
    spreadsheet_id = ref.get("spreadsheet_id") or source.get("spreadsheet_id")
    if not spreadsheet_id:
        return None
    ref["spreadsheet_id"] = str(spreadsheet_id).strip()
    ref["sheet_name"] = str(ref.get("sheet_name") or source.get("sheet_name") or "data").strip() or "data"
    ref["title"] = str(ref.get("title") or source.get("title") or source.get("spreadsheet_title") or "").strip()
    for key in _SHEET_EXTRA_KEYS:
        if key not in ref and source.get(key) not in (None, ""):
            ref[key] = source[key]
    return ref


def _canonical_type(task_type: str | None) -> str:
    key = str(task_type or "").strip()
    return next((name for name in TASK_CONFIG_MODELS if name.lower() == key.lower()), key)


def migrate_config(task_type: str | None, config: Any) -> tuple[dict[str, Any] | None, str]:
    if not isinstance(config, dict):
        return None, "skipped:config 不是 JSON 对象"
    normalized_type = _canonical_type(task_type)
    if get_task_config_model(normalized_type) is None:
        return config, "unchanged"
    candidate = deepcopy(config)
    is_c3 = normalized_type in ("google_sheet", "google_sheet_C3")
    if is_c3 or normalized_type == "backtest_training":
        nested = candidate.get("sheet")
        if isinstance(nested, dict):
            for key in ("spreadsheet_id", "sheet_name", "title", *_SHEET_EXTRA_KEYS):
                if key in candidate and key in nested and candidate[key] != nested[key]:
                    return None, "skipped:新旧 Sheet 引用冲突"
        ref = _build_single_sheet(candidate)
        sheets = candidate.get("sheets")
        if not sheets:
            if ref is None:
                return None, "skipped:缺少 spreadsheet_id"
            candidate["sheets"] = [ref]
        elif ref is not None:
            if not isinstance(sheets, list) or len(sheets) != 1 or not isinstance(sheets[0], dict):
                return None, "skipped:新旧 Sheet 引用冲突"
            current_ref = sheets[0]
            for key, value in ref.items():
                if key in current_ref and current_ref[key] != value:
                    return None, "skipped:新旧 Sheet 引用冲突"
            candidate["sheets"] = [{**ref, **current_ref}]
        for key in (*_C3_FLAT_SHEET_KEYS, "sheet") if is_c3 else ("sheet",):
            candidate.pop(key, None)

    if normalized_type in ("google_sheet_C5", "google_sheet_C7", "google_sheet_C1_1"):
        if "exclude_years" in candidate:
            if "exclude_recent_years" not in candidate:
                candidate["exclude_recent_years"] = candidate["exclude_years"]
            candidate.pop("exclude_years")
    try:
        shaped = validate_task_config_shape(normalized_type, candidate)
    except ValidationError as exc:
        # 不输出校验器携带的 input_value，配置可能包含敏感字段。
        locations = [".".join(map(str, item["loc"])) for item in exc.errors(include_input=False)]
        return None, "skipped:模型校验失败 " + ",".join(locations)
    return shaped, "unchanged" if shaped == config else "migrated"


def _infer_config_kind(config: dict[str, Any]) -> str | None:
    if config.get("task_type"):
        return str(config["task_type"])
    if isinstance(config.get("sheet"), dict):
        return "backtest_training"
    if config.get("spreadsheet_id"):
        return "google_sheet"
    return None


def _prepare_rows(rows, label: str, verbose: bool):
    stats = {"total": 0, "migrated": 0, "unchanged": 0, "skipped": 0}
    changes = []
    for row in rows:
        stats["total"] += 1
        try:
            config = loads(row.config) if row.config else None
        except (TypeError, ValueError):
            stats["skipped"] += 1
            logger.warning("[%s] %s config 解析失败", label, row.id)
            continue
        if not isinstance(config, dict):
            stats["skipped"] += 1
            logger.warning("[%s] %s config 不是对象", label, row.id)
            continue
        task_type = row.task_type if label == "task" else _infer_config_kind(config)
        if label == "template" and not task_type:
            stats["skipped"] += 1
            logger.warning("[template] %s 缺少可判定的 task_type", row.id)
            continue
        candidate = dict(config)
        if label == "template":
            candidate["task_type"] = task_type
        new_config, status = migrate_config(task_type, candidate)
        if status.startswith("skipped:"):
            stats["skipped"] += 1
            logger.warning("[%s] %s %s", label, row.id, status)
            continue
        changed = new_config != config
        stats["migrated" if changed else "unchanged"] += 1
        if changed:
            changes.append({"table": label, "id": row.id, "before": row.config, "after": dumps(new_config)})
        if verbose:
            logger.info("[%s] %s %s", label, row.id, "migrated" if changed else "unchanged")
    return stats, changes


def apply_changes(session, changes: list[dict[str, Any]], backup_file: Path) -> None:
    if session.query(Task.id).filter(Task.status == "running").first():
        raise ValueError("仍有运行中的任务，禁止迁移配置")
    with backup_file.open("x", encoding="utf-8") as stream:
        stream.write(dumps({"database": session.get_bind().url.render_as_string(hide_password=True), "changes": changes}))
        stream.flush()
        os.fsync(stream.fileno())
    try:
        for item in changes:
            model = Task if item["table"] == "task" else TaskTemplate
            row = session.get(model, item["id"], populate_existing=True, with_for_update=True)
            if row is None or row.config != item["before"]:
                raise ValueError("配置在预检后发生变化，迁移已取消")
            if model is Task and row.status == "running":
                raise ValueError("任务在预检后进入运行中，迁移已取消")
            # Core UPDATE 不触发模型的 onupdate 时间戳；只修改 config。
            session.execute(update(model.__table__).where(model.id == item["id"]).values(
                config=item["after"],
                **({"updated_at": row.updated_at} if hasattr(row, "updated_at") else {}),
            ))
        session.commit()
    except Exception:
        session.rollback()
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description="任务配置结构统一迁移（保留执行语义）")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--backup-file", type=Path, help="应用前保存原始配置；文件必须尚不存在")
    parser.add_argument("--task-id")
    parser.add_argument("--include-templates", action="store_true")
    parser.add_argument("--template-id", type=int)
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()
    if args.apply and not args.backup_file:
        parser.error("--apply 必须指定 --backup-file")
    if args.template_id is not None and not args.include_templates:
        parser.error("--template-id 需要 --include-templates")
    app = create_app()
    with app.app_context():
        tasks = db.session.query(Task)
        if args.task_id:
            tasks = tasks.filter(Task.id == args.task_id)
        task_stats, changes = _prepare_rows(tasks.yield_per(200), "task", args.verbose)
        template_stats = {"total": 0, "migrated": 0, "unchanged": 0, "skipped": 0}
        if args.include_templates:
            templates = db.session.query(TaskTemplate)
            if args.template_id is not None:
                templates = templates.filter(TaskTemplate.id == args.template_id)
            template_stats, template_changes = _prepare_rows(templates.yield_per(200), "template", args.verbose)
            changes.extend(template_changes)
        print("target:", db.engine.url.host, db.engine.url.port, db.engine.url.database)
        print("mode:", "APPLY" if args.apply else "DRY-RUN")
        print("tasks:", task_stats)
        print("templates:", template_stats)
        if task_stats["skipped"] or template_stats["skipped"]:
            print("存在未通过预检的配置，未写入任何数据。")
            return 1
        if args.apply:
            try:
                apply_changes(db.session, changes, args.backup_file)
            except (ValueError, OSError) as exc:
                print("迁移未提交:", type(exc).__name__)
                return 1
            print("applied:", len(changes))
        else:
            print("dry-run 未写库。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

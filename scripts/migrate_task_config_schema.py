"""任务配置（Task.config / TaskTemplate.config）结构统一迁移脚本。

背景：
    2026-10 配置结构统一（见 docs/model_update/2026-10-09-任务配置Pydantic统一.md）
    把 Google Sheet 引用收敛为唯一形态 ``sheets: [{spreadsheet_id, sheet_name,
    title, ...}]``，并为每类任务建立 Pydantic 配置模型
    （app/schemas/task_configs.py）。此前的三种引用形态——C3 顶层平铺
    ``spreadsheet_id/sheet_name/title``、C4/C5/C7 ``sheets[]``、单品回测嵌套
    ``sheet{}``——统一为 sheets[]，读取端不再容忍旧形态。

做法：
    逐行读取 t_param_tasks 与 t_param_task_templates 的 config JSON：
    - C3（google_sheet）：顶层平铺键打包为 ``sheets:[1]``（title 回退
      spreadsheet_title）；
    - backtest_training：嵌套 ``sheet{}`` 平移为 ``sheets:[1]``（含
      google_sheet_id/c7_model_version 附加键）；
    - 其余已知类型：直接过类型模型结构收口（sheet_name 缺省、类型矫正）。
    迁移后写入仍用 ``json.dumps`` 默认序列化，与 create_task 落库格式一致
    （列表页 stock_code LIKE 文本匹配依赖该格式）。

用法（项目根目录执行；线上库先 set DATABASE_URL=...）：
    .venv\\Scripts\\python scripts\\migrate_task_config_schema.py            # dry-run
    .venv\\Scripts\\python scripts\\migrate_task_config_schema.py --apply    # 落库
    可选：--task-id <id>（单个任务）、--template-id <id>（单个模板）、
          --include-templates（连同任务模板表迁移）、--verbose

幂等：已迁移的行重新执行只做模型校验收口，不再变形；可重复执行。
"""

from __future__ import annotations

import argparse
from app.utils.json_utils import dumps, loads
import sys
from pathlib import Path
from typing import Any

# 支持直接 `python scripts/migrate_task_config_schema.py` 执行，无需设置 PYTHONPATH。
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import create_app
from app.extensions import db
from app.models import Task, TaskTemplate
from app.schemas.task_configs import validate_task_config_shape
from app.utils.logger import get_logger

logger = get_logger("scripts.migrate_task_config_schema")

# C3 顶层平铺键 → SheetRef 字段（title 优先，回退 spreadsheet_title 展示标题）
_C3_FLAT_SHEET_KEYS = ("spreadsheet_id", "sheet_name", "title", "spreadsheet_title")

# 嵌套 sheet{} 中需要平移进 SheetRef 的附加键（占用校验/C7 版本）
_SHEET_EXTRA_KEYS = ("google_sheet_id", "c7_model_version")


def _build_single_sheet(source: dict[str, Any]) -> dict[str, Any] | None:
    """把平铺键或嵌套 sheet{} 收敛为单个 SheetRef dict；无引用信息返回 None。"""
    spreadsheet_id = str(
        source.get("spreadsheet_id") or source.get("sheet", {}).get("spreadsheet_id") or ""
    ).strip()
    if not spreadsheet_id:
        return None
    nested = source.get("sheet") if isinstance(source.get("sheet"), dict) else {}
    ref: dict[str, Any] = {
        "spreadsheet_id": spreadsheet_id,
        "sheet_name": str(
            nested.get("sheet_name") or source.get("sheet_name") or "data"
        ).strip() or "data",
        "title": str(nested.get("title") or source.get("title") or "").strip(),
    }
    for key in _SHEET_EXTRA_KEYS:
        value = nested.get(key) or source.get(key)
        if value not in (None, ""):
            ref[key] = value
    return ref


def migrate_config(task_type: str | None, config: Any) -> tuple[dict[str, Any] | None, str]:
    """把单条 config 迁移到统一形态。返回 (新config或None, 状态)。

    状态：migrated（形态变形或模型收口有变化）/ unchanged（已符合）/
    skipped:<原因>（无法安全迁移，保持原样）。
    """
    if not isinstance(config, dict):
        return None, "skipped:config 不是 JSON 对象"

    normalized_type = (task_type or "").strip()
    candidate = dict(config)
    changed = False

    is_c3 = normalized_type == "google_sheet"
    is_training = normalized_type == "backtest_training"
    if is_c3 or is_training:
        existing_sheets = candidate.get("sheets")
        has_canonical = isinstance(existing_sheets, list) and existing_sheets
        if not has_canonical:
            # C3 模板可能带 spreadsheet_title 展示标题，作为 title 回退
            if is_c3 and not candidate.get("title") and candidate.get("spreadsheet_title"):
                candidate["title"] = candidate["spreadsheet_title"]
            ref = _build_single_sheet(candidate)
            if ref is None:
                return None, "skipped:缺少 spreadsheet_id"
            candidate["sheets"] = [ref]
            changed = True
        # 旧形态键从顶层移除（读取端不再容忍，留着只会污染编辑器）
        for key in (*_C3_FLAT_SHEET_KEYS, "sheet") if is_c3 else ("sheet",):
            if key in candidate:
                candidate.pop(key, None)
                changed = True
        if is_c3 and candidate.get("spreadsheet_title"):
            candidate.pop("spreadsheet_title", None)
            changed = True

    try:
        shaped = validate_task_config_shape(normalized_type, candidate)
    except Exception as exc:
        return None, f"skipped:模型校验失败({exc})"

    if shaped != config:
        changed = True
    return (shaped if changed else config), ("migrated" if changed else "unchanged")


def _iter_tasks(session, task_id: str | None):
    query = session.query(Task)
    if task_id:
        query = query.filter(Task.id == task_id)
    for row in query.yield_per(200):
        yield row


def _iter_templates(session, template_id: int | None):
    query = session.query(TaskTemplate)
    if template_id:
        query = query.filter(TaskTemplate.id == template_id)
    for row in query.yield_per(200):
        yield row


def _infer_config_kind(config: dict[str, Any]) -> str | None:
    """模板行无 task_type，按引用形态启发式推断（training 创建页无模板功能，
    实际只会命中 C3 平铺；sheet{} 分支兜底防御）。"""
    if isinstance(config.get("sheet"), dict):
        return "backtest_training"
    sheets = config.get("sheets")
    if not isinstance(sheets, list) and config.get("spreadsheet_id"):
        return "google_sheet"
    return None


def _migrate_rows(session, rows, label: str, apply: bool, verbose: bool) -> dict[str, int]:
    stats = {"total": 0, "migrated": 0, "unchanged": 0, "skipped": 0}
    for row in rows:
        stats["total"] += 1
        try:
            config = loads(row.config) if row.config else None
        except (TypeError, ValueError) as exc:
            stats["skipped"] += 1
            logger.warning("[%s] %s config 解析失败，跳过: %s", label, row.id, exc)
            continue
        if config is None:
            stats["skipped"] += 1
            if verbose:
                logger.info("[%s] %s config 为空，跳过", label, row.id)
            continue

        task_type = getattr(row, "task_type", None) or (
            _infer_config_kind(config) if label == "template" else None
        )
        new_config, status = migrate_config(task_type, config)
        if status.startswith("skipped"):
            stats["skipped"] += 1
            logger.warning("[%s] %s %s", label, row.id, status)
            continue

        if status == "migrated":
            stats[status] += 1
            if verbose:
                logger.info("[%s] %s %s", label, row.id, status)
            if apply:
                row.config = dumps(new_config)
                session.add(row)
        else:
            stats["unchanged"] += 1
    if apply:
        session.commit()
    return stats


def main() -> int:
    parser = argparse.ArgumentParser(description="任务配置结构统一迁移（sheets[] 形态）")
    parser.add_argument("--apply", action="store_true", help="落库（默认 dry-run 只打印诊断）")
    parser.add_argument("--task-id", help="只迁移单个任务")
    parser.add_argument("--include-templates", action="store_true", help="连同任务模板表迁移")
    parser.add_argument("--template-id", type=int, help="只迁移单个模板（需 --include-templates）")
    parser.add_argument("--verbose", action="store_true", help="打印每行迁移明细")
    args = parser.parse_args()

    app = create_app()
    with app.app_context():
        session = db.session
        task_stats = _migrate_rows(
            session, _iter_tasks(session, args.task_id), "task", args.apply, args.verbose
        )
        template_stats = {"total": 0, "migrated": 0, "unchanged": 0, "skipped": 0}
        if args.include_templates:
            template_stats = _migrate_rows(
                session,
                _iter_templates(session, args.template_id),
                "template",
                args.apply,
                args.verbose,
            )

        mode = "APPLY" if args.apply else "DRY-RUN"
        print(f"== 任务配置结构迁移 [{mode}] ==")
        print(f"tasks:     {task_stats}")
        if args.include_templates:
            print(f"templates: {template_stats}")
        if not args.apply:
            print("dry-run 未写库；确认后追加 --apply 执行迁移。")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())

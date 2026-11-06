"""One-way migration for US class-share symbols in stock metadata.

Project standard is Yahoo-style ``BRK-B.US``; legacy rows may store
``BRK_B``, ``BRK_B.US`` or ``BRK.B``. Default mode only prints the plan;
``--apply`` writes the changes and requires ``--backup-file`` (must not exist).

Run from the repository root:
    .venv\\Scripts\\python.exe scripts\\migrate_us_class_share_symbols.py
    .venv\\Scripts\\python.exe scripts\\migrate_us_class_share_symbols.py --apply --backup-file backup.json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import create_app
from app.extensions import db
from app.models import StockMetadata
from app.utils.market import normalize_stock_code

US_MARKET_TYPES = ("en", "us")
MERGE_FIELDS = ("stock_name", "exchange_market", "security_type_name", "source")


def _row_sort_key(row: dict[str, Any]) -> tuple[str, int]:
    return str(row.get("updated_at") or ""), int(row.get("id") or 0)


def _is_empty(value: Any) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def build_migration_plan(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Group US metadata rows by canonical code and return update/merge actions."""
    groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in rows or []:
        code = str(row.get("stock_code") or "").strip()
        market = str(row.get("market_type") or "").strip().lower()
        if not code or market not in US_MARKET_TYPES:
            continue
        target = normalize_stock_code(code, market, row.get("exchange_market"))
        if not target:
            continue
        groups.setdefault((market, target), []).append(row)

    plan: list[dict[str, Any]] = []
    for (_market, target), group in groups.items():
        if len(group) == 1 and group[0].get("stock_code") == target:
            continue
        target_rows = [row for row in group if row.get("stock_code") == target]
        survivor = max(target_rows or group, key=_row_sort_key)
        others = [row for row in group if row.get("id") != survivor.get("id")]

        updates: dict[str, Any] = {"stock_code": target}
        for field in MERGE_FIELDS:
            for candidate in [survivor, *sorted(
                (row for row in group if row.get("id") != survivor.get("id")),
                key=_row_sort_key,
                reverse=True,
            )]:
                if not _is_empty(candidate.get(field)):
                    updates[field] = candidate[field]
                    break
        if not others and survivor.get("stock_code") == target and all(
            (survivor.get(key) or None) == (value or None)
            for key, value in updates.items()
            if key != "stock_code"
        ):
            continue
        plan.append({
            "survivor_id": survivor.get("id"),
            "delete_ids": [row.get("id") for row in others],
            "target_code": target,
            "updates": updates,
            "before": group,
        })
    plan.sort(key=lambda item: (item["target_code"], int(item["survivor_id"] or 0)))
    return plan


def _load_plan() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    rows = [
        row.to_dict()
        for row in StockMetadata.query
        .filter(StockMetadata.market_type.in_(US_MARKET_TYPES))
        .order_by(StockMetadata.id)
        .all()
    ]
    return rows, build_migration_plan(rows)


def apply_changes(session, plan: list[dict[str, Any]], backup_file: Path) -> None:
    """Write the plan in one transaction; abort if a row changed after planning."""
    if backup_file.exists():
        raise FileExistsError(f"backup file already exists: {backup_file}")
    backup_file.parent.mkdir(parents=True, exist_ok=True)
    with backup_file.open("x", encoding="utf-8") as stream:
        json.dump(
            {
                "database": session.get_bind().url.render_as_string(hide_password=True),
                "changes": plan,
            },
            stream,
            ensure_ascii=False,
            indent=2,
        )
        stream.flush()
        os.fsync(stream.fileno())

    try:
        for action in plan:
            locked: dict[int, StockMetadata] = {}
            for before in action["before"]:
                row = session.get(
                    StockMetadata,
                    before["id"],
                    with_for_update=True,
                    populate_existing=True,
                )
                if row is None or row.to_dict() != before:
                    raise ValueError(f"stock_metadata row {before['id']} changed after planning")
                locked[before["id"]] = row
            survivor = locked.get(action["survivor_id"])
            if survivor is None:
                raise ValueError(f"missing survivor row {action['survivor_id']}")
            for delete_id in action["delete_ids"]:
                session.delete(locked[delete_id])
            for key, value in action["updates"].items():
                setattr(survivor, key, value)
            session.flush()
        session.commit()
    except Exception:
        session.rollback()
        raise


def _reexec_with_venv() -> None:
    """Allow double-click runs with the repository virtualenv."""
    if os.environ.get("US_CLASS_SHARE_MIGRATION_NO_REEXEC") == "1":
        return
    python = Path(__file__).resolve().parents[1] / (
        ".venv/Scripts/python.exe" if os.name == "nt" else ".venv/bin/python"
    )
    if not python.exists() or Path(sys.executable).resolve() == python.resolve():
        return
    os.execv(str(python), [str(python), str(Path(__file__).resolve()), *sys.argv[1:]])


def main() -> int:
    parser = argparse.ArgumentParser(description="Migrate legacy US class-share symbols in stock metadata")
    parser.add_argument("--apply", action="store_true", help="write changes (default: dry-run)")
    parser.add_argument("--backup-file", type=Path, help="required with --apply; must not exist")
    parser.add_argument("--audit-internal", action="store_true", help="also report internal K-line store row counts")
    args = parser.parse_args()
    if args.apply and not args.backup_file:
        parser.error("--apply requires --backup-file")

    _reexec_with_venv()
    app = create_app()
    with app.app_context():
        rows, plan = _load_plan()
        updates = sum(1 for item in plan if not item["delete_ids"])
        merges = len(plan) - updates
        print("mode:", "APPLY" if args.apply else "DRY-RUN")
        print("target:", db.engine.url.host, db.engine.url.port, db.engine.url.database)
        print("us_rows:", len(rows))
        print("planned_changes:", len(plan), "updates:", updates, "merges:", merges)
        for action in plan:
            fields = sorted(key for key in action["updates"] if key != "stock_code")
            print(
                " -", action["target_code"],
                "survivor", action["survivor_id"],
                "delete", action["delete_ids"],
                "fields", fields,
            )
        if args.audit_internal:
            from app.services.kline_service import KlineService

            service = KlineService()
            for target in sorted({action["target_code"] for action in plan}):
                base = target[:-3] if target.endswith(".US") else target
                legacy = base.replace("-", "_")
                canonical_rows = service.read_internal_kline_data(stock_code=base, market_type="en")
                legacy_rows = service.read_internal_kline_data(stock_code=legacy, market_type="en")
                print("internal:", base, "canonical_rows:", len(canonical_rows), "legacy_rows:", len(legacy_rows))
        if args.apply:
            apply_changes(db.session, plan, args.backup_file)
            print("applied:", len(plan))
        return 0


if __name__ == "__main__":
    raise SystemExit(main())

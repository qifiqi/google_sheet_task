#!/usr/bin/env python3
"""Bulk import stock metadata into stock_metadata.

Supports CSV and JSON inputs. Column names may include table prefixes like
`task_result_summary_index.stock_code`; the importer will strip the prefix
before mapping to canonical fields.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app import create_app
from app.extensions import db
from app.utils.dfcf_api import DFCJStockApi
from app.services.stock_metadata_service import bulk_upsert_stock_metadata


PREFIXES = (
    "task_result_summary_index.",
    "stock_metadata.",
    "stocks.",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Bulk import stock metadata from CSV or JSON.")
    parser.add_argument("input_file", help="Path to a CSV or JSON file.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse and preview rows without writing to the database.",
    )
    parser.add_argument(
        "--commit-every",
        type=int,
        default=500,
        help="Commit every N rows when importing. Default: 500.",
    )
    return parser.parse_args()


def _strip_prefix(key: Any) -> str:
    text = str(key or "").strip()
    lowered = text.lower()
    for prefix in PREFIXES:
        if lowered.startswith(prefix):
            return text[len(prefix):]
    return text


def _normalize_row(row: dict[str, Any]) -> dict[str, Any]:
    normalized: dict[str, Any] = {}
    for key, value in row.items():
        clean_key = _strip_prefix(key)
        if clean_key:
            normalized[clean_key] = value
    return normalized


def _load_json_rows(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, dict):
        if isinstance(payload.get("rows"), list):
            payload = payload["rows"]
        elif isinstance(payload.get("data"), list):
            payload = payload["data"]
        else:
            payload = [payload]
    if not isinstance(payload, list):
        raise ValueError("JSON input must be a list of objects or an object with rows/data list.")
    rows: list[dict[str, Any]] = []
    for item in payload:
        if isinstance(item, dict):
            rows.append(_normalize_row(item))
    return rows


def _load_csv_rows(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8-sig", newline="") as fp:
        reader = csv.DictReader(fp)
        return [_normalize_row(row) for row in reader]


def load_rows(path: Path) -> list[dict[str, Any]]:
    suffix = path.suffix.lower()
    if suffix == ".csv":
        return _load_csv_rows(path)
    if suffix in {".json", ".jsonl"}:
        if suffix == ".jsonl":
            rows: list[dict[str, Any]] = []
            with path.open("r", encoding="utf-8") as fp:
                for raw_line in fp:
                    line = raw_line.strip()
                    if not line:
                        continue
                    item = json.loads(line)
                    if isinstance(item, dict):
                        rows.append(_normalize_row(item))
            return rows
        return _load_json_rows(path)
    if suffix in {".txt", ".list", ""}:
        rows: list[dict[str, Any]] = []
        with path.open("r", encoding="utf-8") as fp:
            for raw_line in fp:
                code = str(raw_line or "").strip()
                if code:
                    rows.append({"stock_code": code})
        return rows
    raise ValueError("Only .csv, .json and .jsonl are supported.")


def _pick_search_result(results: list[dict[str, Any]], stock_code: str) -> dict[str, Any]:
    normalized_code = str(stock_code or "").strip().upper()
    if not results:
        return {}
    for item in results:
        if str(item.get("code") or "").strip().upper() == normalized_code:
            return item
    return results[0]


def _resolve_stock_row(row: dict[str, Any], api: DFCJStockApi, page_size: int) -> dict[str, Any] | None:
    stock_code = str(row.get("stock_code") or "").strip()
    if not stock_code:
        return None

    stock_name = str(row.get("stock_name") or "").strip()
    if stock_name:
        return _normalize_row(row)

    raw_results = api.get_search_list_by_stock_code(stock_code, page_size=page_size)
    if isinstance(raw_results, dict) and raw_results.get("error"):
        return None
    if not isinstance(raw_results, list):
        return None

    picked = _pick_search_result(raw_results, stock_code)
    if not picked:
        return None

    resolved_name = str(picked.get("shortName") or picked.get("name") or "").strip()
    if not resolved_name:
        resolved_name = stock_code

    market_value = picked.get("marketType") or picked.get("market") or row.get("market_type")
    exchange_market = picked.get("market") or row.get("exchange_market")
    security_type_name = picked.get("securityTypeName") or row.get("security_type_name")
    source = picked.get("source") or row.get("source") or "search"

    return {
        "stock_code": stock_code,
        "stock_name": resolved_name,
        "market_type": market_value,
        "exchange_market": exchange_market,
        "security_type_name": security_type_name,
        "source": source,
        "raw": picked,
    }


def resolve_stock_rows(rows: list[dict[str, Any]], page_size: int = 20) -> list[dict[str, Any]]:
    api = DFCJStockApi()
    resolved_rows: list[dict[str, Any]] = []
    seen_codes: set[str] = set()

    for row in rows:
        normalized_row = _normalize_row(row)
        stock_code = str(normalized_row.get("stock_code") or "").strip()
        if not stock_code:
            continue
        code_key = stock_code.upper()
        if code_key in seen_codes:
            continue
        seen_codes.add(code_key)

        resolved_row = _resolve_stock_row(normalized_row, api, page_size)
        if resolved_row:
            resolved_rows.append(resolved_row)

    return resolved_rows


def import_stock_metadata_file(path: Path, dry_run: bool = False, commit_every: int = 500) -> dict[str, int]:
    rows = load_rows(path)
    if dry_run:
        return {"imported": 0, "total": len(rows)}

    resolved_rows = resolve_stock_rows(rows)
    imported = 0
    for index, row in enumerate(resolved_rows, start=1):
        if bulk_upsert_stock_metadata([row]):
            imported += 1
        if commit_every > 0 and index % commit_every == 0:
            db.session.commit()
    db.session.commit()
    return {"imported": imported, "total": len(rows), "resolved": len(resolved_rows)}


def main() -> int:
    args = parse_args()
    app = create_app()
    input_path = Path(args.input_file).expanduser().resolve()
    if not input_path.exists():
        raise SystemExit(f"Input file not found: {input_path}")

    with app.app_context():
        result = import_stock_metadata_file(
            input_path,
            dry_run=args.dry_run,
            commit_every=args.commit_every,
        )
        if args.dry_run:
            print(f"Dry run completed. Parsed {result['total']} rows.")
        else:
            print(
                f"Imported {result['imported']} rows from {result['total']} rows "
                f"({result.get('resolved', 0)} resolved)."
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import gzip
import json
from pathlib import Path
from typing import Any

from xpl_worker.config import PROJECT_ROOT


class ReturnSeriesReader:
    def load_rows(self, returns_json: str | None) -> list[dict[str, Any]]:
        payload = self.load_payload(returns_json)
        if not payload:
            return []

        dates = payload.get("dates") or []
        index_returns = payload.get("index_returns") or []
        start_returns = payload.get("start_returns") or []
        rows: list[dict[str, Any]] = []
        for index, date in enumerate(dates):
            rows.append({
                "date": date,
                "index_return": index_returns[index] if index < len(index_returns) else None,
                "start_return": start_returns[index] if index < len(start_returns) else None,
            })
        return rows

    def load_payload(self, returns_json: str | None) -> dict[str, Any]:
        payload = self._parse_json(returns_json)
        if not isinstance(payload, dict):
            return {}
        if payload.get("storage") == "local_gzip":
            payload = self._load_archived_payload(payload)
        return payload if isinstance(payload, dict) else {}

    def _load_archived_payload(self, pointer: dict[str, Any]) -> dict[str, Any]:
        path_value = pointer.get("path")
        series_id = str(pointer.get("series_id") or "")
        if not path_value or not series_id:
            return {}

        archive_path = Path(path_value)
        if not archive_path.is_absolute():
            archive_path = PROJECT_ROOT / archive_path
        if not archive_path.exists():
            return {}

        with gzip.open(archive_path, "rt", encoding="utf-8") as handle:
            archive_payload = json.load(handle)
        series = archive_payload.get("series") if isinstance(archive_payload, dict) else {}
        payload = series.get(series_id) if isinstance(series, dict) else None
        return payload if isinstance(payload, dict) else {}

    def _parse_json(self, raw: str | None) -> dict[str, Any]:
        if not raw:
            return {}
        try:
            payload = json.loads(raw)
        except (TypeError, ValueError):
            return {}
        return payload if isinstance(payload, dict) else {}


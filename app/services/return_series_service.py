import json
import gzip
import os
from datetime import datetime
from pathlib import Path
from typing import Any

from app.models import TaskResultReturn, db


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ARCHIVE_DIR = PROJECT_ROOT / "data" / "return_series_archives"


class ReturnSeriesService:
    """Build and persist return-series snapshots for later analysis."""

    def __init__(self, archive_dir: Path | None = None):
        self.archive_dir = archive_dir or DEFAULT_ARCHIVE_DIR

    def build_payload(
        self,
        rows: list[dict[str, Any]],
        source_columns: dict[str, str] | None = None,
        step_index: int | None = None,
    ) -> dict[str, Any]:
        dates: list[Any] = []
        index_returns: list[Any] = []
        start_returns: list[Any] = []

        for item in rows or []:
            if not isinstance(item, dict):
                continue
            dates.append(item.get("date") or item.get("stock_date"))
            index_returns.append(item.get("index_return"))
            start_returns.append(item.get("start_return"))

        payload: dict[str, Any] = {
            "version": 1,
            "row_count": len(dates),
            "dates": dates,
            "index_returns": index_returns,
            "start_returns": start_returns,
        }
        if source_columns:
            payload["source_columns"] = source_columns
        if step_index is not None:
            payload["created_from_step_index"] = step_index
        return payload

    def dumps(
        self,
        rows: list[dict[str, Any]],
        source_columns: dict[str, str] | None = None,
        step_index: int | None = None,
    ) -> str:
        return json.dumps(
            self.build_payload(rows, source_columns, step_index),
            ensure_ascii=False,
            allow_nan=False,
        )

    def create_for_task(
        self,
        task_id: str,
        rows: list[dict[str, Any]],
        source_columns: dict[str, str] | None = None,
        step_index: int | None = None,
    ) -> TaskResultReturn:
        return TaskResultReturn(
            task_id=task_id,
            returns_json=self.dumps(rows, source_columns, step_index),
        )

    def load_rows(self, returns_json: str | None) -> list[dict[str, Any]]:
        payload = self.load_payload(returns_json)
        if not payload:
            return []

        dates = payload.get("dates") or []
        index_returns = payload.get("index_returns") or []
        start_returns = payload.get("start_returns") or []
        return [
            {
                "date": date,
                "index_return": index_returns[index] if index < len(index_returns) else None,
                "start_return": start_returns[index] if index < len(start_returns) else None,
            }
            for index, date in enumerate(dates)
        ]

    def load_payload(self, returns_json: str | None) -> dict[str, Any]:
        if not returns_json:
            return {}
        payload = self._parse_json(returns_json)
        if not isinstance(payload, dict):
            return {}
        if payload.get("storage") == "local_gzip":
            payload = self._load_archived_payload(payload)
            if not isinstance(payload, dict):
                return {}
        return payload

    def archive_task_series(self, task_id: str) -> dict[str, Any]:
        records = (
            TaskResultReturn.query.filter(TaskResultReturn.task_id == task_id)
            .order_by(TaskResultReturn.id.asc())
            .all()
        )
        archive_items: dict[str, Any] = {}
        pointer_updates: list[tuple[TaskResultReturn, dict[str, Any]]] = []

        for record in records:
            payload = self._parse_json(record.returns_json)
            if not payload or payload.get("storage") == "local_gzip":
                continue
            series_id = str(record.id)
            archive_items[series_id] = payload
            pointer_updates.append((record, self._build_archive_pointer(record.id, payload)))

        if not archive_items:
            return {
                "archived": 0,
                "path": None,
                "bytes": 0,
            }

        archive_path = self.archive_dir / f"{task_id}.json.gz"
        archive_path.parent.mkdir(parents=True, exist_ok=True)

        archive_payload = {
            "version": 1,
            "task_id": task_id,
            "archived_at": datetime.now().isoformat(timespec="seconds"),
            "series": archive_items,
        }
        self._write_gzip_json(archive_path, archive_payload)

        normalized_path = self._path_for_pointer(archive_path)
        for record, pointer in pointer_updates:
            pointer["path"] = normalized_path
            record.returns_json = json.dumps(pointer, ensure_ascii=False, allow_nan=False)

        db.session.commit()
        return {
            "archived": len(pointer_updates),
            "path": normalized_path,
            "bytes": archive_path.stat().st_size,
        }

    def delete_task_archive(self, task_id: str) -> bool:
        archive_path = self.archive_dir / f"{task_id}.json.gz"
        if not archive_path.exists():
            return False
        archive_path.unlink()
        return True

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

    def _build_archive_pointer(self, series_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        return {
            "version": 1,
            "storage": "local_gzip",
            "path": "",
            "series_id": series_id,
            "row_count": payload.get("row_count") or len(payload.get("dates") or []),
            "source_columns": payload.get("source_columns"),
            "created_from_step_index": payload.get("created_from_step_index"),
        }

    def _parse_json(self, raw: str | None) -> dict[str, Any]:
        if not raw:
            return {}
        try:
            payload = json.loads(raw)
        except (TypeError, ValueError):
            return {}
        return payload if isinstance(payload, dict) else {}

    def _write_gzip_json(self, archive_path: Path, payload: dict[str, Any]) -> None:
        temp_path = archive_path.with_suffix(f"{archive_path.suffix}.tmp")
        with gzip.open(temp_path, "wt", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
        os.replace(temp_path, archive_path)

    def _path_for_pointer(self, archive_path: Path) -> str:
        try:
            return archive_path.relative_to(PROJECT_ROOT).as_posix()
        except ValueError:
            return str(archive_path)

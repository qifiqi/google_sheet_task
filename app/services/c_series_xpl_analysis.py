import json
import time
from typing import Any

from app.services.config_manager import get_config_manager
from app.services.return_series_service import ReturnSeriesService
from app.services.xpl_analysis_job_service import XplAnalysisJobService


RETURN_SERIES_SNAPSHOT_KEY = "_return_series_snapshot"
RETURN_ANALYSIS_ASYNC_KEY = "_return_analysis_async"


class CSeriesXplAnalysisService:
    """Shared C-series XPL analysis helpers for sync and async paths."""

    def __init__(
        self,
        *,
        return_series_service: ReturnSeriesService | None = None,
        xpl_analysis_job_service: XplAnalysisJobService | None = None,
    ):
        self.return_series_service = return_series_service or ReturnSeriesService()
        self.xpl_analysis_job_service = xpl_analysis_job_service or XplAnalysisJobService()

    def is_async_enabled(self, config_data: dict[str, Any]) -> bool:
        if "xpl_analysis_async_enabled" in config_data:
            return self._to_bool(config_data.get("xpl_analysis_async_enabled"))
        return self._to_bool(get_config_manager().get_config("xpl_analysis_async_enabled", False))

    def max_attempts(self, config_data: dict[str, Any]) -> int:
        raw_value = config_data.get("xpl_analysis_max_attempts")
        if raw_value is None:
            raw_value = get_config_manager().get_config("xpl_analysis_max_attempts", 3)
        try:
            return max(1, int(raw_value))
        except (TypeError, ValueError):
            return 3

    def build_async_result(
        self,
        rows: list[dict[str, Any]],
        *,
        source_columns: dict[str, str] | None = None,
        config_data: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        snapshot: dict[str, Any] = {
            "rows": rows,
            "source_columns": source_columns or {},
            RETURN_ANALYSIS_ASYNC_KEY: True,
            "max_attempts": self.max_attempts(config_data or {}),
        }
        return {
            "analysis_status": "pending",
            "flat_result": None,
            "analyze_result": None,
            RETURN_SERIES_SNAPSHOT_KEY: snapshot,
        }

    def build_sync_result(
        self,
        xpl,
        rows: list[dict[str, Any]],
        *,
        source_columns: dict[str, str] | None = None,
    ) -> tuple[dict[str, Any], float]:
        started = time.perf_counter()
        flat_result, analyze_result = xpl.get_return_analysis_v1(rows)
        elapsed = time.perf_counter() - started
        return {
            "analysis_status": "completed",
            "flat_result": flat_result,
            "analyze_result": analyze_result,
            RETURN_SERIES_SNAPSHOT_KEY: {
                "rows": rows,
                "source_columns": source_columns or {},
            },
        }, elapsed

    def persist_snapshot_for_task_result(
        self,
        *,
        task_id: str,
        task_result,
        snapshot: dict[str, Any],
        step_index: int,
    ) -> None:
        rows = snapshot.get("rows") or []
        if not rows:
            return

        return_series = self.return_series_service.create_for_task(
            task_id=task_id,
            rows=rows,
            source_columns=snapshot.get("source_columns"),
            step_index=step_index,
        )
        from app.extensions import db

        db.session.add(return_series)
        db.session.flush()
        task_result.return_series_id = return_series.id

        if snapshot.get(RETURN_ANALYSIS_ASYNC_KEY):
            self.xpl_analysis_job_service.create_pending_job(
                task_id=task_id,
                task_result_id=task_result.id,
                return_series_id=return_series.id,
                max_attempts=snapshot.get("max_attempts") or 3,
                commit=False,
            )

    def summarize_for_log(
        self,
        *,
        rows: int,
        read_elapsed: float | None = None,
        xpl_elapsed: float | None = None,
        flat_result: dict[str, Any] | None = None,
        analyze_result: dict[str, Any] | None = None,
        analysis_status: str | None = None,
    ) -> str:
        summary: dict[str, Any] = {"rows": rows}
        if read_elapsed is not None:
            summary["read"] = self._format_elapsed(read_elapsed)
        if xpl_elapsed is not None:
            summary["xpl"] = self._format_elapsed(xpl_elapsed)
        if analyze_result is not None:
            summary["analyze_result_keys"] = len(analyze_result) if isinstance(analyze_result, dict) else 0
        if analysis_status:
            summary["analysis_status"] = analysis_status
        if isinstance(flat_result, dict):
            summary["flat_result"] = {
                key: flat_result.get(key)
                for key in [
                    "index_annualized_return",
                    "start_annualized_return",
                    "annualized_return_diff",
                    "index_sharpe_ratio",
                    "start_sharpe_ratio",
                    "start_drawdown",
                ]
                if key in flat_result
            }
        return json.dumps(summary, ensure_ascii=False, default=str)

    @staticmethod
    def _format_elapsed(seconds: float) -> str:
        return f"{seconds:.3f}s"

    @staticmethod
    def _to_bool(value: Any) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return bool(value)
        if isinstance(value, str):
            return value.strip().lower() in {"1", "true", "yes", "on", "y"}
        return False

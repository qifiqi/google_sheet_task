from __future__ import annotations

import socket
import time
import json
from concurrent.futures import ProcessPoolExecutor, as_completed,ThreadPoolExecutor
from dataclasses import dataclass
from os import getpid
from typing import Any, Callable

from app.extensions import db
from app.models import Task, TaskLog, TaskResult, TaskResultReturn, XplAnalysisJob
from app.services.return_series_service import ReturnSeriesService
from app.services.xpl_analysis_job_service import XplAnalysisJobService
from app.utils.logger import get_logger


logger = get_logger(__name__)


def run_xpl_analysis(return_rows: list[dict[str, Any]]) -> tuple[dict[str, Any], dict[str, Any]]:
    from app.services.xpl_service import xpl_analyzer

    return xpl_analyzer.get_return_analysis_v1(return_rows)


@dataclass
class XplWorkerRunResult:
    claimed: int = 0
    completed: int = 0
    failed: int = 0


class XplAnalysisWorker:
    """Database-backed worker for async XPL analysis jobs."""

    def __init__(
        self,
        *,
        worker_id: str | None = None,
        job_service: XplAnalysisJobService | None = None,
        return_series_service: ReturnSeriesService | None = None,
        process_count: int = 6,
        claim_batch_size: int = 12,
        stale_after_seconds: int = 300,
        poll_interval_seconds: float = 2.0,
        xpl_runner: Callable[[list[dict[str, Any]]], tuple[dict[str, Any], dict[str, Any]]] = run_xpl_analysis,
    ):
        self.worker_id = worker_id or f"{socket.gethostname()}-{getpid()}"
        self.job_service = job_service or XplAnalysisJobService()
        self.return_series_service = return_series_service or ReturnSeriesService()
        self.process_count = max(1, int(process_count or 1))
        self.claim_batch_size = max(1, int(claim_batch_size or 1))
        self.stale_after_seconds = max(1, int(stale_after_seconds or 300))
        self.poll_interval_seconds = max(0.1, float(poll_interval_seconds or 2.0))
        self.xpl_runner = xpl_runner
        self.executor = ThreadPoolExecutor(max_workers=process_count)
        # self.executor = ProcessPoolExecutor(max_workers=process_count)

    def run_forever(self, stop_event=None) -> None:
        logger.info("XPL异步分析worker启动: worker_id=%s", self.worker_id)
        while not (stop_event and stop_event.is_set()):
            result = self.run_once()
            if result.claimed == 0:
                time.sleep(self.poll_interval_seconds)

    def run_once(self) -> XplWorkerRunResult:
        jobs = self.job_service.claim_jobs(
            self.worker_id,
            limit=self.claim_batch_size,
            stale_after_seconds=self.stale_after_seconds,
        )
        if not jobs:
            return XplWorkerRunResult()

        prepared_jobs = []
        result = XplWorkerRunResult(claimed=len(jobs))
        for job in jobs:
            rows = self._load_return_rows(job)
            if not rows:
                self.job_service.mark_failed(job.id, "return series is empty")
                result.failed += 1
                continue
            prepared_jobs.append((job.id, rows))

        if not prepared_jobs:
            return result

        future_to_job_id = {
            self.executor.submit(self.xpl_runner, rows): (job_id, time.perf_counter())
            for job_id, rows in prepared_jobs
        }
        for future in as_completed(future_to_job_id):
            job_id, started = future_to_job_id[future]
            try:
                flat_result, analyze_result = future.result()
                elapsed = time.perf_counter() - started
                self.job_service.mark_completed(job_id, flat_result, analyze_result, elapsed)
                self._push_stock_param_result(job_id)
                result.completed += 1
            except Exception as exc:
                self.job_service.mark_failed(job_id, exc)
                result.failed += 1

        return result

    def run_job_inline(self, job_id: int) -> bool:
        """Process one already-claimed job without spawning a process pool."""
        job = db.session.get(XplAnalysisJob, job_id)
        if not job:
            return False
        started = time.perf_counter()
        try:
            rows = self._load_return_rows(job)
            if not rows:
                raise ValueError("return series is empty")
            flat_result, analyze_result = self.xpl_runner(rows)
            self.job_service.mark_completed(
                job.id,
                flat_result,
                analyze_result,
                time.perf_counter() - started,
            )
            self._push_stock_param_result(job.id)
            return True
        except Exception as exc:
            self.job_service.mark_failed(job.id, exc)
            return False

    def _load_return_rows(self, job: XplAnalysisJob) -> list[dict[str, Any]]:
        return_series = db.session.get(TaskResultReturn, job.return_series_id)
        if not return_series:
            return []
        return self.return_series_service.load_rows(return_series.returns_json)

    def _push_stock_param_result(self, job_id: int) -> None:
        try:
            job = db.session.get(XplAnalysisJob, job_id)
            if not job:
                return
            task = db.session.get(Task, job.task_id)
            task_result = db.session.get(TaskResult, job.task_result_id)
            if not task or not task_result:
                return

            config_data = self._parse_json(task.config, {})
            result_payload = self._parse_json(task_result.result, {})
            parameters = self._parse_json(task_result.parameters, [])
            if isinstance(parameters, list) and parameters:
                config_data = dict(config_data)
                config_data.setdefault("kline", parameters[-1])

            from app.services.google_sheet_service import GoogleSheetService

            service = GoogleSheetService(config_data, task.id)
            payload = service._build_stock_param_result_payload(
                task_name=task.name,
                task_index=task_result.step_index,
                config_data=config_data,
                result=result_payload,
            )
            service.send_stock_param_result_data(payload)
            db.session.add(TaskLog(
                task_id=task.id,
                level="info",
                message=f"XPL异步分析完成后已推送StockParamResult: result_id={task_result.id}",
            ))
            db.session.commit()
        except Exception as exc:
            db.session.rollback()
            logger.warning("XPL异步分析完成后推送StockParamResult失败: job_id=%s, error=%s", job_id, exc)

    def _parse_json(self, raw: str | None, default: Any) -> Any:
        if not raw:
            return default
        try:
            parsed = json.loads(raw)
        except (TypeError, ValueError):
            return default
        return parsed

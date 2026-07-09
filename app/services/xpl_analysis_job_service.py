import json
import math
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models import TaskLog, TaskResult, XplAnalysisJob
from app.utils.logger import get_logger


logger = get_logger(__name__)


class XplAnalysisJobStatus:
    PENDING = "pending"
    RUNNING = "running"
    RETRYING = "retrying"
    COMPLETED = "completed"
    ERROR = "error"
    CANCELLED = "cancelled"


TERMINAL_STATUSES = {
    XplAnalysisJobStatus.COMPLETED,
    XplAnalysisJobStatus.ERROR,
    XplAnalysisJobStatus.CANCELLED,
}

CLAIMABLE_STATUSES = {
    XplAnalysisJobStatus.PENDING,
    XplAnalysisJobStatus.RETRYING,
}


class XplAnalysisJobService:
    """Persistence and state transitions for async XPL analysis jobs."""

    def create_pending_job(
        self,
        task_id: str,
        task_result_id: int,
        return_series_id: int,
        *,
        max_attempts: int = 3,
        commit: bool = True,
    ) -> XplAnalysisJob:
        existing = XplAnalysisJob.query.filter_by(task_result_id=task_result_id).first()
        if existing:
            return existing

        job = XplAnalysisJob(
            task_id=task_id,
            task_result_id=task_result_id,
            return_series_id=return_series_id,
            status=XplAnalysisJobStatus.PENDING,
            attempts=0,
            max_attempts=max(1, int(max_attempts or 3)),
        )
        db.session.add(job)
        try:
            if commit:
                db.session.commit()
            else:
                db.session.flush()
        except IntegrityError:
            db.session.rollback()
            existing = XplAnalysisJob.query.filter_by(task_result_id=task_result_id).first()
            if existing:
                return existing
            raise
        return job

    def recover_stale_running(self, stale_after_seconds: int = 300) -> int:
        cutoff = datetime.now() - timedelta(seconds=max(1, int(stale_after_seconds or 300)))
        count = (
            XplAnalysisJob.query
            .filter(
                XplAnalysisJob.status == XplAnalysisJobStatus.RUNNING,
                XplAnalysisJob.locked_at < cutoff,
            )
            .update(
                {
                    "status": XplAnalysisJobStatus.RETRYING,
                    "locked_by": None,
                    "locked_at": None,
                    "updated_at": datetime.now(),
                    "error_message": "running job stale, recovered for retry",
                },
                synchronize_session=False,
            )
        )
        if count:
            db.session.commit()
        return count

    def claim_jobs(
        self,
        worker_id: str,
        limit: int = 4,
        stale_after_seconds: int = 300,
    ) -> list[XplAnalysisJob]:
        self.recover_stale_running(stale_after_seconds)
        limit = max(1, int(limit or 1))
        candidates = (
            XplAnalysisJob.query
            .filter(XplAnalysisJob.status.in_(CLAIMABLE_STATUSES))
            .order_by(XplAnalysisJob.created_at.asc(), XplAnalysisJob.id.asc())
            .limit(limit)
            .all()
        )

        claimed: list[XplAnalysisJob] = []
        for candidate in candidates:
            now = datetime.now()
            updated = (
                XplAnalysisJob.query
                .filter(
                    XplAnalysisJob.id == candidate.id,
                    XplAnalysisJob.status.in_(CLAIMABLE_STATUSES),
                )
                .update(
                    {
                        "status": XplAnalysisJobStatus.RUNNING,
                        "locked_by": worker_id,
                        "locked_at": now,
                        "started_at": now,
                        "updated_at": now,
                        "error_message": None,
                    },
                    synchronize_session=False,
                )
            )
            if updated:
                claimed_job = db.session.get(XplAnalysisJob, candidate.id)
                if claimed_job:
                    claimed.append(claimed_job)
        if claimed:
            db.session.commit()
        return claimed

    def mark_completed(
        self,
        job_id: int,
        flat_result: dict[str, Any],
        analyze_result: dict[str, Any],
        elapsed_seconds: float | None = None,
    ) -> XplAnalysisJob | None:
        job = db.session.get(XplAnalysisJob, job_id)
        if not job or job.status == XplAnalysisJobStatus.CANCELLED:
            return job

        task_result = db.session.get(TaskResult, job.task_result_id)
        if not task_result:
            job.status = XplAnalysisJobStatus.ERROR
            job.error_message = "task result not found"
            job.finished_at = datetime.now()
            db.session.commit()
            return job

        payload = self._parse_result_payload(task_result.result)
        payload.update({
            "analysis_status": XplAnalysisJobStatus.COMPLETED,
            "flat_result": flat_result or {},
            "analyze_result": analyze_result or {},
        })
        if elapsed_seconds is not None:
            payload["analysis_elapsed_seconds"] = float(elapsed_seconds)

        task_result.result = json.dumps(
            self._sanitize_json_value(payload),
            ensure_ascii=False,
            allow_nan=False,
            default=str,
        )
        now = datetime.now()
        job.status = XplAnalysisJobStatus.COMPLETED
        job.finished_at = now
        job.locked_at = None
        job.compute_elapsed_seconds = float(elapsed_seconds) if elapsed_seconds is not None else None
        job.push_status = job.push_status or "pending"
        job.error_message = None
        job.updated_at = now
        db.session.add(TaskLog(
            task_id=job.task_id,
            level="info",
            message=(
                f"XPL异步分析完成: result_id={job.task_result_id}, "
                f"elapsed={elapsed_seconds:.3f}s" if elapsed_seconds is not None
                else f"XPL异步分析完成: result_id={job.task_result_id}"
            ),
        ))
        db.session.commit()
        self._refresh_summary_index(job)
        return job

    def mark_failed(self, job_id: int, error: Exception | str) -> XplAnalysisJob | None:
        job = db.session.get(XplAnalysisJob, job_id)
        if not job or job.status == XplAnalysisJobStatus.CANCELLED:
            return job

        error_message = self._format_error_message(error)
        attempts = int(job.attempts or 0) + 1
        final_error = attempts >= int(job.max_attempts or 1)
        status = XplAnalysisJobStatus.ERROR if final_error else XplAnalysisJobStatus.RETRYING

        job.attempts = attempts
        job.status = status
        job.locked_by = None
        job.locked_at = None
        job.finished_at = datetime.now() if final_error else None
        job.error_message = error_message
        job.updated_at = datetime.now()

        task_result = db.session.get(TaskResult, job.task_result_id)
        if task_result:
            payload = self._parse_result_payload(task_result.result)
            payload["analysis_status"] = status
            payload["analysis_error"] = error_message
            task_result.result = json.dumps(
                self._sanitize_json_value(payload),
                ensure_ascii=False,
                allow_nan=False,
                default=str,
            )
        db.session.add(TaskLog(
            task_id=job.task_id,
            level="warning" if not final_error else "error",
            message=(
                f"XPL异步分析失败: result_id={job.task_result_id}, "
                f"attempts={attempts}/{job.max_attempts}, status={status}, error={error_message}"
            ),
        ))
        db.session.commit()
        return job

    def cancel_jobs_for_task(self, task_id: str, from_step_index: int | None = None) -> int:
        query = XplAnalysisJob.query.filter(
            XplAnalysisJob.task_id == task_id,
            ~XplAnalysisJob.status.in_(TERMINAL_STATUSES),
        )
        if from_step_index is not None:
            result_ids = (
                db.session.query(TaskResult.id)
                .filter(
                    TaskResult.task_id == task_id,
                    TaskResult.step_index >= from_step_index,
                )
            )
            query = query.filter(XplAnalysisJob.task_result_id.in_(result_ids))

        count = query.update(
            {
                "status": XplAnalysisJobStatus.CANCELLED,
                "locked_by": None,
                "locked_at": None,
                "finished_at": datetime.now(),
                "updated_at": datetime.now(),
            },
            synchronize_session=False,
        )
        if count:
            db.session.commit()
        return count

    def retry_job(self, job_id: int) -> XplAnalysisJob | None:
        job = db.session.get(XplAnalysisJob, job_id)
        if not job:
            return None
        if job.status not in {XplAnalysisJobStatus.ERROR, XplAnalysisJobStatus.RETRYING}:
            return job
        job.status = XplAnalysisJobStatus.PENDING
        job.locked_by = None
        job.locked_at = None
        job.started_at = None
        job.finished_at = None
        job.load_elapsed_seconds = None
        job.compute_elapsed_seconds = None
        job.save_elapsed_seconds = None
        job.push_status = "pending"
        job.pushed_at = None
        job.push_error_message = None
        job.error_message = None
        job.updated_at = datetime.now()
        task_result = db.session.get(TaskResult, job.task_result_id)
        if task_result:
            payload = self._parse_result_payload(task_result.result)
            payload["analysis_status"] = XplAnalysisJobStatus.PENDING
            payload.pop("analysis_error", None)
            task_result.result = json.dumps(
                self._sanitize_json_value(payload),
                ensure_ascii=False,
                allow_nan=False,
                default=str,
            )
        db.session.commit()
        return job

    def retry_failed_for_task(self, task_id: str) -> int:
        jobs = XplAnalysisJob.query.filter(
            XplAnalysisJob.task_id == task_id,
            XplAnalysisJob.status == XplAnalysisJobStatus.ERROR,
        ).all()
        count = 0
        for job in jobs:
            job.status = XplAnalysisJobStatus.PENDING
            job.locked_by = None
            job.locked_at = None
            job.started_at = None
            job.finished_at = None
            job.load_elapsed_seconds = None
            job.compute_elapsed_seconds = None
            job.save_elapsed_seconds = None
            job.push_status = "pending"
            job.pushed_at = None
            job.push_error_message = None
            job.error_message = None
            job.updated_at = datetime.now()
            task_result = db.session.get(TaskResult, job.task_result_id)
            if task_result:
                payload = self._parse_result_payload(task_result.result)
                payload["analysis_status"] = XplAnalysisJobStatus.PENDING
                payload.pop("analysis_error", None)
                task_result.result = json.dumps(
                    self._sanitize_json_value(payload),
                    ensure_ascii=False,
                    allow_nan=False,
                    default=str,
                )
            count += 1
        if count:
            db.session.commit()
        return count

    def stats(self, task_id: str | None = None) -> dict[str, Any]:
        query = db.session.query(XplAnalysisJob.status, func.count(XplAnalysisJob.id))
        if task_id:
            query = query.filter(XplAnalysisJob.task_id == task_id)
        stats = {status: int(count) for status, count in query.group_by(XplAnalysisJob.status).all()}

        meta_query = XplAnalysisJob.query
        if task_id:
            meta_query = meta_query.filter(XplAnalysisJob.task_id == task_id)

        oldest_pending = (
            meta_query
            .filter(XplAnalysisJob.status.in_(CLAIMABLE_STATUSES))
            .order_by(XplAnalysisJob.created_at.asc(), XplAnalysisJob.id.asc())
            .first()
        )
        oldest_pending_seconds = None
        if oldest_pending and oldest_pending.created_at:
            oldest_pending_seconds = max(0, int((datetime.now() - oldest_pending.created_at).total_seconds()))

        running_workers_query = db.session.query(func.count(func.distinct(XplAnalysisJob.locked_by))).filter(
            XplAnalysisJob.status == XplAnalysisJobStatus.RUNNING,
            XplAnalysisJob.locked_by.isnot(None),
        )
        if task_id:
            running_workers_query = running_workers_query.filter(XplAnalysisJob.task_id == task_id)

        avg_query = db.session.query(
            func.avg(XplAnalysisJob.load_elapsed_seconds),
            func.avg(XplAnalysisJob.compute_elapsed_seconds),
            func.avg(XplAnalysisJob.save_elapsed_seconds),
            func.max(XplAnalysisJob.finished_at),
        ).filter(XplAnalysisJob.status == XplAnalysisJobStatus.COMPLETED)
        if task_id:
            avg_query = avg_query.filter(XplAnalysisJob.task_id == task_id)
        avg_load, avg_compute, avg_save, latest_finished_at = avg_query.first() or (None, None, None, None)

        stats["_meta"] = {
            "oldest_pending_seconds": oldest_pending_seconds,
            "running_worker_count": int(running_workers_query.scalar() or 0),
            "avg_load_elapsed_seconds": float(avg_load) if avg_load is not None else None,
            "avg_compute_elapsed_seconds": float(avg_compute) if avg_compute is not None else None,
            "avg_save_elapsed_seconds": float(avg_save) if avg_save is not None else None,
            "latest_finished_at": latest_finished_at.isoformat() if latest_finished_at else None,
        }
        return stats

    def has_unfinished_task_jobs(self, task_id: str) -> bool:
        return (
            XplAnalysisJob.query
            .filter(
                XplAnalysisJob.task_id == task_id,
                ~XplAnalysisJob.status.in_(TERMINAL_STATUSES),
            )
            .first()
            is not None
        )

    def _refresh_summary_index(self, job: XplAnalysisJob) -> None:
        try:
            from app.services.model_summary_service import model_summary_service

            model_summary_service.upsert_task_result(job.task_result_id)
            if not self.has_unfinished_task_jobs(job.task_id):
                model_summary_service.upsert_task(job.task_id)
        except Exception as exc:
            logger.warning(
                "XPL异步分析完成后刷新汇总索引失败: job_id=%s, task_id=%s, error=%s",
                job.id,
                job.task_id,
                exc,
            )

    def _parse_result_payload(self, raw: str | None) -> dict[str, Any]:
        if not raw:
            return {}
        try:
            payload = json.loads(raw)
        except (TypeError, ValueError):
            return {}
        return payload if isinstance(payload, dict) else {}

    def _format_error_message(self, error: Exception | str) -> str:
        text = str(error)
        if len(text) > 2000:
            text = text[:1997] + "..."
        return text

    def _sanitize_json_value(self, value: Any) -> Any:
        if isinstance(value, dict):
            return {str(key): self._sanitize_json_value(item) for key, item in value.items()}
        if isinstance(value, list):
            return [self._sanitize_json_value(item) for item in value]
        if isinstance(value, tuple):
            return [self._sanitize_json_value(item) for item in value]
        if isinstance(value, float) and not math.isfinite(value):
            return None
        return value

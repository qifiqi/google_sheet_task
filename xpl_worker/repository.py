from __future__ import annotations

import json
import logging
import math
import time
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Engine

from xpl_worker.models import XplJob


logger = logging.getLogger(__name__)


class XplJobStatus:
    PENDING = "pending"
    RUNNING = "running"
    RETRYING = "retrying"
    COMPLETED = "completed"
    ERROR = "error"


class XplJobRepository:
    def __init__(self, engine: Engine):
        self.engine = engine

    def recover_stale_running(self, stale_after_seconds: int) -> int:
        with self.engine.begin() as conn:
            retrying = conn.execute(
                text(
                    """
                    UPDATE xpl_analysis_jobs
                    SET status = 'retrying',
                        locked_by = NULL,
                        locked_at = NULL,
                        error_message = 'running job stale, recovered for retry',
                        updated_at = NOW()
                    WHERE status = 'running'
                      AND locked_at < NOW() - (:stale_after_seconds * INTERVAL '1 second')
                      AND attempts < max_attempts
                    """
                ),
                {"stale_after_seconds": int(stale_after_seconds)},
            ).rowcount or 0
            errored = conn.execute(
                text(
                    """
                    UPDATE xpl_analysis_jobs
                    SET status = 'error',
                        locked_by = NULL,
                        locked_at = NULL,
                        finished_at = NOW(),
                        error_message = 'running job stale and max attempts reached',
                        updated_at = NOW()
                    WHERE status = 'running'
                      AND locked_at < NOW() - (:stale_after_seconds * INTERVAL '1 second')
                      AND attempts >= max_attempts
                    """
                ),
                {"stale_after_seconds": int(stale_after_seconds)},
            ).rowcount or 0
        return int(retrying + errored)

    def claim_jobs(self, worker_id: str, limit: int, stale_after_seconds: int) -> list[XplJob]:
        self.recover_stale_running(stale_after_seconds)
        with self.engine.begin() as conn:
            rows = conn.execute(
                text(
                    """
                    -- 原子领取 job，多个 worker 进程并发消费时不会重复处理同一条记录。
                    WITH picked AS (
                        SELECT id
                        FROM xpl_analysis_jobs
                        WHERE status IN ('pending', 'retrying')
                          AND attempts < max_attempts
                        ORDER BY created_at ASC, id ASC
                        FOR UPDATE SKIP LOCKED
                        LIMIT :limit
                    )
                    UPDATE xpl_analysis_jobs AS j
                    SET status = 'running',
                        attempts = attempts + 1,
                        locked_by = :worker_id,
                        locked_at = NOW(),
                        started_at = COALESCE(started_at, NOW()),
                        updated_at = NOW(),
                        error_message = NULL
                    FROM picked
                    WHERE j.id = picked.id
                    RETURNING
                        j.id,
                        j.task_id,
                        j.task_result_id,
                        j.return_series_id,
                        j.attempts,
                        j.max_attempts
                    """
                ),
                {"worker_id": worker_id, "limit": int(limit)},
            ).mappings().all()
        jobs = [
            XplJob(
                id=int(row["id"]),
                task_id=str(row["task_id"]),
                task_result_id=int(row["task_result_id"]),
                return_series_id=int(row["return_series_id"]),
                attempts=int(row["attempts"] or 0),
                max_attempts=int(row["max_attempts"] or 1),
            )
            for row in rows
        ]
        if jobs:
            logger.info("已领取 XPL jobs: worker_id=%s, job_ids=%s", worker_id, [job.id for job in jobs])
        return jobs

    def get_return_series_json(self, return_series_id: int) -> str | None:
        with self.engine.connect() as conn:
            return conn.execute(
                text(
                    """
                    SELECT returns_json
                    FROM task_results_return
                    WHERE id = :return_series_id
                    """
                ),
                {"return_series_id": int(return_series_id)},
            ).scalar_one_or_none()

    def get_return_series_json_map(self, return_series_ids: list[int]) -> dict[int, str | None]:
        ids = sorted({int(item) for item in return_series_ids if item is not None})
        if not ids:
            return {}
        with self.engine.connect() as conn:
            rows = conn.execute(
                text(
                    """
                    SELECT id, returns_json
                    FROM task_results_return
                    WHERE id = ANY(:return_series_ids)
                    """
                ),
                {"return_series_ids": ids},
            ).mappings().all()
        found = {int(row["id"]): row["returns_json"] for row in rows}
        missing_ids = [item for item in ids if item not in found]
        if missing_ids:
            logger.warning("收益序列记录不存在: ids=%s", missing_ids)
        return found

    def mark_completed(
        self,
        job_id: int,
        worker_id: str,
        flat_result: dict[str, Any],
        analyze_result: dict[str, Any],
        compute_elapsed_seconds: float | None,
        load_elapsed_seconds: float | None,
    ) -> bool:
        save_started = time.perf_counter()
        with self.engine.begin() as conn:
            job = conn.execute(
                text(
                    """
                    SELECT id, task_id, task_result_id
                    FROM xpl_analysis_jobs
                    WHERE id = :job_id
                      AND status = 'running'
                      AND locked_by = :worker_id
                    """
                ),
                {"job_id": int(job_id), "worker_id": worker_id},
            ).mappings().first()
            if not job:
                logger.warning("跳过完成写回，当前 worker 未持有 job 锁: job_id=%s, worker_id=%s", job_id, worker_id)
                return False

            raw_result = conn.execute(
                text("SELECT result FROM task_results WHERE id = :task_result_id"),
                {"task_result_id": int(job["task_result_id"])},
            ).scalar_one_or_none()
            payload = self._parse_json_object(raw_result)
            payload.update({
                "analysis_status": XplJobStatus.COMPLETED,
                "flat_result": flat_result or {},
                "analyze_result": analyze_result or {},
            })
            if compute_elapsed_seconds is not None:
                payload["analysis_elapsed_seconds"] = float(compute_elapsed_seconds)
                payload["analysis_compute_elapsed_seconds"] = float(compute_elapsed_seconds)
            if load_elapsed_seconds is not None:
                payload["analysis_load_elapsed_seconds"] = float(load_elapsed_seconds)

            save_elapsed_seconds = 0.0
            conn.execute(
                text(
                    """
                    UPDATE task_results
                    SET result = :result
                    WHERE id = :task_result_id
                    """
                ),
                {
                    "task_result_id": int(job["task_result_id"]),
                    "result": self._dumps_json(payload),
                },
            )
            save_elapsed_seconds = time.perf_counter() - save_started
            payload["analysis_save_elapsed_seconds"] = float(save_elapsed_seconds)
            conn.execute(
                text(
                    """
                    UPDATE task_results
                    SET result = :result
                    WHERE id = :task_result_id
                    """
                ),
                {
                    "task_result_id": int(job["task_result_id"]),
                    "result": self._dumps_json(payload),
                },
            )
            conn.execute(
                text(
                    """
                    UPDATE xpl_analysis_jobs
                    SET status = 'completed',
                        locked_by = NULL,
                        locked_at = NULL,
                        finished_at = NOW(),
                        load_elapsed_seconds = :load_elapsed_seconds,
                        compute_elapsed_seconds = :compute_elapsed_seconds,
                        save_elapsed_seconds = :save_elapsed_seconds,
                        push_status = COALESCE(push_status, 'pending'),
                        error_message = NULL,
                        updated_at = NOW()
                    WHERE id = :job_id
                    """
                ),
                {
                    "job_id": int(job_id),
                    "load_elapsed_seconds": load_elapsed_seconds,
                    "compute_elapsed_seconds": compute_elapsed_seconds,
                    "save_elapsed_seconds": save_elapsed_seconds,
                },
            )
            self._insert_task_log(
                conn,
                str(job["task_id"]),
                "info",
                (
                    f"XPL异步分析完成: result_id={job['task_result_id']}, "
                    f"load={load_elapsed_seconds:.3f}s, xpl={compute_elapsed_seconds:.3f}s, "
                    f"save={save_elapsed_seconds:.3f}s, worker={worker_id}"
                    if load_elapsed_seconds is not None and compute_elapsed_seconds is not None
                    else f"XPL异步分析完成: result_id={job['task_result_id']}, worker={worker_id}"
                ),
            )
        logger.info(
            "XPL job 已完成: job_id=%s, task_result_id=%s, load=%s, xpl=%s, save=%.3fs",
            job_id,
            job["task_result_id"],
            f"{load_elapsed_seconds:.3f}s" if load_elapsed_seconds is not None else "-",
            f"{compute_elapsed_seconds:.3f}s" if compute_elapsed_seconds is not None else "-",
            save_elapsed_seconds,
        )
        return True

    def mark_failed(
        self,
        job: XplJob,
        worker_id: str,
        error: Exception | str,
        load_elapsed_seconds: float | None = None,
        compute_elapsed_seconds: float | None = None,
    ) -> bool:
        error_message = self._format_error_message(error)
        final_error = int(job.attempts or 0) >= int(job.max_attempts or 1)
        status = XplJobStatus.ERROR if final_error else XplJobStatus.RETRYING
        with self.engine.begin() as conn:
            locked_job = conn.execute(
                text(
                    """
                    SELECT id, task_id, task_result_id, attempts, max_attempts
                    FROM xpl_analysis_jobs
                    WHERE id = :job_id
                      AND status = 'running'
                      AND locked_by = :worker_id
                    """
                ),
                {"job_id": int(job.id), "worker_id": worker_id},
            ).mappings().first()
            if not locked_job:
                logger.warning("跳过失败写回，当前 worker 未持有 job 锁: job_id=%s, worker_id=%s", job.id, worker_id)
                return False

            raw_result = conn.execute(
                text("SELECT result FROM task_results WHERE id = :task_result_id"),
                {"task_result_id": int(locked_job["task_result_id"])},
            ).scalar_one_or_none()
            payload = self._parse_json_object(raw_result)
            payload["analysis_status"] = status
            payload["analysis_error"] = error_message
            if load_elapsed_seconds is not None:
                payload["analysis_load_elapsed_seconds"] = float(load_elapsed_seconds)
            if compute_elapsed_seconds is not None:
                payload["analysis_compute_elapsed_seconds"] = float(compute_elapsed_seconds)
            conn.execute(
                text(
                    """
                    UPDATE task_results
                    SET result = :result
                    WHERE id = :task_result_id
                    """
                ),
                {
                    "task_result_id": int(locked_job["task_result_id"]),
                    "result": self._dumps_json(payload),
                },
            )
            conn.execute(
                text(
                    """
                    UPDATE xpl_analysis_jobs
                    SET status = :status,
                        locked_by = NULL,
                        locked_at = NULL,
                        finished_at = CASE WHEN :final_error THEN NOW() ELSE NULL END,
                        load_elapsed_seconds = COALESCE(:load_elapsed_seconds, load_elapsed_seconds),
                        compute_elapsed_seconds = COALESCE(:compute_elapsed_seconds, compute_elapsed_seconds),
                        error_message = :error_message,
                        updated_at = NOW()
                    WHERE id = :job_id
                    """
                ),
                {
                    "job_id": int(job.id),
                    "status": status,
                    "final_error": final_error,
                    "load_elapsed_seconds": load_elapsed_seconds,
                    "compute_elapsed_seconds": compute_elapsed_seconds,
                    "error_message": error_message,
                },
            )
            self._insert_task_log(
                conn,
                str(locked_job["task_id"]),
                "error" if final_error else "warning",
                (
                    f"XPL异步分析失败: result_id={locked_job['task_result_id']}, "
                    f"attempts={locked_job['attempts']}/{locked_job['max_attempts']}, "
                    f"status={status}, worker={worker_id}, error={error_message}"
                ),
            )
        logger.warning(
            "XPL job 执行失败: job_id=%s, status=%s, attempts=%s/%s, error=%s",
            job.id,
            status,
            job.attempts,
            job.max_attempts,
            error_message,
        )
        return True

    def _insert_task_log(self, conn, task_id: str, level: str, message: str) -> None:
        conn.execute(
            text(
                """
                INSERT INTO task_logs (task_id, level, message, timestamp)
                VALUES (:task_id, :level, :message, :timestamp)
                """
            ),
            {
                "task_id": task_id,
                "level": level,
                "message": message,
                "timestamp": datetime.now(timezone.utc).replace(tzinfo=None),
            },
        )

    def _parse_json_object(self, raw: str | None) -> dict[str, Any]:
        if not raw:
            return {}
        try:
            payload = json.loads(raw)
        except (TypeError, ValueError):
            return {}
        return payload if isinstance(payload, dict) else {}

    def _dumps_json(self, payload: dict[str, Any]) -> str:
        return json.dumps(
            self._sanitize_json_value(payload),
            ensure_ascii=False,
            allow_nan=False,
            default=str,
        )

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

    def _format_error_message(self, error: Exception | str) -> str:
        text_value = str(error)
        if len(text_value) > 2000:
            return text_value[:1997] + "..."
        return text_value

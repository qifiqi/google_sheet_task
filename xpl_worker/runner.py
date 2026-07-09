from __future__ import annotations

import logging
import socket
import time
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor, as_completed
from os import getpid
from typing import Callable

from xpl_worker.interfaces import XplJobStore
from xpl_worker.models import XplJob, XplWorkerRunResult
from xpl_worker.processor import analyze_return_rows
from xpl_worker.return_series import ReturnSeriesReader


logger = logging.getLogger(__name__)


class XplWorker:
    def __init__(
        self,
        *,
        repository: XplJobStore,
        return_series_reader: ReturnSeriesReader | None = None,
        worker_id: str | None = None,
        executor_type: str = "process",
        concurrency: int = 2,
        batch_size: int = 8,
        stale_after_seconds: int = 300,
        poll_interval_seconds: float = 2.0,
        xpl_runner: Callable = analyze_return_rows,
    ):
        self.repository = repository
        self.return_series_reader = return_series_reader or ReturnSeriesReader()
        self.worker_id = worker_id or f"{socket.gethostname()}-{getpid()}"
        self.executor_type = executor_type if executor_type in {"process", "thread"} else "process"
        self.concurrency = max(1, int(concurrency or 1))
        self.batch_size = max(1, int(batch_size or 1))
        self.stale_after_seconds = max(1, int(stale_after_seconds or 300))
        self.poll_interval_seconds = max(0.1, float(poll_interval_seconds or 2.0))
        self.xpl_runner = xpl_runner
        self._executor = None

    def run_forever(self) -> None:
        logger.info(
            "XPL worker 已启动: worker_id=%s, 执行器=%s, 并发=%s, 批量=%s",
            self.worker_id,
            self.executor_type,
            self.concurrency,
            self.batch_size,
        )
        with self._make_executor() as executor:
            self._executor = executor
            while True:
                result = self.run_once()
                logger.info(
                    "XPL worker 批次完成: 领取=%s, 完成=%s, 失败=%s",
                    result.claimed,
                    result.completed,
                    result.failed,
                )
                if result.claimed == 0:
                    time.sleep(self.poll_interval_seconds)

    def run_once(self) -> XplWorkerRunResult:
        owns_executor = self._executor is None
        if owns_executor:
            with self._make_executor() as executor:
                self._executor = executor
                try:
                    return self._run_once_with_executor()
                finally:
                    self._executor = None
        return self._run_once_with_executor()

    def _run_once_with_executor(self) -> XplWorkerRunResult:
        batch_started = time.perf_counter()
        jobs = self.repository.claim_jobs(
            self.worker_id,
            limit=self.batch_size,
            stale_after_seconds=self.stale_after_seconds,
        )
        claim_elapsed = time.perf_counter() - batch_started
        result = XplWorkerRunResult(claimed=len(jobs))
        if not jobs:
            return result

        # 收益序列是 worker 路径里最大的载荷，领取一批 job 后统一批量读取，
        # 避免每个 job 单独查询一次数据库。
        load_started = time.perf_counter()
        returns_json_map = self.repository.get_return_series_json_map(
            [job.return_series_id for job in jobs]
        )
        prepared_jobs: list[tuple[XplJob, list[dict], float]] = []
        for job in jobs:
            job_load_started = time.perf_counter()
            try:
                returns_json = returns_json_map.get(job.return_series_id)
                rows = self.return_series_reader.load_rows(returns_json)
                if not rows:
                    raise ValueError("收益序列为空")
                job_load_elapsed = time.perf_counter() - job_load_started
                prepared_jobs.append((job, rows, job_load_elapsed))
                logger.info(
                    "XPL job 数据准备完成: job_id=%s, return_series_id=%s, rows=%s, load=%.3fs",
                    job.id,
                    job.return_series_id,
                    len(rows),
                    job_load_elapsed,
                )
            except Exception as exc:
                self.repository.mark_failed(
                    job,
                    self.worker_id,
                    exc,
                    load_elapsed_seconds=time.perf_counter() - job_load_started,
                )
                result = XplWorkerRunResult(result.claimed, result.completed, result.failed + 1)
        load_elapsed = time.perf_counter() - load_started

        if not prepared_jobs:
            logger.info(
                "XPL worker 批次无可执行数据: 领取=%s, 失败=%s, claim=%.3fs, load=%.3fs",
                result.claimed,
                result.failed,
                claim_elapsed,
                load_elapsed,
            )
            return result

        assert self._executor is not None
        compute_started = time.perf_counter()
        future_to_job = {
            self._executor.submit(self.xpl_runner, rows): (job, time.perf_counter(), load_elapsed)
            for job, rows, load_elapsed in prepared_jobs
        }
        for future in as_completed(future_to_job):
            job, started, load_elapsed = future_to_job[future]
            try:
                flat_result, analyze_result = future.result()
                compute_elapsed = time.perf_counter() - started
                if self.repository.mark_completed(
                    job.id,
                    self.worker_id,
                    flat_result,
                    analyze_result,
                    compute_elapsed,
                    load_elapsed,
                ):
                    result = XplWorkerRunResult(result.claimed, result.completed + 1, result.failed)
                else:
                    logger.warning("跳过完成写回，当前 worker 未持有 job 锁: job_id=%s", job.id)
            except Exception as exc:
                self.repository.mark_failed(
                    job,
                    self.worker_id,
                    exc,
                    load_elapsed_seconds=load_elapsed,
                    compute_elapsed_seconds=time.perf_counter() - started,
                )
                result = XplWorkerRunResult(result.claimed, result.completed, result.failed + 1)
        compute_elapsed = time.perf_counter() - compute_started
        total_elapsed = time.perf_counter() - batch_started
        logger.info(
            (
                "XPL worker 批次耗时: 领取=%s, 准备=%s, 完成=%s, 失败=%s, "
                "claim=%.3fs, load=%.3fs, compute_write=%.3fs, total=%.3fs"
            ),
            result.claimed,
            len(prepared_jobs),
            result.completed,
            result.failed,
            claim_elapsed,
            load_elapsed,
            compute_elapsed,
            total_elapsed,
        )
        return result

    def _make_executor(self):
        if self.executor_type == "thread":
            return ThreadPoolExecutor(max_workers=self.concurrency)
        return ProcessPoolExecutor(max_workers=self.concurrency)

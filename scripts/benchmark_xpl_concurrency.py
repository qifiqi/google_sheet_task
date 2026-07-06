"""Benchmark XPL analysis with serial, thread, and process executors.

Usage:
    python scripts/benchmark_xpl_concurrency.py --jobs 24 --workers 4
    python scripts/benchmark_xpl_concurrency.py --jobs 60 --workers 8 --rows 800

The process-pool result includes Windows spawn and payload serialization cost.
That is useful for local planning because a real external worker also pays
process and IPC overhead unless it reads payloads directly from the database.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import logging
import os
import random
import statistics
import sys
import time
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Callable, Iterable


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

ReturnRows = list[dict[str, Any]]


@dataclass(frozen=True)
class BenchmarkResult:
    mode: str
    jobs: int
    workers: int
    wall_seconds: float
    avg_job_seconds: float
    p95_job_seconds: float
    jobs_per_second: float


def build_return_rows(row_count: int, seed: int) -> ReturnRows:
    rng = random.Random(seed)
    rows: ReturnRows = []
    current = date(2023, 1, 2)

    while len(rows) < row_count:
        if current.weekday() < 5:
            rows.append(
                {
                    "date": current.isoformat(),
                    "index_return": round(rng.uniform(-0.035, 0.035), 6),
                    "start_return": round(rng.uniform(-0.045, 0.045), 6),
                }
            )
        current += timedelta(days=1)

    return rows


def run_xpl_once(rows: ReturnRows) -> float:
    from app.services.xpl_service import XPLAnalyzer

    logging.getLogger("app.services.xpl_service").setLevel(logging.WARNING)
    analyzer = XPLAnalyzer()
    started = time.perf_counter()
    flat_result, analyze_result = analyzer.get_return_analysis_v1(rows)
    if not flat_result or not analyze_result:
        raise RuntimeError("XPL analysis returned empty result")
    return time.perf_counter() - started


def run_serial(payloads: list[ReturnRows]) -> list[float]:
    return [run_xpl_once(rows) for rows in payloads]


def run_executor(
    executor_factory: Callable[[], concurrent.futures.Executor],
    payloads: list[ReturnRows],
) -> list[float]:
    with executor_factory() as executor:
        return list(executor.map(run_xpl_once, payloads))


def summarize(mode: str, jobs: int, workers: int, wall_seconds: float, job_seconds: list[float]) -> BenchmarkResult:
    p95 = sorted(job_seconds)[int(len(job_seconds) * 0.95) - 1] if job_seconds else 0.0
    return BenchmarkResult(
        mode=mode,
        jobs=jobs,
        workers=workers,
        wall_seconds=wall_seconds,
        avg_job_seconds=statistics.mean(job_seconds) if job_seconds else 0.0,
        p95_job_seconds=p95,
        jobs_per_second=jobs / wall_seconds if wall_seconds > 0 else 0.0,
    )


def measure(mode: str, workers: int, payloads: list[ReturnRows]) -> BenchmarkResult:
    started = time.perf_counter()
    if mode == "serial":
        job_seconds = run_serial(payloads)
        effective_workers = 1
    elif mode == "threads":
        job_seconds = run_executor(
            lambda: concurrent.futures.ThreadPoolExecutor(max_workers=workers),
            payloads,
        )
        effective_workers = workers
    elif mode == "processes":
        job_seconds = run_executor(
            lambda: concurrent.futures.ProcessPoolExecutor(max_workers=workers),
            payloads,
        )
        effective_workers = workers
    else:
        raise ValueError(f"unknown mode: {mode}")
    wall_seconds = time.perf_counter() - started
    return summarize(mode, len(payloads), effective_workers, wall_seconds, job_seconds)


def print_results(results: Iterable[BenchmarkResult]) -> None:
    rows = list(results)
    print()
    print("mode       jobs workers wall_s  avg_job_s p95_job_s jobs/s")
    print("---------- ---- ------- ------- --------- --------- ------")
    for item in rows:
        print(
            f"{item.mode:<10} "
            f"{item.jobs:>4} "
            f"{item.workers:>7} "
            f"{item.wall_seconds:>7.2f} "
            f"{item.avg_job_seconds:>9.3f} "
            f"{item.p95_job_seconds:>9.3f} "
            f"{item.jobs_per_second:>6.2f}"
        )

    serial = next((item for item in rows if item.mode == "serial"), None)
    if serial:
        print()
        for item in rows:
            if item.mode == "serial":
                continue
            speedup = serial.wall_seconds / item.wall_seconds if item.wall_seconds else 0.0
            print(f"{item.mode} speedup vs serial: {speedup:.2f}x")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Benchmark XPL analysis concurrency.")
    parser.add_argument("--jobs", type=int, default=24, help="Number of XPL analysis jobs to run.")
    parser.add_argument("--rows", type=int, default=780, help="Rows per generated return series.")
    parser.add_argument("--workers", type=int, default=min(4, os.cpu_count() or 1), help="Thread/process workers.")
    parser.add_argument(
        "--mode",
        choices=("all", "serial", "threads", "processes"),
        default="all",
        help="Benchmark mode.",
    )
    parser.add_argument("--seed", type=int, default=20260703, help="Random seed.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.jobs <= 0:
        raise SystemExit("--jobs must be positive")
    if args.rows <= 0:
        raise SystemExit("--rows must be positive")
    if args.workers <= 0:
        raise SystemExit("--workers must be positive")

    payloads = [
        build_return_rows(args.rows, args.seed + index)
        for index in range(args.jobs)
    ]

    modes = ["serial", "threads", "processes"] if args.mode == "all" else [args.mode]
    results = [measure(mode, args.workers, payloads) for mode in modes]
    print_results(results)


if __name__ == "__main__":
    main()

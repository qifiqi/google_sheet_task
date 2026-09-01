"""Benchmark XPL calculation with threads using tests/test/d.py data.

Usage:
    python scripts/benchmark_xpl_threads_from_d.py --jobs 12 --workers 4
    python scripts/benchmark_xpl_threads_from_d.py --jobs 24 --workers 8 --skip-serial
"""

from __future__ import annotations

import argparse
import concurrent.futures
import importlib.util
import logging
import os
import statistics
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA_FILE = PROJECT_ROOT / "tests" / "test" / "d.py"

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

ReturnRows = list[dict[str, Any]]
_THREAD_LOCAL = threading.local()


@dataclass(frozen=True)
class RunSummary:
    mode: str
    jobs: int
    workers: int
    wall_seconds: float
    avg_job_seconds: float
    p95_job_seconds: float
    min_job_seconds: float
    max_job_seconds: float
    jobs_per_second: float


def load_data_text(data_file: Path) -> str:
    spec = importlib.util.spec_from_file_location("xpl_benchmark_data", data_file)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load data module: {data_file}")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    data = getattr(module, "data", None)
    if not isinstance(data, str) or not data.strip():
        raise RuntimeError(f"{data_file} must define a non-empty string variable named data")
    return data


def get_thread_analyzer():
    analyzer = getattr(_THREAD_LOCAL, "analyzer", None)
    if analyzer is None:
        from app.services.xpl_service import XPLAnalyzer

        logging.getLogger("app.services.xpl_service").setLevel(logging.ERROR)
        analyzer = XPLAnalyzer()
        _THREAD_LOCAL.analyzer = analyzer
    return analyzer


def parse_return_rows(data_text: str) -> ReturnRows:
    analyzer = get_thread_analyzer()
    rows = analyzer._parse_input_data(data_text)
    if not rows:
        raise RuntimeError("Parsed data is empty")
    return rows


def calculate_once(rows: ReturnRows) -> float:
    analyzer = get_thread_analyzer()
    started = time.perf_counter()
    flat_result, analyze_result = analyzer.get_return_analysis_v1(rows)
    elapsed = time.perf_counter() - started
    if not flat_result or not analyze_result:
        raise RuntimeError("XPL analysis returned empty result")
    return elapsed


def summarize(mode: str, jobs: int, workers: int, wall_seconds: float, job_seconds: list[float]) -> RunSummary:
    sorted_seconds = sorted(job_seconds)
    p95_index = min(len(sorted_seconds) - 1, max(0, int(len(sorted_seconds) * 0.95) - 1))
    return RunSummary(
        mode=mode,
        jobs=jobs,
        workers=workers,
        wall_seconds=wall_seconds,
        avg_job_seconds=statistics.mean(job_seconds),
        p95_job_seconds=sorted_seconds[p95_index],
        min_job_seconds=min(job_seconds),
        max_job_seconds=max(job_seconds),
        jobs_per_second=jobs / wall_seconds if wall_seconds > 0 else 0.0,
    )


def run_serial(rows: ReturnRows, jobs: int) -> RunSummary:
    started = time.perf_counter()
    job_seconds = [calculate_once(rows) for _ in range(jobs)]
    return summarize("serial", jobs, 1, time.perf_counter() - started, job_seconds)


def run_threads(rows: ReturnRows, jobs: int, workers: int) -> RunSummary:
    started = time.perf_counter()
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
        futures = [executor.submit(calculate_once, rows) for _ in range(jobs)]
        job_seconds = [future.result() for future in concurrent.futures.as_completed(futures)]
    return summarize("threads", jobs, workers, time.perf_counter() - started, job_seconds)


def print_summaries(summaries: list[RunSummary]) -> None:
    print()
    print("mode     jobs workers wall_s  avg_s   p95_s   min_s   max_s   jobs/s")
    print("-------- ---- ------- ------- ------- ------- ------- ------- ------")
    for item in summaries:
        print(
            f"{item.mode:<8} "
            f"{item.jobs:>4} "
            f"{item.workers:>7} "
            f"{item.wall_seconds:>7.3f} "
            f"{item.avg_job_seconds:>7.3f} "
            f"{item.p95_job_seconds:>7.3f} "
            f"{item.min_job_seconds:>7.3f} "
            f"{item.max_job_seconds:>7.3f} "
            f"{item.jobs_per_second:>6.2f}"
        )

    serial = next((item for item in summaries if item.mode == "serial"), None)
    threaded = next((item for item in summaries if item.mode == "threads"), None)
    if serial and threaded:
        speedup = serial.wall_seconds / threaded.wall_seconds if threaded.wall_seconds else 0.0
        print()
        print(f"threads speedup vs serial: {speedup:.2f}x")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Benchmark XPL thread concurrency with tests/test/d.py data.")
    parser.add_argument("--data-file", type=Path, default=DEFAULT_DATA_FILE, help="Python file containing data string.")
    parser.add_argument("--jobs", type=int, default=12, help="Number of XPL calculations to run.")
    parser.add_argument("--workers", type=int, default=min(4, os.cpu_count() or 1), help="Thread workers.")
    parser.add_argument("--skip-serial", action="store_true", help="Only run the threaded benchmark.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.jobs <= 0:
        raise SystemExit("--jobs must be positive")
    if args.workers <= 0:
        raise SystemExit("--workers must be positive")
    if not args.data_file.exists():
        raise SystemExit(f"data file does not exist: {args.data_file}")

    logging.disable(logging.WARNING)
    logging.getLogger("app.services.xpl_service").setLevel(logging.ERROR)

    data_text = load_data_text(args.data_file)
    rows = parse_return_rows(data_text)
    print(f"data_file: {args.data_file}")
    print(f"rows: {len(rows)}")
    print("warming up XPL once...")
    warmup_seconds = calculate_once(rows)
    print(f"warmup_s: {warmup_seconds:.3f}")

    summaries: list[RunSummary] = []
    if not args.skip_serial:
        summaries.append(run_serial(rows, args.jobs))
    summaries.append(run_threads(rows, args.jobs, args.workers))
    print_summaries(summaries)


if __name__ == "__main__":
    main()

from __future__ import annotations

import argparse
import logging
import sys
from urllib.parse import urlsplit, urlunsplit

from xpl_worker.config import PROJECT_ROOT, WorkerConfig, load_env_files
from xpl_worker.db import create_worker_engine
from xpl_worker.repository import XplJobRepository
from xpl_worker.runner import XplWorker


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="启动独立 XPL 分析 worker。")
    parser.add_argument("--executor", choices=["process", "thread"], default=None)
    parser.add_argument("--concurrency", type=int, default=None)
    parser.add_argument("--processes", type=int, default=None, help="Compatibility alias for --concurrency.")
    parser.add_argument("--batch-size", type=int, default=None)
    parser.add_argument("--poll-interval", type=float, default=None)
    parser.add_argument("--stale-after", type=int, default=None)
    parser.add_argument("--once", action="store_true")
    return parser.parse_args()


def _setup_path() -> None:
    root = str(PROJECT_ROOT)
    if root not in sys.path:
        sys.path.insert(0, root)


def _setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )


def _mask_database_url(database_url: str) -> str:
    try:
        parts = urlsplit(database_url)
        if not parts.password:
            return database_url
        username = parts.username or ""
        host = parts.hostname or ""
        port = f":{parts.port}" if parts.port else ""
        netloc = f"{username}:***@{host}{port}" if username else f"{host}{port}"
        return urlunsplit((parts.scheme, netloc, parts.path, parts.query, parts.fragment))
    except Exception:
        return "<invalid database url>"


def main() -> None:
    _setup_path()
    args = _parse_args()
    load_env_files()
    _setup_logging()

    config = WorkerConfig.from_env()
    if args.executor:
        config = WorkerConfig(
            database_url=config.database_url,
            executor=args.executor,
            concurrency=config.concurrency,
            batch_size=config.batch_size,
            poll_interval_seconds=config.poll_interval_seconds,
            stale_after_seconds=config.stale_after_seconds,
        )
    concurrency = args.concurrency or args.processes or config.concurrency
    batch_size = args.batch_size or config.batch_size
    poll_interval = args.poll_interval if args.poll_interval is not None else config.poll_interval_seconds
    stale_after = args.stale_after or config.stale_after_seconds

    engine = create_worker_engine(config.database_url)
    logging.getLogger(__name__).info(
        "独立 XPL worker 配置: database=%s, 执行器=%s, 并发=%s, 批量=%s, 空闲轮询=%.3fs, 超时恢复=%ss",
        _mask_database_url(config.database_url),
        config.executor,
        concurrency,
        batch_size,
        poll_interval,
        stale_after,
    )
    worker = XplWorker(
        repository=XplJobRepository(engine),
        executor_type=config.executor,
        concurrency=concurrency,
        batch_size=batch_size,
        poll_interval_seconds=poll_interval,
        stale_after_seconds=stale_after,
    )

    if args.once:
        result = worker.run_once()
        print(
            "XPL worker 单批执行完成: "
            f"领取={result.claimed}, 完成={result.completed}, 失败={result.failed}"
        )
        return
    worker.run_forever()


if __name__ == "__main__":
    main()

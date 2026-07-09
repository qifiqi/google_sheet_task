from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def load_env_files(app_env: str | None = None) -> None:
    """不依赖 Flask 启动流程，直接加载 .env 和 .env.{APP_ENV}。"""
    env_name = (app_env or os.environ.get("APP_ENV") or "production").strip() or "production"
    for path in (PROJECT_ROOT / ".env", PROJECT_ROOT / f".env.{env_name}"):
        if not path.exists():
            continue
        for raw_line in path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value


def _get_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


def _get_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


@dataclass(frozen=True)
class WorkerConfig:
    database_url: str
    executor: str = "process"
    concurrency: int = 2
    batch_size: int = 8
    poll_interval_seconds: float = 2.0
    stale_after_seconds: int = 300

    @classmethod
    def from_env(cls) -> "WorkerConfig":
        database_url = os.environ.get("XPL_WORKER_DATABASE_URL") or os.environ.get("DATABASE_URL")
        if not database_url:
            database_url = f"sqlite:///{(PROJECT_ROOT / 'instance' / 'app.db').as_posix()}"

        executor = (os.environ.get("XPL_WORKER_EXECUTOR") or "process").strip().lower()
        if executor not in {"process", "thread"}:
            executor = "process"

        return cls(
            database_url=database_url,
            executor=executor,
            concurrency=max(1, _get_int("XPL_WORKER_CONCURRENCY", _get_int("XPL_WORKER_PROCESSES", 2))),
            batch_size=max(1, _get_int("XPL_WORKER_BATCH_SIZE", 8)),
            poll_interval_seconds=max(0.1, _get_float("XPL_WORKER_POLL_INTERVAL", 2.0)),
            stale_after_seconds=max(1, _get_int("XPL_WORKER_STALE_AFTER", 300)),
        )

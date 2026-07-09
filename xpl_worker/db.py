from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine


def create_worker_engine(database_url: str) -> Engine:
    if database_url.startswith("postgresql"):
        return create_engine(
            database_url,
            pool_pre_ping=True,
            pool_recycle=3600,
            pool_size=5,
            max_overflow=10,
            pool_timeout=30,
            connect_args={
                "connect_timeout": 10,
                "options": "-c statement_timeout=30000",
            },
        )
    if database_url.startswith("sqlite"):
        return create_engine(
            database_url,
            pool_pre_ping=True,
            connect_args={
                "timeout": 30,
                "check_same_thread": False,
            },
        )
    return create_engine(database_url, pool_pre_ping=True, pool_recycle=3600)


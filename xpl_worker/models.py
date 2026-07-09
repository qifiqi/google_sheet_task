from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class XplJob:
    id: int
    task_id: str
    task_result_id: int
    return_series_id: int
    attempts: int
    max_attempts: int


@dataclass(frozen=True)
class XplWorkerRunResult:
    claimed: int = 0
    completed: int = 0
    failed: int = 0


ReturnRows = list[dict[str, Any]]


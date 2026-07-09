from __future__ import annotations

from typing import Any, Protocol

from xpl_worker.models import XplJob


class XplJobStore(Protocol):
    """独立 worker 的数据访问边界。

    runner 只依赖这个接口。当前实现是直接 SQL，但处理流程不需要关心
    底层具体是数据库、HTTP 接口，还是测试用的 fake store。
    """

    def claim_jobs(self, worker_id: str, limit: int, stale_after_seconds: int) -> list[XplJob]:
        ...

    def get_return_series_json_map(self, return_series_ids: list[int]) -> dict[int, str | None]:
        ...

    def mark_completed(
        self,
        job_id: int,
        worker_id: str,
        flat_result: dict[str, Any],
        analyze_result: dict[str, Any],
        compute_elapsed_seconds: float | None,
        load_elapsed_seconds: float | None,
    ) -> bool:
        ...

    def mark_failed(
        self,
        job: XplJob,
        worker_id: str,
        error: Exception | str,
        load_elapsed_seconds: float | None = None,
        compute_elapsed_seconds: float | None = None,
    ) -> bool:
        ...

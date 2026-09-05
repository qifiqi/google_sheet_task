"""单模型历史结果汇总索引服务门面（query / exporter / jobs 三 mixin 组合）。

对外契约保持不变：`app/services/model_summary_service.py` re-export
`ModelSummaryService` 与单例 `model_summary_service`（对齐 task/facade 先例）。
"""

from __future__ import annotations

import threading
from typing import Any

from app.services.model_summary.exporter import SummaryExportMixin
from app.services.model_summary.jobs import SummaryJobMixin
from app.services.model_summary.query import SummaryQueryMixin


class ModelSummaryService(SummaryQueryMixin, SummaryExportMixin, SummaryJobMixin):
    """维护和查询单模型汇总索引。

    作业注册表与锁是门面实例状态：
    - _jobs / _jobs_lock：后台重建作业注册表；
    - _index_lock：索引差分更新 / 全量重建互斥锁。
    """

    def __init__(self):
        """初始化实例状态。"""
        self._jobs: dict[str, dict[str, Any]] = {}
        self._jobs_lock = threading.Lock()
        self._index_lock = threading.RLock()


model_summary_service = ModelSummaryService()

"""单模型历史结果汇总索引服务（门面 re-export，实现拆分见 app/services/model_summary/）。"""

from app.services.model_summary.extractor import (
    MODEL_SUMMARY_REBUILD_TASK_TYPE,
    SummaryRecord,
    extract_summary_records,
)
from app.services.model_summary.facade import ModelSummaryService, model_summary_service

__all__ = [
    "MODEL_SUMMARY_REBUILD_TASK_TYPE",
    "ModelSummaryService",
    "SummaryRecord",
    "extract_summary_records",
    "model_summary_service",
]

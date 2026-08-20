"""任务结果汇总索引的远程 CRUD 访问。"""

from __future__ import annotations

import json
from datetime import date, datetime
from collections.abc import Mapping
from typing import Any

from app.repositories.base import SdkCrudRepository, normalize_bool_fields


class TaskResultSummaryIndexRepository(SdkCrudRepository):
    """转换汇总指标 JSON 与 is_best 布尔字段。"""

    group_name = "param_task_result_summary_index"

    def to_api_payload(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        """保存前序列化汇总 JSON，并格式化时间字段。"""
        result = dict(payload)
        for field in ("metrics_json", "parameter_summary"):
            if isinstance(result.get(field), (dict, list)):
                result[field] = json.dumps(result[field], ensure_ascii=False, default=str)
        for field in ("result_timestamp", "created_at", "updated_at"):
            if isinstance(result.get(field), (date, datetime)):
                result[field] = result[field].isoformat()
        return result

    def normalize_record(self, record: Mapping[str, Any]) -> dict[str, Any]:
        """读取后还原汇总 JSON，并标准化最佳结果标记。"""
        result = normalize_bool_fields(record, "is_best")
        for field in ("metrics_json", "parameter_summary"):
            if isinstance(result.get(field), str):
                try:
                    result[field] = json.loads(result[field])
                except json.JSONDecodeError:
                    pass
        return result

"""任务收益序列的远程 CRUD 访问。"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from app.repositories.base import RemoteRecord, SdkCrudRepository


class TaskResultReturnRepository(SdkCrudRepository):
    """转换 returns_json；按 task_id 查询等待 ParamTaskResultsReturn/Query。"""

    group_name = "param_task_results_return"

    def to_api_payload(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        """保存前将收益序列转换为远端需要的 JSON 文本。"""
        result = dict(payload)
        if isinstance(result.get("returns_json"), (dict, list)):
            result["returns_json"] = json.dumps(result["returns_json"], ensure_ascii=False)
        return result

    def normalize_record(self, record: Mapping[str, Any]) -> RemoteRecord:
        """读取后还原收益序列，并兼容旧代码的属性访问。"""
        result = dict(record)
        if isinstance(result.get("returns_json"), str):
            try:
                result["returns_json"] = json.loads(result["returns_json"])
            except json.JSONDecodeError:
                pass
        return RemoteRecord(result)

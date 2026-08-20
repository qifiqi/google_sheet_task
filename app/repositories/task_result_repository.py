"""任务结果的远程 CRUD 访问。"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from app.repositories.base import RemoteRecord, SdkCrudRepository, normalize_bool_fields


class TaskResultRepository(SdkCrudRepository):
    """转换结果与参数 JSON；按 task_id 查询等待 ParamTaskResults/Query。"""

    group_name = "param_task_results"

    def to_api_payload(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        """保存前序列化参数和结果中的结构化数据。"""
        result = dict(payload)
        for field in ("parameters", "result"):
            if isinstance(result.get(field), (dict, list)):
                result[field] = json.dumps(result[field], ensure_ascii=False, default=str)
        return result

    def normalize_record(self, record: Mapping[str, Any]) -> RemoteRecord:
        """读取后还原 JSON 字段，并保持旧代码的属性访问方式。"""
        result = normalize_bool_fields(record, "success")
        for field in ("parameters", "result"):
            if isinstance(result.get(field), str):
                try:
                    result[field] = json.loads(result[field])
                except json.JSONDecodeError:
                    pass
        return RemoteRecord(result)

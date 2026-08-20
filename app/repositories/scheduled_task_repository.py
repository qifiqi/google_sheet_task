"""定时任务记录的远程 CRUD 访问。"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from app.repositories.base import SdkCrudRepository, normalize_bool_fields


class ScheduledTaskRepository(SdkCrudRepository):
    """负责定时任务参数 JSON 和运行状态字段的协议转换。"""
    group_name = "param_scheduled_tasks"

    def to_api_payload(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        """保存前将任务参数对象转换为远端接口需要的 JSON 文本。"""
        result = dict(payload)
        if isinstance(result.get("task_params"), (dict, list)):
            result["task_params"] = json.dumps(result["task_params"], ensure_ascii=False)
        return result

    def normalize_record(self, record: Mapping[str, Any]) -> dict[str, Any]:
        """读取后还原任务参数，并标准化布尔状态字段。"""
        result = normalize_bool_fields(record, "is_active", "is_running")
        task_params = result.get("task_params")
        if isinstance(task_params, str):
            try:
                result["task_params"] = json.loads(task_params)
            except json.JSONDecodeError:
                pass
        return result

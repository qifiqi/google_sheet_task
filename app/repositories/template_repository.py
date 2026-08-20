"""任务模板记录的远程 CRUD 访问。"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from app.repositories.base import SdkCrudRepository


class TaskTemplateRepository(SdkCrudRepository):
    """负责 ``config`` 字段在字典与 JSON 文本之间的协议转换。"""
    group_name = "param_task_templates"

    def to_api_payload(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        """保存前将模板配置序列化为远端接口需要的 JSON 文本。"""
        result = dict(payload)
        if isinstance(result.get("config"), (dict, list)):
            result["config"] = json.dumps(result["config"], ensure_ascii=False)
        return result

    def normalize_record(self, record: Mapping[str, Any]) -> dict[str, Any]:
        """读取后尽可能将 JSON 配置还原为字典或列表。"""
        result = dict(record)
        config = result.get("config")
        if isinstance(config, str):
            try:
                result["config"] = json.loads(config)
            except json.JSONDecodeError:
                pass
        return result

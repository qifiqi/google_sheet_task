"""任务主表的远程 CRUD 访问。"""

from __future__ import annotations

import json
from datetime import date, datetime
from collections.abc import Mapping
from typing import Any

from app.repositories.base import SdkCrudRepository


class RemoteTaskRecord(dict):
    """兼容旧任务服务属性访问的远端任务 DTO。"""

    def __getattr__(self, name: str) -> Any:
        """兼容旧服务以属性形式读取任务字段。"""
        try:
            return self[name]
        except KeyError as exc:
            raise AttributeError(name) from exc

    def __setattr__(self, name: str, value: Any) -> None:
        """兼容旧服务以属性形式更新任务字段。"""
        self[name] = value

    def to_dict(self) -> dict[str, Any]:
        """维持旧路由和服务所使用的任务序列化入口。"""
        return dict(self)

    def get_progress_percentage(self) -> float:
        """按当前与总步骤计算任务进度，未设置总步骤时返回零。"""
        total_steps = int(self.get("total_steps") or 0)
        if total_steps <= 0:
            return 0
        return round((int(self.get("current_step") or 0) / total_steps) * 100, 2)


class TaskRepository(SdkCrudRepository):
    """处理字符串任务主键、配置 JSON 和时间字段的 SDK 协议转换。"""

    group_name = "param_tasks"

    @staticmethod
    def normalize_id(record_id: Any) -> str:
        """任务 ID 是 UUID 字符串，不能按通用数值主键转换。"""
        value = str(record_id or "").strip()
        if not value:
            raise ValueError("任务 ID 不能为空")
        return value

    def to_api_payload(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        """将任务配置和时间对象转换为远程接口可序列化的字段。"""
        result = dict(payload)
        if isinstance(result.get("config"), (dict, list)):
            result["config"] = json.dumps(result["config"], ensure_ascii=False)
        for field in ("start_time", "end_time", "created_at", "updated_at"):
            value = result.get(field)
            if isinstance(value, (datetime, date)):
                result[field] = value.isoformat()
        return result

    def normalize_record(self, record: Mapping[str, Any]) -> RemoteTaskRecord:
        """将远程字典包装为兼容旧服务属性访问的任务 DTO。"""
        result = dict(record)
        if isinstance(result.get("config"), str):
            try:
                result["config"] = json.loads(result["config"])
            except json.JSONDecodeError:
                result["config"] = {}
        return RemoteTaskRecord(result)

"""TaskTemplate HTTP 仓储（本地对应 app/repositories/task_template_repository.py）。"""
from __future__ import annotations

import json
from typing import Any

from app.exceptions import NotFoundError
from app.repositories.http_backend.base import HttpRepositoryBase, dump_row
from app.remote_api import RemoteApiNotFoundError


class TaskTemplateHttpRepository(HttpRepositoryBase):
    """task_templates 表远程访问；数值主键，config 列存 JSON 字符串。"""

    group_name = "param_task_templates"

    _DT_FIELDS = ("created_at", "updated_at")

    @staticmethod
    def _normalize(record: dict[str, Any]) -> dict[str, Any]:
        """对齐本地 to_dict 语义：config JSON 串解析为 dict（坏 JSON 保留原串）。"""
        result = dict(record)
        if isinstance(result.get("config"), str):
            try:
                result["config"] = json.loads(result["config"])
            except json.JSONDecodeError:
                pass
        return result

    # ---- 读 ----

    def list_all(self, task_type=None):
        """保持本地 Python 端过滤语义：按 config.task_type 过滤，解析失败跳过。"""
        results = []
        for record in self.iter_pages({}):
            data = self._normalize(record)
            if task_type:
                config = data.get("config")
                if not isinstance(config, dict) or config.get("task_type") != task_type:
                    continue
            results.append(data)
        results.sort(key=lambda item: str(item.get("created_at") or ""), reverse=True)
        return results

    def get(self, template_id):
        try:
            raw = self.api.param_task_templates.get_info_by_id(
                {"id": self.normalize_id(template_id)}
            )
        except RemoteApiNotFoundError:
            return None
        return self._normalize(dict(raw)) if isinstance(raw, dict) else None

    def get_required(self, template_id):
        data = self.get(template_id)
        if data is None:
            raise NotFoundError(f"模板不存在: {template_id}")
        return data

    # ---- 写 ----

    def create(self, name, description, config_str):
        return self.save({
            "name": name,
            "description": description,
            "config": config_str,
        })

    def update(self, template_id, fields):
        row = self.get(template_id)
        if row is None:
            return None
        payload = dump_row({**row, **fields}, datetime_fields=self._DT_FIELDS)
        if isinstance(payload.get("config"), (dict, list)):
            payload["config"] = json.dumps(payload["config"], ensure_ascii=False)
        return self.save(payload)

    def delete(self, template_id, commit=True):
        try:
            super().delete(template_id)
        except RemoteApiNotFoundError:
            return False
        return True

    def to_api_payload(self, payload):
        return dump_row(payload, datetime_fields=self._DT_FIELDS)

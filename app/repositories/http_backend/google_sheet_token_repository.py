"""GoogleSheetToken HTTP 仓储（本地对应 app/repositories/google_sheet_token_repository.py）。

远端 param_google_sheet_tokens 分页无过滤字段（RequsetPageDto）；token 表行数
小（几十行），统一全量拉取 + 本地筛选/聚合。
"""
from __future__ import annotations

from typing import Any

from app.repositories.http_backend.base import (
    HttpRepositoryBase,
    RemoteRecord,
    dump_row,
    normalize_bool_fields,
)
from app.remote_api import RemoteApiNotFoundError


class GoogleSheetTokenHttpRepository(HttpRepositoryBase):
    """google_sheet_tokens 表远程访问；数值主键。"""

    group_name = "param_google_sheet_tokens"

    _DT_FIELDS = ("last_used_at", "created_at", "updated_at")
    _BOOL_FIELDS = ("is_active",)

    def normalize_record(self, record):
        return normalize_bool_fields(dict(record), *self._BOOL_FIELDS)

    # ---- 读 ----

    def apply_in_use_counts(self, usage: dict, commit=True) -> int:
        """按主键回写 current_in_use_count（对账）；返回更新的行数。

        TODO(db-to-http): 读-改-写窗口存在并发竞态；Redis 裁决层接入后由
        分布式锁保证互斥（迁移文档 §占用语义）。
        """
        updated = 0
        for token_id, count in (usage or {}).items():
            row = self.get(int(token_id))
            if row is None:
                continue
            self.save({**row, "current_in_use_count": int(count)})
            updated += 1
        return updated

    def list_entities_ordered(self, task_type=None):
        """list_tokens 的实体形态（服务层转 dict）。

        对齐本地多键排序：is_active desc, current_in_use_count asc,
        task_usage_count asc, name asc。
        """
        rows = self.list_all()
        if task_type:
            rows = [row for row in rows if row.get("task_type") == task_type]
        rows.sort(
            key=lambda row: (
                not bool(row.get("is_active")),
                int(row.get("current_in_use_count") or 0),
                int(row.get("task_usage_count") or 0),
                str(row.get("name") or ""),
            )
        )
        return [RemoteRecord(row) for row in rows]

    def list_active_entities(self, task_type=None):
        """启用中的 token 实体（随机选取/可用统计用）；返回列表。

        TODO(db-to-http): 本地版返回 SQLAlchemy query 供调用方续查；
        HTTP 版返回 list，调用方的 .all()/.count() 已在服务层适配。
        """
        rows = self.list_all()
        if task_type:
            rows = [row for row in rows if row.get("task_type") == task_type]
        return [RemoteRecord(row) for row in rows if row.get("is_active")]

    def add_entity(self, entity, flush=True):
        """挂起新建实体（导入流程先 flush 取 id 再补 token_file）。

        HTTP 版接受 ORM 实体或 dict：ORM 实体经 to_dict 序列化后远端写入，
        远端回显 id 时回写到实体。
        """
        payload = entity.to_dict() if hasattr(entity, "to_dict") else dict(entity)
        saved = self.save(dump_row(payload, datetime_fields=self._DT_FIELDS))
        if isinstance(saved, dict) and saved.get("id") is not None and hasattr(entity, "id"):
            try:
                entity.id = saved["id"]
            except AttributeError:
                pass
        return entity

    def get_by_context(self, token_context, task_type):
        """按内容+任务类型查重（导入幂等）；返回实体形态或 None。"""
        for row in self.list_all():
            if row.get("task_type") == task_type and row.get("token_context") == token_context:
                return RemoteRecord(row)
        return None

    def count_active(self):
        return len(self.list_active_entities())

    def sum_field(self, field_name):
        """对指定数值列求和（占用汇总）。"""
        total = 0
        for row in self.list_all():
            value = row.get(field_name)
            if value is not None:
                try:
                    total = total + value
                except TypeError:
                    continue
        return total

    # ---- 写 ----

    def get(self, token_id):
        try:
            raw = self.api.param_google_sheet_tokens.get_info_by_id(
                {"id": self.normalize_id(token_id)}
            )
        except RemoteApiNotFoundError:
            return None
        return self.normalize_record(dict(raw)) if isinstance(raw, dict) else None

    def delete(self, token_id, commit=True):
        try:
            super().delete(token_id)
        except RemoteApiNotFoundError:
            return False
        return True

    def to_api_payload(self, payload):
        return dump_row(payload, datetime_fields=self._DT_FIELDS)

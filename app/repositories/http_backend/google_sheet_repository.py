"""GoogleSheet HTTP 仓储（本地对应 app/repositories/google_sheet_repository.py）。

远端 GetParamGoogleSheetListRequestDto 支持 task_id / table_type / is_active /
is_in_use 过滤；registry_scope、spreadsheet_id 无服务端过滤，走全量拉取本地匹配
（registry 表行数小）。
"""
from __future__ import annotations

from typing import Any

from app.repositories.http_backend.base import (
    HttpRepositoryBase,
    dump_row,
    normalize_bool_fields,
)
from app.repositories.sdk_client import SdkNotFoundError


class GoogleSheetHttpRepository(HttpRepositoryBase):
    """google_sheet（registry）表远程访问；数值主键。"""

    group_name = "param_google_sheet"

    _DT_FIELDS = ("created_at", "updated_at")
    _BOOL_FIELDS = ("is_active", "is_in_use")

    def normalize_record(self, record):
        return normalize_bool_fields(dict(record), *self._BOOL_FIELDS)

    # ---- 读 ----

    def list_filtered(self, include_inactive=False, only_available=False, task_id=None, table_type=None):
        """管理端/选择器列表（google_sheet_registry_service.list_sheets 语义）。

        only_available 的 OR 条件（is_in_use=False OR current_task_id=task_id）
        远端无 OR 能力：分两次查询（is_in_use=False 与 task_id 过滤）后按 id 合并。
        """
        base_payload: dict[str, Any] = {}
        if table_type:
            base_payload["table_type"] = table_type
        if not include_inactive:
            base_payload["is_active"] = True

        merged: dict[Any, dict[str, Any]] = {}
        if only_available:
            queries: list[dict[str, Any]] = [{**base_payload, "is_in_use": False}]
            if task_id:
                queries.append({**base_payload, "task_id": task_id})
        else:
            queries = [base_payload]

        for payload in queries:
            for row in self.list_all(payload):
                merged.setdefault(row["id"], row)

        return sorted(
            merged.values(),
            key=lambda item: (str(item.get("name") or ""), item.get("id") or 0),
        )

    def get_by_spreadsheet_id(self, spreadsheet_id):
        """按 spreadsheet_id 取第一条配置（占用收集用）。"""
        for row in self.list_all():
            if str(row.get("spreadsheet_id") or "") == str(spreadsheet_id):
                return row
        return None

    def get_duplicate_row(self, spreadsheet_id, scope_value, exclude_id=None):
        """同 scope 下 spreadsheet_id 查重；返回 dict 或 None。"""
        for row in self.list_all():
            if (
                str(row.get("spreadsheet_id") or "") == str(spreadsheet_id)
                and row.get("registry_scope") == scope_value
                and (exclude_id is None or row.get("id") != exclude_id)
            ):
                return row
        return None

    # ---- 占用（条件写：读-改-写，TODO redis 裁决层） ----

    def occupy(self, sheet_id, task_id, commit=True):
        """任务占用 Sheet：同任务幂等；成功返回占用后的 dict，占用校验失败返回 None。

        TODO(db-to-http): 远端无条件更新端点，此处读-改-写存在并发竞态窗口；
        待 Redis 裁决层接入后由分布式锁保证互斥（迁移文档 §占用语义）。
        """
        row = self.get(sheet_id)
        if row is None:
            return None
        if row.get("current_task_id") == task_id:
            if not row.get("is_in_use"):
                row = self.save({**row, "is_in_use": True})
            return row
        updated = self.save({**row, "is_in_use": True, "current_task_id": task_id})
        # 对齐原语义：提交后复核，防止读到过期状态。
        fresh = self.get(sheet_id)
        if fresh is None or not fresh.get("is_in_use") or fresh.get("current_task_id") != task_id:
            return None
        return fresh if fresh is not None else updated

    def release_by_task(self, task_id, commit=True):
        """按任务释放其占用的全部 Sheet；返回受影响行数。"""
        rows = self.list_all({"task_id": task_id})
        updated = 0
        for row in rows:
            if row.get("current_task_id") == task_id:
                self.save({**row, "is_in_use": False, "current_task_id": None})
                updated += 1
        return updated

    # ---- CRUD ----

    def get(self, sheet_id):
        try:
            raw = self.client.call(
                self.group_name, "get_info_by_id", {"id": self.normalize_id(sheet_id)}
            )
        except SdkNotFoundError:
            return None
        return self.normalize_record(dict(raw)) if isinstance(raw, dict) else None

    def create(self, fields, commit=True):
        # TODO(db-to-http): 数值主键由远端生成；ModifyOrAdd 若不回显 ret_obj，
        # 返回记录缺 id，调用方如需 id 须以 spreadsheet_id 复查。
        return self.save(dump_row(fields, datetime_fields=self._DT_FIELDS))

    def update(self, sheet_id, fields, commit=True):
        row = self.get(sheet_id)
        if row is None:
            return None
        return self.save(dump_row({**row, **fields}, datetime_fields=self._DT_FIELDS))

    def delete(self, sheet_id, commit=True):
        try:
            super().delete(sheet_id)
        except SdkNotFoundError:
            return False
        return True

    def to_api_payload(self, payload):
        return dump_row(payload, datetime_fields=self._DT_FIELDS)

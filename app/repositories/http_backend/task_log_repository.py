"""TaskLog HTTP 仓储（本地对应 app/repositories/task_log_repository.py）。

远端 GetParamTaskLogsListRequestDto 支持 task_id / level 过滤；timestamp 条件
删除（delete_older_than）远端无范围端点，走 timestamp 升序分页扫描、遇到窗口
外记录即停（老日志排前，可提前终止）。
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from app.models import TaskLog
from app.repositories.http_backend.base import HttpRepositoryBase, dump_row
from app.repositories.sdk_client import SdkNotFoundError


class TaskLogHttpRepository(HttpRepositoryBase):
    """task_logs 表远程访问；数值主键。"""

    group_name = "param_task_logs"

    _DT_FIELDS = ("timestamp",)

    def to_api_payload(self, payload):
        return dump_row(payload, datetime_fields=self._DT_FIELDS)

    # ---- 读 ----

    def get_last(self, task_id):
        """最新一条日志（看门狗活性检查）。

        TODO(db-to-http): 远端单一 order_field 无法表达 timestamp desc, id desc
        双键排序；同一时间戳多条时取返回首条。
        """
        page = self.page(
            {"task_id": task_id}, page_size=1,
            order_field="timestamp", order_type="desc",
        )
        items = page["items"]
        return items[0] if items else None

    def list_by_task(self, task_id, limit=500):
        """按时间正序返回最新 limit 条日志。"""
        page = self.page(
            {"task_id": task_id}, page_size=max(1, int(limit)),
            order_field="timestamp", order_type="desc",
        )
        return list(reversed(page["items"]))

    def list_by_task_paginated(self, task_id, page, per_page, level=None):
        payload: dict[str, Any] = {"task_id": task_id}
        if level:
            payload["level"] = level
        current_page = max(page or 1, 1)
        size = max(min(per_page or 50, 200), 1)
        result = self.page(
            payload, page_index=current_page, page_size=size,
            order_field="timestamp", order_type="desc",
        )
        total = result["total"]
        return {
            "items": result["items"],
            "total": total,
            "pages": (total + size - 1) // size if size else 0,
            "current_page": current_page,
            "per_page": size,
        }

    def count_by_task(self, task_id):
        return self.page({"task_id": task_id}, page_size=1)["total"]

    def last_write_time(self, task_id):
        """最新日志时间（datetime 或 None）。"""
        row = self.get_last(task_id)
        if not row or not row.get("timestamp"):
            return None
        value = row["timestamp"]
        if isinstance(value, datetime):
            return value
        try:
            return datetime.fromisoformat(str(value))
        except ValueError:
            return None

    # ---- 写 ----

    def create_log(self, task_id, level, message, commit=True):
        """写入一条任务日志（执行链每步热路径：一次 ModifyOrAdd）。"""
        log = {
            "task_id": task_id,
            "level": level,
            "message": TaskLog.normalize_message(message),
            "timestamp": datetime.now(),
        }
        return self.save(dump_row(log, datetime_fields=self._DT_FIELDS))

    def delete_by_task(self, task_id, commit=True):
        """按任务删除全部日志；远端无按条件删除端点，逐 id 删除。

        TODO(db-to-http): 建议远端提供按 task_id 批量删除端点（迁移文档
        无法接入清单）；删除为逐行非原子操作。
        """
        deleted = 0
        for row in list(self.iter_pages({"task_id": task_id})):
            try:
                super().delete(row["id"])
                deleted += 1
            except SdkNotFoundError:
                continue
        return deleted

    def delete_older_than(self, cutoff, commit=True):
        """清理窗口条件：timestamp 升序扫描（老日志排前），越界即停。"""
        deleted = 0
        for row in self.iter_pages({}, order_field="timestamp", order_type="asc"):
            ts = self._parse_dt(row.get("timestamp"))
            if ts is None or ts >= cutoff:
                break
            try:
                super().delete(row["id"])
                deleted += 1
            except SdkNotFoundError:
                continue
        return deleted

    def list_ids_older_than(self, cutoff, limit):
        """到期日志 id 分批读取（调度清理的批量语义）。"""
        ids: list[Any] = []
        for row in self.iter_pages({}, order_field="timestamp", order_type="asc"):
            ts = self._parse_dt(row.get("timestamp"))
            if ts is None or ts >= cutoff:
                break
            ids.append(row["id"])
            if len(ids) >= limit:
                break
        return ids

    def delete_by_ids(self, ids, commit=True):
        """按 id 集合删除；返回删除行数。"""
        if not ids:
            return 0
        deleted = 0
        for record_id in ids:
            try:
                super().delete(record_id)
                deleted += 1
            except SdkNotFoundError:
                continue
        return deleted

    @staticmethod
    def _parse_dt(value):
        if isinstance(value, datetime):
            return value
        if isinstance(value, str) and value:
            try:
                return datetime.fromisoformat(value)
            except ValueError:
                return None
        return None

"""ScheduledTask HTTP 仓储（本地对应 app/repositories/scheduled_task_repository.py）。

远端 param_scheduled_tasks 分页无过滤字段；定时任务表行数小，统一全量拉取 +
本地筛选。acquire/release 运行锁为读-改-写（TODO Redis 裁决层）。
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from app.exceptions import NotFoundError
from app.repositories.http_backend.base import (
    HttpRepositoryBase,
    RemoteRecord,
    dump_row,
    normalize_bool_fields,
)
from app.repositories.sdk_client import SdkNotFoundError


class ScheduledTaskHttpRepository(HttpRepositoryBase):
    """scheduled_tasks 表远程访问；数值主键。"""

    group_name = "param_scheduled_tasks"

    _DT_FIELDS = ("last_run_time", "next_run_time", "created_at", "updated_at")
    _BOOL_FIELDS = ("is_active", "is_running")

    def normalize_record(self, record):
        return normalize_bool_fields(dict(record), *self._BOOL_FIELDS)

    # ---- 读 ----

    def count(self):
        return self.page({}, page_size=1)["total"]

    def count_active(self):
        return len(self.list_active_entities())

    def list_paginated(self, page, per_page):
        """created_at desc 全量排序后本地切片分页。"""
        rows = self.list_all(order_field="created_at", order_type="desc")
        rows.sort(key=lambda item: str(item.get("created_at") or ""), reverse=True)
        current_page = max(page or 1, 1)
        size = max(min(per_page or 10, 100), 1)
        total = len(rows)
        start = (current_page - 1) * size
        items = rows[start:start + size]
        pages = (total + size - 1) // size if size else 0
        return {
            "items": items,
            "total": total,
            "pages": pages,
            "current_page": current_page,
            "per_page": size,
        }

    def get(self, task_id):
        try:
            raw = self.client.call(
                self.group_name, "get_info_by_id", {"id": self.normalize_id(task_id)}
            )
        except SdkNotFoundError:
            return None
        return self.normalize_record(dict(raw)) if isinstance(raw, dict) else None

    def get_required(self, task_id):
        """HTTP 语义不进数据层，由全局处理器映射 404。"""
        data = self.get(task_id)
        if data is None:
            raise NotFoundError(f"定时任务不存在: {task_id}")
        return data

    def get_stats(self):
        """聚合统计：{total, active}。"""
        return {"total": self.count(), "active": self.count_active()}

    def refresh_entity(self, entity):
        """重新加载实体状态；HTTP 版记录本就即时读取，原样返回。"""
        return entity

    def list_active_entities(self):
        """活跃任务实体（调度器 add_job 消费实体属性）。"""
        rows = [
            row for row in self.list_all()
            if self._as_bool(row.get("is_active"))
        ]
        return [RemoteRecord(row) for row in rows]

    def get_by_name_and_function(self, name, task_function):
        """默认任务播种的存在性检查；返回实体或 None。"""
        for row in self.list_all():
            if row.get("name") == name and row.get("task_function") == task_function:
                return RemoteRecord(row)
        return None

    # ---- 运行锁（条件写：TODO Redis 裁决层，见迁移文档 §占用语义） ----

    @staticmethod
    def _as_bool(value):
        return value if isinstance(value, bool) else str(value).strip().lower() in {"1", "true", "yes", "on"}

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

    def acquire_run_lock(self, task_id, instance_id, now, stale_before=None, commit=True):
        """乐观锁获取执行权：仅当 is_running 为假时置位；返回 1/0。

        stale_before 提供时，is_running 为真但 last_run_time 缺失或早于该时刻的
        陈旧锁允许被接管。
        TODO(db-to-http): 读-改-写窗口存在并发竞态；调度器单线程触发时窗口
        不构成实际风险，多实例部署前须接入 Redis 裁决层。
        """
        row = self.get(task_id)
        if row is None:
            return 0
        if self._as_bool(row.get("is_running")):
            last_run = self._parse_dt(row.get("last_run_time"))
            if stale_before is None or (last_run is not None and last_run >= stale_before):
                return 0
        saved = self.save({
            **row,
            "is_running": True,
            "running_instance_id": instance_id,
            "last_run_time": now.isoformat() if isinstance(now, datetime) else now,
        })
        return 1 if saved is not None else 0

    def release_run_lock(self, task_id, instance_id, commit=True):
        """按实例释放运行锁。"""
        row = self.get(task_id)
        if row is None or row.get("running_instance_id") != instance_id:
            return 0
        self.save({**row, "is_running": False, "running_instance_id": None})
        return 1

    def update_next_run(self, task_id, next_run_time, commit=True):
        """仅更新下次执行时间（add_job 场景，不计执行次数）。"""
        return self.update(task_id, {"next_run_time": next_run_time}, commit=commit)

    def record_run(self, task_id, next_run_time, commit=True):
        """累计执行次数并写入下次执行时间；返回实体。"""
        row = self.get(task_id)
        if row is None:
            return None
        row["run_count"] = (row.get("run_count") or 0) + 1
        row["next_run_time"] = next_run_time
        return RemoteRecord(self.save(dump_row(row, datetime_fields=self._DT_FIELDS)))

    # ---- 写 ----

    def create(self, fields, commit=True):
        return self.save(dump_row(fields, datetime_fields=self._DT_FIELDS))

    def update(self, task_id, fields, commit=True):
        row = self.get(task_id)
        if row is None:
            return None
        return self.save(dump_row({**row, **fields}, datetime_fields=self._DT_FIELDS))

    def delete(self, task_id, commit=True):
        try:
            super().delete(task_id)
        except SdkNotFoundError:
            return False
        return True

    def to_api_payload(self, payload):
        return dump_row(payload, datetime_fields=self._DT_FIELDS)

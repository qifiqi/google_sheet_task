"""Task HTTP 仓储（本地对应 app/repositories/task_repository.py）。

远端 GetParamTasksListRequestDto 支持 task_types[] / statuses[] / keyword /
created_from 过滤；current_step、created_by_user_id、name 精确匹配、双键排序
无服务端过滤能力，相关方法退化为过滤拉取 + 本地判读（TODO 已逐方法标注）。
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Any

from app.exceptions import NotFoundError
from app.repositories.http_backend.base import (
    HttpRepositoryBase,
    RemoteRecord,
    dump_row,
)
from app.repositories.sdk_client import SdkNotFoundError


# 与本地模型/服务层任务状态字面量一致（task 状态机全集）。
_TASK_STATUSES = ("pending", "running", "completed", "error", "cancelled")


class TaskHttpRepository(HttpRepositoryBase):
    """param_tasks 表远程访问；任务 id 为应用生成的字符串主键。"""

    group_name = "param_tasks"

    _DT_FIELDS = ("start_time", "end_time", "created_at", "updated_at")

    @staticmethod
    def normalize_id(record_id: Any) -> str:
        """任务 ID 是应用生成的字符串主键，不能按数值转换。"""
        value = str(record_id or "").strip()
        if not value:
            raise ValueError("任务 ID 不能为空")
        return value

    def to_api_payload(self, payload):
        return dump_row(
            payload,
            datetime_fields=self._DT_FIELDS,
            json_fields=("config",),
        )

    def normalize_record(self, record):
        """对齐本地 to_dict 语义：config JSON 串解析为 dict。"""
        result = dict(record)
        if isinstance(result.get("config"), str):
            try:
                result["config"] = json.loads(result["config"])
            except json.JSONDecodeError:
                result["config"] = {}
        return RemoteRecord(result)

    # ---- 内部工具 ----

    def _get_raw(self, task_id):
        try:
            raw = self.client.call(
                self.group_name, "get_info_by_id", {"id": self.normalize_id(task_id)}
            )
        except SdkNotFoundError:
            return None
        return self.normalize_record(dict(raw)) if isinstance(raw, dict) else None

    def _conditional_transition(self, task_id, expect_status, fields) -> int:
        """读-改-写状态迁移；命中返回 1，否则 0。

        TODO(db-to-http): 远端无条件更新端点，本方法存在并发竞态窗口；
        Redis 裁决层接入后由分布式锁保证互斥（迁移文档 §状态机语义）。
        """
        row = self._get_raw(task_id)
        if row is None or row.get("status") != expect_status:
            return 0
        self.save({**row, **fields})
        return 1

    def _filtered_page(self, *, task_type=None, task_types=None, status=None,
                       keyword=None, created_from=None, page_index=1, page_size=200,
                       order_field="created_at", order_type="desc"):
        types = list(task_types) if task_types else ([task_type] if task_type else [])
        payload: dict[str, Any] = {}
        if types:
            payload["task_types"] = types
        if status and status != "all":
            payload["statuses"] = [status]
        if keyword:
            payload["keyword"] = keyword
        if created_from:
            payload["created_from"] = created_from
        return self.page(
            payload, page_index=page_index, page_size=page_size,
            order_field=order_field, order_type=order_type,
        )

    @staticmethod
    def _pages(total, size):
        return (total + size - 1) // size if size else 0

    # ---- 读 ----

    def get(self, task_id):
        return self._get_raw(task_id)

    def get_required(self, task_id):
        task_dict = self.get(task_id)
        if task_dict is None:
            raise NotFoundError(f"任务不存在: {task_id}")
        return task_dict

    def list_all(self, task_type=None, task_types=None):
        records = self.list_all_filtered(task_type=task_type, task_types=task_types)
        return list(records)

    def list_all_filtered(self, *, task_type=None, task_types=None, status=None, created_from=None):
        payload: dict[str, Any] = {}
        types = list(task_types) if task_types else ([task_type] if task_type else [])
        if types:
            payload["task_types"] = types
        if status:
            payload["statuses"] = [status]
        if created_from:
            payload["created_from"] = created_from
        return list(self.iter_pages(payload, order_field="created_at", order_type="desc"))

    def get_latest_task_id_by_type(self, task_type, statuses=None):
        """指定类型的最近一个任务 id（created_at desc）；无则 None。

        TODO(db-to-http): 双键排序（created_at desc, id desc）退化为单字段。
        """
        payload: dict[str, Any] = {"task_types": [task_type]}
        if statuses:
            payload["statuses"] = list(statuses)
        page = self.page(payload, page_size=1, order_field="created_at", order_type="desc")
        items = page["items"]
        return items[0]["id"] if items else None

    def list_paginated(self, page, per_page, task_type=None, task_types=None,
                       status=None, keyword=None):
        current_page = max(page or 1, 1)
        size = max(min(per_page or 10, 100), 1)
        result = self._filtered_page(
            task_type=task_type, task_types=task_types, status=status, keyword=keyword,
            page_index=current_page, page_size=size,
        )
        total = result["total"]
        return {
            "items": result["items"],
            "total": total,
            "pages": self._pages(total, size),
            "current_page": current_page,
            "per_page": size,
        }

    def list_paginated_with_statistics(self, page, per_page, task_type=None,
                                       task_types=None, status=None, keyword=None):
        """任务分页 + 同过滤条件的聚合统计。

        统计口径对齐本地 SQL：按状态各查一次 total；pending_started 与
        完成时长本地判读。TODO(db-to-http): 完成时长需扫描全部 completed
        任务（含 config 大字段），任务量上千后应推动远端提供聚合端点。
        """
        current_page = max(page or 1, 1)
        size = max(min(per_page or 10, 100), 1)
        list_status = status if (status and status != "all") else None
        page_result = self._filtered_page(
            task_type=task_type, task_types=task_types, status=list_status,
            keyword=keyword, page_index=current_page, page_size=size,
        )
        total = page_result["total"]

        same_filter = dict(
            task_type=task_type, task_types=task_types, keyword=keyword,
        )
        completed = self._filtered_page(status="completed", page_size=1, **same_filter)["total"]
        running = self._filtered_page(status="running", page_size=1, **same_filter)["total"]
        error = self._filtered_page(status="error", page_size=1, **same_filter)["total"]

        # pending 特例：仅统计已开跑（current_step > 0）的待执行任务。
        pending_started = 0
        for row in self.list_all_filtered(status="pending"):
            if int(row.get("current_step") or 0) > 0:
                pending_started += 1

        today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        today_new = self._filtered_page(
            created_from=today_start.isoformat(), page_size=1, **same_filter
        )["total"]

        total_duration_seconds = 0.0
        duration_count = 0
        for row in self.list_all_filtered(status="completed"):
            start_time = self._parse_dt(row.get("start_time"))
            end_time = self._parse_dt(row.get("end_time"))
            if start_time is None or end_time is None:
                continue
            total_duration_seconds += (end_time - start_time).total_seconds()
            duration_count += 1

        return {
            "items": page_result["items"],
            "pagination": {
                "page": current_page,
                "per_page": size,
                "total": total,
                "pages": self._pages(total, size),
                "has_prev": current_page > 1,
                "has_next": current_page * size < total,
                "prev_num": current_page - 1 if current_page > 1 else None,
                "next_num": current_page + 1 if current_page * size < total else None,
            },
            "aggregates": {
                "total": total,
                "completed": completed,
                "running": running,
                "error": error,
                "pending_started": pending_started,
                "today_new": today_new,
                "total_duration_seconds": total_duration_seconds,
                "duration_count": duration_count,
            },
        }

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

    def get_status_value(self, task_id):
        """仅取任务状态值（执行链每步取消检查的热路径）。"""
        row = self._get_raw(task_id)
        return row.get("status") if row else None

    def get_entity_fresh(self, task_id):
        """过期会话缓存后重读实体；HTTP 版即单次远端读取。"""
        return self._get_raw(task_id)

    def list_running_backtest_entities(self):
        return [
            row
            for row in self.list_all_filtered(
                task_types=["backtest_training", "backtest_multi_product"], status="running"
            )
        ]

    def list_pending_backtest_entities(self, exclude_task_id):
        """待执行回测任务实体（按创建时间先后，接力启动用）。"""
        rows = [
            row
            for row in self.list_all_filtered(
                task_types=["backtest_training", "backtest_multi_product"], status="pending"
            )
            if row.get("id") != exclude_task_id
        ]
        rows.sort(key=lambda item: (str(item.get("created_at") or ""), str(item.get("id") or "")))
        return rows

    def mark_running_if_not_running(self, task_id, start_time, commit=True):
        """原子置 running（非 running 状态才生效）；返回 1/0。"""
        row = self._get_raw(task_id)
        if row is None or row.get("status") == "running":
            return 0
        self.save({**row, "status": "running",
                   "start_time": start_time.isoformat() if hasattr(start_time, "isoformat") else start_time})
        return 1

    def revert_running_to_pending(self, task_id, commit=True):
        """启动失败回退：running → pending 并清 start_time。"""
        row = self._get_raw(task_id)
        if row is None or row.get("status") != "running":
            return 0
        self.save({**row, "status": "pending", "start_time": None})
        return 1

    def mark_running_if_pending(self, task_id, start_time=None, commit=True):
        """仅当任务处于 pending 时置为 running。"""
        fields = {"status": "running"}
        if start_time is not None:
            fields["start_time"] = start_time.isoformat() if hasattr(start_time, "isoformat") else start_time
        return self._conditional_transition(task_id, "pending", fields)

    def list_watchdog_tasks(self, created_cutoff, abandon_prefix, restart_prefix):
        """watchdog 巡检任务集；error_message 前缀判读在本地完成。"""
        rows = self.list_all_filtered(
            status=None,
            created_from=created_cutoff.isoformat() if hasattr(created_cutoff, "isoformat") else created_cutoff,
        )
        result = []
        for row in rows:
            status = row.get("status")
            message = row.get("error_message") or ""
            if status == "running":
                result.append(row)
            elif status == "error" and not message.startswith(abandon_prefix):
                result.append(row)
            elif status == "cancelled" and message.startswith(restart_prefix):
                result.append(row)
        return result

    def list_by_status_ordered(self, status, limit):
        """按状态取任务（updated_at desc，钉钉批量重启用）。

        TODO(db-to-http): 双键排序（updated_at desc, created_at desc）退化。
        """
        page = self.page(
            {"statuses": [status]}, page_size=max(1, int(limit)),
            order_field="updated_at", order_type="desc",
        )
        return page["items"]

    def list_by_name(self, name, limit=2):
        """按名称取任务。

        TODO(db-to-http): 远端无 name 精确过滤，全量拉取后本地匹配；
        钉钉命令解析低频调用，暂可接受，建议远端补 name 过滤。
        """
        hits = [row for row in self.list_all() if row.get("name") == name]
        hits.sort(key=lambda item: str(item.get("created_at") or ""), reverse=True)
        return hits[:limit]

    def list_id_config_by_status(self, status):
        """按状态取 [{id, config}] 投影。"""
        return [
            {"id": row.get("id"), "config": row.get("config")}
            for row in self.list_all_filtered(status=status)
        ]

    def list_watchdog_active_ids(self, created_cutoff):
        """watchdog 重试缓存清理用：窗口内活跃任务 id。"""
        rows = self.list_all_filtered(
            created_from=created_cutoff.isoformat() if hasattr(created_cutoff, "isoformat") else created_cutoff,
        )
        active = {"pending", "running", "error", "cancelled"}
        return [row["id"] for row in rows if row.get("status") in active]

    def count(self):
        return self.page({}, page_size=1)["total"]

    def count_by_status(self, status):
        return self.page({"statuses": [status]}, page_size=1)["total"]

    def summary_counts(self):
        """admin 仪表盘四连 count 合并。"""
        return {
            "total": self.count(),
            "completed": self.count_by_status("completed"),
            "running": self.count_by_status("running"),
            "error": self.count_by_status("error"),
        }

    def list_recent(self, limit=10):
        page = self.page(
            {}, page_size=max(1, int(limit)),
            order_field="created_at", order_type="desc",
        )
        return page["items"]

    def list_distinct_task_types(self):
        """TODO(db-to-http): 远端无 distinct 端点，全量拉取本地去重。"""
        types = {row.get("task_type") for row in self.list_all()}
        return [task_type for task_type in types if task_type]

    def list_recent_entities(self, task_types, limit=10, status=None):
        payload: dict[str, Any] = {"task_types": list(task_types)}
        if status:
            payload["statuses"] = [status]
        page = self.page(
            payload, page_size=max(1, int(limit)),
            order_field="created_at", order_type="desc",
        )
        return page["items"]

    def count_grouped_by_status(self, task_types):
        types = list(task_types)
        result = {}
        for status in _TASK_STATUSES:
            total = self.page(
                {"task_types": types, "statuses": [status]}, page_size=1,
            )["total"]
            if total:
                result[status] = total
        return result

    def count_grouped_by_task_type(self, task_types):
        result = {}
        for task_type in task_types:
            total = self.page({"task_types": [task_type]}, page_size=1)["total"]
            if total:
                result[task_type] = total
        return result

    def count_daily_created(self, task_types, start_time):
        """窗口内按日创建计数：created_from 拉取窗口内任务，本地按日分组。

        TODO(db-to-http): 远端无 created_to/分组聚合，窗口大时数据量放大。
        """
        rows = self.list_all_filtered(
            task_types=task_types,
            created_from=start_time.isoformat() if hasattr(start_time, "isoformat") else start_time,
        )
        buckets: dict[str, int] = {}
        for row in rows:
            created = str(row.get("created_at") or "")
            if created:
                key = created[:10]
                buckets[key] = buckets.get(key, 0) + 1
        return sorted(buckets.items())

    def count_daily_completed(self, task_types, start_time):
        rows = self.list_all_filtered(
            task_types=task_types, status="completed",
            created_from=start_time.isoformat() if hasattr(start_time, "isoformat") else start_time,
        )
        buckets: dict[str, int] = {}
        for row in rows:
            end_time = self._parse_dt(row.get("end_time"))
            if end_time is None or end_time < start_time:
                continue
            key = end_time.date().isoformat()
            buckets[key] = buckets.get(key, 0) + 1
        return sorted(buckets.items())

    def list_by_ids(self, ids):
        """TODO(db-to-http): 远端无 ids 批量查询，逐 id 读取。"""
        result = []
        for task_id in ids or []:
            row = self._get_raw(task_id)
            if row is not None:
                result.append(row)
        return result

    # ---- 写 ----

    def create(self, fields, commit=True):
        return self.save(dump_row(fields, datetime_fields=self._DT_FIELDS, json_fields=("config",)))

    def update_fields(self, task_id, commit=True, **fields):
        """部分字段更新：读全行-合并-写回。

        TODO(db-to-http): 读-改-写窗口存在丢失更新竞态（任务线程并发更新
        status/current_step 场景）；单任务写入方在执行链内串行，实际冲突
        面为 任务线程 vs API 请求。Redis 裁决层接入后收敛。
        """
        row = self._get_raw(task_id)
        if row is None:
            return None
        return self.save(dump_row(
            {**row, **fields},
            datetime_fields=self._DT_FIELDS,
            json_fields=("config",),
        ))

    def clear_created_by(self, user_id, commit=False):
        """删用户时置空其创建的任务引用；返回受影响行数。

        TODO(db-to-http): 远端无 created_by 过滤与批量更新，全量扫描逐行写。
        """
        affected = 0
        for row in self.list_all():
            if row.get("created_by_user_id") == user_id:
                self.save({**row, "created_by_user_id": None})
                affected += 1
        return affected

    def delete(self, task_id, commit=True):
        row = self._get_raw(task_id)
        if row is None:
            return False
        try:
            super().delete(task_id)
        except SdkNotFoundError:
            return False
        return True

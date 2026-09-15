"""TaskResult / TaskResultReturn HTTP 仓储
（本地对应 app/repositories/task_result_repository.py）。

远端 GetParamTaskResultsListRequestDto 支持 task_ids[] / success 过滤；
GetParamTaskResultsReturnListRequestDto 支持 task_id / stock_code /
start_return_date / end_return_date 过滤。join 语义（get_with_task_type、
list_paginated 的任务类型过滤）按"每表一次查询 + 业务层拼接"实现。
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from app.repositories.http_backend.base import (
    HttpRepositoryBase,
    RemoteRecord,
    dump_row,
    normalize_bool_fields,
)
from app.remote_api import RemoteApiNotFoundError

# /api/results 列表的历史精简投影键（本地 _RESULT_SUMMARY_FIELDS 语义）。
_RESULT_SUMMARY_KEYS = ("id", "task_id", "step_index", "success", "timestamp")


class TaskResultHttpRepository(HttpRepositoryBase):
    """task_results（数值主键）与 task_results_return 双表远程访问。"""

    group_name = "param_task_results"
    _RETURN_GROUP = "param_task_results_return"

    _DT_FIELDS = ("timestamp", "created_at", "updated_at")
    _RETURN_DT_FIELDS = ("stock_date", "start_return_date", "end_return_date",
                         "created_at", "updated_at")
    _BOOL_FIELDS = ("success",)

    def normalize_record(self, record):
        return normalize_bool_fields(dict(record), *self._BOOL_FIELDS)

    def _normalize_return(self, record):
        return RemoteRecord(dict(record))

    def to_api_payload(self, payload):
        return dump_row(payload, datetime_fields=self._DT_FIELDS)

    # ---- 内部工具 ----

    def _get_raw(self, result_id):
        try:
            raw = self.api.param_task_results.get_info_by_id(
                {"id": self.normalize_id(result_id)}
            )
        except RemoteApiNotFoundError:
            return None
        return self.normalize_record(dict(raw)) if isinstance(raw, dict) else None

    def _get_return_raw(self, pk):
        raw = self.api.param_task_results_return.get_info_by_id({"id": int(pk)})
        return self._normalize_return(dict(raw)) if isinstance(raw, dict) else None

    def _task_exists(self, task_id) -> bool:
        raw = self.api.param_tasks.get_info_by_id({"id": str(task_id)})
        return isinstance(raw, dict)

    def _results_by_task_ids(self, task_ids, *, success=None, order_desc=True):
        """task_ids 分块（远端数组参数）过滤查询，合并后按 timestamp 排序。"""
        merged: list[dict[str, Any]] = []
        chunk_size = 100
        ids = list(task_ids)
        for start in range(0, len(ids), chunk_size):
            payload: dict[str, Any] = {"task_ids": ids[start:start + chunk_size]}
            if success is not None:
                payload["success"] = success
            merged.extend(self.iter_pages(payload, order_field="timestamp",
                                          order_type="desc" if order_desc else "asc"))
        merged.sort(
            key=lambda row: (str(row.get("timestamp") or ""), int(row.get("id") or 0)),
            reverse=order_desc,
        )
        return merged

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

    # ---- TaskResult 读 ----

    def get(self, result_id):
        return self._get_raw(result_id)

    def get_with_task_type(self, result_id):
        """返回结果 dict 并附带 task_type 键（两表各查一次拼接）。"""
        result = self._get_raw(result_id)
        if result is None:
            return None
        raw_task = self.api.param_tasks.get_info_by_id(
            {"id": str(result.get("task_id"))}
        )
        result["task_type"] = raw_task.get("task_type") if isinstance(raw_task, dict) else None
        return result

    def list_by_task(self, task_id):
        rows = self._results_by_task_ids([task_id])
        rows.sort(key=lambda row: (int(row.get("step_index") or 0), int(row.get("id") or 0)))
        return rows

    def list_by_task_paginated(self, task_id, page, per_page):
        """任务详情结果分页 + 成功/失败计数（本地 step asc 排序语义）。"""
        current_page = max(page or 1, 1)
        size = max(min(per_page or 20, 100), 1)
        # 本地排序语义为 step_index asc, id asc：整集排序后本地切片。
        rows = sorted(
            self.list_all({"task_ids": [task_id]}),
            key=lambda row: (int(row.get("step_index") or 0), int(row.get("id") or 0)),
        )
        total = len(rows)
        start = (current_page - 1) * size
        data = {
            "items": rows[start:start + size],
            "total": total,
            "pages": (total + size - 1) // size if size else 0,
            "current_page": current_page,
            "per_page": size,
        }
        data.update(self.count_by_task_success(task_id))
        return data

    def list_paginated(self, page, per_page, task_id=None):
        """/api/results 列表（精简投影 + 任务类型过滤语义）。

        未指定 task_id 时：取存在结果的可见任务类型对应的任务 id 集，
        分块过滤结果后本地分页。TODO(db-to-http): 远端无 join/聚合端点，
        任务量大时为 O(任务数) 次调用，建议远端补 join 查询端点。
        """
        current_page = max(page or 1, 1)
        size = max(min(per_page or 20, 100), 1)

        if task_id:
            if not self._task_exists(task_id):
                return {"items": [], "total": 0, "current_page": current_page, "per_page": size}
            rows = self._results_by_task_ids([task_id])
        else:
            distinct_types = {
                row.get("task_type")
                for row in self.iter_pages({}, group="param_tasks")
                if row.get("task_type")
            }
            if not distinct_types:
                return {"items": [], "total": 0, "current_page": current_page, "per_page": size}
            task_ids = [
                row["id"]
                for row in self.iter_pages({"task_types": sorted(distinct_types)}, group="param_tasks")
            ]
            if not task_ids:
                return {"items": [], "total": 0, "current_page": current_page, "per_page": size}
            rows = self._results_by_task_ids(task_ids)

        total = len(rows)
        start = (current_page - 1) * size
        items = [
            {
                "id": row.get("id"),
                "task_id": row.get("task_id"),
                "step_index": row.get("step_index"),
                "success": row.get("success"),
                "timestamp": row.get("timestamp"),
            }
            for row in rows[start:start + size]
        ]
        return {"items": items, "total": total, "current_page": current_page, "per_page": size}

    def count_by_task_success(self, task_id):
        """{total_success, total_failed}：success 布尔过滤各查一次 total。"""
        success = self.page({"task_ids": [task_id], "success": True}, page_size=1)["total"]
        failed = self.page({"task_ids": [task_id], "success": False}, page_size=1)["total"]
        return {"total_success": success, "total_failed": failed}

    def latest_time_by_task(self, task_id):
        """任务最新结果时间（ISO 字符串或 None）。"""
        page = self.page(
            {"task_ids": [task_id]}, page_size=1,
            order_field="timestamp", order_type="desc",
        )
        items = page["items"]
        return items[0].get("timestamp") if items else None

    # ---- TaskResultReturn 读 ----

    def get_return_entity(self, pk):
        """TaskResultReturn 实体形态（RemoteRecord 属性兼容）。"""
        return self._get_return_raw(pk)

    def list_return_entities(self, ids):
        """按主键批量取收益序列实体。TODO(db-to-http): 逐 id 读取。"""
        result = []
        for item in {value for value in ids if value}:
            row = self._get_return_raw(item)
            if row is not None:
                result.append(row)
        return result

    def list_return_entities_in_write_order(self, task_id):
        """按任务直查收益序列实体，主键升序（写入序）。"""
        rows = list(self.iter_pages({"task_id": task_id}, group=self._RETURN_GROUP))
        rows.sort(key=lambda row: int(row.get("id") or 0))
        return [self._normalize_return(row) for row in rows]

    # ---- 预览/导出 ----

    def list_preview_entities(self, task_id, result_ids=None, success_only=False):
        """全局预览结果实体（RemoteRecord 属性兼容消费）。"""
        payload: dict[str, Any] = {"task_id": task_id}
        if success_only:
            payload["success"] = True
        rows = list(self.iter_pages(payload))
        if result_ids is not None:
            wanted = set(result_ids)
            rows = [row for row in rows if row.get("id") in wanted]
        rows.sort(key=lambda row: (
            int(row.get("step_index") or 0),
            str(row.get("timestamp") or ""),
            int(row.get("id") or 0),
        ))
        return [self.normalize_record(row) for row in rows]

    def get_export_entity(self, result_id):
        """结果导出链路实体；不存在返回 None（保留 result 原始 JSON 串语义）。"""
        return self._get_raw(result_id)

    def list_preview_index_rows(self, task_id):
        """全局预览轻量参数索引。

        NOTE(db-to-http): 远端无列投影，整行返回（含 result 大字段），
        网络放大待远端投影端点收敛。
        """
        rows = list(self.iter_pages({"task_id": task_id}))
        rows.sort(key=lambda row: (int(row.get("step_index") or 0), int(row.get("id") or 0)))
        return [
            {
                "id": row.get("id"),
                "parameters": row.get("parameters"),
                "success": row.get("success"),
                "step_index": row.get("step_index"),
            }
            for row in rows
        ]

    def list_by_task_paginated_raw_parameters(self, task_id, page, per_page):
        """回测详情页结果分页：parameters 保持原始 JSON 串。"""
        current_page = max(page or 1, 1)
        size = max(min(per_page or 10, 100), 1)
        rows = [
            row for row in self.iter_pages({"task_id": task_id})
        ]
        rows.sort(key=lambda row: (
            int(row.get("step_index") or 0),
            str(row.get("timestamp") or ""),
            int(row.get("id") or 0),
        ))
        total = len(rows)
        start = (current_page - 1) * size
        page_rows = rows[start:start + size]
        return {
            "items": [
                {
                    "id": row.get("id"),
                    "task_id": row.get("task_id"),
                    "step_index": row.get("step_index"),
                    "parameters": row.get("parameters"),
                    "success": row.get("success"),
                    "error_message": row.get("error_message"),
                    "timestamp": row.get("timestamp"),
                }
                for row in page_rows
            ],
            "total": total,
            "pages": (total + size - 1) // size if size else 0,
            "current_page": current_page,
            "per_page": size,
            "has_prev": current_page > 1,
            "has_next": current_page * size < total,
            "prev_num": current_page - 1 if current_page > 1 else None,
            "next_num": current_page + 1 if current_page * size < total else None,
        }

    def list_export_rows(self, task_ids):
        """批量导出投影：(task_id, step_index, result 原始 JSON 串)。"""
        if not task_ids:
            return []
        rows = self._results_by_task_ids(list(task_ids))
        rows.sort(key=lambda row: (str(row.get("task_id") or ""), int(row.get("step_index") or 0)))
        return [
            {
                "task_id": row.get("task_id"),
                "step_index": row.get("step_index"),
                "result": row.get("result"),
            }
            for row in rows
        ]

    # ---- TaskResult 写 ----

    def create(self, fields, commit: bool = True):
        return self.save(dump_row(fields, datetime_fields=self._DT_FIELDS))

    def create_with_return(self, result_fields, return_fields=None, commit=True):
        """TaskResult + TaskResultReturn 写入并回链 return_series_id。

        TODO(db-to-http): 远端无跨表事务，两表顺序独立提交，中途失败会留下
        孤儿收益序列行；return_series_id 通过"写入后按 task_id 倒序回查"
        取回（同任务并发写入时存在取错行竞态，执行链内同任务串行写入）。
        """
        return_series_id = None
        if return_fields:
            saved_return = self.api.param_task_results_return.modify_or_add(
                dump_row(return_fields, datetime_fields=self._RETURN_DT_FIELDS),
            )
            if isinstance(saved_return, dict) and saved_return.get("id") is not None:
                return_series_id = saved_return["id"]
            else:
                # 远端 ModifyOrAdd 不回显记录：按 id 倒序回查该任务最新一行。
                page = self.page(
                    {"task_id": return_fields.get("task_id")},
                    page_size=1,
                    order_field="id", order_type="desc",
                    group=self._RETURN_GROUP,
                )
                items = page["items"]
                if items:
                    return_series_id = items[0].get("id")

        result_fields = dict(result_fields)
        if return_series_id is not None:
            result_fields["return_series_id"] = return_series_id
        return self.save(dump_row(result_fields, datetime_fields=self._DT_FIELDS))

    def delete(self, result_id, commit=True):
        row = self._get_raw(result_id)
        if row is None:
            return False
        try:
            self.api.param_task_results.delete({"id": self.normalize_id(result_id)})
        except RemoteApiNotFoundError:
            return False
        return True

    def delete_by_task(self, task_id, commit=True):
        """TODO(db-to-http): 远端无按条件删除，逐 id 删除（非原子）。"""
        deleted = 0
        for row in list(self.iter_pages({"task_id": task_id})):
            try:
                self.api.param_task_results.delete({"id": self.normalize_id(row["id"])})
                deleted += 1
            except RemoteApiNotFoundError:
                continue
        return deleted

    def list_entities_by_task_ordered(self, task_id):
        """任务结果实体（step asc）。"""
        rows = list(self.iter_pages({"task_id": task_id}))
        rows.sort(key=lambda row: int(row.get("step_index") or 0))
        return [self.normalize_record(row) for row in rows]

    def list_return_entities_by_task(self, task_id):
        """任务收益序列实体（stock_date asc）。"""
        rows = list(self.iter_pages({"task_id": task_id}, group=self._RETURN_GROUP))
        rows.sort(key=lambda row: str(row.get("stock_date") or ""))
        return [self._normalize_return(row) for row in rows]

    def list_step_indexes_by_task(self, task_id):
        return [
            int(row["step_index"])
            for row in self.iter_pages({"task_id": task_id})
            if row.get("step_index") is not None and int(row["step_index"]) >= 0
        ]

    def list_ids_by_task(self, task_id):
        return [row["id"] for row in self.iter_pages({"task_id": task_id})]

    def list_return_series_ids_by_task(self, task_id):
        """任务全部非空 return_series_id（按 id asc）。"""
        rows = [row for row in self.iter_pages({"task_id": task_id}) if row.get("return_series_id") is not None]
        rows.sort(key=lambda row: int(row.get("id") or 0))
        return [row["return_series_id"] for row in rows]

    def list_return_ids_by_task(self, task_id):
        return [
            row["id"]
            for row in self.iter_pages({"task_id": task_id}, group=self._RETURN_GROUP)
        ]

    def list_ids_older_than(self, cutoff, limit):
        """到期结果 id 分批读取；远端无时间过滤，全量扫描本地筛选。

        TODO(db-to-http): results 表持续增长，清理窗口建议远端补时间过滤。
        """
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
        """按 id 集合删除；返回删除行数（逐行非原子，TODO 同上）。"""
        if not ids:
            return 0
        deleted = 0
        for record_id in ids:
            try:
                self.api.param_task_results.delete({"id": self.normalize_id(record_id)})
                deleted += 1
            except RemoteApiNotFoundError:
                continue
        return deleted

    def delete_returns_by_task(self, task_id, commit=True):
        deleted = 0
        for row in list(self.iter_pages({"task_id": task_id}, group=self._RETURN_GROUP)):
            try:
                self.api.param_task_results_return.delete(
                    {"id": self.normalize_id(row["id"])}
                )
                deleted += 1
            except RemoteApiNotFoundError:
                continue
        return deleted

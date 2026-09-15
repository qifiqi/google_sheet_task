"""回测相关 HTTP 仓储：TaskResultSummaryIndex / BacktestProductResultCache /
BacktestSheetRunLock / XplAnalysisJobs（本地对应 app/repositories/backtest_repository.py）。

窗口函数（dedupe_best_per_task / page_summary_index 的 best_per_stock）远端无
等价端点，退化为过滤拉取 + 本地分组去重；acquire/release 锁语义保留读-改-写
（TODO Redis 裁决层）。所有窗口/锁方法均带 TODO 标注。
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
from app.remote_api import RemoteApiDuplicateKeyError, RemoteApiNotFoundError


_SUMMARY_GROUP = "param_task_result_summary_index"
_CACHE_GROUP = "param_backtest_product_result_cache"
_LOCK_GROUP = "param_backtest_sheet_run_locks"
_XPL_GROUP = "param_xpl_analysis_jobs"


class BacktestHttpRepository(HttpRepositoryBase):
    """回测聚合仓储（不绑定单一 model，四个远端控制器分组）。"""

    group_name = _SUMMARY_GROUP

    def normalize_record(self, record):
        return normalize_bool_fields(dict(record), "is_best")

    def _dt(self, value):
        if isinstance(value, datetime):
            return value
        if isinstance(value, str) and value:
            try:
                return datetime.fromisoformat(value)
            except ValueError:
                return None
        return None

    def _delete_ids(self, group, ids) -> int:
        deleted = 0
        for record_id in ids:
            try:
                self._controller(group).delete({"id": self.normalize_id(record_id)})
                deleted += 1
            except RemoteApiNotFoundError:
                continue
        return deleted

    # ---- XplAnalysisJobs（遗留绩效分析任务清理） ----

    def delete_legacy_performance_analysis_jobs(
        self,
        *,
        task_id=None,
        result_ids=None,
        return_series_ids=None,
        commit: bool = True,
    ):
        """遗留绩效分析任务清理；HTTP 模式远端表恒存在，按条件全量扫描删除。

        TODO(db-to-http): xpl_jobs 分页无过滤字段，全量扫描本地筛选；
        建议远端补 task_id 过滤（迁移文档无法接入清单）。
        """

        def _match(row: dict[str, Any]) -> bool:
            if task_id and row.get("task_id") == task_id:
                return True
            if result_ids and row.get("task_result_id") in set(result_ids):
                return True
            if return_series_ids and row.get("return_series_id") in set(return_series_ids):
                return True
            return False

        victims = [row["id"] for row in self.iter_pages({}, group=_XPL_GROUP) if _match(row)]
        self._delete_ids(_XPL_GROUP, victims)

    # ---- TaskResultSummaryIndex 读 ----

    def list_summary_index_entities_by_result(self, task_result_id):
        rows = list(self.iter_pages({"task_result_id": task_result_id}))
        return [self.normalize_record(row) for row in rows]

    def get_task_result_pair(self, task_result_id):
        """(Task, TaskResult) 记录对（RemoteRecord 属性兼容 join 替代）。"""
        result = self.api.param_task_results.get_info_by_id(
            {"id": self.normalize_id(task_result_id)}
        )
        if not isinstance(result, dict):
            return None
        raw_task = self.api.param_tasks.get_info_by_id(
            {"id": str(result.get("task_id"))}
        )
        if not isinstance(raw_task, dict):
            return None
        return (RemoteRecord(dict(raw_task)), RemoteRecord(dict(result)))

    def list_task_ids_by_visible_types(self, visible_types, task_id=None, stock_code=None):
        """可见类型任务 id；stock_code 对 name/config 的模糊匹配在本地完成。

        TODO(db-to-http): 远端 keyword 不保证覆盖 config 大字段，本地判读。
        """
        result = []
        for row in self.iter_pages({"task_types": list(visible_types)}, group="param_tasks"):
            if task_id and row.get("id") != task_id:
                continue
            config = row.get("config")
            if isinstance(config, (dict, list)):
                import json as _json

                config = _json.dumps(config, ensure_ascii=False)
            hay = f"{row.get('name') or ''}{config or ''}"
            if stock_code and str(stock_code) not in hay:
                continue
            result.append(row["id"])
        return result

    def _fetch_results_for_tasks(self, matched_task_ids, result_id=None):
        if not matched_task_ids:
            return []
        if result_id:
            row = self.api.param_task_results.get_info_by_id(
                {"id": self.normalize_id(result_id)}
            )
            if isinstance(row, dict) and row.get("task_id") in set(matched_task_ids) and row.get("success"):
                return [RemoteRecord(dict(row))]
            return []
        return self._results_success_by_ids(matched_task_ids)

    def _results_success_by_ids(self, task_ids):
        """task_ids 分块 success=True 过滤查询（结果按 timestamp desc 排序）。"""
        merged: list[dict[str, Any]] = []
        chunk = 100
        ids = list(task_ids)
        for start in range(0, len(ids), chunk):
            payload = {"task_ids": ids[start:start + chunk], "success": True}
            merged.extend(self.iter_pages(payload, group="param_task_results",
                                          order_field="timestamp", order_type="desc"))
        merged.sort(key=lambda row: (str(row.get("timestamp") or ""), int(row.get("id") or 0)),
                    reverse=True)
        return merged

    def list_task_result_pairs_by_filters(self, matched_task_ids, result_id=None):
        """(Task, TaskResult) 记录对列表；任务详情按 id 缓存拼接。"""
        results = self._fetch_results_for_tasks(matched_task_ids, result_id=result_id)
        pairs = []
        task_cache: dict[str, RemoteRecord] = {}
        for result in results:
            task_key = str(result.get("task_id"))
            if task_key not in task_cache:
                raw_task = self.api.param_tasks.get_info_by_id({"id": task_key})
                if not isinstance(raw_task, dict):
                    continue
                task_cache[task_key] = RemoteRecord(dict(raw_task))
            pairs.append((task_cache[task_key], result))
        return pairs

    def list_finished_task_ids(self, finished_statuses, supported_types, task_type=None, task_id=None):
        payload: dict[str, Any] = {"statuses": list(finished_statuses)}
        payload["task_types"] = [task_type] if task_type else list(supported_types)
        rows = [
            row for row in self.iter_pages(payload, group="param_tasks",
                                           order_field="created_at", order_type="asc")
            if not task_id or row.get("id") == task_id
        ]
        return [row["id"] for row in rows]

    def list_task_result_pairs_for_rebuild(self, task_ids):
        results = self._results_success_by_ids(task_ids)
        results.sort(key=lambda row: (str(row.get("task_id") or ""), int(row.get("id") or 0)))
        pairs = []
        task_cache: dict[str, RemoteRecord] = {}
        for result in results:
            task_key = str(result.get("task_id"))
            if task_key not in task_cache:
                raw_task = self.api.param_tasks.get_info_by_id({"id": task_key})
                if not isinstance(raw_task, dict):
                    continue
                task_cache[task_key] = RemoteRecord(dict(raw_task))
            pairs.append((task_cache[task_key], result))
        return pairs

    # ---- TaskResultSummaryIndex 写/删 ----

    def delete_summary_index_by_task_ids(self, task_ids, commit=True):
        """TODO(db-to-http): 逐 task_id 查询后逐 id 删除（非原子）。"""
        deleted = 0
        for task_id in task_ids:
            ids = [row["id"] for row in self.iter_pages({"task_id": task_id})]
            deleted += self._delete_ids(_SUMMARY_GROUP, ids)
        return deleted

    def dedupe_best_per_task(self, group_expression=None, task_type=None, task_id=None, commit: bool = True):
        """按分组保留每组最新最优一条；返回删除行数。

        TODO(db-to-http): 远端无窗口函数端点，过滤拉取 + 本地分组复现；
        大任务量下为 O(索引行数) 拉取，建议远端补窗口删除端点
        （迁移文档无法接入清单）。
        """
        payload: dict[str, Any] = {}
        if task_id:
            payload["task_id"] = task_id
        if task_type:
            payload["task_type"] = task_type
        rows = list(self.iter_pages(payload))

        def group_key(row: dict[str, Any]) -> tuple:
            return (
                row.get("task_id"),
                row.get("period_key") or "",
                row.get("year_label") or "",
                row.get("kline_range") or "",
            )

        def rank_key(row: dict[str, Any]) -> tuple:
            ts = self._dt(row.get("result_timestamp"))
            return (
                (ts.date().isoformat() if ts else ""),
                float(row.get("best_metric_value") or 0),
                int(row.get("id") or 0),
            )

        groups: dict[tuple, list[dict[str, Any]]] = {}
        for row in rows:
            groups.setdefault(group_key(row), []).append(row)

        deleted = 0
        for members in groups.values():
            members.sort(key=rank_key, reverse=True)
            keep, *dupes = members
            if dupes:
                deleted += self._delete_ids(_SUMMARY_GROUP, [row["id"] for row in dupes])
            if not keep.get("is_best"):
                self.save({**keep, "is_best": True})
        return deleted

    def list_summary_index_entities_by_task_ordered(self, task_id):
        """任务汇总实体（对齐本地排序：date desc, metric desc,
        period/year/kline asc, id desc；多向排序用稳定多趟实现）。"""
        rows = list(self.iter_pages({"task_id": task_id}))
        rows.sort(key=lambda row: int(row.get("id") or 0), reverse=True)
        rows.sort(key=lambda row: str(row.get("kline_range") or ""))
        rows.sort(key=lambda row: str(row.get("year_label") or ""))
        rows.sort(key=lambda row: str(row.get("period_key") or ""))
        rows.sort(key=lambda row: float(row.get("best_metric_value") or 0), reverse=True)
        rows.sort(key=lambda row: (
            self._dt(row.get("result_timestamp")).date().isoformat()
            if self._dt(row.get("result_timestamp")) else ""
        ), reverse=True)
        return [self.normalize_record(row) for row in rows]

    def count_index_rows(self, task_type=None, task_id=None):
        payload: dict[str, Any] = {}
        if task_id:
            payload["task_id"] = task_id
        if task_type:
            payload["task_type"] = task_type
        return self.page(payload, page_size=1)["total"]

    def delete_summary_index_by_scope(self, task_type=None, task_id=None, commit=True):
        payload: dict[str, Any] = {}
        if task_id:
            payload["task_id"] = task_id
        if task_type:
            payload["task_type"] = task_type
        ids = [row["id"] for row in self.iter_pages(payload)]
        return self._delete_ids(_SUMMARY_GROUP, ids)

    def page_summary_index(self, filters, page, per_page, *, best_per_stock=False):
        """汇总索引动态过滤分页查询。

        - 单值过滤（task_type/stock_keyword/market_type/period_key/
          excess_return_min/时间区间/task_id/result_id）由远端
          GetParamTaskResultSummaryIndexListRequestDto 表达；
        - visible_types（IN 列表）远端无多值过滤：逐类型查询合并；
        - best_per_stock 窗口去重本地复现（is_best + stock_code 非空过滤
          后按 stock_code 分组取组内最新最优）。
        """
        current_page = max(int(page or 1), 1)
        size = max(min(int(per_page or 20), 100), 1)

        def _base_payload(extra: dict[str, Any] | None = None) -> dict[str, Any]:
            payload: dict[str, Any] = dict(extra or {})
            if filters.get("task_type"):
                payload["task_type"] = filters["task_type"]
            if filters.get("stock_keyword"):
                payload["stock_keyword"] = filters["stock_keyword"]
            if filters.get("market_type"):
                payload["market_type"] = filters["market_type"]
            if filters.get("period_key"):
                payload["period_key"] = filters["period_key"]
            if filters.get("excess_return_min") is not None:
                payload["best_metric_value_gt"] = filters["excess_return_min"]
            if filters.get("result_date_from"):
                payload["result_timestamp_from"] = self._iso(filters["result_date_from"])
            if filters.get("result_date_to"):
                payload["result_timestamp_to"] = self._iso(filters["result_date_to"])
            if filters.get("task_id"):
                payload["task_id"] = filters["task_id"]
            if filters.get("result_id"):
                payload["task_result_id"] = int(filters["result_id"])
            return payload

        visible_types = filters.get("visible_types")
        type_list = list(visible_types) if visible_types else [None]
        rows: dict[Any, dict[str, Any]] = {}
        for task_type in type_list:
            scoped = _base_payload({"task_type": task_type} if task_type else None)
            if best_per_stock:
                scoped["is_best"] = True
            for row in self.iter_pages(scoped):
                if best_per_stock and not (row.get("stock_code") or ""):
                    continue
                rows[row["id"]] = row

        items_all = list(rows.values())
        if best_per_stock:
            best: dict[str, dict[str, Any]] = {}
            for row in items_all:
                code = row.get("stock_code")
                current = best.get(code)
                if current is None or self._rank_key(row) > self._rank_key(current):
                    best[code] = row
            items_all = list(best.values())
            # 稳定多趟：先股票代码 asc，再组内最优 rank desc（rank 为主键）。
            items_all.sort(key=lambda row: str(row.get("stock_code") or ""))
            items_all.sort(key=self._rank_key, reverse=True)
        else:
            items_all.sort(key=self._rank_key, reverse=True)

        summary_items = [
            {
                "stock_code": row.get("stock_code"),
                "task_id": row.get("task_id"),
                "best_metric_value": row.get("best_metric_value"),
            }
            for row in items_all
        ]
        total = len(items_all)
        start = (current_page - 1) * size
        return {
            "items": [self.normalize_record(row) for row in items_all[start:start + size]],
            "summary_items": summary_items,
            "total": total,
            "pages": (total + size - 1) // size if size else 0,
            "has_prev": current_page > 1,
            "has_next": current_page * size < total,
        }

    @staticmethod
    def _iso(value):
        return value.isoformat() if hasattr(value, "isoformat") else value

    def _rank_key(self, row: dict[str, Any]) -> tuple:
        ts = self._dt(row.get("result_timestamp"))
        return (
            ts.date().isoformat() if ts else "",
            float(row.get("best_metric_value") or 0),
            int(row.get("id") or 0),
        )

    def delete_summary_index_by_result_ids(self, result_ids, commit=True):
        """TODO(db-to-http): task_result_id 过滤逐值查询后逐 id 删除。"""
        deleted = 0
        for result_id in result_ids:
            ids = [
                row["id"]
                for row in self.iter_pages({"task_result_id": result_id})
            ]
            deleted += self._delete_ids(_SUMMARY_GROUP, ids)
        return deleted

    def delete_summary_index_by_task_or_results(self, task_id, result_ids, commit=True):
        victims: dict[Any, None] = {}
        for row in self.iter_pages({"task_id": task_id}):
            victims[row["id"]] = None
        for result_id in result_ids:
            for row in self.iter_pages({"task_result_id": result_id}):
                victims[row["id"]] = None
        return self._delete_ids(_SUMMARY_GROUP, list(victims))

    # ---- BacktestProductResultCache ----

    def _find_cache_rows(self, batch_id, cache_key):
        """cache 分组无过滤字段（RequsetPageDto），全量扫描本地匹配。

        TODO(db-to-http): 建议远端补 batch_id/cache_key 过滤。
        """
        return [
            row for row in self.iter_pages({}, group=_CACHE_GROUP)
            if row.get("batch_id") == batch_id and row.get("cache_key") == cache_key
        ]

    def exists_product_cache(self, batch_id, cache_key):
        return len(self._find_cache_rows(batch_id, cache_key)) > 0

    def get_product_cache(self, batch_id, cache_key):
        rows = self._find_cache_rows(batch_id, cache_key)
        return rows[0] if rows else None

    def insert_product_cache_if_absent(self, batch_id, cache_key, fields, commit=True):
        """已存在则跳过（不覆盖），返回是否新插入。

        TODO(db-to-http): 读-改-写幂等窗口；同 batch 并发写入时依赖远端
        唯一约束兜底（DuplicateKey 判失败），无约束时可能重复插入。
        """
        if self.exists_product_cache(batch_id, cache_key):
            return False
        payload = {"batch_id": batch_id, "cache_key": cache_key, **fields}
        try:
            self.api.param_backtest_product_result_cache.modify_or_add(dump_row(payload))
        except RemoteApiDuplicateKeyError:
            return False
        return True

    # ---- BacktestSheetRunLock（acquire/release 语义红线） ----

    def get_lock(self, spreadsheet_id):
        page = self.page(
            {"spreadsheet_id": spreadsheet_id}, page_size=1, group=_LOCK_GROUP,
        )
        items = page["items"]
        return items[0] if items else None

    def acquire_lock(self, spreadsheet_id, task_id, task_type, commit=True):
        """原子获取 per-sheet 运行锁；返回 (acquired, locked_task_id)。

        - 同任务已持锁 → (True, None)（幂等）；
        - 他任务持锁 → (False, 该任务 id)；
        - 无锁 → 插入行；唯一约束冲突（并发竞态）→ 复查后判失败。
        TODO(db-to-http): 读-改-写窗口存在双持锁竞态；Redis 裁决层接入前，
        单实例执行链串行调用可接受。
        """
        if not spreadsheet_id:
            return True, None
        existing = self.get_lock(spreadsheet_id)
        if existing is not None:
            if existing.get("task_id") == task_id:
                return True, None
            return False, existing.get("task_id")
        try:
            self.api.param_backtest_sheet_run_locks.modify_or_add(dump_row({
                "spreadsheet_id": spreadsheet_id,
                "task_id": task_id,
                "task_type": task_type,
            }))
        except RemoteApiDuplicateKeyError:
            existing = self.get_lock(spreadsheet_id)
            return False, existing.get("task_id") if existing else None
        return True, None

    def release_lock(self, spreadsheet_id, task_id, commit=True):
        """仅持锁任务可释放；返回是否实际删除。"""
        if not spreadsheet_id:
            return False
        lock = self.get_lock(spreadsheet_id)
        if not lock:
            return False
        if lock.get("task_id") != task_id:
            return False
        try:
            self.api.param_backtest_sheet_run_locks.delete({"id": self.normalize_id(lock["id"])})
        except RemoteApiNotFoundError:
            return False
        return True

    def release_locks_by_task(self, task_id, commit=True):
        """按任务清其持有的全部锁；返回删除行数。"""
        ids = [
            row["id"]
            for row in self.iter_pages({"task_id": task_id}, group=_LOCK_GROUP)
        ]
        return self._delete_ids(_LOCK_GROUP, ids)

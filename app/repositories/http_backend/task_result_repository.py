"""TaskResult / TaskResultReturn HTTP 仓储
（本地对应 app/repositories/task_result_repository.py）。

远端 GetParamTaskResultsListRequestDto 支持 task_ids[] / success 过滤；
GetParamTaskResultsReturnListRequestDto 支持 task_id / stock_code /
start_return_date / end_return_date 过滤。join 语义（get_with_task_type、
list_paginated 的任务类型过滤）按"每表一次查询 + 业务层拼接"实现。
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any

from app.repositories.http_backend.base import (
    HttpRepositoryBase,
    RemoteRecord,
    dump_row,
    normalize_bool_fields,
)
from app.remote_api import (
    RemoteApiNotFoundError,
    RemoteApiOperationError,
    RemoteApiProtocolError,
)
from app.remote_api.capabilities import require_e12

logger = logging.getLogger(__name__)

# /api/results 列表的历史精简投影键（本地 _RESULT_SUMMARY_FIELDS 语义）。
_RESULT_SUMMARY_KEYS = ("id", "task_id", "step_index", "success", "timestamp")

# tasks/<id>/results 字段投影允许的存储列（本地 _RESULT_FIELD_COLUMNS 的键集）；
# return_date_range 为计算字段（收益序列首末日期），不在列集里。
_RESULT_FIELD_KEYS = (
    "id",
    "task_id",
    "step_index",
    "parameters",
    "result",
    "return_series_id",
    "success",
    "error_message",
    "timestamp",
)


def _json_dict(value):
    """parameters/result 的 JSON 对象解析（坏 JSON 静默降级空 dict，对齐本地）。"""
    if isinstance(value, dict):
        return value
    try:
        parsed = json.loads(value) if value else {}
    except (TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _iso_date(value):
    """日期值 → ISO 字符串；空值返回 None（本地 isoformat 语义）。"""
    if value is None or value == "":
        return None
    return value if isinstance(value, str) else value.isoformat()


def _parse_stock_dates(stock_date) -> list[str]:
    """stock_date JSON 数组解析（坏 JSON 静默降级空列表，对齐本地）。"""
    try:
        dates = json.loads(stock_date) if stock_date else []
    except (TypeError, ValueError):
        return []
    return [date for date in dates if date]


class TaskResultHttpRepository(HttpRepositoryBase):
    """task_results（数值主键）与 task_results_return 双表远程访问。"""

    group_name = "param_task_results"
    capture_insert_id = True
    _RETURN_GROUP = "param_task_results_return"

    _DT_FIELDS = ("timestamp", "created_at", "updated_at")
    _RETURN_DT_FIELDS = ("stock_date", "start_return_date", "end_return_date",
                         "created_at", "updated_at")
    _BOOL_FIELDS = ("success",)

    def normalize_record(self, record):
        return RemoteRecord(normalize_bool_fields(dict(record), *self._BOOL_FIELDS))

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

    def get_entity(self, result_id):
        """实体形态读取（runtime_view/results 链属性访问）；HTTP 版即 RemoteRecord。"""
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

    def list_by_task_fields(self, task_id, fields):
        """字段白名单投影任务结果列表（本地 _RESULT_FIELD_COLUMNS 语义）。

        返回键与请求 fields 一一对应、顺序同 list_by_task；return_date_range
        为计算字段。TODO(db-to-http): 远端无列投影端点（E7），整行拉取后
        本地投影，result 大字段的网络放大待远端收敛。
        """
        rows = self.list_by_task(task_id)
        ranges = (
            self._return_date_ranges(
                [row["return_series_id"] for row in rows if row.get("return_series_id")]
            )
            if "return_date_range" in fields
            else {}
        )
        items = []
        for row in rows:
            item: dict[str, Any] = {}
            for name in fields:
                if name == "return_date_range":
                    item[name] = ranges.get(row.get("return_series_id"))
                elif name == "parameters":
                    item[name] = _json_dict(row.get("parameters"))
                elif name == "result":
                    item[name] = _json_dict(row.get("result"))
                elif name in _RESULT_FIELD_KEYS:
                    item[name] = row.get(name)
            items.append(item)
        return items

    def _return_date_ranges(self, series_ids) -> dict[Any, dict[str, str | None]]:
        """批量取收益序列首末日期：{series_id: {"start": .., "end": ..}}。

        优先 start/end_return_date 落库列，历史行 NULL 时回退解析
        stock_date JSON（本地 _return_date_ranges 语义；远端无 in 查询，
        逐序列读取）。
        """
        ranges: dict[Any, dict[str, str | None]] = {}
        for series_id in series_ids:
            raw = self._get_return_raw(series_id)
            if raw is None:
                ranges[series_id] = {"start": None, "end": None}
                continue
            start = _iso_date(raw.get("start_return_date"))
            end = _iso_date(raw.get("end_return_date"))
            if start is None or end is None:
                dates = _parse_stock_dates(raw.get("stock_date"))
                start = start or (dates[0] if dates else None)
                end = end or (dates[-1] if dates else None)
            ranges[series_id] = {"start": start, "end": end}
        return ranges

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

    def list_paginated(self, page, per_page, task_id=None, success=None, keyword=None):
        """/api/results 列表：精简键 + 任务名/类型 join + success/keyword 过滤。

        - 精简键（id/task_id/step_index/success/timestamp）+ task_name/task_type
          + parameters_preview/error_preview（200 字符截断，对齐本地 substr 语义）；
        - keyword 对齐本地“任务名称或 task_id”模糊语义：经任务表 keyword 过滤
          取候选任务（远端任务 keyword 已覆盖 name/description/id）；
        - total_success/total_failed 按 success 过滤前全集聚合（对齐本地口径）；
        - TODO(db-to-http): 远端无 join/聚合端点（E6），任务量大时为 O(任务数)
          次调用；task_name/task_type 在非 keyword 路径对页内条目逐条补齐。
        """
        current_page = max(page or 1, 1)
        size = max(min(per_page or 20, 100), 1)

        task_info: dict[str, dict[str, Any]] = {}
        if task_id:
            if not self._task_exists(task_id):
                return {"items": [], "total": 0, "current_page": current_page, "per_page": size}
            task_ids = [task_id]
            raw = self.api.param_tasks.get_info_by_id({"id": str(task_id)})
            if isinstance(raw, dict):
                task_info[str(task_id)] = dict(raw)
        else:
            if keyword:
                task_rows = list(self.iter_pages({"keyword": keyword}, group="param_tasks"))
            else:
                distinct_types = {
                    row.get("task_type")
                    for row in self.iter_pages({}, group="param_tasks")
                    if row.get("task_type")
                }
                task_rows = (
                    list(self.iter_pages(
                        {"task_types": sorted(distinct_types)}, group="param_tasks",
                    ))
                    if distinct_types else []
                )
            task_ids = [row["id"] for row in task_rows]
            for row in task_rows:
                task_info[str(row["id"])] = row
            if not task_ids:
                return {"items": [], "total": 0, "current_page": current_page, "per_page": size}

        rows = self._results_by_task_ids(task_ids, order_desc=True)
        total_success = sum(1 for row in rows if row.get("success"))
        total_failed = len(rows) - total_success
        if success is not None:
            rows = [row for row in rows if bool(row.get("success")) == bool(success)]

        start = (current_page - 1) * size
        items = []
        for row in rows[start:start + size]:
            task_key = str(row.get("task_id"))
            info = task_info.get(task_key)
            if info is None:
                try:
                    raw = self.api.param_tasks.get_info_by_id({"id": task_key})
                    info = dict(raw) if isinstance(raw, dict) else {}
                except RemoteApiNotFoundError:
                    info = {}
                task_info[task_key] = info
            items.append({
                "id": row.get("id"),
                "task_id": row.get("task_id"),
                "step_index": row.get("step_index"),
                "success": row.get("success"),
                "timestamp": row.get("timestamp"),
                "task_name": info.get("name"),
                "task_type": info.get("task_type"),
                "parameters_preview": str(row.get("parameters") or "")[:200],
                "error_preview": str(row.get("error_message") or "")[:200],
            })
        return {
            "items": items,
            "total": len(rows),
            "current_page": current_page,
            "per_page": size,
            "total_success": total_success,
            "total_failed": total_failed,
        }

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
        payload: dict[str, Any] = {"task_ids": [task_id]}
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
        rows = list(self.iter_pages({"task_ids": [task_id]}))
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
            row for row in self.iter_pages({"task_ids": [task_id]})
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

    def create_with_return(
        self,
        result_fields,
        return_fields=None,
        commit=True,
        *,
        kline_series_id=None,
    ):
        """TaskResult + TaskResultReturn 写入并回链 return_series_id。

        远端无跨表事务（E4 未提供），本方法按“
        收益序列 → 结果 → 随机K线关联”顺序写入，并在失败时做尽力补偿：
        - 关联行按 id 安全删除；
        - 结果/收益行仅在确认本任务没有更早结果行（首步）时按 task_id 整删；
          存在更早结果行时不做任务级回收（会误删历史步骤），记录部分写入日志。
        return_series_id 优先取插入回执 ``ret_count``（数值主键表新 id 不回
        ``ret_obj``），缺失时按 task_id 倒序回查兜底。
        """
        task_id = (result_fields or {}).get("task_id")
        if kline_series_id:
            require_e12(self.api)
        created_return_id = None
        created_result: dict[str, Any] | None = None
        created_link_id = None
        try:
            if return_fields:
                raw, ret_count = self.api.param_task_results_return.modify_or_add(
                    dump_row(return_fields, datetime_fields=self._RETURN_DT_FIELDS),
                    with_count=True,
                )
                created_return_id = self._insert_id(raw, ret_count)
                if created_return_id is None:
                    # 远端未回显主键：按 id 倒序回查该任务最新一行。
                    page = self.page(
                        {"task_id": return_fields.get("task_id")},
                        page_size=1,
                        order_field="id", order_type="desc",
                        group=self._RETURN_GROUP,
                    )
                    items = page["items"]
                    if items:
                        created_return_id = items[0].get("id")

            payload = dict(result_fields)
            if created_return_id is not None:
                payload["return_series_id"] = created_return_id
            created_result = self.save(
                dump_row(payload, datetime_fields=self._DT_FIELDS)
            )
            # 随机K线结果关联：远端 ParamTaskResultKlineLinks（E12，2026-10-29 上线）。
            if kline_series_id:
                result_id = (created_result or {}).get("id")
                if result_id is None:
                    raise RemoteApiProtocolError(
                        "远端未回传结果主键，无法写入随机K线关联"
                    )
                link = self.api.param_task_result_kline_links.modify_or_add(dump_row({
                    "result_id": result_id,
                    "task_id": (created_result or {}).get("task_id"),
                    "series_id": int(kline_series_id),
                }))
                if isinstance(link, dict):
                    created_link_id = link.get("id")
            return created_result
        except Exception:
            self._compensate_partial_write(
                task_id, created_result, created_return_id, created_link_id
            )
            raise

    @staticmethod
    def _insert_id(raw: Any, ret_count: int | None) -> Any:
        """插入回执取 id：对象/字符串优先，数值主键表回退 ``ret_count``。"""
        if isinstance(raw, dict) and raw.get("id") is not None:
            return raw["id"]
        if isinstance(raw, str) and raw.strip():
            value = raw.strip()
            try:
                return int(value)
            except ValueError:
                return value
        if raw is None and ret_count is not None:
            return ret_count
        return None

    def _compensate_partial_write(
        self,
        task_id: Any,
        created_result: dict[str, Any] | None,
        created_return_id: Any,
        created_link_id: Any,
    ) -> None:
        """失败后的尽力补偿；任务级整删只在“首步”时安全（远端无行级删除）。"""
        if created_link_id is not None:
            try:
                self.api.param_task_result_kline_links.delete(
                    {"id": self.normalize_id(created_link_id)}
                )
            except Exception as exc:
                logger.warning("随机K线关联补偿删除失败 id=%s: %s", created_link_id, exc)
        if not task_id:
            return
        created_result_id = (created_result or {}).get("id")
        has_prior = False
        try:
            for row in self.iter_pages({"task_ids": [task_id]}, page_size=2):
                if row.get("id") != created_result_id:
                    has_prior = True
                    break
        except Exception as exc:
            logger.warning(
                "部分写入无法确认任务历史结果，跳过补偿: task_id=%s err=%s", task_id, exc
            )
            return
        if has_prior:
            logger.warning(
                "任务结果部分写入（存在更早结果行，未做任务级回收）: "
                "task_id=%s step=%s result_id=%s return_id=%s",
                task_id,
                (created_result or {}).get("step_index"),
                created_result_id,
                created_return_id,
            )
            return
        for label, controller in (
            ("结果", self.api.param_task_results),
            ("收益序列", self.api.param_task_results_return),
        ):
            try:
                controller.delete({"task_id": task_id})
            except Exception as exc:
                logger.warning(
                    "部分写入补偿删除%s失败 task_id=%s: %s", label, task_id, exc
                )

    def delete(self, result_id, commit=True):
        """删除单条结果；不存在返回 False。

        远端 ``ParamTaskResults/Delete`` 实为按 task_id 整任务删除（id 字段
        被忽略，2026-10-28 实测），行级删除无法表达：仅当目标结果是该任务
        唯一结果时等价可删，多结果任务显式报错（不做"删一条变删全部"的
        静默放大）。
        """
        row = self._get_raw(result_id)
        if row is None:
            return False
        task_id = row.get("task_id")
        siblings = list(self.iter_pages({"task_ids": [task_id]})) if task_id else []
        if len(siblings) > 1:
            raise RemoteApiOperationError(
                "远端仅支持按任务删除结果（ParamTaskResults/Delete 按 task_id 整删），"
                f"该任务还有 {len(siblings) - 1} 条其他结果，单条删除无法表达",
                code=400,
            )
        self.api.param_task_results.delete({"task_id": task_id})
        return True

    def delete_by_task(self, task_id, commit=True):
        """按任务删除全部结果；远端 Delete 按 task_id 整任务删除（单调用原子）。

        task_id 须与行内存储形式一致（本仓写入即应用原生形式）；
        行不存在时不调用远端（远端 0 行匹配报"操作失败"）。
        """
        rows = list(self.iter_pages({"task_ids": [task_id]}))
        if not rows:
            return 0
        self.api.param_task_results.delete({"task_id": task_id})
        return len(rows)

    def list_entities_by_task_ordered(self, task_id):
        """任务结果实体（step asc）。"""
        rows = list(self.iter_pages({"task_ids": [task_id]}))
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
            for row in self.iter_pages({"task_ids": [task_id]})
            if row.get("step_index") is not None and int(row["step_index"]) >= 0
        ]

    def list_ids_by_task(self, task_id):
        return [row["id"] for row in self.iter_pages({"task_ids": [task_id]})]

    def list_return_series_ids_by_task(self, task_id):
        """任务全部非空 return_series_id（按 id asc）。"""
        rows = [row for row in self.iter_pages({"task_ids": [task_id]}) if row.get("return_series_id") is not None]
        rows.sort(key=lambda row: int(row.get("id") or 0))
        return [row["return_series_id"] for row in rows]

    def list_return_ids_by_task(self, task_id):
        return [
            row["id"]
            for row in self.iter_pages({"task_id": task_id}, group=self._RETURN_GROUP)
        ]

    def list_rows_older_than(self, cutoff, limit):
        """到期结果行分批读取（行内含 task_id，供 Delete 校验）；全量扫描本地筛选。

        TODO(db-to-http): 远端无时间过滤，results 表持续增长，清理窗口建议
        远端补时间过滤与按任务批量删除端点。
        """
        rows: list[dict[str, Any]] = []
        for row in self.iter_pages({}, order_field="timestamp", order_type="asc"):
            ts = self._parse_dt(row.get("timestamp"))
            if ts is None or ts >= cutoff:
                break
            rows.append(row)
            if len(rows) >= limit:
                break
        return rows

    def delete_rows(self, rows, commit=True):
        """按行集合删除；远端无行级端点，按行归属任务去重后整任务删除。

        同任务未入批的其余行会被一并删除（远端 Delete 语义即任务级）；
        返回提交删除的批次行数。
        """
        if not rows:
            return 0
        task_ids: list[Any] = []
        seen: set[Any] = set()
        for row in rows:
            tid = row.get("task_id")
            if tid and tid not in seen:
                seen.add(tid)
                task_ids.append(tid)
        for tid in task_ids:
            self.api.param_task_results.delete({"task_id": tid})
        return len(rows)

    def delete_returns_by_task(self, task_id, commit=True):
        """按任务删除全部收益序列；远端 Delete 按 task_id 整任务删除。"""
        rows = list(self.iter_pages({"task_id": task_id}, group=self._RETURN_GROUP))
        if not rows:
            return 0
        self.api.param_task_results_return.delete({"task_id": task_id})
        return len(rows)

    # ---- 任务结果扩展读（dev_vue 合并引入；远端可表达的部分拼远端端点） ----

    def get_entity_by_return_series_id(self, return_series_id):
        """按收益序列 ID 反查所属结果实体（报告参数配置指标回读）。

        远端 return 列表无 return_series_id 过滤：先按主键取 return 行获得
        归属任务，再扫该任务结果行取最新匹配（同序列理论上只挂一条结果）。
        """
        return_raw = self._get_return_raw(return_series_id)
        if not isinstance(return_raw, dict):
            return None
        task_id = return_raw.get("task_id")
        if not task_id:
            return None
        rows = [
            row
            for row in self.iter_pages({"task_ids": [task_id]})
            if row.get("return_series_id") == return_series_id
        ]
        if not rows:
            return None
        rows.sort(key=lambda row: int(row.get("id") or 0))
        return self.normalize_record(rows[-1])

    def list_recent_entities_by_task(self, task_id, limit=30):
        """任务最近 N 条结果实体（step desc/id desc 取尾；RemoteRecord 属性兼容）。"""
        rows = list(self.iter_pages({"task_ids": [task_id]}))
        rows.sort(key=lambda row: (int(row.get("step_index") or 0), int(row.get("id") or 0)), reverse=True)
        return [self.normalize_record(row) for row in rows[: max(1, int(limit))]]

    def get_latest_return_series_id(self, task_id):
        """任务最新一条非空 return_series_id（id desc 语义）；无则 None。"""
        ids = self.list_return_series_ids_by_task(task_id)
        return ids[-1] if ids else None

    def list_recent_return_columns_by_task(self, task_id, limit=120):
        """任务最近 N 条收益序列的 (stock_date, index_return, start_return) 投影
        （stock_date desc 取尾，调用方自行反转为升序）。"""
        rows = list(self.iter_pages({"task_id": task_id}, group=self._RETURN_GROUP))
        rows.sort(key=lambda row: str(row.get("stock_date") or ""), reverse=True)
        return [
            {
                "stock_date": row.get("stock_date"),
                "index_return": row.get("index_return"),
                "start_return": row.get("start_return"),
            }
            for row in rows[: max(1, int(limit))]
        ]

    # ---- 随机K线结果关联（ParamTaskResultKlineLinks，E12 端点 2026-10-29 上线） ----

    def count_by_kline_series(self, task_id: str, series_id: int) -> int:
        page = self.page(
            {"task_id": task_id, "series_id": series_id},
            group="param_task_result_kline_links",
        )
        return int(page.get("total") or 0)

    def list_by_kline_series(
        self,
        task_id: str,
        series_id: int,
        offset: int | None = None,
        limit: int | None = None,
    ):
        """使用指定随机K线序列的结果列表（审计反查，按执行顺序）。

        关联行与结果行分属两个控制器：先取关联 result_id 分页，再远端按
        task_id 拉结果行过滤（TODO(db-to-http): 远端补 result_ids 过滤）。
        """
        links = list(self.iter_pages(
            {"task_id": task_id, "series_id": series_id},
            group="param_task_result_kline_links",
        ))
        links.sort(key=lambda row: int(row.get("id") or 0))
        if offset is not None:
            links = links[offset:]
        if limit is not None:
            links = links[:limit]
        wanted = {int(row.get("result_id") or 0) for row in links}
        wanted.discard(0)
        if not wanted:
            return []
        rows = [
            row for row in self.iter_pages({"task_id": task_id})
            if row.get("id") in wanted
        ]
        rows.sort(key=lambda row: (int(row.get("step_index") or 0), int(row.get("id") or 0)))
        return [
            {
                "id": row.get("id"),
                "step_index": row.get("step_index"),
                "success": row.get("success"),
                "timestamp": self._parse_dt(row.get("timestamp")),
            }
            for row in rows
        ]


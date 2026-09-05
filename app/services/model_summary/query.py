"""单模型历史结果汇总索引 · 查询编排（facade 的查询 mixin）。"""

from __future__ import annotations

import math
from datetime import datetime
from typing import Any

from app.exceptions import ValidationError
from app.repositories import backtest_repository
from app.services.model_summary import extractor
from app.utils.task_types import normalize_task_type


class SummaryQueryMixin:
    """汇总索引查询：best_only 走索引分页，best_only=false 走全量结果聚合。"""

    def query(
        self,
        user: Any,
        filters: dict[str, Any],
        *,
        ignore_permissions: bool = False,
    ) -> dict[str, Any]:
        """处理query相关逻辑。"""
        page = max(int(filters.get("page") or 1), 1)
        per_page = min(max(int(filters.get("per_page") or 50), 1), 200)
        task_type = str(filters.get("task_type") or "").strip()
        result_date_from = str(filters.get("result_date_from") or "").strip()
        result_date_to = str(filters.get("result_date_to") or "").strip()
        stock_code = str(filters.get("stock_code") or "").strip()
        market_type = extractor._normalize_market_type(filters.get("market_type"))
        excess_return_min = extractor._normalize_excess_return_min(filters.get("excess_return_min"))
        period_filter = str(filters.get("period_filter") or "").strip()
        best_only = str(filters.get("best_only", "true")).lower() not in {"false", "0", "no"}

        if not best_only:
            return self._query_all_results(
                user,
                filters,
                page,
                per_page,
                task_type,
                stock_code,
                ignore_permissions=ignore_permissions,
            )

        allowed_types = extractor.SUPPORTED_TASK_TYPES
        if not allowed_types:
            return self._empty_response(page, per_page)

        index_filters: dict[str, Any] = {
            "stock_keyword": stock_code,
            "market_type": market_type,
            "period_key": period_filter,
            "excess_return_min": excess_return_min,
        }

        if task_type:
            if task_type not in allowed_types:
                return self._empty_response(page, per_page, columns=self._columns_for_task_type(task_type))
            index_filters["task_type"] = task_type
        else:
            visible_types = [
                allowed_type
                for allowed_type in allowed_types
                if normalize_task_type(allowed_type) != "backtest_training"
            ]
            if not visible_types:
                return self._empty_response(page, per_page)
            index_filters["visible_types"] = visible_types

        # 添加时间范围查询（无效日期格式忽略，与原逻辑一致）
        if result_date_from:
            try:
                index_filters["result_date_from"] = datetime.strptime(result_date_from, "%Y-%m-%d")
            except ValueError:
                pass  # 忽略无效的日期格式

        if result_date_to:
            try:
                # 包含结束日期的整天
                index_filters["result_date_to"] = datetime.strptime(
                    result_date_to, "%Y-%m-%d"
                ).replace(hour=23, minute=59, second=59)
            except ValueError:
                pass  # 忽略无效的日期格式

        task_id = str(filters.get("task_id") or "").strip()
        if task_id:
            index_filters["task_id"] = task_id

        result_id = filters.get("result_id")
        if result_id:
            index_filters["result_id"] = result_id

        summary_type = str(filters.get("summary_type") or "task").strip().lower()
        if summary_type not in {"task", "stock"}:
            summary_type = "task"

        page_data = backtest_repository.page_summary_index(
            index_filters, page, per_page, best_per_stock=(summary_type == "stock")
        )
        summary = self._summary_from_items(page_data["summary_items"])

        return {
            "status": "success",
            "summary_type": summary_type,
            "columns": self._columns_for_task_type(task_type),
            "summary": summary,
            "items": page_data["items"],
            "pagination": {
                "page": page,
                "per_page": per_page,
                "total": page_data["total"],
                "pages": page_data["pages"],
                "has_prev": page_data["has_prev"],
                "has_next": page_data["has_next"],
            },
        }

    def _query_all_results(
        self,
        user: Any,
        filters: dict[str, Any],
        page: int,
        per_page: int,
        task_type: str,
        stock_code: str,
        *,
        ignore_permissions: bool = False,
    ) -> dict[str, Any]:
        """处理_query_all_results相关逻辑。"""
        columns = self._columns_for_task_type(task_type)
        market_type = extractor._normalize_market_type(filters.get("market_type"))
        excess_return_min = extractor._normalize_excess_return_min(filters.get("excess_return_min"))
        period_filter = str(filters.get("period_filter") or "").strip()
        if not stock_code:
            raise ValidationError("查询全部结果时必须输入单个股票代码")

        allowed_types = extractor.SUPPORTED_TASK_TYPES
        if not allowed_types:
            return self._empty_response(page, per_page, columns=columns)
        if task_type:
            if task_type not in allowed_types:
                return self._empty_response(page, per_page, columns=columns)
            visible_types = [task_type]
        else:
            visible_types = [
                allowed_type
                for allowed_type in allowed_types
                if normalize_task_type(allowed_type) != "backtest_training"
            ]
        if not visible_types:
            return self._empty_response(page, per_page, columns=columns)

        task_id = str(filters.get("task_id") or "").strip()
        result_id = filters.get("result_id")
        matched_task_ids = backtest_repository.list_task_ids_by_visible_types(
            visible_types,
            task_id=task_id,
            stock_code=stock_code,
        )
        if not matched_task_ids:
            return self._empty_response(page, per_page, columns=columns)

        pairs = backtest_repository.list_task_result_pairs_by_filters(
            matched_task_ids,
            result_id=result_id,
        )

        rows: list[extractor.SummaryRecord] = []
        for task, result in pairs:
            rows.extend(
                row
                for row in extractor._extract_candidate_records(task, result)
                if extractor._matches_market_type(row.stock_code, market_type)
            )
        if excess_return_min is not None:
            rows = [
                row
                for row in rows
                if row.best_metric_value is not None and row.best_metric_value > excess_return_min
            ]
        if period_filter:
            rows = [row for row in rows if row.period_key == period_filter]

        total = len(rows)
        start = (page - 1) * per_page
        paged_rows = rows[start:start + per_page]
        pages = math.ceil(total / per_page) if total else 0
        records = [self._record_to_dict(row) for row in rows]
        summary = self._summary_from_items(records)
        return {
            "status": "success",
            "summary_type": str(filters.get("summary_type") or "task"),
            "columns": columns,
            "summary": summary,
            "items": [self._record_to_dict(row) for row in paged_rows],
            "pagination": {
                "page": page,
                "per_page": per_page,
                "total": total,
                "pages": pages,
                "has_prev": page > 1,
                "has_next": page < pages,
            },
        }

    def _record_to_dict(self, row: extractor.SummaryRecord) -> dict[str, Any]:
        """处理_record_to_dict相关逻辑。"""
        return {
            "id": None,
            "task_id": row.task_id,
            "task_result_id": row.task_result_id,
            "task_type": row.task_type,
            "task_name": row.task_name,
            "stock_code": row.stock_code,
            "stock_name": row.stock_name,
            "model_key": row.model_key,
            "model_name": row.model_name,
            "year_label": row.year_label,
            "period_key": row.period_key,
            "kline_range": row.kline_range,
            "parameter_summary": row.parameter_summary,
            "best_metric_name": row.best_metric_name,
            "best_metric_value": row.best_metric_value,
            "metrics": row.metrics,
            "is_best": False,
            "result_timestamp": row.result_timestamp.isoformat() if row.result_timestamp else None,
            "created_at": None,
            "updated_at": None,
        }

    def _summary_from_items(self, items) -> dict[str, int]:
        """处理_summary_from_items相关逻辑。"""
        stock_codes: set[str] = set()
        cn_stock_codes: set[str] = set()
        us_stock_codes: set[str] = set()
        task_ids: set[str] = set()
        return_beats_counts = {
            "return_beats_gt_0": 0,
            "return_beats_gt_20": 0,
            "return_beats_gt_50": 0,
            "return_beats_gt_100": 0,
        }

        for item in items:
            stock_code = str((item or {}).get("stock_code") or "").strip()
            if stock_code:
                stock_codes.add(stock_code)
                if extractor._is_cn_stock_code(stock_code):
                    cn_stock_codes.add(stock_code)
                else:
                    us_stock_codes.add(stock_code)

            task_id = str((item or {}).get("task_id") or "").strip()
            if task_id:
                task_ids.add(task_id)

            value = extractor._safe_number((item or {}).get("best_metric_value"))
            if value is None:
                continue
            if value > 0:
                return_beats_counts["return_beats_gt_0"] += 1
            if value > 0.2:
                return_beats_counts["return_beats_gt_20"] += 1
            if value > 0.5:
                return_beats_counts["return_beats_gt_50"] += 1
            if value > 1:
                return_beats_counts["return_beats_gt_100"] += 1

        return {
            "stock_count": len(stock_codes),
            "cn_stock_count": len(cn_stock_codes),
            "us_stock_count": len(us_stock_codes),
            "task_count": len(task_ids),
            **return_beats_counts,
        }

    def _columns_for_task_type(self, task_type: str | None) -> list[dict[str, str]]:
        """处理_columns_for_task_type相关逻辑。"""
        return (
            extractor.BACKTEST_SUMMARY_COLUMNS
            if normalize_task_type(task_type) == "backtest_training"
            else extractor.SUMMARY_COLUMNS
        )

    def _empty_response(
        self,
        page: int,
        per_page: int,
        columns: list[dict[str, str]] | None = None,
    ) -> dict[str, Any]:
        """处理_empty_response相关逻辑。"""
        return {
            "status": "success",
            "columns": columns or extractor.SUMMARY_COLUMNS,
            "summary": self._summary_from_items([]),
            "items": [],
            "pagination": {
                "page": page,
                "per_page": per_page,
                "total": 0,
                "pages": 0,
                "has_prev": False,
                "has_next": False,
            },
        }

"""任务结果汇总索引的远程 CRUD 访问。"""

from __future__ import annotations

import json
from datetime import date, datetime
from collections.abc import Mapping
from typing import Any

from app.repositories.base import SdkCrudRepository, normalize_bool_fields
from app.repositories.sdk_client import SdkProtocolError


class TaskResultSummaryIndexRepository(SdkCrudRepository):
    """转换汇总指标 JSON 与 is_best 布尔字段。"""

    group_name = "param_task_result_summary_index"

    def list_indexes(
        self,
        *,
        page_index: int = 1,
        page_size: int = 100,
        task_id: str | None = None,
        task_result_id: int | None = None,
        task_type: str | None = None,
        task_types: list[str] | None = None,
        is_best: bool | None = None,
        stock_keyword: str | None = None,
        market_type: str | None = None,
        period_key: str | None = None,
        best_metric_value_gt: float | None = None,
        result_timestamp_from: str | None = None,
        result_timestamp_to: str | None = None,
        order_field: str = "result_timestamp",
        order_type: str = "desc",
    ) -> dict[str, Any]:
        """按索引关联条件分页读取远程汇总记录。"""
        payload: dict[str, Any] = {
            "page_index": max(1, int(page_index)),
            "page_size": max(1, int(page_size)),
            "order_field": order_field,
            "order_type": order_type,
        }
        for key, value in (
            ("task_id", task_id),
            ("task_result_id", task_result_id),
            ("task_type", task_type),
            ("task_types", task_types),
            ("is_best", is_best),
            ("stock_keyword", stock_keyword),
            ("market_type", market_type),
            ("period_key", period_key),
            ("best_metric_value_gt", best_metric_value_gt),
            ("result_timestamp_from", result_timestamp_from),
            ("result_timestamp_to", result_timestamp_to),
        ):
            if value is not None and value != "":
                payload[key] = value
        raw = self.client.call(self.group_name, "get_data_by_page_list", payload)
        return self._normalize_page(raw)

    def get_data_summary(
        self,
        *,
        page_index: int,
        page_size: int,
        task_type: str | None,
        task_types: list[str],
        stock_keyword: str | None,
        market_type: str | None,
        period_key: str | None,
        is_best: bool | None,
        best_only: bool,
        summary_type: str,
        best_metric_value_gt: float | None,
        result_timestamp_from: str | None,
        result_timestamp_to: str | None,
        task_id: str | None,
        task_result_id: int | None,
    ) -> dict[str, Any]:
        """调用服务端汇总查询，保留筛选、去重、排序和聚合在远端执行。"""
        payload: dict[str, Any] = {
            "page_index": max(1, int(page_index)),
            "page_size": max(1, int(page_size)),
            "order_field": "result_timestamp",
            "order_type": "desc",
            "task_types": task_types,
            "best_only": bool(best_only),
            "summary_type": summary_type,
        }
        for key, value in (
            ("task_type", task_type),
            ("stock_keyword", stock_keyword),
            ("market_type", market_type),
            ("period_key", period_key),
            ("is_best", is_best),
            ("best_metric_value_gt", best_metric_value_gt),
            ("result_timestamp_from", result_timestamp_from),
            ("result_timestamp_to", result_timestamp_to),
            ("task_id", task_id),
            ("task_result_id", task_result_id),
        ):
            if value is not None and value != "":
                payload[key] = value
        raw = self.client.call(self.group_name, "get_data_summary", payload)
        response = self._as_mapping(raw, "汇总查询结果")
        page = self._normalize_page(response)
        summary = response.get("summary")
        if not isinstance(summary, Mapping):
            raise SdkProtocolError("远程汇总查询响应缺少 summary")
        return {
            **page,
            "summary": dict(summary),
            "summary_type": str(response.get("summary_type") or summary_type),
        }

    def to_api_payload(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        """保存前序列化汇总 JSON，并格式化时间字段。"""
        result = dict(payload)
        for field in ("metrics_json", "parameter_summary"):
            if isinstance(result.get(field), (dict, list)):
                result[field] = json.dumps(result[field], ensure_ascii=False, default=str)
        for field in ("result_timestamp", "created_at", "updated_at"):
            if isinstance(result.get(field), (date, datetime)):
                result[field] = result[field].isoformat()
        return result

    def normalize_record(self, record: Mapping[str, Any]) -> dict[str, Any]:
        """读取后还原汇总 JSON，并标准化最佳结果标记。"""
        result = normalize_bool_fields(record, "is_best")
        for field in ("metrics_json", "parameter_summary"):
            if isinstance(result.get(field), str):
                try:
                    result[field] = json.loads(result[field])
                except json.JSONDecodeError:
                    result[field] = {}
        result["metrics"] = result.pop("metrics_json", {}) or {}
        return result

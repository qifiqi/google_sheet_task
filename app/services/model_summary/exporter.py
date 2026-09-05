"""单模型历史结果汇总索引 · CSV 导出（facade 的导出 mixin）。"""

from __future__ import annotations

import csv
import io
import json
import re
from datetime import datetime
from typing import Any

from app.services.model_summary import extractor


CSV_LEADING_COLUMNS = [
    ("stock_code", "产品/股票"),
    ("stock_name", "股票名"),
    ("task_name", "任务名"),
    ("task_type", "类型"),
    ("best_metric_value", "return beats"),
    ("result_timestamp", "结果时间"),
]

CSV_TRAILING_COLUMNS = [
    ("task_result_id", "结果 ID"),
]


def _csv_text(value: Any) -> str:
    """处理_csv_text相关逻辑。"""
    if value in (None, ""):
        return ""
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, default=str, separators=(",", ":"))
    return str(value)


def _format_csv_metric(value: Any, format_name: str | None = None) -> str:
    """处理_format_csv_metric相关逻辑。"""
    if value in (None, ""):
        return ""
    if not format_name and isinstance(value, str):
        return value
    number = extractor._safe_number(value)
    if number is None:
        return _csv_text(value)
    if format_name == "percent":
        return f"{number * 100:.2f}%"
    if format_name == "integer":
        return str(int(round(number)))
    return f"{number:.4f}".rstrip("0").rstrip(".")


def _format_csv_parameter_summary(value: Any) -> str:
    """处理_format_csv_parameter_summary相关逻辑。"""
    if isinstance(value, dict):
        parameter_value = value.get("parameter")
        if isinstance(parameter_value, list):
            return ",".join(_csv_text(item) for item in parameter_value)
        a1 = value.get("A1")
        b1 = value.get("B1")
        if a1 not in (None, "") or b1 not in (None, ""):
            return ",".join(_csv_text(item) for item in (a1, b1) if item not in (None, ""))
        return _csv_text(parameter_value)

    parameter_value = value
    if isinstance(parameter_value, list):
        return ",".join(_csv_text(item) for item in parameter_value)
    return _csv_text(parameter_value)


def _interval_display_value(item: dict[str, Any]) -> str:
    """处理_interval_display_value相关逻辑。"""
    return _csv_text(item.get("kline_range") or item.get("year_label"))


class SummaryExportMixin:
    """汇总索引 CSV 导出：翻页聚合查询载荷后统一渲染。"""

    def export_csv(
        self,
        user: Any,
        filters: dict[str, Any],
        *,
        ignore_permissions: bool = False,
    ) -> dict[str, Any]:
        """处理export_csv相关逻辑。"""
        export_filters = dict(filters)
        export_filters["page"] = 1
        export_filters["per_page"] = 200
        items: list[dict[str, Any]] = []
        columns: list[dict[str, str]] = []
        summary_type = str(export_filters.get("summary_type") or "task").strip().lower() or "task"

        while True:
            payload = self.query(
                user,
                export_filters,
                ignore_permissions=ignore_permissions,
            )
            if not columns:
                columns = payload.get("columns") or []
            items.extend(payload.get("items") or [])

            pagination = payload.get("pagination") or {}
            if not pagination.get("has_next"):
                break
            export_filters["page"] = int(export_filters["page"]) + 1

        return {
            "status": "success",
            "filename": self._export_filename(export_filters, summary_type),
            "content": self._render_csv(columns, items),
            "count": len(items),
        }

    def _export_filename(self, filters: dict[str, Any], summary_type: str) -> str:
        """处理_export_filename相关逻辑。"""
        custom_filename = self._safe_filename_part(filters.get("filename"))
        if custom_filename and custom_filename != "all":
            return custom_filename if custom_filename.lower().endswith(".csv") else f"{custom_filename}.csv"

        task_type = self._safe_filename_part(filters.get("task_type") or "all")
        stock_code = self._safe_filename_part(filters.get("stock_code") or "all")
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        return f"model_summary_{summary_type}_{task_type}_{stock_code}_{timestamp}.csv"

    def _safe_filename_part(self, value: Any) -> str:
        """处理_safe_filename_part相关逻辑。"""
        text = str(value or "").strip()
        if not text:
            return "all"
        text = re.sub(r'[\\/:*?"<>|\r\n\t]+', "_", text)
        return text[:80] or "all"

    def _render_csv(self, columns: list[dict[str, str]], items: list[dict[str, Any]]) -> str:
        """处理_render_csv相关逻辑。"""
        buffer = io.StringIO(newline="")
        writer = csv.writer(buffer)
        headers = (
            [label for _key, label in CSV_LEADING_COLUMNS]
            + ["参数"]
            + ["年份/区间"]
            + [column.get("label") or column.get("key") or "" for column in columns]
            + [label for _key, label in CSV_TRAILING_COLUMNS]
        )
        writer.writerow(headers)

        for item in items:
            metrics = item.get("metrics") if isinstance(item.get("metrics"), dict) else {}
            row = [
                self._csv_column_value(item, key, "percent" if key == "best_metric_value" else None)
                for key, _label in CSV_LEADING_COLUMNS
            ]
            row.append(_format_csv_parameter_summary(item.get("parameter_summary")))
            row.append(_interval_display_value(item))
            row.extend(
                _format_csv_metric(metrics.get(column.get("key")), column.get("format"))
                for column in columns
            )
            row.extend(
                self._csv_column_value(item, key)
                for key, _label in CSV_TRAILING_COLUMNS
            )
            writer.writerow(row)
        return buffer.getvalue()

    def _csv_column_value(
        self,
        item: dict[str, Any],
        key: str,
        format_name: str | None = None,
    ) -> str:
        """处理_csv_column_value相关逻辑。"""
        value = item.get(key)
        if key == "task_type":
            return extractor.TASK_TYPE_LABELS.get(str(value or ""), _csv_text(value))
        if key == "result_timestamp" and value:
            return str(value).replace("T", " ")
        if format_name:
            return _format_csv_metric(value, format_name)
        return _csv_text(value)

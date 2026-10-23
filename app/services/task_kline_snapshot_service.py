"""随机价格K线快照服务。

源快照按（任务+股票+窗口）存一次日期/OHLC 数组；每个随机组只存 stock_val 数组，
读取时按索引拼回完整 K 线行，避免按参数组合重复存储整行 JSON。
"""

from __future__ import annotations

import csv
import io
import random
import re
from typing import Any

from app.exceptions import NotFoundError
from app.repositories import task_kline_snapshot_repository
from app.services.kline_service import KlineService
from app.utils.json_utils import dumps, loads


class TaskKlineSnapshotService:
    @staticmethod
    def _normalize_kline_key(kline_key: Any) -> str:
        """窗口键统一成字符串：整年模式传 int 年份，PG 的 varchar 列不接受 int 绑定。"""
        return str(kline_key).strip()

    def get_or_create_source(
        self,
        *,
        task_id: str,
        stock_code: str,
        kline_key: str,
        rows: list[dict[str, Any]],
        stock_name: str | None = None,
        market_type: str | None = None,
        data_source: str | None = None,
        adjust_type: str | None = None,
    ) -> dict[str, Any]:
        kline_key = self._normalize_kline_key(kline_key)
        if not task_id or not stock_code or not kline_key:
            raise ValueError("随机K线源快照缺少任务、股票或窗口键")
        existing = task_kline_snapshot_repository.get_source(
            task_id, stock_code, kline_key
        )
        if existing:
            return existing
        if not rows:
            raise ValueError("随机K线源数据为空")

        dates: list[str] = []
        price_arrays: dict[str, list[float]] = {
            field: [] for field in ("open", "high", "low", "close")
        }
        vwap_values: list[Any] = []
        for row in rows:
            stock_date = str(row.get("stock_date") or "").strip()
            if not stock_date:
                raise ValueError("随机K线源数据缺少 stock_date")
            dates.append(stock_date)
            for field, values in price_arrays.items():
                raw = row.get(field)
                if raw in (None, ""):
                    raise ValueError(f"随机K线源数据缺少 {field}")
                values.append(float(raw))
            vwap_values.append(row.get("vwap"))

        first_row = rows[0]
        fields = {
            "task_id": task_id,
            "stock_code": stock_code,
            "stock_name": stock_name or first_row.get("stock_name"),
            "market_type": market_type,
            "kline_key": kline_key,
            "data_source": first_row.get("data_source") or data_source,
            "adjust_type": adjust_type,
            "start_date": min(dates),
            "end_date": max(dates),
            "row_count": len(rows),
            "dates_json": dumps(dates),
            "open_json": dumps(price_arrays["open"]),
            "high_json": dumps(price_arrays["high"]),
            "low_json": dumps(price_arrays["low"]),
            "close_json": dumps(price_arrays["close"]),
            "vwap_json": dumps(vwap_values),
        }
        return task_kline_snapshot_repository.create_source(fields)

    def get_or_create_series(
        self,
        *,
        source: dict[str, Any],
        task_id: str,
        stock_code: str,
        kline_key: str,
        random_group: int,
        price_mode: str,
        random_price_range: str,
        seed: str,
        rows: list[dict[str, Any]],
    ) -> dict[str, Any]:
        normalized_mode = str(price_mode or "").strip().lower()
        if normalized_mode != "random_price":
            raise ValueError("随机K线序列仅支持 price_mode=random_price")
        normalized_range = str(random_price_range or "high_low").strip().lower()
        if normalized_range not in {"high_low", "open_close"}:
            raise ValueError(f"不支持的随机价格区间: {random_price_range}")
        kline_key = self._normalize_kline_key(kline_key)
        if source.get("task_id") != task_id or source.get("stock_code") != stock_code:
            raise ValueError("随机K线序列与源快照归属不一致")
        if self._normalize_kline_key(source.get("kline_key")) != kline_key:
            raise ValueError("随机K线序列与源快照窗口不一致")
        if not seed:
            raise ValueError("随机K线序列缺少随机种子")

        existing = task_kline_snapshot_repository.get_series(
            task_id, stock_code, kline_key, normalized_range, int(random_group)
        )
        if existing:
            return existing

        values = self._build_random_values(rows, normalized_range, seed)
        row_count = int(source.get("row_count") or len(values))
        if len(values) != row_count:
            raise ValueError("随机K线序列行数与源快照不一致")

        fields = {
            "source_id": source["id"],
            "task_id": task_id,
            "stock_code": stock_code,
            "kline_key": kline_key,
            "dataset_key": f"{kline_key}:{normalized_range}:random-{int(random_group)}",
            "random_group": int(random_group),
            "price_mode": normalized_mode,
            "random_price_range": normalized_range,
            "seed": seed,
            "row_count": len(values),
            "values_json": dumps(values),
        }
        return task_kline_snapshot_repository.create_series(fields)

    @staticmethod
    def _build_random_values(
        rows: list[dict[str, Any]],
        random_price_range: str,
        seed: str,
    ) -> list[float]:
        projected = KlineService.build_price_rows(
            rows,
            "random_price",
            include_ohlc=True,
            random_price_range=random_price_range,
            random_generator=random.Random(seed),
        )
        return [float(row["stock_val"]) for row in projected]

    @staticmethod
    def merge_rows(
        source: dict[str, Any], series: dict[str, Any]
    ) -> list[dict[str, Any]]:
        dates = loads(source["dates_json"])
        opens = loads(source["open_json"])
        highs = loads(source["high_json"])
        lows = loads(source["low_json"])
        closes = loads(source["close_json"])
        vwap_values = loads(source["vwap_json"]) if source.get("vwap_json") else None
        values = loads(series["values_json"])
        lengths = {
            len(dates),
            len(opens),
            len(highs),
            len(lows),
            len(closes),
            len(values),
        }
        if vwap_values is not None:
            lengths.add(len(vwap_values))
        row_count = int(source.get("row_count") or 0)
        if len(lengths) != 1 or (row_count and lengths != {row_count}):
            raise ValueError("随机K线快照行数不一致")
        merged = []
        for index, (stock_date, value, open_value, high, low, close) in enumerate(
            zip(dates, values, opens, highs, lows, closes)
        ):
            row = {
                "stock_date": stock_date,
                "stock_val": value,
                "open": open_value,
                "high": high,
                "low": low,
                "close": close,
            }
            if vwap_values is not None:
                row["vwap"] = vwap_values[index]
            merged.append(row)
        return merged

    def list_task_snapshots(self, task_id: str) -> list[dict[str, Any]]:
        return task_kline_snapshot_repository.list_series_with_source(task_id)

    def get_series_detail(
        self, series_id: int, *, task_id: str | None = None
    ) -> dict[str, Any]:
        series = task_kline_snapshot_repository.get_series_by_id(series_id)
        if not series or (task_id and series["task_id"] != task_id):
            raise NotFoundError("随机K线快照不存在")
        source = task_kline_snapshot_repository.get_source_by_id(series["source_id"])
        if not source:
            raise NotFoundError("随机K线快照源数据不存在")
        return {
            "series": self._series_metadata(series),
            "source": self._source_metadata(source),
            "rows": self.merge_rows(source, series),
        }

    def get_result_snapshot(self, result_id: int) -> dict[str, Any] | None:
        link = task_kline_snapshot_repository.get_link_by_result(result_id)
        if not link:
            return None
        return self.get_series_detail(link["series_id"], task_id=link["task_id"])

    def export_csv(self, detail: dict[str, Any]) -> tuple[str, str]:
        output = io.StringIO()
        writer = csv.writer(output, lineterminator="\n")
        writer.writerow(["stock_date", "stock_val", "open", "high", "low", "close"])
        for row in detail.get("rows") or []:
            writer.writerow([
                row.get("stock_date", ""),
                row.get("stock_val", ""),
                row.get("open", ""),
                row.get("high", ""),
                row.get("low", ""),
                row.get("close", ""),
            ])
        series = detail.get("series") or {}
        raw_name = "_".join([
            str(series.get("stock_code") or "random"),
            str(series.get("dataset_key") or series.get("id") or "kline"),
        ])
        filename = re.sub(r"[^0-9A-Za-z._-]+", "-", raw_name).strip("-") + ".csv"
        return filename, output.getvalue()

    @staticmethod
    def _series_metadata(series: dict[str, Any]) -> dict[str, Any]:
        return {key: value for key, value in series.items() if key != "values_json"}

    @staticmethod
    def _source_metadata(source: dict[str, Any]) -> dict[str, Any]:
        excluded = {
            "dates_json",
            "open_json",
            "high_json",
            "low_json",
            "close_json",
            "vwap_json",
        }
        return {key: value for key, value in source.items() if key not in excluded}


task_kline_snapshot_service = TaskKlineSnapshotService()

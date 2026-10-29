"""TaskKlineSnapshot HTTP 仓储（随机K线三表，本地对应
app/repositories/task_kline_snapshot_repository.py；E10-E12 端点，2026-10-29 上线实测通过）。

- 源快照 → ``param_task_kline_sources``（五字段唯一键 get-or-create）；
- 随机序列 → ``param_task_random_series``；
- 结果关联 → ``param_task_result_kline_links``（result_id+series_id 幂等）。
分页摘要不含 *_json 大字段，大字段仅经 GetInfoById 读取。
"""
from __future__ import annotations

from typing import Any

from app.repositories.http_backend.base import (
    HttpRepositoryBase,
    dump_row,
)
from app.remote_api.capabilities import require_e12

_SOURCE_DT = ("created_at",)
_SERIES_DT = ("created_at",)
_LINK_DT = ("created_at",)


def _first(items):
    return items[0] if items else None


class TaskKlineSnapshotHttpRepository(HttpRepositoryBase):
    """随机K线快照聚合仓储 HTTP 版：三表经三个远程控制器访问。"""

    group_name = "param_task_kline_sources"

    _GROUP_SERIES = "param_task_random_series"
    _GROUP_LINKS = "param_task_result_kline_links"

    def normalize_record(self, record):
        return dict(record)

    def _save_via(self, group: str, fields: dict, dt_fields) -> dict:
        """group 指定控制器的 save（镜像 base.save 的回执形态处理）。"""
        payload = dump_row(fields, datetime_fields=dt_fields)
        if payload.get("id") is None:
            payload.pop("id", None)
        raw = self._controller(group).modify_or_add(payload)
        if raw is None:
            return self.normalize_record(payload)
        if isinstance(raw, str):
            value = raw.strip()
            try:
                value = self.normalize_id(value)
            except (TypeError, ValueError):
                pass
            return self.normalize_record({**payload, "id": value})
        return self.normalize_record(self._as_mapping(raw, "保存结果"))

    def _get_via(self, group: str, record_id):
        raw = self._controller(group).get_info_by_id({"id": self.normalize_id(record_id)})
        if raw is None:
            return None
        return self.normalize_record(self._as_mapping(raw, "详情"))

    # ---- 源快照 ----

    def get_source(self, task_id: str, stock_code: str, kline_key: str):
        rows = [
            row for row in self.iter_pages(
                {"task_id": task_id, "stock_code": stock_code, "kline_key": kline_key},
            )
        ]
        return _first(rows)

    def get_source_by_id(self, source_id: int):
        return self.get(source_id)

    def create_source(self, fields: dict, commit: bool = True):
        require_e12(self.api)
        return self.save(dump_row(fields, datetime_fields=_SOURCE_DT))

    # ---- 随机序列 ----

    def get_series(
        self,
        task_id: str,
        stock_code: str,
        kline_key: str,
        random_price_range: str,
        random_group: int,
    ):
        rows = [
            row for row in self.iter_pages(
                {
                    "task_id": task_id,
                    "stock_code": stock_code,
                    "kline_key": kline_key,
                    "random_price_range": random_price_range,
                },
                group=self._GROUP_SERIES,
            )
            if int(row.get("random_group") or 0) == int(random_group)
        ]
        return _first(rows)

    def get_series_by_id(self, series_id: int):
        return self._get_via(self._GROUP_SERIES, series_id)

    def get_series_owner(self, series_id: int):
        row = self.get_series_by_id(series_id)
        return (row or {}).get("task_id")

    def create_series(self, fields: dict, commit: bool = True):
        require_e12(self.api)
        return self._save_via(self._GROUP_SERIES, fields, _SERIES_DT)

    def count_series_by_task(
        self,
        task_id: str,
        stock_code: str = "",
        random_group: int | None = None,
    ) -> int:
        payload: dict[str, Any] = {"task_id": task_id}
        if (stock_code or "").strip():
            payload["stock_code"] = stock_code.strip()
        if random_group is not None:
            payload["random_group"] = random_group
        page = self.page(payload, group=self._GROUP_SERIES)
        return int(page.get("total") or 0)

    def list_series_with_source(
        self,
        task_id: str,
        offset: int | None = None,
        limit: int | None = None,
        stock_code: str = "",
        random_group: int | None = None,
    ):
        payload: dict[str, Any] = {"task_id": task_id}
        if (stock_code or "").strip():
            payload["stock_code"] = stock_code.strip()
        if random_group is not None:
            payload["random_group"] = random_group
        rows = list(self.iter_pages(payload, group=self._GROUP_SERIES))
        rows.sort(key=lambda row: int(row.get("id") or 0))
        if offset is not None:
            rows = rows[offset:]
        if limit is not None:
            rows = rows[:limit]

        sources: dict[int, dict] = {}
        items = []
        for row in rows:
            source_id = row.get("source_id")
            if source_id not in sources:
                sources[source_id] = self.get_source_by_id(source_id) or {}
            source = sources[source_id]
            items.append({
                "id": row.get("id"),
                "source_id": row.get("source_id"),
                "task_id": row.get("task_id"),
                "stock_code": row.get("stock_code"),
                "kline_key": row.get("kline_key"),
                "dataset_key": row.get("dataset_key"),
                "random_group": row.get("random_group"),
                "price_mode": row.get("price_mode"),
                "random_price_range": row.get("random_price_range"),
                "seed": row.get("seed"),
                "row_count": row.get("row_count"),
                "created_at": row.get("created_at"),
                "stock_name": source.get("stock_name"),
                "market_type": source.get("market_type"),
                "data_source": source.get("data_source"),
                "adjust_type": source.get("adjust_type"),
                "start_date": source.get("start_date"),
                "end_date": source.get("end_date"),
            })
        return items

    def list_series_bundle(self, task_id: str):
        """导出用：任务全部序列（含 values_json）与源快照（含数组大字段）。"""
        rows = [
            self._get_via(self._GROUP_SERIES, series_id)
            for series_id in (
                row.get("id")
                for row in self.iter_pages({"task_id": task_id}, group=self._GROUP_SERIES)
            )
        ]
        rows = [row for row in rows if row]
        rows.sort(key=lambda row: int(row.get("id") or 0))
        if not rows:
            return [], {}
        sources: dict[int, dict] = {}
        for row in rows:
            source_id = row.get("source_id")
            if source_id not in sources:
                sources[source_id] = self.get_source_by_id(source_id) or {}
        return rows, sources

    # ---- 结果关联 ----

    def count_links_by_series(self, task_id: str, series_id: int) -> int:
        page = self.page(
            {"task_id": task_id, "series_id": series_id},
            group=self._GROUP_LINKS,
        )
        return int(page.get("total") or 0)

    def list_link_result_ids(self, task_id: str, series_id: int) -> list[int]:
        rows = list(self.iter_pages(
            {"task_id": task_id, "series_id": series_id},
            group=self._GROUP_LINKS,
        ))
        rows.sort(key=lambda row: int(row.get("id") or 0))
        return [int(row.get("result_id") or 0) for row in rows]

    def create_link(self, result_id: int, task_id: str, series_id: int):
        require_e12(self.api)
        return self._save_via(
            self._GROUP_LINKS,
            {"result_id": result_id, "task_id": task_id, "series_id": series_id},
            _LINK_DT,
        )

    def delete_links_by_result_ids(self, result_ids: list[int], commit: bool = True):
        """按结果集清关联（远端无 result_ids 批量端点：逐 result_id 分页定位后删除）。"""
        deleted = 0
        for result_id in result_ids or []:
            for row in list(self.iter_pages({"result_id": result_id}, group=self._GROUP_LINKS)):
                try:
                    self._controller(self._GROUP_LINKS).delete({"id": self.normalize_id(row["id"])})
                    deleted += 1
                except Exception:
                    continue
        return deleted

    def delete_by_task(self, task_id: str, commit: bool = True):
        """任务级三表清理：links → series → sources，逐 id 删除（非原子）。"""
        deleted = 0
        for row in list(self.iter_pages({"task_id": task_id}, group=self._GROUP_LINKS)):
            try:
                self._controller(self._GROUP_LINKS).delete({"id": self.normalize_id(row["id"])})
                deleted += 1
            except Exception:
                continue
        for group in (self._GROUP_SERIES, self.group_name):
            for row in list(self.iter_pages({"task_id": task_id}, group=group)):
                try:
                    self._controller(group).delete({"id": self.normalize_id(row["id"])})
                    deleted += 1
                except Exception:
                    continue
        return deleted

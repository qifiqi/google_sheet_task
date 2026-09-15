"""StockMetadata HTTP 仓储（本地对应 app/repositories/stock_metadata_repository.py）。

远端 GetParamStockMetadataListRequestDto 支持 stock_code / market_type 过滤；
唯一键 (stock_code, market_type)，多候选代码逐个查询后本地取最新。
"""
from __future__ import annotations

from typing import Any

from app.repositories.http_backend.base import HttpRepositoryBase, dump_row
from app.remote_api import RemoteApiNotFoundError
from app.utils.market import normalize_stock_code


class StockMetadataHttpRepository(HttpRepositoryBase):
    """stock_metadata 表远程访问；数值主键。"""

    group_name = "param_stock_metadata"

    _DT_FIELDS = ("created_at", "updated_at")

    def _latest_by_code(self, stock_code, market_type) -> dict[str, Any] | None:
        page = self.page(
            {"stock_code": stock_code, "market_type": market_type},
            page_size=1,
            order_field="updated_at",
            order_type="desc",
        )
        # TODO(db-to-http): 远端单一 order_field 无法表达 updated_at desc, id desc
        # 双键排序；同一 (code, market) 多行时取返回首条，次序稳定性依赖远端。
        items = page["items"]
        return items[0] if items else None

    # ---- 读 ----

    def get(self, stock_code, market_type):
        """按 (stock_code, market_type) 取最新一条；不存在返回 None。"""
        return self._latest_by_code(stock_code, market_type)

    def find_latest_by_codes(self, stock_codes, market_type):
        """候选代码（同一证券的不同后缀形态）中取最新一条；不存在返回 None。"""
        candidates = [str(code) for code in stock_codes if code]
        if not candidates:
            return None
        hits = [
            row
            for code in candidates
            if (row := self._latest_by_code(code, market_type)) is not None
        ]
        if not hits:
            return None
        hits.sort(key=lambda item: str(item.get("updated_at") or ""), reverse=True)
        return hits[0]

    # ---- 写 ----

    def upsert(self, fields, commit=True):
        """按 (stock_code, market_type) 存在则更新、否则新建；返回 dict。

        查询前与模型事件监听器做同一 stock_code 标准化（600000 → 600000.SH）。
        """
        stock_code = normalize_stock_code(
            fields.get("stock_code"),
            fields.get("market_type"),
            fields.get("exchange_market"),
        )
        market_type = fields.get("market_type")
        payload = {**fields, "stock_code": stock_code}

        row = self._latest_by_code(stock_code, market_type)
        if row is not None:
            payload = {**row, **payload}
        return self.save(dump_row(payload, datetime_fields=self._DT_FIELDS))

    def bulk_upsert(self, rows, commit=True):
        """循环 upsert；返回处理行数。

        TODO(db-to-http): 远端无批量 upsert 端点，循环逐行写入；
        大批量导入时建议远端提供批量端点（见迁移文档无法接入清单）。
        """
        count = 0
        for fields in rows or []:
            if self.upsert(fields, commit=False):
                count += 1
        return count

    def delete_by_id(self, record_id):
        try:
            super().delete(record_id)
        except RemoteApiNotFoundError:
            return False
        return True

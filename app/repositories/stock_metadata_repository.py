"""StockMetadata 仓储（契约见 docs/design/data-layer-refactor/02 §2.11）。

语义对齐 stock_metadata_service：
- 唯一键为 (stock_code, market_type)，查询按 updated_at desc, id desc 取最新；
- upsert 不做代码标准化（上游 normalize_stock_payload 负责，模型事件兜底）。
"""
from app.extensions import db
from app.models import StockMetadata
from app.repositories.base import BaseRepository
from app.utils.market import normalize_stock_code


class StockMetadataRepository(BaseRepository):
    model = StockMetadata

    # ---- 读 ----

    def get(self, stock_code, market_type):
        """按 (stock_code, market_type) 取最新一条；不存在返回 None。"""
        row = (
            StockMetadata.query
            .filter(
                StockMetadata.stock_code == stock_code,
                StockMetadata.market_type == market_type,
            )
            .order_by(StockMetadata.updated_at.desc(), StockMetadata.id.desc())
            .first()
        )
        return row.to_dict() if row else None

    def count(self):
        return StockMetadata.query.count()

    # ---- 写 ----

    def upsert(self, fields, commit=True):
        """按 (stock_code, market_type) 存在则更新、否则新建；返回 dict。

        - 查询前与模型事件监听器做同一 stock_code 标准化（600000 → 600000.SS），
          否则首次插入后再 upsert 会因查不到旧行而撞唯一约束；
        - 会话内已挂起（未 flush）的同键对象直接原地更新，避免同一会话内
          重复插入撞唯一约束（对齐原 stock_metadata_service 语义）；
        - with no_autoflush 避免查询触发未提交对象的 flush；
        - commit 默认开启，需要并入调用方事务时传 commit=False。
        """
        stock_code = normalize_stock_code(
            fields.get("stock_code"),
            fields.get("market_type"),
            fields.get("exchange_market"),
        )
        market_type = fields.get("market_type")
        payload = {**fields, "stock_code": stock_code}

        for pending in db.session.new:
            if (
                isinstance(pending, StockMetadata)
                and pending.stock_code == stock_code
                and pending.market_type == market_type
            ):
                for key, value in payload.items():
                    setattr(pending, key, value)
                return pending.to_dict()

        with db.session.no_autoflush:
            row = (
                StockMetadata.query
                .filter(
                    StockMetadata.stock_code == stock_code,
                    StockMetadata.market_type == market_type,
                )
                .order_by(StockMetadata.updated_at.desc(), StockMetadata.id.desc())
                .first()
            )
        if row is None:
            row = StockMetadata(**payload)
            db.session.add(row)
        else:
            for key, value in payload.items():
                setattr(row, key, value)
        if commit:
            self._commit()
        return row.to_dict()

    def bulk_upsert(self, rows, commit=True):
        """循环 upsert 后统一提交；返回处理行数。"""
        count = 0
        for fields in rows or []:
            if self.upsert(fields, commit=False):
                count += 1
        if commit:
            self._commit()
        return count

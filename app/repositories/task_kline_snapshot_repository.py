"""随机价格K线快照仓储（源快照 / 随机序列 / 结果关联）。"""

from __future__ import annotations

from sqlalchemy import func
from sqlalchemy.orm import load_only

from app.extensions import db
from app.models import TaskKlineSource, TaskRandomSeries, TaskResultKlineLink
from app.repositories.base import BaseRepository


class TaskKlineSnapshotRepository(BaseRepository):
    """随机K线快照聚合仓储：三张表同属一个审计聚合。"""

    def get_source(self, task_id: str, stock_code: str, kline_key: str):
        row = TaskKlineSource.query.filter_by(
            task_id=task_id,
            stock_code=stock_code,
            kline_key=kline_key,
        ).first()
        return row.to_dict() if row else None

    def get_source_by_id(self, source_id: int):
        row = db.session.get(TaskKlineSource, source_id)
        return row.to_dict() if row else None

    def create_source(self, fields: dict, commit: bool = True):
        try:
            row = TaskKlineSource(**fields)
            db.session.add(row)
            if commit:
                self._commit()
            return row.to_dict()
        except Exception:
            db.session.rollback()
            raise

    def get_series(
        self,
        task_id: str,
        stock_code: str,
        kline_key: str,
        random_price_range: str,
        random_group: int,
    ):
        row = TaskRandomSeries.query.filter_by(
            task_id=task_id,
            stock_code=stock_code,
            kline_key=kline_key,
            random_price_range=random_price_range,
            random_group=random_group,
        ).first()
        return row.to_dict() if row else None

    def get_series_by_id(self, series_id: int):
        row = db.session.get(TaskRandomSeries, series_id)
        return row.to_dict() if row else None

    def get_series_owner(self, series_id: int):
        """序列所属任务ID（不加载 values_json 大字段）。"""
        row = (
            db.session.query(TaskRandomSeries.task_id)
            .filter(TaskRandomSeries.id == series_id)
            .first()
        )
        return row[0] if row else None

    def create_series(self, fields: dict, commit: bool = True):
        try:
            row = TaskRandomSeries(**fields)
            db.session.add(row)
            if commit:
                self._commit()
            return row.to_dict()
        except Exception:
            db.session.rollback()
            raise

    @staticmethod
    def _apply_series_filters(
        query,
        stock_code: str = "",
        random_group: int | None = None,
    ):
        normalized_stock = (stock_code or "").strip()
        if normalized_stock:
            query = query.filter(
                TaskRandomSeries.stock_code == normalized_stock
            )
        if random_group is not None:
            query = query.filter(
                TaskRandomSeries.random_group == random_group
            )
        return query

    def count_series_by_task(
        self,
        task_id: str,
        stock_code: str = "",
        random_group: int | None = None,
    ) -> int:
        query = db.session.query(func.count(TaskRandomSeries.id)).filter(
            TaskRandomSeries.task_id == task_id
        )
        query = self._apply_series_filters(query, stock_code, random_group)
        return query.scalar()

    def list_series_with_source(
        self,
        task_id: str,
        offset: int | None = None,
        limit: int | None = None,
        stock_code: str = "",
        random_group: int | None = None,
    ):
        query = (
            db.session.query(TaskRandomSeries, TaskKlineSource)
            .options(
                load_only(
                    TaskRandomSeries.id,
                    TaskRandomSeries.source_id,
                    TaskRandomSeries.task_id,
                    TaskRandomSeries.stock_code,
                    TaskRandomSeries.kline_key,
                    TaskRandomSeries.dataset_key,
                    TaskRandomSeries.random_group,
                    TaskRandomSeries.price_mode,
                    TaskRandomSeries.random_price_range,
                    TaskRandomSeries.seed,
                    TaskRandomSeries.row_count,
                    TaskRandomSeries.created_at,
                ),
                load_only(
                    TaskKlineSource.id,
                    TaskKlineSource.stock_name,
                    TaskKlineSource.market_type,
                    TaskKlineSource.data_source,
                    TaskKlineSource.adjust_type,
                    TaskKlineSource.start_date,
                    TaskKlineSource.end_date,
                ),
            )
            .join(TaskKlineSource, TaskKlineSource.id == TaskRandomSeries.source_id)
            .filter(TaskRandomSeries.task_id == task_id)
            .order_by(TaskRandomSeries.id.asc())
        )
        query = self._apply_series_filters(query, stock_code, random_group)
        if offset is not None:
            query = query.offset(offset)
        if limit is not None:
            query = query.limit(limit)
        return [self._list_item(series, source) for series, source in query.all()]

    def list_series_bundle(self, task_id: str):
        """导出用：加载任务全部序列与源快照（含数组大字段）。"""
        series_rows = (
            TaskRandomSeries.query.filter_by(task_id=task_id)
            .order_by(TaskRandomSeries.id.asc())
            .all()
        )
        if not series_rows:
            return [], {}
        source_ids = list({row.source_id for row in series_rows})
        sources = {}
        # 分块绕开 SQLite 的 IN 参数上限（本地开发库；PG/MySQL 同样正确）。
        for start in range(0, len(source_ids), 500):
            chunk = source_ids[start:start + 500]
            for row in TaskKlineSource.query.filter(
                TaskKlineSource.id.in_(chunk)
            ).all():
                sources[row.id] = row.to_dict()
        return [row.to_dict() for row in series_rows], sources

    @staticmethod
    def _list_item(series: TaskRandomSeries, source: TaskKlineSource) -> dict:
        return {
            "id": series.id,
            "source_id": series.source_id,
            "task_id": series.task_id,
            "stock_code": series.stock_code,
            "kline_key": series.kline_key,
            "dataset_key": series.dataset_key,
            "random_group": series.random_group,
            "price_mode": series.price_mode,
            "random_price_range": series.random_price_range,
            "seed": series.seed,
            "row_count": series.row_count,
            "created_at": series.created_at.isoformat() if series.created_at else None,
            "stock_name": source.stock_name,
            "market_type": source.market_type,
            "data_source": source.data_source,
            "adjust_type": source.adjust_type,
            "start_date": source.start_date,
            "end_date": source.end_date,
        }

    def delete_links_by_result_ids(self, result_ids: list[int], commit: bool = True):
        if not result_ids:
            return 0
        try:
            deleted = TaskResultKlineLink.query.filter(
                TaskResultKlineLink.result_id.in_(result_ids)
            ).delete(synchronize_session=False)
            if commit:
                self._commit()
            return deleted
        except Exception:
            db.session.rollback()
            raise

    def delete_by_task(self, task_id: str, commit: bool = True):
        try:
            TaskResultKlineLink.query.filter_by(task_id=task_id).delete(
                synchronize_session=False
            )
            TaskRandomSeries.query.filter_by(task_id=task_id).delete(
                synchronize_session=False
            )
            TaskKlineSource.query.filter_by(task_id=task_id).delete(
                synchronize_session=False
            )
            if commit:
                self._commit()
        except Exception:
            db.session.rollback()
            raise

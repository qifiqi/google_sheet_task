"""随机价格K线快照仓储（源快照 / 随机序列 / 结果关联）。"""

from __future__ import annotations

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

    def get_link_by_result(self, result_id: int):
        row = TaskResultKlineLink.query.filter_by(result_id=result_id).first()
        return row.to_dict() if row else None

    def list_series_with_source(self, task_id: str):
        rows = (
            db.session.query(TaskRandomSeries, TaskKlineSource)
            .join(TaskKlineSource, TaskKlineSource.id == TaskRandomSeries.source_id)
            .filter(TaskRandomSeries.task_id == task_id)
            .order_by(TaskRandomSeries.id.asc())
            .all()
        )
        items = []
        for series, source in rows:
            item = series.to_dict()
            item.pop("values_json", None)
            item.update({
                "stock_name": source.stock_name,
                "market_type": source.market_type,
                "data_source": source.data_source,
                "adjust_type": source.adjust_type,
                "start_date": source.start_date,
                "end_date": source.end_date,
            })
            items.append(item)
        return items

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

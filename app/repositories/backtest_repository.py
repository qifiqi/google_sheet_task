"""回测相关仓储：TaskResultSummaryIndex / BacktestProductResultCache / BacktestSheetRunLock
（契约见 docs/design/data-layer-refactor/02 §2.12）。

锁红线（对齐 runtime.py 现有语义）：
- acquire_lock：同任务重复获取幂等成功；已被其他任务持有则失败并返回持锁任务；
  无锁行则插入并提交，撞唯一约束（并发竞态）时回滚复查后判失败；
- release_lock：持锁任务不匹配时拒绝释放（返回 False），不得删除他人锁。
"""
from sqlalchemy import MetaData, Table, inspect, or_
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models import (
    BacktestProductResultCache,
    BacktestSheetRunLock,
    TaskResultSummaryIndex,
)
from app.repositories.base import BaseRepository


class BacktestRepository(BaseRepository):
    # 聚合仓储不绑定单一 model。
    model = None

    # ---- TaskResultSummaryIndex ----

    def get_summary_index(self, task_id):
        """任务全部汇总索引行（dict 列表，按 id asc）。"""
        rows = (
            TaskResultSummaryIndex.query.filter_by(task_id=task_id)
            .order_by(TaskResultSummaryIndex.id.asc())
            .all()
        )
        return [row.to_dict() for row in rows]

    def get_summary_index_row(self, task_result_id, model_key):
        row = (
            TaskResultSummaryIndex.query
            .filter_by(task_result_id=task_result_id, model_key=model_key)
            .first()
        )
        return row.to_dict() if row else None

    def upsert_summary_index(self, task_result_id, model_key, fields, commit=True):
        """按 (task_result_id, model_key) 唯一键存在则更新、否则新建。"""
        with db.session.no_autoflush:
            row = (
                TaskResultSummaryIndex.query
                .filter_by(task_result_id=task_result_id, model_key=model_key)
                .first()
            )
        if row is None:
            row = TaskResultSummaryIndex(task_result_id=task_result_id, model_key=model_key, **fields)
            db.session.add(row)
        else:
            for key, value in fields.items():
                setattr(row, key, value)
        if commit:
            self._commit()
        return row.to_dict()

    def delete_xpl_analysis_jobs(self, *, task_id=None, result_ids=None, return_series_ids=None):
        """遗留 xpl_analysis_jobs 表清理（目标库存在该表时）。"""
        if not inspect(db.engine).has_table("xpl_analysis_jobs"):
            return

        jobs_table = Table(
            "xpl_analysis_jobs",
            MetaData(),
            autoload_with=db.engine,
        )
        clauses = []
        if task_id:
            clauses.append(jobs_table.c.task_id == task_id)
        if result_ids:
            clauses.append(jobs_table.c.task_result_id.in_(result_ids))
        if return_series_ids:
            clauses.append(jobs_table.c.return_series_id.in_(return_series_ids))
        if clauses:
            db.session.execute(jobs_table.delete().where(or_(*clauses)))

    def delete_summary_index_by_result_ids(self, result_ids, commit=True):
        deleted = (
            TaskResultSummaryIndex.query
            .filter(TaskResultSummaryIndex.task_result_id.in_(result_ids))
            .delete(synchronize_session=False)
        )
        if commit:
            self._commit()
        return deleted

    def delete_summary_index_by_task_or_results(self, task_id, result_ids, commit=True):
        deleted = (
            TaskResultSummaryIndex.query
            .filter(
                (TaskResultSummaryIndex.task_id == task_id)
                | TaskResultSummaryIndex.task_result_id.in_(result_ids)
            )
            .delete(synchronize_session=False)
        )
        if commit:
            self._commit()
        return deleted

    def delete_summary_index(self, task_id, commit=True):
        """按任务清汇总索引；返回删除行数。"""
        deleted = (
            TaskResultSummaryIndex.query.filter_by(task_id=task_id)
            .delete(synchronize_session=False)
        )
        if commit:
            self._commit()
        return deleted

    def delete_summary_index_older_than(self, cutoff, commit=True):
        """清理窗口条件压 SQL 层；返回删除行数。"""
        deleted = (
            TaskResultSummaryIndex.query
            .filter(TaskResultSummaryIndex.created_at < cutoff)
            .delete(synchronize_session=False)
        )
        if commit:
            self._commit()
        return deleted

    # ---- BacktestProductResultCache ----

    def get_product_cache(self, batch_id, cache_key):
        row = (
            BacktestProductResultCache.query
            .filter_by(batch_id=batch_id, cache_key=cache_key)
            .first()
        )
        return row.to_dict() if row else None

    def upsert_product_cache(self, batch_id, cache_key, fields, commit=True):
        """按 (batch_id, cache_key) 唯一键存在则更新、否则新建。"""
        with db.session.no_autoflush:
            row = (
                BacktestProductResultCache.query
                .filter_by(batch_id=batch_id, cache_key=cache_key)
                .first()
            )
        if row is None:
            row = BacktestProductResultCache(batch_id=batch_id, cache_key=cache_key, **fields)
            db.session.add(row)
        else:
            for key, value in fields.items():
                setattr(row, key, value)
        if commit:
            self._commit()
        return row.to_dict()

    def delete_product_cache_by_task(self, task_id, commit=True):
        """按来源任务清产品缓存；返回删除行数。"""
        deleted = (
            BacktestProductResultCache.query.filter_by(source_task_id=task_id)
            .delete(synchronize_session=False)
        )
        if commit:
            self._commit()
        return deleted

    # ---- BacktestSheetRunLock（acquire/release 原子性红线） ----

    def get_lock(self, spreadsheet_id):
        row = BacktestSheetRunLock.query.filter_by(spreadsheet_id=spreadsheet_id).first()
        return row.to_dict() if row else None

    def acquire_lock(self, spreadsheet_id, task_id, task_type, commit=True):
        """原子获取 per-sheet 运行锁。

        返回 (acquired, locked_task_id)：
        - 同任务已持锁 → (True, None)（幂等）；
        - 他任务持锁 → (False, 该任务 id)；
        - 无锁 → 插入行并提交；唯一约束冲突（并发竞态）→ 回滚复查后判失败。
        """
        if not spreadsheet_id:
            return True, None

        existing = BacktestSheetRunLock.query.filter_by(spreadsheet_id=spreadsheet_id).first()
        if existing and existing.task_id == task_id:
            return True, None
        if existing:
            return False, existing.task_id

        lock = BacktestSheetRunLock(
            spreadsheet_id=spreadsheet_id,
            task_id=task_id,
            task_type=task_type,
        )
        db.session.add(lock)
        try:
            if commit:
                self._commit()
            return True, None
        except IntegrityError:
            db.session.rollback()
            existing = BacktestSheetRunLock.query.filter_by(spreadsheet_id=spreadsheet_id).first()
            return False, existing.task_id if existing else None

    def release_lock(self, spreadsheet_id, task_id, commit=True):
        """仅持锁任务可释放；返回是否实际删除。"""
        if not spreadsheet_id:
            return False

        lock = BacktestSheetRunLock.query.filter_by(spreadsheet_id=spreadsheet_id).first()
        if not lock:
            return False
        if lock.task_id != task_id:
            return False

        db.session.delete(lock)
        if commit:
            self._commit()
        return True

    def release_locks_by_task(self, task_id, commit=True):
        """按任务清其持有的全部锁（watchdog 公共入口）；返回删除行数。"""
        deleted = (
            BacktestSheetRunLock.query.filter_by(task_id=task_id)
            .delete(synchronize_session=False)
        )
        if commit:
            self._commit()
        return deleted

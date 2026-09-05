"""回测相关仓储：TaskResultSummaryIndex / BacktestProductResultCache / BacktestSheetRunLock
（契约见 docs/design/data-layer-refactor/02 §2.12）。

锁红线（对齐 runtime.py 现有语义）：
- acquire_lock：同任务重复获取幂等成功；已被其他任务持有则失败并返回持锁任务；
  无锁行则插入并提交，撞唯一约束（并发竞态）时回滚复查后判失败；
- release_lock：持锁任务不匹配时拒绝释放（返回 False），不得删除他人锁。
"""
from sqlalchemy import MetaData, Table, func, inspect, or_
from sqlalchemy.orm import Load
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models import (
    BacktestProductResultCache,
    BacktestSheetRunLock,
    Task,
    TaskResult,
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

    def find_summary_index_entities_by_result(self, task_result_id):
        return TaskResultSummaryIndex.query.filter_by(task_result_id=task_result_id).all()

    def find_summary_index_entities_by_result_ids(self, result_ids):
        if not result_ids:
            return []
        return (
            TaskResultSummaryIndex.query
            .filter(TaskResultSummaryIndex.task_result_id.in_(result_ids))
            .all()
        )

    def get_task_result_pair(self, task_result_id):
        """(Task, TaskResult) join 实体，供候选记录提取。"""
        return (
            db.session.query(Task, TaskResult)
            .join(TaskResult, TaskResult.task_id == Task.id)
            .filter(TaskResult.id == task_result_id)
            .first()
        )

    def list_task_ids_by_visible_types(self, visible_types, task_id=None, stock_code=None):
        query = db.session.query(Task.id).filter(Task.task_type.in_(visible_types))
        if task_id:
            query = query.filter(Task.id == task_id)
        query = query.filter(or_(
            Task.name.ilike(f"%{stock_code}%"),
            Task.config.ilike(f"%{stock_code}%"),
        ))
        return [row[0] for row in query.all()]

    def list_task_result_pairs_by_filters(self, matched_task_ids, result_id=None):
        query = (
            db.session.query(Task, TaskResult)
            .join(TaskResult, TaskResult.task_id == Task.id)
            .options(
                Load(Task).load_only(Task.id, Task.name, Task.task_type, Task.config),
                Load(TaskResult).load_only(
                    TaskResult.id,
                    TaskResult.task_id,
                    TaskResult.parameters,
                    TaskResult.result,
                    TaskResult.success,
                    TaskResult.timestamp,
                ),
            )
            .filter(Task.id.in_(matched_task_ids), TaskResult.success == True)
        )
        if result_id:
            query = query.filter(TaskResult.id == int(result_id))
        return (
            query.order_by(TaskResult.timestamp.desc(), TaskResult.id.desc()).all()
        )

    def list_rebuild_task_ids(self, task_ids_query):
        """占位（由调用方传入查询的复杂场景不使用）。"""
        raise NotImplementedError

    def list_finished_task_ids(self, finished_statuses, supported_types, task_type=None, task_id=None):
        query = db.session.query(Task.id).filter(Task.status.in_(finished_statuses))
        if task_type:
            query = query.filter(Task.task_type == task_type)
        else:
            query = query.filter(Task.task_type.in_(supported_types))
        if task_id:
            query = query.filter(Task.id == task_id)
        rows = query.order_by(Task.created_at.asc(), Task.id.asc()).all()
        return [row[0] for row in rows]

    def list_task_result_pairs_for_rebuild(self, task_ids):
        return (
            db.session.query(Task, TaskResult)
            .join(TaskResult, TaskResult.task_id == Task.id)
            .options(
                Load(Task).load_only(Task.id, Task.name, Task.task_type, Task.config),
                Load(TaskResult).load_only(
                    TaskResult.id,
                    TaskResult.task_id,
                    TaskResult.parameters,
                    TaskResult.result,
                    TaskResult.success,
                    TaskResult.timestamp,
                ),
            )
            .filter(Task.id.in_(task_ids), TaskResult.success == True)
            .order_by(Task.id.asc(), TaskResult.id.asc())
            .all()
        )

    def delete_summary_index_by_task_ids(self, task_ids, commit=True):
        deleted = (
            TaskResultSummaryIndex.query
            .filter(TaskResultSummaryIndex.task_id.in_(task_ids))
            .delete(synchronize_session=False)
        )
        if commit:
            self._commit()
        return deleted

    def dedupe_best_per_task(self, group_expression=None, task_type=None, task_id=None):
        """按分组窗口函数去重，仅保留每组最新最优一条；返回删除行数。

        group_expression 缺省为汇总索引的周期分组
        （coalesce(nullif(period_key), nullif(year_label), nullif(kline_range))）。
        """
        if group_expression is None:
            group_expression = func.coalesce(
                func.nullif(TaskResultSummaryIndex.period_key, ""),
                func.nullif(TaskResultSummaryIndex.year_label, ""),
                func.nullif(TaskResultSummaryIndex.kline_range, ""),
                "",
            )
        ranked_query = db.session.query(
            TaskResultSummaryIndex.id.label("id"),
            func.row_number().over(
                partition_by=(TaskResultSummaryIndex.task_id, group_expression),
                order_by=(
                    func.date(TaskResultSummaryIndex.result_timestamp).desc(),
                    TaskResultSummaryIndex.best_metric_value.desc(),
                    TaskResultSummaryIndex.id.desc(),
                ),
            ).label("row_number"),
        )
        if task_id:
            ranked_query = ranked_query.filter(TaskResultSummaryIndex.task_id == task_id)
        if task_type:
            ranked_query = ranked_query.filter(TaskResultSummaryIndex.task_type == task_type)
        ranked = ranked_query.subquery()
        duplicate_ids = db.session.query(ranked.c.id).filter(ranked.c.row_number > 1)
        deleted = (
            TaskResultSummaryIndex.query
            .filter(TaskResultSummaryIndex.id.in_(duplicate_ids))
            .delete(synchronize_session=False)
        )
        TaskResultSummaryIndex.query.filter(
            TaskResultSummaryIndex.id.in_(
                db.session.query(ranked.c.id).filter(ranked.c.row_number == 1)
            )
        ).update({"is_best": True}, synchronize_session=False)
        return deleted

    def find_summary_index_entities_by_task_ordered(self, task_id):
        """任务汇总实体（保留最优判定顺序）。"""
        return (
            TaskResultSummaryIndex.query
            .filter_by(task_id=task_id)
            .order_by(
                func.date(TaskResultSummaryIndex.result_timestamp).desc(),
                TaskResultSummaryIndex.best_metric_value.desc(),
                TaskResultSummaryIndex.period_key.asc(),
                TaskResultSummaryIndex.year_label.asc(),
                TaskResultSummaryIndex.kline_range.asc(),
                TaskResultSummaryIndex.id.desc(),
            )
            .all()
        )

    def count_index_rows(self, task_type=None, task_id=None):
        query = TaskResultSummaryIndex.query
        if task_id:
            query = query.filter(TaskResultSummaryIndex.task_id == task_id)
        if task_type:
            query = query.filter(TaskResultSummaryIndex.task_type == task_type)
        return query.count()

    def delete_summary_index_by_scope(self, task_type=None, task_id=None, commit=True):
        """按 task_id/task_type 双条件批量删除汇总索引（rebuild reset 分支）；返回删除行数。"""
        query = TaskResultSummaryIndex.query
        if task_id:
            query = query.filter(TaskResultSummaryIndex.task_id == task_id)
        if task_type:
            query = query.filter(TaskResultSummaryIndex.task_type == task_type)
        deleted = query.delete(synchronize_session=False)
        if commit:
            self._commit()
        return deleted

    def page_summary_index(self, filters, page, per_page, *, best_per_stock=False):
        """汇总索引动态过滤分页查询。

        filters（全部可选）：task_type / visible_types / stock_keyword / market_type /
        period_key / excess_return_min / result_date_from / result_date_to（datetime）/
        task_id / result_id。日期解析与业务归一化留在服务层。
        best_per_stock=True 时按股票窗口函数取每组最新最优一条（summary_type=stock 语义）。
        返回 {items(to_dict 投影), summary_items, total, pages, has_prev, has_next}。
        """
        query = TaskResultSummaryIndex.query
        task_type = filters.get("task_type")
        if task_type:
            query = query.filter(TaskResultSummaryIndex.task_type == task_type)
        visible_types = filters.get("visible_types")
        if visible_types:
            query = query.filter(TaskResultSummaryIndex.task_type.in_(visible_types))
        stock_keyword = filters.get("stock_keyword")
        if stock_keyword:
            pattern = f"%{stock_keyword}%"
            query = query.filter(or_(
                TaskResultSummaryIndex.stock_code.ilike(pattern),
                TaskResultSummaryIndex.stock_name.ilike(pattern),
                TaskResultSummaryIndex.task_name.ilike(pattern),
            ))
        market_type = filters.get("market_type")
        if market_type:
            query = query.filter(TaskResultSummaryIndex.market_type == market_type)
        period_key = filters.get("period_key")
        if period_key:
            query = query.filter(TaskResultSummaryIndex.period_key == period_key)
        excess_return_min = filters.get("excess_return_min")
        if excess_return_min is not None:
            query = query.filter(TaskResultSummaryIndex.best_metric_value > excess_return_min)
        result_date_from = filters.get("result_date_from")
        if result_date_from:
            query = query.filter(TaskResultSummaryIndex.result_timestamp >= result_date_from)
        result_date_to = filters.get("result_date_to")
        if result_date_to:
            query = query.filter(TaskResultSummaryIndex.result_timestamp <= result_date_to)
        task_id = filters.get("task_id")
        if task_id:
            query = query.filter(TaskResultSummaryIndex.task_id == task_id)
        result_id = filters.get("result_id")
        if result_id:
            query = query.filter(TaskResultSummaryIndex.task_result_id == int(result_id))

        if best_per_stock:
            query = query.filter(
                TaskResultSummaryIndex.is_best == True,
                TaskResultSummaryIndex.stock_code.isnot(None),
                TaskResultSummaryIndex.stock_code != "",
            )
            subquery = (
                query.with_entities(
                    TaskResultSummaryIndex.id.label("id"),
                    func.row_number().over(
                        partition_by=TaskResultSummaryIndex.stock_code,
                        order_by=(
                            func.date(TaskResultSummaryIndex.result_timestamp).desc(),
                            TaskResultSummaryIndex.best_metric_value.desc(),
                            TaskResultSummaryIndex.id.desc(),
                        ),
                    ).label("row_number"),
                ).subquery()
            )
            query = (
                TaskResultSummaryIndex.query
                .join(subquery, TaskResultSummaryIndex.id == subquery.c.id)
                .filter(subquery.c.row_number == 1)
                .order_by(
                    func.date(TaskResultSummaryIndex.result_timestamp).desc(),
                    TaskResultSummaryIndex.best_metric_value.desc(),
                    TaskResultSummaryIndex.stock_code.asc(),
                    TaskResultSummaryIndex.id.desc(),
                )
            )
        else:
            query = query.order_by(
                func.date(TaskResultSummaryIndex.result_timestamp).desc(),
                TaskResultSummaryIndex.best_metric_value.desc(),
                TaskResultSummaryIndex.id.desc(),
            )

        summary_query = query.with_entities(
            TaskResultSummaryIndex.stock_code,
            TaskResultSummaryIndex.task_id,
            TaskResultSummaryIndex.best_metric_value,
        )
        summary_items = [
            {"stock_code": row[0], "task_id": row[1], "best_metric_value": row[2]}
            for row in summary_query.all()
        ]
        pagination = query.paginate(page=page, per_page=per_page, error_out=False)
        return {
            "items": [item.to_dict() for item in pagination.items],
            "summary_items": summary_items,
            "total": pagination.total,
            "pages": pagination.pages,
            "has_prev": pagination.has_prev,
            "has_next": pagination.has_next,
        }

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

    def product_cache_exists(self, batch_id, cache_key):
        return (
            BacktestProductResultCache.query
            .filter_by(batch_id=batch_id, cache_key=cache_key)
            .first()
        ) is not None

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

    def insert_product_cache_if_absent(self, batch_id, cache_key, fields, commit=True):
        """已存在则跳过（不覆盖），返回是否新插入。

        先查后插 + 唯一约束兜底并发竞态：撞约束回滚并返回 False（先写者胜）。
        与 upsert_product_cache 的覆盖语义不同，二者不可互换。
        """
        if self.product_cache_exists(batch_id, cache_key):
            return False
        db.session.add(BacktestProductResultCache(batch_id=batch_id, cache_key=cache_key, **fields))
        try:
            if commit:
                self._commit()
            return True
        except IntegrityError:
            db.session.rollback()
            return False

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

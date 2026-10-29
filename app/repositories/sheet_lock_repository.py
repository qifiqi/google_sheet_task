"""Sheet 执行锁仓储（全任务类型统一，键为 spreadsheet_id）。

存储复用历史表 t_param_backtest_sheet_run_locks（模型 SheetExecutionLock）。

锁红线（对齐原 backtest 锁语义，全类型通用）：
- acquire：同任务重复获取幂等成功；已被其他任务持有则失败并返回持锁任务；
  无锁行则插入并提交，撞唯一约束（并发竞态）时回滚复查后判失败；
- release：持锁任务不匹配时拒绝释放（返回 False），不得删除他人锁。
"""
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models import SheetExecutionLock
from app.repositories.base import BaseRepository


class SheetLockRepository(BaseRepository):
    # 聚合仓储不绑定单一 model。
    model = None

    def get(self, spreadsheet_id):
        row = SheetExecutionLock.query.filter_by(spreadsheet_id=spreadsheet_id).first()
        return row.to_dict() if row else None

    def acquire(self, spreadsheet_id, task_id, task_type, commit=True):
        """原子获取单把执行锁。

        返回 (acquired, holder_task_id)：
        - 同任务已持锁 → (True, None)（幂等）；
        - 他任务持锁 → (False, 该任务 id)；
        - 无锁 → 插入行并提交；唯一约束冲突（并发竞态）→ 回滚复查后判失败。

        注意：commit=False 供外层 base.transaction() 组合时，IntegrityError
        分支的 rollback 会连带回滚整个外层事务；当前唯一调用链 acquire_all
        固定 commit=True，如需事务内组合请先改用 SAVEPOINT。
        """
        if not spreadsheet_id:
            return True, None

        existing = SheetExecutionLock.query.filter_by(spreadsheet_id=spreadsheet_id).first()
        if existing and existing.task_id == task_id:
            return True, None
        if existing:
            return False, existing.task_id

        lock = SheetExecutionLock(
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
            existing = SheetExecutionLock.query.filter_by(spreadsheet_id=spreadsheet_id).first()
            return False, existing.task_id if existing else None

    def acquire_all(self, spreadsheet_ids, task_id, task_type):
        """按顺序原子获取多把锁；任一冲突则回滚本次全部已获取（全拿全放）。

        返回 (acquired_all, holder_task_id, acquired_ids)。
        """
        acquired = []
        for spreadsheet_id in spreadsheet_ids:
            lock_acquired, holder_task_id = self.acquire(
                spreadsheet_id, task_id, task_type
            )
            if not lock_acquired:
                for acquired_spreadsheet_id in acquired:
                    self.release(acquired_spreadsheet_id, task_id)
                return False, holder_task_id, acquired
            acquired.append(spreadsheet_id)
        return True, None, acquired

    def release(self, spreadsheet_id, task_id, commit=True):
        """仅持锁任务可释放；返回是否实际删除。"""
        if not spreadsheet_id:
            return False

        lock = SheetExecutionLock.query.filter_by(spreadsheet_id=spreadsheet_id).first()
        if not lock:
            return False
        if lock.task_id != task_id:
            return False

        db.session.delete(lock)
        if commit:
            self._commit()
        return True

    def release_all_by_task(self, task_id, commit=True):
        """按任务清其持有的全部锁（收尾/看门狗公共入口）；返回删除行数。"""
        deleted = (
            SheetExecutionLock.query.filter_by(task_id=task_id)
            .delete(synchronize_session=False)
        )
        if commit:
            self._commit()
        return deleted

    def list_spreadsheet_ids_by_task(self, task_id):
        """任务当前持有的全部锁键（收尾接力集合依据，与释放动作同源）。"""
        rows = SheetExecutionLock.query.filter_by(task_id=task_id).all()
        return sorted(row.spreadsheet_id for row in rows)

    def find_conflict(self, spreadsheet_ids, exclude_task_id=None):
        """返回任一 sheet 的他任务持锁者 id；全部空闲返回 None。"""
        for spreadsheet_id in spreadsheet_ids:
            lock = SheetExecutionLock.query.filter_by(spreadsheet_id=spreadsheet_id).first()
            if lock and lock.task_id != exclude_task_id:
                return lock.task_id
        return None


sheet_lock_repository = SheetLockRepository()

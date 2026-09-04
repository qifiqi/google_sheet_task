"""repository 基类与通用约定（见 docs/design/data-layer-refactor/02 §1）。

通用规则：
1. 所有写方法签名带 commit: bool = True，默认方法内提交（保持现状事务粒度），
   异常时 rollback 后原样 raise（禁止 raise e）；
2. 读方法一律不 commit；
3. 返回 JSON 兼容结构（to_dict() / with_entities 投影）；
   get_* 不存在返回 None，get_required_* 抛 NotFoundError；
4. repository 内禁止 import app.services / app.routes / Flask；
5. 跨 repository 原子流程在 service/route 层组合：
   with repo.transaction(): 各写方法传 commit=False，上下文退出统一提交；
6. 无兼容入口：每个能力只有一个方法入口。
"""
from contextlib import contextmanager

from app.extensions import db


class BaseRepository:
    model = None  # 子类指定对应模型类

    @contextmanager
    def transaction(self):
        """多步原子流程：调用方在各写方法传 commit=False，由此上下文统一提交/回滚。"""
        try:
            yield
            db.session.commit()
        except Exception:
            db.session.rollback()
            raise

    def _commit(self):
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
            raise

    def _rollback(self):
        db.session.rollback()

    def get_entity(self, pk):
        """返回 ORM 实例（不 commit）。

        任务执行域（runtime/runner 线程目标）的正式实体访问方法，长期保留；
        其余场景一律使用 dict 返回方法。
        """
        return db.session.get(self.model, pk) if self.model else None

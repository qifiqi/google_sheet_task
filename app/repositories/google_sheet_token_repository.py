"""GoogleSheetToken 仓储（契约见 docs/design/data-layer-refactor/02 §2.9）。

可用性筛选、状态流转方法按 google_sheet_token_service 调用点定形后补入（B2）。
"""
from app.extensions import db
from app.exceptions import NotFoundError
from app.models import GoogleSheetToken
from app.repositories.base import BaseRepository


class GoogleSheetTokenRepository(BaseRepository):
    model = GoogleSheetToken

    # ---- 读 ----

    def apply_in_use_counts(self, usage: dict[int, int], commit=True) -> int:
        """按主键回写 current_in_use_count（对账）；不加载 token_context 大字段。

        返回更新的行数。usage 为 {token_id: 目标占用数}。
        """
        updated = 0
        for token_id, count in (usage or {}).items():
            updated += (
                GoogleSheetToken.query
                .filter_by(id=int(token_id))
                .update(
                    {"current_in_use_count": int(count)},
                    synchronize_session=False,
                )
            )
        if commit:
            self._commit()
        return updated

    def list_entities_ordered(self, task_type=None):
        """list_tokens 的实体形态（服务层转 dict）。"""
        query = GoogleSheetToken.query
        if task_type:
            query = query.filter_by(task_type=task_type)
        return query.order_by(
            GoogleSheetToken.is_active.desc(),
            GoogleSheetToken.current_in_use_count.asc(),
            GoogleSheetToken.task_usage_count.asc(),
            GoogleSheetToken.name.asc(),
        ).all()

    def list_active_entities(self, task_type=None):
        """启用中的 token 实体（随机选取/可用统计用）。"""
        query = GoogleSheetToken.query.filter_by(is_active=True)
        if task_type:
            query = query.filter_by(task_type=task_type)
        return query

    def add_entity(self, entity, flush=True):
        """挂起新建实体（导入流程需先 flush 取 id 再补 token_file）。"""
        db.session.add(entity)
        if flush:
            db.session.flush()
        return entity

    def get_by_context(self, token_context, task_type):
        """按内容+任务类型查重（导入幂等）。"""
        return GoogleSheetToken.query.filter_by(
            token_context=token_context,
            task_type=task_type,
        ).first()

    def count_active(self):
        return GoogleSheetToken.query.filter_by(is_active=True).count()

    def sum_field(self, field_name):
        """对指定数值列求和（占用汇总）。"""
        from sqlalchemy import func

        column = getattr(GoogleSheetToken, field_name)
        return db.session.query(
            func.coalesce(func.sum(column), 0)
        ).scalar() or 0

    def delete(self, token_id, commit=True):
        row = db.session.get(GoogleSheetToken, token_id)
        if row is None:
            return False
        db.session.delete(row)
        if commit:
            self._commit()
        return True


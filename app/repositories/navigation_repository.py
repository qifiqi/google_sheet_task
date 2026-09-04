"""NavigationMenuItem 仓储（契约见 docs/design/data-layer-refactor/02 §2.6）。"""
from app.extensions import db
from app.models import NavigationMenuItem
from app.repositories.base import BaseRepository


class NavigationRepository(BaseRepository):
    model = NavigationMenuItem

    # ---- 读 ----

    def list_all(self):
        """按 sort_order, id 排序返回全部菜单项。"""
        return [
            row.to_dict()
            for row in NavigationMenuItem.query
            .order_by(NavigationMenuItem.sort_order.asc(), NavigationMenuItem.id.asc())
            .all()
        ]

    def list_visible(self):
        """仅可见菜单项（meta_api /meta/nav 语义）。"""
        rows = (
            NavigationMenuItem.query
            .filter_by(is_visible=True)
            .order_by(NavigationMenuItem.sort_order.asc(), NavigationMenuItem.id.asc())
            .all()
        )
        return [row.to_dict() for row in rows]

    def get(self, item_id):
        row = db.session.get(NavigationMenuItem, item_id)
        return row.to_dict() if row else None

    def get_by_key(self, key):
        row = NavigationMenuItem.query.filter_by(key=key).first()
        return row.to_dict() if row else None

    def exists_key(self, key):
        return db.session.query(NavigationMenuItem.id).filter_by(key=key).first() is not None

    def count_children(self, key):
        return NavigationMenuItem.query.filter_by(parent_key=key).count()

    # ---- 写 ----

    def create(self, fields, commit=True):
        """保留 flush 取 id 语义：先 flush 拿到自增 id 再按需提交。"""
        row = NavigationMenuItem(**fields)
        db.session.add(row)
        db.session.flush()
        if commit:
            self._commit()
        return row.to_dict()

    def update(self, item_id, fields, commit=True):
        row = db.session.get(NavigationMenuItem, item_id)
        if row is None:
            return None
        for key, value in fields.items():
            setattr(row, key, value)
        if commit:
            self._commit()
        return row.to_dict()

    def delete(self, item_id, commit=True):
        row = db.session.get(NavigationMenuItem, item_id)
        if row is None:
            return False
        db.session.delete(row)
        if commit:
            self._commit()
        return True

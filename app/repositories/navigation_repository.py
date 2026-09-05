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

    def list_all_entities(self):
        """返回 ORM 实体（只读场景）。

        app/navigation.py 属启动播种模块（重构范围外），其
        sync_navigation_permissions/build_navigation_tree 依赖实体属性访问，
        因此 auth_api/meta_api 过渡期经本方法提供实体；待 navigation 归属
        归位二期再收敛为 dict 返回。
        """
        return NavigationMenuItem.query.all()

    def list_visible_entities(self):
        """list_visible 的实体形态，供范围外的 build_navigation_tree 消费。"""
        return (
            NavigationMenuItem.query
            .filter_by(is_visible=True)
            .order_by(NavigationMenuItem.sort_order.asc(), NavigationMenuItem.id.asc())
            .all()
        )

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

    def list_all_for_admin(self):
        """管理端列表：按 parent_key, sort_order, id 排序（config_api 现有语义）。"""
        rows = (
            NavigationMenuItem.query
            .order_by(
                NavigationMenuItem.parent_key.asc(),
                NavigationMenuItem.sort_order.asc(),
                NavigationMenuItem.id.asc(),
            )
            .all()
        )
        return [row.to_dict() for row in rows]

    def create_entity(self, fields, commit=True):
        """创建并返回实体。

        sync_navigation_permissions（app/navigation.py，重构范围外）依赖实体
        属性读写，导航菜单 CRUD 需要实体形态与 flush 取 id 语义。
        """
        row = NavigationMenuItem(**fields)
        db.session.add(row)
        db.session.flush()
        if commit:
            self._commit()
        return row

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

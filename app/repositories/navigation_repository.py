"""NavigationMenuItem 仓储（契约见 docs/design/data-layer-refactor/02 §2.6）。"""
from app.extensions import db
from app.models import NavigationMenuItem
from app.repositories.base import BaseRepository


class NavigationRepository(BaseRepository):
    model = NavigationMenuItem

    # ---- 读 ----

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

    def get_by_key(self, key):
        row = NavigationMenuItem.query.filter_by(key=key).first()
        return row.to_dict() if row else None

    def count_children(self, key):
        return NavigationMenuItem.query.filter_by(parent_key=key).count()

    # ---- 写 ----

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

    def delete(self, item_id, commit=True):
        row = db.session.get(NavigationMenuItem, item_id)
        if row is None:
            return False
        db.session.delete(row)
        if commit:
            self._commit()
        return True

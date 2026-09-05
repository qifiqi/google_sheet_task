"""User / Role / Permission 及关联表仓储（契约见 docs/design/data-layer-refactor/02 §2.7）。

关联表操作使用 SQLAlchemy Core 的 delete(table) 表达式构造（自动参数绑定）。
跨 repository 原子流程说明：
- delete_user 只清 user_roles 关联并删除用户行；
- Task.created_by_user_id 置空由调用方用 task_repository.clear_created_by(commit=False)
  组合进同一 transaction()（auth_api 删用户场景）。
"""
from sqlalchemy import delete

from app.extensions import db
from app.models import (
    Permission,
    Role,
    User,
    role_permissions,
    user_roles,
)
from app.repositories.base import BaseRepository


class RbacRepository(BaseRepository):
    # rbac 聚合仓储不绑定单一 model；实体访问走下方显式方法。
    model = None

    # ---- User 读 ----

    def get_user(self, user_id, include_permissions=False):
        user = db.session.get(User, user_id)
        return user.to_dict(include_permissions=include_permissions) if user else None

    def get_user_by_username(self, username, include_permissions=False):
        user = User.query.filter_by(username=username).first()
        return user.to_dict(include_permissions=include_permissions) if user else None

    def get_user_credentials(self, username):
        """登录用：仅投影鉴权所需列（不暴露给接口响应）。"""
        row = (
            User.query
            .with_entities(
                User.id,
                User.username,
                User.password_hash,
                User.is_active,
                User.token_version,
            )
            .filter_by(username=username)
            .first()
        )
        if row is None:
            return None
        return {
            "id": row.id,
            "username": row.username,
            "password_hash": row.password_hash,
            "is_active": row.is_active,
            "token_version": row.token_version,
        }

    def get_user_entity(self, user_id):
        """登录态装饰器使用的实体访问（utils/auth.py 热路径，长期保留）。"""
        return db.session.get(User, user_id)

    def get_user_state(self, user_id):
        """refresh 令牌等鉴权场景用：{id, is_active, token_version} 或 None。"""
        row = (
            User.query
            .with_entities(User.id, User.is_active, User.token_version)
            .filter_by(id=user_id)
            .first()
        )
        if row is None:
            return None
        return {
            "id": row.id,
            "is_active": row.is_active,
            "token_version": row.token_version,
        }

    def update_last_login(self, user_id, value, commit=True):
        """登录成功更新最后登录时间。"""
        return self.update_user(user_id, {"last_login": value}, commit=commit)

    def username_exists(self, username):
        return db.session.query(User.id).filter_by(username=username).first() is not None

    def list_users(self):
        return [u.to_dict() for u in User.query.order_by(User.id.asc()).all()]

    # ---- User 写 ----

    def create_user(self, username, password_hash, role_ids=None, commit=True, **fields):
        user = User(
            username=username,
            password_hash=password_hash,
            **fields,
        )
        if role_ids:
            user.roles = Role.query.filter(Role.id.in_(role_ids)).all()
        db.session.add(user)
        if commit:
            self._commit()
        return user.to_dict()

    def update_user(self, user_id, fields, role_ids=None, commit=True):
        user = db.session.get(User, user_id)
        if user is None:
            return None
        for key, value in fields.items():
            setattr(user, key, value)
        if role_ids is not None:
            user.roles = Role.query.filter(Role.id.in_(role_ids)).all() if role_ids else []
        if commit:
            self._commit()
        return user.to_dict()

    def delete_user(self, user_id, commit=True):
        """清 user_roles 关联并删除用户；Task.created_by_user_id 由调用方组合。"""
        user = db.session.get(User, user_id)
        if user is None:
            return False
        db.session.execute(
            delete(user_roles).where(user_roles.c.user_id == user.id)
        )
        db.session.delete(user)
        if commit:
            self._commit()
        return True

    # ---- Role 读 ----

    def role_code_exists(self, code):
        return db.session.query(Role.id).filter_by(code=code).first() is not None

    def get_role(self, role_id, include_permissions=False):
        role = db.session.get(Role, role_id)
        return role.to_dict(include_permissions=include_permissions) if role else None

    def list_roles(self, include_permissions=True):
        return [
            r.to_dict(include_permissions=include_permissions)
            for r in Role.query.order_by(Role.id.asc()).all()
        ]

    def list_roles_by_ids(self, role_ids):
        if not role_ids:
            return []
        return Role.query.filter(Role.id.in_(role_ids)).all()

    # ---- Role 写 ----

    def create_role(self, code, name, permission_ids=None, commit=True, **fields):
        role = Role(code=code, name=name, **fields)
        if permission_ids:
            role.permissions = Permission.query.filter(Permission.id.in_(permission_ids)).all()
        db.session.add(role)
        if commit:
            self._commit()
        return role.to_dict(include_permissions=True)

    def update_role(self, role_id, fields, permission_ids=None, commit=True):
        role = db.session.get(Role, role_id)
        if role is None:
            return None
        for key, value in fields.items():
            setattr(role, key, value)
        if permission_ids is not None:
            role.permissions = (
                Permission.query.filter(Permission.id.in_(permission_ids)).all()
                if permission_ids
                else []
            )
        if commit:
            self._commit()
        return role.to_dict(include_permissions=True)

    def delete_role(self, role_id, commit=True):
        """清 role_permissions + user_roles 关联后删除角色（auth_api 现有语义）。"""
        role = db.session.get(Role, role_id)
        if role is None:
            return False
        db.session.execute(
            delete(role_permissions).where(role_permissions.c.role_id == role.id)
        )
        db.session.execute(
            delete(user_roles).where(user_roles.c.role_id == role.id)
        )
        db.session.delete(role)
        if commit:
            self._commit()
        return True

    # ---- Permission 读 ----

    def list_permissions(self):
        """按 group, code 排序（auth_api 现有语义）。"""
        return [
            p.to_dict()
            for p in Permission.query.order_by(Permission.group.asc(), Permission.code.asc()).all()
        ]

    def list_permission_codes(self):
        """权限编码列表（utils/auth.py 登录热路径；权限缓存仍留在 auth 层）。"""
        rows = Permission.query.with_entities(Permission.code).all()
        return [row[0] for row in rows]

    def list_alert_oncall_active_entities(self):
        """启用中且参与值班的用户实体（钉钉通知取手机号/角色）。"""
        return User.query.filter_by(is_active=True, is_alert_oncall=True).all()

    def list_roles_all_entities(self):
        """角色实体全量（含权限关联懒加载），供 is_alert_oncall 判断等场景。"""
        return Role.query.all()

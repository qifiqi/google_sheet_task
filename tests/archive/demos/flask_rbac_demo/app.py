"""Flask RBAC 演示程序（重建版）。

原 app.py 未纳入 git 且在 2026-08-29 目录整理时被误删；本文件依据
instance/demo_rbac.db 中的表结构、种子数据与 token_version 递增痕迹重建，
功能与原演示一致：最小 Flask + SQLAlchemy RBAC，含登录、token_version
会话吊销与两个权限门面页面。

启动：

    python app.py   # http://127.0.0.1:5001

内置账号（首启自动播种）：admin / editor / viewer，密码均为 demo123。
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from flask import Flask, jsonify, render_template_string, request
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import check_password_hash, generate_password_hash

BASE_DIR = Path(__file__).resolve().parent

app = Flask(__name__)
app.config.update(
    SQLALCHEMY_DATABASE_URI=f"sqlite:///{BASE_DIR / 'instance' / 'demo_rbac.db'}",
    SQLALCHEMY_ENGINE_OPTIONS={"pool_pre_ping": True},
)
db = SQLAlchemy(app)


user_roles = db.Table(
    "user_roles",
    db.Column("user_id", db.Integer, db.ForeignKey("users.id"), primary_key=True),
    db.Column("role_id", db.Integer, db.ForeignKey("roles.id"), primary_key=True),
)
role_permissions = db.Table(
    "role_permissions",
    db.Column("role_id", db.Integer, db.ForeignKey("roles.id"), primary_key=True),
    db.Column("permission_id", db.Integer, db.ForeignKey("permissions.id"), primary_key=True),
)


class Permission(db.Model):
    __tablename__ = "permissions"
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(100), unique=True, nullable=False)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.String(255), default="")


class Role(db.Model):
    __tablename__ = "roles"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(64), nullable=False)
    code = db.Column(db.String(64), unique=True, nullable=False)
    description = db.Column(db.String(255), default="")
    is_system = db.Column(db.Boolean, default=False)
    permissions = db.relationship(Permission, secondary=role_permissions)


class User(db.Model):
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    token_version = db.Column(db.Integer, nullable=False, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    roles = db.relationship(Role, secondary=user_roles)

    def get_permissions(self) -> set[str]:
        return {permission.code for role in self.roles for permission in role.permissions}


DEMO_USERS = ("admin", "editor", "viewer")
DEMO_PASSWORD = "demo123"
ROLE_PERMISSIONS = {
    "admin": {"task:view", "task:create", "task:delete", "report:view", "page:admin", "page:demo"},
    "editor": {"task:view", "task:create", "report:view", "page:demo"},
    "viewer": {"task:view", "page:demo"},
}


def seed_demo_data() -> None:
    db.create_all()
    if User.query.count():
        return
    permission_map: dict[str, Permission] = {}
    for code, name in [
        ("task:view", "查看任务"),
        ("task:create", "创建任务"),
        ("task:delete", "删除任务"),
        ("report:view", "查看报表"),
        ("page:admin", "访问管理页面"),
        ("page:demo", "访问演示页面"),
    ]:
        permission = Permission(code=code, name=name)
        db.session.add(permission)
        permission_map[code] = permission
    for index, (name, code, description, is_system) in enumerate([
        ("管理员", "admin", "演示内置角色 admin", True),
        ("编辑", "editor", "演示内置角色 editor", False),
        ("访客", "viewer", "演示内置角色 viewer", False),
    ], start=1):
        role = Role(
            name=name,
            code=code,
            description=description,
            is_system=is_system,
            permissions=[permission_map[item] for item in ROLE_PERMISSIONS[code]],
        )
        db.session.add(role)
        db.session.add(User(
            username=code,
            password_hash=generate_password_hash(DEMO_PASSWORD),
            is_active=True,
            token_version=index,
            roles=[role],
        ))
    db.session.commit()


def _current_user():
    username = request.headers.get("X-Demo-User") or request.args.get("user")
    if not username:
        return None
    return User.query.filter_by(username=username, is_active=True).first()


def _require_permission(code: str):
    user = _current_user()
    if user is None:
        return None, (jsonify({"message": "未登录演示账号"}), 401)
    if code not in user.get_permissions():
        return None, (jsonify({"message": f"权限不足，需要 {code}"}), 403)
    return user, None


PAGE_TEMPLATE = "<h1>{{ title }}</h1><p>当前用户：{{ username }}，token_version={{ version }}</p>"


@app.get("/")
def index():
    return render_template_string(
        PAGE_TEMPLATE,
        title="Flask RBAC 演示",
        username=request.args.get("user", "匿名"),
        version="-",
    )


@app.get("/admin")
def admin_page():
    user, error = _require_permission("page:admin")
    if error:
        return error
    return render_template_string(
        PAGE_TEMPLATE, title="管理页面", username=user.username, version=user.token_version
    )


@app.get("/demo")
def demo_page():
    user, error = _require_permission("page:demo")
    if error:
        return error
    return render_template_string(
        PAGE_TEMPLATE, title="演示页面", username=user.username, version=user.token_version
    )


@app.post("/change-password")
def change_password():
    """修改密码并递增 token_version，模拟吊销全部存量会话。"""
    user, error = _require_permission("page:demo")
    if error:
        return error
    payload = request.get_json(silent=True) or {}
    new_password = str(payload.get("password") or "")
    if len(new_password) < 6:
        return jsonify({"message": "新密码至少 6 位"}), 400
    user.password_hash = generate_password_hash(new_password)
    user.token_version += 1
    db.session.commit()
    return jsonify({"message": "密码已更新", "token_version": user.token_version})


if __name__ == "__main__":
    with app.app_context():
        seed_demo_data()
    app.run(host="127.0.0.1", port=5001)

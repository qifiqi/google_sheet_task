from app.extensions import db
from app.models import NavigationMenuItem, Permission, Role, User
from app.navigation import sync_navigation_permissions
from app.startup import init_rbac
from app.utils.auth import create_access_token


def _auth_headers(user):
    token = create_access_token(user.id, token_version=user.token_version)
    return {"Authorization": f"Bearer {token}"}


def test_init_rbac_purges_legacy_non_page_permissions(app_factory):
    """接口级权限已移除：init_rbac 应清理历史非 page 权限及其角色关联。"""
    with app_factory.app_context():
        legacy = Permission(code="task:view", group="task", name="查看任务")
        page_perm = Permission(code="page:admin:tasks", group="page", name="访问任务管理页面")
        db.session.add_all([legacy, page_perm])
        db.session.flush()
        role = Role(name="遗留角色", code="legacy_role")
        role.permissions = [legacy, page_perm]
        db.session.add(role)
        db.session.commit()

        init_rbac()

        assert Permission.query.filter_by(code="task:view").first() is None
        assert Permission.query.filter_by(code="page:admin:tasks").first() is not None
        refreshed_role = Role.query.filter_by(code="legacy_role").one()
        assert [perm.code for perm in refreshed_role.permissions] == ["page:admin:tasks"]


def test_navigation_page_permission_is_created_from_database_route(app_factory):
    with app_factory.app_context():
        item = NavigationMenuItem(
            key="report",
            label="报表中心",
            path="/reports",
            permission="page:reports:view",
            is_visible=True,
        )
        db.session.add(item)
        db.session.flush()
        sync_navigation_permissions([item])
        db.session.commit()

        permission = Permission.query.filter_by(code="page:reports:view").one()
        assert permission.group == "page"
        assert permission.route_path == "/reports"
        assert permission.name == "访问 报表中心 页面"


def test_navigation_update_refreshes_page_permission_details(app_factory):
    with app_factory.app_context():
        item = NavigationMenuItem(
            key="report",
            label="旧报表",
            path="/reports",
            permission="page:reports:view",
            is_visible=True,
        )
        db.session.add(item)
        db.session.flush()
        sync_navigation_permissions([item])
        db.session.commit()

        item.label = "新报表"
        item.path = "/new-reports"
        sync_navigation_permissions([item])
        db.session.commit()

        permission = Permission.query.filter_by(code="page:reports:view").one()
        assert permission.route_path == "/new-reports"
        assert permission.name == "访问 新报表 页面"


def test_navigation_api_creates_page_permission_visible_to_role_management(app_factory):
    app = app_factory
    with app.app_context():
        role = Role(name="路由管理员", code="navigation_admin")
        user = User(username="navigation_admin_user", password_hash="test", is_active=True)
        user.roles = [role]
        db.session.add_all([role, user])
        db.session.commit()
        headers = _auth_headers(user)

    client = app.test_client()
    create_response = client.post(
        "/api/navigation-menu-items",
        headers=headers,
        json={
            "key": "report",
            "label": "报表中心",
            "path": "/reports",
            "permission": "page:reports:view",
            "is_visible": True,
        },
    )

    assert create_response.status_code == 200
    permissions_response = client.get("/api/admin/permissions", headers=headers)
    page_permissions = permissions_response.get_json()["data"]["page"]
    assert any(item["code"] == "page:reports:view" for item in page_permissions)

    nav_response = client.get("/api/meta/nav", headers=headers)
    page_permission_mappings = nav_response.get_json()["data"]["page_permissions"]
    assert {"path": "/reports", "permission": "page:reports:view"} in page_permission_mappings


def test_login_required_allows_authenticated_user(app_factory):
    app = app_factory

    @app.route("/__test_login_required")
    def login_required_route():
        from app.utils.auth import login_required

        @login_required
        def protected():
            return "ok"

        return protected()

    with app.app_context():
        role = Role(name="普通角色", code="plain_role")
        user = User(username="plain_role_user", password_hash="test", is_active=True)
        user.roles = [role]
        db.session.add_all([role, user])
        db.session.commit()
        headers = _auth_headers(user)

    client = app.test_client()
    assert client.get("/__test_login_required", headers=headers).status_code == 200
    assert client.get("/__test_login_required").status_code == 401

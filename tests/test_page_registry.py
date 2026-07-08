from app.config import BASE_PERMISSIONS, PERMISSIONS
from app.navigation import DEFAULT_NAVIGATION_MENU, build_nav_permission_map
from app.page_registry import PageDef, page_permission_map, page_permission_prefixes, page_permissions


def _flatten_nav(items):
    rows = []
    for item in items:
        rows.append(item)
        rows.extend(_flatten_nav(item.get("children") or []))
    return rows


def test_page_permissions_are_generated_from_registry():
    base_codes = {code for _group, code, _name, _route_path in BASE_PERMISSIONS}
    page_codes = {code for _group, code, _name, _route_path in page_permissions()}
    permission_codes = {code for _group, code, _name, _route_path in PERMISSIONS}

    assert "page:admin:tasks" not in base_codes
    assert "page:admin:tasks" in page_codes
    assert "page:admin:tasks" in permission_codes
    assert "page:backtest_multi_product:create" in permission_codes


def test_default_navigation_menu_is_generated_from_registry():
    rows = {item["key"]: item for item in _flatten_nav(DEFAULT_NAVIGATION_MENU)}

    assert rows["dashboard"]["path"] == "/admin"
    assert rows["task"]["label"] == "任务模块"
    assert rows["tasks"]["path"] == "/admin/tasks"
    assert rows["c7"]["permission"] == "page:google_sheet:c7"
    assert "backtest_create" not in rows


def test_navigation_permission_map_keeps_legacy_paths():
    permission_map = build_nav_permission_map()

    assert permission_map["/admin/tasks"] == "page:admin:tasks"
    assert permission_map["/google-sheet/?version=c7"] == "page:google_sheet:c7"
    assert permission_map["/task/list?version=c7"] == "page:google_sheet:c7"


def test_page_permission_map_includes_aliases_and_hidden_pages():
    permission_map = page_permission_map()
    prefixes = page_permission_prefixes()

    assert permission_map["/admin/tasks"] == "page:admin:tasks"
    assert permission_map["/admin/tasks/"] == "page:admin:tasks"
    assert permission_map["/task/list?version=c7"] == "page:google_sheet:c7"
    assert permission_map["/backtest-training/create"] == "page:backtest:create"
    assert {
        "prefix": "/backtest-training/detail/",
        "permission": "page:backtest:list",
    } in prefixes


def test_seed_default_data_syncs_registry_permissions_and_menu(app_factory):
    from app.models import NavigationMenuItem, Permission
    from app.seed_data import seed_default_data

    app = app_factory
    seed_default_data(app, include_scheduler=False)

    with app.app_context():
        assert Permission.query.filter_by(code="page:admin:tasks").first()
        assert Permission.query.filter_by(code="page:backtest_multi_product:create").first()

        tasks_item = NavigationMenuItem.query.filter_by(key="tasks").first()
        assert tasks_item
        assert tasks_item.path == "/admin/tasks"
        assert tasks_item.permission == "page:admin:tasks"


def test_admin_registry_fallback_renders_simple_template_page(app_factory, monkeypatch):
    from jinja2 import ChoiceLoader, DictLoader

    from app.routes import admin as admin_routes

    page = PageDef(
        key="registry_test",
        label="Registry Test",
        path="/admin/registry-test",
        template="admin/registry_test.html",
        permission="page:admin:registry_test",
    )
    app = app_factory
    monkeypatch.setattr(admin_routes, "PAGE_DEFS", (*admin_routes.PAGE_DEFS, page))
    app.jinja_loader = ChoiceLoader([
        DictLoader({"admin/registry_test.html": "registry fallback ok"}),
        app.jinja_loader,
    ])

    response = app.test_client().get("/admin/registry-test")

    assert response.status_code == 200
    assert b"registry fallback ok" in response.data

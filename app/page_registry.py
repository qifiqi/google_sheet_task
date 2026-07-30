"""Central page, page-permission and default navigation declarations."""
from dataclasses import dataclass, field


@dataclass(frozen=True)
class PageDef:
    key: str
    label: str
    path: str
    template: str | None
    permission: str | None
    parent_key: str | None = None
    sort_order: int = 0
    visible: bool = True
    endpoint: str | None = None
    permission_name: str | None = None
    aliases: tuple[str, ...] = field(default_factory=tuple)
    path_prefixes: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class NavGroupDef:
    key: str
    label: str
    sort_order: int


NAV_GROUPS = (
    NavGroupDef(key="task", label="任务模块", sort_order=10),
    NavGroupDef(key="data", label="数据模块", sort_order=20),
    NavGroupDef(key="scheduler_group", label="调度模块", sort_order=30),
    NavGroupDef(key="system", label="系统模块", sort_order=40),
    NavGroupDef(key="business", label="业务模块", sort_order=50),
)


PAGE_DEFS = (
    PageDef(
        key="dashboard",
        label="仪表盘",
        path="/admin",
        template="admin/dashboard.html",
        permission="page:admin:dashboard",
        sort_order=0,
    ),
    PageDef(
        key="tasks",
        label="任务管理",
        path="/admin/tasks",
        template="admin/tasks.html",
        permission="page:admin:tasks",
        parent_key="task",
        sort_order=10,
    ),
    PageDef(
        key="templates",
        label="任务模板",
        path="/admin/templates",
        template="admin/templates.html",
        permission="page:admin:templates",
        parent_key="task",
        sort_order=20,
    ),
    PageDef(
        key="results",
        label="任务结果",
        path="/admin/results",
        template="admin/results.html",
        permission="page:admin:results",
        parent_key="task",
        sort_order=30,
    ),
    PageDef(
        key="xpl_analysis_jobs",
        label="XPL Job 运维",
        path="/admin/xpl-analysis-jobs",
        template="admin/xpl_analysis_jobs.html",
        permission="page:admin:xpl_analysis_jobs",
        parent_key="task",
        sort_order=40,
        permission_name="访问 XPL Job 运维页面",
    ),
    PageDef(
        key="model_summary",
        label="单模型汇总",
        path="/admin/model-summary",
        template="admin/model_summary.html",
        permission="page:admin:model_summary",
        parent_key="data",
        sort_order=10,
    ),
    PageDef(
        key="eastmoney_kline",
        label="东方财富 K 线",
        path="/admin/eastmoney-kline",
        template="admin/eastmoney_kline.html",
        permission=None,
        parent_key="data",
        sort_order=20,
    ),
    PageDef(
        key="scheduler",
        label="定时任务",
        path="/admin/scheduler",
        template="admin/scheduler.html",
        permission="page:admin:scheduler",
        parent_key="scheduler_group",
        sort_order=10,
    ),
    PageDef(
        key="config",
        label="系统配置",
        path="/admin/config",
        template="admin/config.html",
        permission="page:admin:config",
        parent_key="system",
        sort_order=10,
    ),
    PageDef(
        key="sheets",
        label="Google Sheet 管理",
        path="/admin/google-sheets",
        template="admin/google_sheets.html",
        permission="page:admin:google_sheets",
        parent_key="system",
        sort_order=20,
        permission_name="访问 Google Sheet 管理页面",
    ),
    PageDef(
        key="navigation",
        label="路由表管理",
        path="/admin/navigation",
        template="admin/navigation.html",
        permission="page:admin:navigation",
        parent_key="system",
        sort_order=30,
        permission_name="访问路由表页面",
    ),
    PageDef(
        key="logs",
        label="系统日志",
        path="/admin/logs",
        template="admin/logs.html",
        permission="page:admin:logs",
        parent_key="system",
        sort_order=40,
    ),
    PageDef(
        key="users",
        label="用户管理",
        path="/admin/users",
        template="admin/users.html",
        permission="page:admin:users",
        parent_key="system",
        sort_order=50,
    ),
    PageDef(
        key="roles",
        label="角色管理",
        path="/admin/roles",
        template="admin/roles.html",
        permission="page:admin:roles",
        parent_key="system",
        sort_order=60,
    ),
    PageDef(
        key="c3",
        label="Google Sheet C3",
        path="/google-sheet/?version=c3",
        template="google_sheet/create.html",
        permission="page:google_sheet:c3",
        parent_key="business",
        sort_order=10,
        permission_name="访问 Google Sheet C3 页面",
        aliases=("/task/list?version=c3", "/task/create/c3"),
    ),
    PageDef(
        key="c4",
        label="Google Sheet C4",
        path="/google-sheet/?version=c4",
        template="google_sheet_c4/create.html",
        permission="page:google_sheet:c4",
        parent_key="business",
        sort_order=20,
        permission_name="访问 Google Sheet C4 页面",
        aliases=("/task/list?version=c4", "/task/create/c4"),
    ),
    PageDef(
        key="c5",
        label="Google Sheet C5",
        path="/google-sheet/?version=c5",
        template="google_sheet_c5/create.html",
        permission="page:google_sheet:c5",
        parent_key="business",
        sort_order=30,
        permission_name="访问 Google Sheet C5 页面",
        aliases=("/task/list?version=c5", "/task/create/c5"),
    ),
    PageDef(
        key="c7",
        label="Google Sheet C7",
        path="/google-sheet/?version=c7",
        template="google_sheet_c7/create.html",
        permission="page:google_sheet:c7",
        parent_key="business",
        sort_order=40,
        permission_name="访问 Google Sheet C7 页面",
        aliases=("/task/list?version=c7", "/task/create/c7"),
    ),
    PageDef(
        key="backtest",
        label="单品数据回测",
        path="/backtest-training/list",
        template="backtest_training/list.html",
        permission="page:backtest:list",
        parent_key="business",
        sort_order=50,
        permission_name="访问回测列表页面",
        aliases=("/backtest/list",),
        path_prefixes=(
            "/backtest-training/detail/",
            "/backtest-training/global-preview/",
            "/backtest-training/result/",
        ),
    ),
    PageDef(
        key="backtest_create",
        label="回测创建",
        path="/backtest-training/create",
        template="backtest_training/create.html",
        permission="page:backtest:create",
        visible=False,
        permission_name="访问回测创建页面",
        aliases=("/backtest/create",),
    ),
    PageDef(
        key="backtest_multi_product",
        label="多品数据回测",
        path="/backtest-multi-product/list",
        template="backtest_multi_product/list.html",
        permission="page:backtest_multi_product:list",
        parent_key="business",
        sort_order=60,
        permission_name="访问多品数据回测列表页面",
        aliases=("/backtest-multi/list",),
    ),
    PageDef(
        key="backtest_multi_product_create",
        label="多品数据回测创建",
        path="/backtest-multi-product/create",
        template="backtest_multi_product/create.html",
        permission="page:backtest_multi_product:create",
        visible=False,
        permission_name="访问多品数据回测创建页面",
        aliases=("/backtest-multi/create",),
    ),
)


EXTRA_NAV_ITEMS = (
    {"key": "xpl", "label": "夏普率计算", "path": "/xpl", "parent_key": "business", "sort_order": 70},
    {"key": "xpl_v1", "label": "V1 回测数据分析", "path": "/xpl/v1", "parent_key": "business", "sort_order": 80},
)


def page_permissions():
    return [
        (
            "page",
            page.permission,
            page.permission_name or f"访问{page.label}页面",
            page.path,
        )
        for page in PAGE_DEFS
        if page.permission
    ]


def _nav_item_from_page(page):
    item = {
        "key": page.key,
        "label": page.label,
        "path": page.path,
        "permission": page.permission,
        "sort_order": page.sort_order,
    }
    return {key: value for key, value in item.items() if value is not None}


def _add_nav_item(groups, roots, item):
    parent_key = item.pop("parent_key", None)
    if parent_key:
        groups[parent_key]["children"].append(item)
    else:
        roots.append(item)


def default_navigation_menu():
    groups = {
        group.key: {
            "key": group.key,
            "label": group.label,
            "sort_order": group.sort_order,
            "children": [],
        }
        for group in NAV_GROUPS
    }
    roots = []

    for page in sorted(PAGE_DEFS, key=lambda item: item.sort_order):
        if not page.visible:
            continue
        _add_nav_item(groups, roots, {**_nav_item_from_page(page), "parent_key": page.parent_key})

    for item in EXTRA_NAV_ITEMS:
        _add_nav_item(groups, roots, dict(item))

    roots.extend(
        group
        for group in sorted(groups.values(), key=lambda item: item["sort_order"])
        if group["children"]
    )

    def strip_sort_order(item):
        item = dict(item)
        item.pop("sort_order", None)
        if item.get("children"):
            item["children"] = [
                strip_sort_order(child)
                for child in sorted(item["children"], key=lambda child: child.get("sort_order", 0))
            ]
        return item

    return [strip_sort_order(item) for item in sorted(roots, key=lambda item: item.get("sort_order", 0))]


def page_permission_map(include_aliases=True):
    mapping = {}
    for page in PAGE_DEFS:
        if not page.permission:
            continue
        mapping[page.path] = page.permission
        if include_aliases:
            for alias in page.aliases:
                mapping[alias] = page.permission
        if "?" not in page.path:
            trimmed = page.path.rstrip("/")
            mapping[f"{trimmed}/"] = page.permission
    return mapping


def page_permission_prefixes():
    prefixes = []
    for page in PAGE_DEFS:
        if not page.permission:
            continue
        prefixes.extend(
            {"prefix": prefix, "permission": page.permission}
            for prefix in page.path_prefixes
        )
    return prefixes

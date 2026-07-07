"""Default sidebar navigation and helpers."""


DEFAULT_NAVIGATION_MENU = [
    {"key": "dashboard", "label": "仪表盘", "path": "/admin", "permission": "page:admin:dashboard"},
    {"key": "task", "label": "任务模块", "children": [
        {"key": "tasks", "label": "任务管理", "path": "/admin/tasks", "permission": "page:admin:tasks"},
        {"key": "templates", "label": "任务模板", "path": "/admin/templates", "permission": "page:admin:templates"},
        {"key": "results", "label": "任务结果", "path": "/admin/results", "permission": "page:admin:results"},
        {"key": "xpl_analysis_jobs", "label": "XPL Job 运维", "path": "/admin/xpl-analysis-jobs", "permission": "page:admin:xpl_analysis_jobs"},
    ]},
    {"key": "data", "label": "数据模块", "children": [
        {"key": "model_summary", "label": "单模型汇总", "path": "/admin/model-summary", "permission": "page:admin:model_summary"},
    ]},
    {"key": "scheduler_group", "label": "调度模块", "children": [
        {"key": "scheduler", "label": "定时任务", "path": "/admin/scheduler", "permission": "page:admin:scheduler"},
    ]},
    {"key": "system", "label": "系统模块", "children": [
        {"key": "config", "label": "系统配置", "path": "/admin/config", "permission": "page:admin:config"},
        {"key": "sheets", "label": "Google Sheet 管理", "path": "/admin/google-sheets", "permission": "page:admin:google_sheets"},
        {"key": "navigation", "label": "路由表管理", "path": "/admin/navigation", "permission": "page:admin:navigation"},
        {"key": "logs", "label": "系统日志", "path": "/admin/logs", "permission": "page:admin:logs"},
        {"key": "users", "label": "用户管理", "path": "/admin/users", "permission": "page:admin:users"},
        {"key": "roles", "label": "角色管理", "path": "/admin/roles", "permission": "page:admin:roles"},
    ]},
    {"key": "business", "label": "业务模块", "children": [
        {"key": "c3", "label": "Google Sheet C3", "path": "/google-sheet/?version=c3", "permission": "page:google_sheet:c3"},
        {"key": "c4", "label": "Google Sheet C4", "path": "/google-sheet/?version=c4", "permission": "page:google_sheet:c4"},
        {"key": "c5", "label": "Google Sheet C5", "path": "/google-sheet/?version=c5", "permission": "page:google_sheet:c5"},
        {"key": "c7", "label": "Google Sheet C7", "path": "/google-sheet/?version=c7", "permission": "page:google_sheet:c7"},
        {"key": "backtest", "label": "单品数据回测", "path": "/backtest-training/list", "permission": "page:backtest:list"},
        {"key": "backtest_multi_product", "label": "多品数据回测", "path": "/backtest-multi-product/list", "permission": "page:backtest_multi_product:list"},
        {"key": "xpl", "label": "夏普率计算", "path": "/xpl"},
        {"key": "xpl_v1", "label": "V1 回测数据分析", "path": "/xpl/v1"},
    ]},
]


def flatten_navigation_items(items, parent_key=None):
    rows = []
    for index, item in enumerate(items or []):
        row = {
            "key": item.get("key"),
            "label": item.get("label"),
            "path": item.get("path"),
            "permission": item.get("permission"),
            "parent_key": parent_key,
            "sort_order": item.get("sort_order", index * 10),
        }
        rows.append(row)
        rows.extend(flatten_navigation_items(item.get("children") or [], item.get("key")))
    return rows


NAV_LEGACY_PATH_MAP = {
    "/task/list?version=c3": "/google-sheet/?version=c3",
    "/task/list?version=c4": "/google-sheet/?version=c4",
    "/task/list?version=c5": "/google-sheet/?version=c5",
    "/task/list?version=c7": "/google-sheet/?version=c7",
    "/task/create": "/google-sheet/create",
    "/task/create/c3": "/google-sheet/?version=c3",
    "/task/create/c4": "/google-sheet/?version=c4",
    "/task/create/c5": "/google-sheet/?version=c5",
    "/task/create/c7": "/google-sheet/?version=c7",
    "/backtest/list": "/backtest-training/list",
    "/backtest/create": "/backtest-training/create",
    "/backtest-multi/list": "/backtest-multi-product/list",
    "/backtest-multi/create": "/backtest-multi-product/create",
}


def normalize_nav_path(path):
    return NAV_LEGACY_PATH_MAP.get(path, path)


def normalize_nav_label(key, label):
    if key == "backtest" and label == "数据回测":
        return "单品数据回测"
    return label


def build_nav_permission_map(items=None):
    permission_map = {}
    for row in flatten_navigation_items(items or DEFAULT_NAVIGATION_MENU):
        path = normalize_nav_path(row.get("path"))
        permission = row.get("permission")
        if path and permission:
            permission_map[path] = permission

    for legacy_path, normalized_path in NAV_LEGACY_PATH_MAP.items():
        permission = permission_map.get(normalized_path)
        if permission:
            permission_map[legacy_path] = permission

    return permission_map


def build_navigation_tree(rows):
    nodes = {}
    roots = []
    ordered_rows = sorted(rows, key=lambda item: ((item.parent_key or ""), item.sort_order, item.id))

    for row in ordered_rows:
        nodes[row.key] = row.to_dict(include_children=True)

    for row in ordered_rows:
        node = nodes[row.key]
        if row.parent_key and row.parent_key in nodes:
            nodes[row.parent_key]["children"].append(node)
        elif row.parent_key:
            roots.append(node)
        else:
            roots.append(node)

    def prune_empty_children(node):
        children = node.get("children") or []
        if children:
            node["children"] = [prune_empty_children(child) for child in children]
        else:
            node.pop("children", None)
        return node

    return [prune_empty_children(root) for root in roots]

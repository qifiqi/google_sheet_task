"""Default sidebar navigation and helpers."""


DEFAULT_NAVIGATION_MENU = [
    {"key": "dashboard", "label": "仪表盘", "path": "/admin", "permission": "page:admin:dashboard"},
    {"key": "task", "label": "任务模块", "children": [
        {"key": "tasks", "label": "任务管理", "path": "/admin/tasks", "permission": "page:admin:tasks"},
        {"key": "templates", "label": "任务模板", "path": "/admin/templates", "permission": "page:admin:templates"},
        {"key": "results", "label": "任务结果", "path": "/admin/results", "permission": "page:admin:results"},
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

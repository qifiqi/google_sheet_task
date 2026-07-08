"""Default sidebar navigation and helpers."""

from app.page_registry import default_navigation_menu

DEFAULT_NAVIGATION_MENU = default_navigation_menu()


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

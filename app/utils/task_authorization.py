from typing import Any, Dict, Iterable, List, Set


TASK_ACTION_PERMISSION_MAP: Dict[str, str] = {
    "view": "task:view",
    "create": "task:create",
    "delete": "task:delete",
    "cancel": "task:cancel",
    "restart": "task:restart",
}

KNOWN_SCOPED_TASK_TYPES = {
    "google_sheet",
    "google_sheet_c4",
    "google_sheet_c5",
    "backtest_training",
}


def normalize_task_type(task_type: str | None) -> str:
    raw = str(task_type or "").strip().lower()
    if raw in {"google_sheet", "google_sheet_c3", "google_sheet_c31"}:
        return "google_sheet"
    if raw in {"google_sheet_c4"}:
        return "google_sheet_c4"
    if raw in {"google_sheet_c5"}:
        return "google_sheet_c5"
    if raw in {"backtest_training", "backtest"}:
        return "backtest_training"
    return raw


def _scope_permissions_for(task_type: str | None, action: str) -> Set[str]:
    normalized_type = normalize_task_type(task_type)

    if normalized_type == "google_sheet":
        if action == "view":
            return {"google_sheet:c3", "google_sheet:view", "google_sheet:manage"}
        return {"google_sheet:c3", "google_sheet:manage"}
    if normalized_type == "google_sheet_c4":
        if action == "view":
            return {"google_sheet:c4", "google_sheet:view", "google_sheet:manage"}
        return {"google_sheet:c4", "google_sheet:manage"}
    if normalized_type == "google_sheet_c5":
        if action == "view":
            return {"google_sheet:c5", "google_sheet:view", "google_sheet:manage"}
        return {"google_sheet:c5", "google_sheet:manage"}
    if normalized_type == "backtest_training":
        if action == "view":
            return {"backtest:view", "backtest:create"}
        return {"backtest:create"}

    return set()


def authorize_task_type_action(user: Any, action: str, task_type: str | None) -> Dict[str, Any]:
    user_permissions = set(getattr(user, "get_permissions", lambda: set())() or set())
    required_permissions: List[str] = []
    missing_permissions: List[str] = []
    normalized_task_type = normalize_task_type(task_type)

    base_permission = TASK_ACTION_PERMISSION_MAP.get(action)
    if base_permission:
        required_permissions.append(base_permission)
        if base_permission not in user_permissions:
            missing_permissions.append(base_permission)

    scope_permissions = sorted(_scope_permissions_for(task_type, action))
    if scope_permissions:
        required_permissions.extend(scope_permissions)
        if user_permissions.isdisjoint(set(scope_permissions)):
            missing_permissions.extend(scope_permissions)

    # 默认拒绝未知任务类型，避免新任务类型在未配置作用域规则时直接穿透。
    if normalized_task_type and normalized_task_type not in KNOWN_SCOPED_TASK_TYPES:
        unknown_scope_permission = f"task_scope:{normalized_task_type}"
        required_permissions.append(unknown_scope_permission)
        missing_permissions.append(unknown_scope_permission)

    allowed = not missing_permissions
    message = "权限满足" if allowed else f"缺少权限: {'、'.join(missing_permissions)}"

    return {
        "allowed": allowed,
        "action": action,
        "task_type": normalized_task_type,
        "required_permissions": required_permissions,
        "scope_permissions": scope_permissions,
        "missing_permissions": missing_permissions,
        "message": message,
    }


def filter_task_dicts_by_action(user: Any, action: str, tasks: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    filtered: List[Dict[str, Any]] = []
    for item in tasks or []:
        task_type = (item or {}).get("task_type")
        decision = authorize_task_type_action(user, action, task_type)
        if decision["allowed"]:
            filtered.append(item)
    return filtered


def filter_task_types_by_action(user: Any, action: str, task_types: Iterable[str | None]) -> List[str]:
    """过滤可访问的原始任务类型（保留数据库中的 task_type 值）。"""
    allowed_types: List[str] = []
    seen: Set[str] = set()
    for task_type in task_types or []:
        raw = str(task_type or "").strip()
        if not raw or raw in seen:
            continue
        decision = authorize_task_type_action(user, action, raw)
        if decision["allowed"]:
            allowed_types.append(raw)
            seen.add(raw)
    return allowed_types

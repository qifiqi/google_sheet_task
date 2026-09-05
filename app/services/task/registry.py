"""任务类型注册表（docs/design/data-layer-refactor/05 §3.1）。

新增任务类型只需注册一个 TaskTypeSpec，不再修改 runtime 的分发代码。
runner_attr 指向 task_manager 上的执行方法名（签名 (task_id, app) -> None）。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable


@dataclass(frozen=True)
class TaskTypeSpec:
    type_key: str                      # "google_sheet" / "google_sheet_c4" / ...
    display_name: str
    runner_attr: str                   # task_manager 执行方法名
    max_concurrency_key: str | None    # 分类型上限的 SystemConfig key；None = 不单独限
    max_concurrency_default: int = 4


GLOBAL_MAX_KEY = "task_max_workers"        # 全局并发上限
GLOBAL_MAX_DEFAULT = 8

TASK_TYPE_REGISTRY: dict[str, TaskTypeSpec] = {
    spec.type_key: spec
    for spec in (
        TaskTypeSpec("google_sheet", "C3", "_execute_google_sheet_task", "task_concurrency_google_sheet"),
        TaskTypeSpec("google_sheet_c4", "C4", "_execute_google_sheet_c4_task", "task_concurrency_google_sheet_c4"),
        TaskTypeSpec("google_sheet_c5", "C5", "_execute_google_sheet_c5_task", "task_concurrency_google_sheet_c5"),
        TaskTypeSpec("google_sheet_c7", "C7", "_execute_google_sheet_c7_task", "task_concurrency_google_sheet_c7"),
        TaskTypeSpec("backtest_training", "单品回测", "_execute_backtest_training_task", "task_concurrency_backtest_training"),
        TaskTypeSpec("backtest_multi_product", "多品回测", "_execute_backtest_multi_product_task", "task_concurrency_backtest_multi_product"),
    )
}


def register_task_type(spec: TaskTypeSpec) -> None:
    """新任务类型扩展点。"""
    TASK_TYPE_REGISTRY[spec.type_key] = spec


def get_task_type_spec(task_type: str | None) -> TaskTypeSpec | None:
    """按任务类型键取注册项（未注册返回 None，调用方拒绝启动）。"""
    if not task_type:
        return None
    return TASK_TYPE_REGISTRY.get(str(task_type).lower())


def build_runner(task_manager: Any, spec: TaskTypeSpec) -> Callable[..., None]:
    """由 spec 解析 task_manager 上的线程目标函数。"""
    runner = getattr(task_manager, spec.runner_attr, None)
    if runner is None:
        raise LookupError(f"任务类型 {spec.type_key} 的执行器不存在: {spec.runner_attr}")
    return runner

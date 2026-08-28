"""任务类型归一化工具。

仅包含与权限无关的任务类型归一化逻辑，
供回测、模型汇总、全局预览等业务链路使用。
"""

KNOWN_TASK_TYPES = {
    "google_sheet",
    "google_sheet_c4",
    "google_sheet_c5",
    "google_sheet_c7",
    "backtest_training",
    "backtest_multi_product",
    "model_summary_rebuild",
}


def normalize_task_type(task_type: str | None) -> str:
    raw = str(task_type or "").strip().lower()
    if raw in {"google_sheet", "google_sheet_c3", "google_sheet_c31"}:
        return "google_sheet"
    if raw in {"google_sheet_c4"}:
        return "google_sheet_c4"
    if raw in {"google_sheet_c5"}:
        return "google_sheet_c5"
    if raw in {"google_sheet_c7"}:
        return "google_sheet_c7"
    if raw in {"backtest_training", "backtest"}:
        return "backtest_training"
    if raw in {"backtest_multi_product", "multi_product_backtest", "backtest_multi"}:
        return "backtest_multi_product"
    if raw in {"model_summary_rebuild"}:
        return "model_summary_rebuild"
    return raw

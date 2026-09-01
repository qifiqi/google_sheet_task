"""历史指标载荷读取兼容。

新计算结果只产生标准字段；本模块仅用于读取数据库中尚未迁移的旧 JSON。
TODO: 完成数据库历史 TaskResult/导出数据迁移后删除本模块及其调用。
"""

from __future__ import annotations

from typing import Any


_LEGACY_KEYS = {
    "index_sotino_ratio": "index_sortino_ratio",
    "start_sotino_ratio": "start_sortino_ratio",
    "index_weekly_sotino_ratio": "index_weekly_sortino_ratio",
    "start_weekly_sotino_ratio": "start_weekly_sortino_ratio",
    "sotino_ratio": "sortino_ratio",
    "excess_sharp": "excess_sharpe",
    "excess_of_promissory_note": "excess_sortino",
    "cumulative_excess": "excess_cumulative_return",
    "excess_net": "excess_nav",
}


def upgrade_historical_metrics(value: Any) -> Any:
    """读取旧指标 JSON 时转换为当前字段名；新写入路径不要调用旧键回退。"""
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for key, item in value.items():
            normalized_key = _LEGACY_KEYS.get(str(key), key)
            result[normalized_key] = upgrade_historical_metrics(item)
        return result
    if isinstance(value, list):
        return [upgrade_historical_metrics(item) for item in value]
    return value


def extract_core_metrics(core: Any) -> dict[str, Any]:
    """从结果核心字典提取完整 V1 指标。

    统一存储载荷（``metrics_payload.metrics``）优先；历史键
    ``calculate_metrics`` / ``analyze_result`` 作为读取回退。
    TODO: 数据库历史 TaskResult 迁移为 metrics_payload 后删除回退分支。
    """
    if not isinstance(core, dict):
        return {}
    metrics_payload = core.get("metrics_payload")
    if isinstance(metrics_payload, dict) and isinstance(metrics_payload.get("metrics"), dict):
        return metrics_payload["metrics"]
    legacy = core.get("calculate_metrics") or core.get("analyze_result")
    return legacy if isinstance(legacy, dict) else {}


def extract_core_weighted_metrics(core: Any) -> dict[str, Any]:
    """从结果核心字典提取比例后单品指标。

    统一存储载荷（``metrics_payload.weighted_metrics``）优先；历史兄弟键
    ``weighted_calculate_metrics`` 作为读取回退。
    TODO: 数据库历史 TaskResult 迁移为 metrics_payload 后删除回退分支。
    """
    if not isinstance(core, dict):
        return {}
    metrics_payload = core.get("metrics_payload")
    if isinstance(metrics_payload, dict) and isinstance(metrics_payload.get("weighted_metrics"), dict):
        return metrics_payload["weighted_metrics"]
    legacy = core.get("weighted_calculate_metrics")
    return legacy if isinstance(legacy, dict) else {}

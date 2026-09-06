"""多品全局预览 / Word 报告载荷构建（export 域，2026-09 审计 C6(3/3) 拆出）。

仅承载预览/导出侧的载荷组装；共享助手（缓存、指标聚合、比例归一）仍由
`backtest_multi_product_service` 提供，本模块单向导入执行侧助手，执行侧
不再反向依赖预览构建器。
"""

from __future__ import annotations

from collections import OrderedDict
from typing import Any

from app.repositories import task_repository, task_result_repository
from app.services.backtest_multi_product_service import (
    SUMMARY_ROW_DEFS,
    BACKTEST_MULTI_PRODUCT_TASK_TYPE,
    _build_portfolio_metrics,
    _build_portfolio_return_date,
    _build_weighted_product_metrics,
    _core_metrics,
    _core_weighted_metrics,
    _derive_metrics,
    _extract_result_core,
    _fmt_value,
    _get_return_date_for_task_result,
    _get_global_preview_cache,
    _global_preview_cache_key,
    _parse_json,
    _set_global_preview_cache,
    normalize_multi_product_config,
    normalize_ratio_display,
)
from app.utils.backtest_report_metadata import get_backtest_model_version, get_price_type
from app.services.performance_analysis.portfolio_combiner import normalize_weighting_mode


def build_multi_product_global_preview_payload(
    task_id: str,
    ratios_override: list[Any] | None = None,
) -> dict[str, Any] | None:
    """构建多品全局预览的统一 payload。

    预览按 ``parameter_group_index`` 组织参数方案，而不是按执行步骤展示；
    每个方案同时保留原始单产品指标、比例后单产品指标和组合指标，供页面
    表格与 Excel 导出共用同一份数据格式。
    """
    task = task_repository.get_entity(task_id)
    if not task or task.task_type != BACKTEST_MULTI_PRODUCT_TASK_TYPE:
        return None
    config = normalize_multi_product_config(task.to_dict().get("config") or {})
    products = config["products"]
    if ratios_override is not None:
        if len(ratios_override) != len(products):
            raise ValueError("比例数量与产品数量不一致")
        for product, ratio in zip(products, ratios_override):
            product["ratio"] = normalize_ratio_display(
                ratio.get("ratio") if isinstance(ratio, dict) else ratio
            )
    # 结果必须按 step_index 稳定排序，后续按产品索引归位时才能保持执行顺序。
    results = task_result_repository.list_preview_entities(task_id)
    weighting_mode = normalize_weighting_mode(config.get("weighting_mode"))
    cache_key = _global_preview_cache_key(
        task_id,
        products,
        results,
        weighting_mode,
    )
    cached_payload = _get_global_preview_cache(cache_key)
    if cached_payload is not None:
        return cached_payload

    groups: OrderedDict[str, dict[str, Any]] = OrderedDict()
    success_count = 0
    failed_count = 0

    # 第一阶段只建立“方案 -> 产品结果”索引；组合指标和展示行在第二阶段统一计算。
    for result in results:
        parameters = _parse_json(result.parameters, {})
        group_index = int(parameters.get("parameter_group_index") or 0)
        group_key = str(group_index)
        group = groups.setdefault(group_key, {
            "group_key": group_key,
            "group_label": f"参数方案 {group_index + 1}",
            "parameter_group_index": group_index,
            "products": products,
            "product_results": {},
            "failed_results": 0,
        })
        product_index = int(parameters.get("product_index") or 0)
        if not result.success:
            failed_count += 1
            group["failed_results"] += 1
            continue
        success_count += 1
        core = _extract_result_core(result)
        calculate_metrics = _core_metrics(core)
        weighted_calculate_metrics = _core_weighted_metrics(core)
        group["product_results"][product_index] = {
            "result_id": result.id,
            "step_index": result.step_index,
            "timestamp": result.timestamp.isoformat() if result.timestamp else None,
            "parameters": parameters,
            "metrics": _derive_metrics(calculate_metrics if isinstance(calculate_metrics, dict) else {}),
            "return_date": _get_return_date_for_task_result(result),
            "weighted_metrics": (
                _derive_metrics(weighted_calculate_metrics)
                if isinstance(weighted_calculate_metrics, dict) and weighted_calculate_metrics
                else {}
            ),
        }

    # 第二阶段补齐比例指标、组合指标和页面行定义，避免在产品循环中重复聚合。
    serialized_groups = []
    for group in groups.values():
        portfolio_metrics = _derive_metrics(_build_portfolio_metrics(
            group["product_results"],
            products,
            weighting_mode,
        ))
        weighted_metrics_by_product: dict[int, dict[str, Any]] = {}
        metrics_by_product: dict[int, dict[str, Any]] = {}
        for product in products:
            product_index = int(product["product_index"])
            product_result = group["product_results"].get(product_index) or {}
            metrics_by_product[product_index] = product_result.get("metrics") or {}
            weighted_metrics = product_result.get("weighted_metrics") or {}
            current_ratio = (products[product_index] if product_index < len(products) else {}).get("ratio")
            saved_ratio = str((product_result.get("parameters") or {}).get("ratio") or "").strip()
            # 仅保留日收益加权复利一种组合算法；比例未变化时复用已保存的加权指标。
            # TODO: 历史结果参数中的 use_legacy_cumulative_return_weighting 字段迁移后删除。
            if not weighted_metrics or saved_ratio != str(current_ratio or "").strip():
                weighted_metrics = _derive_metrics(
                    _build_weighted_product_metrics(
                        product_result.get("return_date") or [],
                        current_ratio,
                        weighting_mode,
                    )
                )
                product_result["weighted_metrics"] = weighted_metrics
            weighted_metrics_by_product[product_index] = weighted_metrics

        # SUMMARY_ROW_DEFS 是前后端共享的行契约；缺少指数字段的指标以 "-" 展示。
        rows = []
        for category, metric, index_key, result_key, value_type in SUMMARY_ROW_DEFS:
            product_values = []
            for product in products:
                product_index = int(product["product_index"])
                metrics = metrics_by_product.get(product_index) or {}
                weighted_metrics = weighted_metrics_by_product.get(product_index) or {}
                index_value = metrics.get(index_key) if index_key else None
                result_value = metrics.get(result_key) if result_key else None
                product_values.append({
                    "product_index": product_index,
                    "index_value": _fmt_value(index_value, value_type) if index_key else "-",
                    "result_value": _fmt_value(result_value, value_type),
                    "weighted_result_value": _fmt_value(
                        weighted_metrics.get(result_key),
                        value_type,
                    ),
                    "raw_index_value": index_value,
                    "raw_result_value": result_value,
                    "raw_weighted_index_value": weighted_metrics.get(index_key) if index_key else None,
                    "raw_weighted_result_value": weighted_metrics.get(result_key),
                })
            weighted_index_value = portfolio_metrics.get(index_key) if index_key else None
            weighted_result_value = portfolio_metrics.get(result_key) if result_key else None
            rows.append({
                "category": category,
                "metric": metric,
                "value_type": value_type,
                "product_values": product_values,
                "weighted_index_value": (
                    _fmt_value(weighted_index_value, value_type)
                    if index_key and weighted_index_value is not None
                    else "-"
                ),
                "weighted_result_value": (
                    _fmt_value(weighted_result_value, value_type)
                    if weighted_result_value is not None
                    else "-"
                ),
                "raw_weighted_index_value": weighted_index_value,
                "raw_weighted_result_value": weighted_result_value,
            })
        serialized_groups.append({
            **{key: value for key, value in group.items() if key != "product_results"},
            "rows": rows,
            "result_count": len(group["product_results"]),
            "portfolio_metrics": portfolio_metrics,
            "product_metrics": metrics_by_product,
            "weighted_product_metrics": weighted_metrics_by_product,
        })

    payload = {
        "task": {
            "id": task.id,
            "name": task.name,
            "status": task.status,
            "start_date": config["start_date"],
            "end_date": config["end_date"],
        },
        "summary": {
            "total_results": len(results),
            "success_results": success_count,
            "failed_results": failed_count,
            "group_count": len(serialized_groups),
            "product_count": len(products),
        },
        "products": products,
        "groups": serialized_groups,
    }
    _set_global_preview_cache(cache_key, payload)
    return payload


def build_multi_product_global_preview_word_payload(
    task_id: str,
    group_key: str,
    ratios_override: list[Any] | None = None,
) -> dict[str, Any] | None:
    """构建指定参数方案的多品 Word 报告数据。"""
    task = task_repository.get_entity(task_id)
    if not task or task.task_type != BACKTEST_MULTI_PRODUCT_TASK_TYPE:
        return None

    config = normalize_multi_product_config(task.to_dict().get("config") or {})
    products = config["products"]
    if ratios_override is not None:
        if len(ratios_override) != len(products):
            raise ValueError("比例数量与产品数量不一致")
        for product, ratio in zip(products, ratios_override):
            product["ratio"] = normalize_ratio_display(
                ratio.get("ratio") if isinstance(ratio, dict) else ratio
            )

    product_results: dict[int, dict[str, Any]] = {}
    results = task_result_repository.list_preview_entities(task_id, success_only=True)
    for result in results:
        parameters = _parse_json(result.parameters, {})
        if str(parameters.get("parameter_group_index") or 0) != str(group_key):
            continue
        product_index = int(parameters.get("product_index") or 0)
        product_results[product_index] = {
            "return_date": _get_return_date_for_task_result(result),
        }

    missing_indexes = [
        str(product["product_index"] + 1)
        for product in products
        if not product_results.get(product["product_index"], {}).get("return_date")
    ]
    if missing_indexes:
        raise ValueError(f"参数方案缺少产品 {', '.join(missing_indexes)} 的收益序列")

    returns = _build_portfolio_return_date(
        product_results,
        products,
        normalize_weighting_mode(config.get("weighting_mode")),
    )
    if len(returns) < 2:
        raise ValueError("比例组合后的共同交易日不足 2 天")

    model_versions: list[str] = []
    price_types: list[str] = []
    word_products = []
    for product in products:
        sheet = product.get("sheet") if isinstance(product.get("sheet"), dict) else {}
        model_version = get_backtest_model_version(
            sheet.get("title") or product.get("title") or product.get("spreadsheet_title")
        )
        price_type = get_price_type(product.get("price_mode") or product.get("price_type"))
        if model_version and model_version not in model_versions:
            model_versions.append(model_version)
        if price_type and price_type not in price_types:
            price_types.append(price_type)
        word_products.append({
            "stock_code": product.get("stock_code"),
            "product_name": product.get("product_name"),
            "ratio": product.get("ratio"),
            "returns": product_results[product["product_index"]]["return_date"],
        })
    weighting_mode = normalize_weighting_mode(config.get("weighting_mode"))
    return {
        "report_type": "RPT-M",
        "weighting_mode": weighting_mode,
        "products": word_products,
        "metadata": {
            "model_version": "、".join(model_versions),
            "price_type": "、".join(price_types),
        },
    }

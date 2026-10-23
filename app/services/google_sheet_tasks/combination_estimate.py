"""随机价组合数精算：复用执行器展开骨架统计实际执行组合数。

创建页本地公式只覆盖「产品 × 参数 × 随机组」，`count_mode=n_plus_1` 的多
K线窗口（整年/近年/全区间）无法在前端推导，会系统性低估随机价任务量；
本模块按真实展开逻辑计数，估算过程不落随机K线快照。
"""

from __future__ import annotations

import uuid
from typing import Any, Callable

from app.exceptions import ValidationError
from app.services.google_sheet_tasks.c5 import C5Service
from app.services.google_sheet_tasks.c7 import C7Service
from app.services.google_sheet_tasks.c1_1 import C1_1Service
from app.utils.logger import get_logger

logger = get_logger(__name__)

KLINE_SOURCE_CUSTOM = "custom"
PRICE_MODE_RANDOM = "random_price"

SERVICE_CLASSES = {
    "google_sheet_c5": C5Service,
    "google_sheet_c7": C7Service,
    "google_sheet_c1_1": C1_1Service,
}


def _custom_combination_count(products: list, parameters: list, config: dict) -> int:
    """custom K线：单窗口，组合 = 产品 × 内层参数 × 随机组（仅 random_price 生效）。"""
    groups = 1
    if str(config.get("price_mode") or "").strip().lower() == PRICE_MODE_RANDOM:
        groups = max(1, int(config.get("random_group_count") or 1))
    inner = 1
    for values in parameters[1:]:
        if values:
            inner *= len(values)
    return len(products) * inner * groups


def estimate_combination_count(
    task_type: str,
    config: dict[str, Any],
    *,
    service_factory: Callable[[str, dict, str], Any] | None = None,
) -> dict[str, Any]:
    """返回 {estimated_count, source}；行情不可用时 {available: False, message}。"""
    normalized_type = str(task_type or "").strip().lower()
    service_class = SERVICE_CLASSES.get(normalized_type)
    if not service_class:
        raise ValidationError("组合数精算仅支持 C5/C7/C1.1")

    config = dict(config or {})
    parameters = config.get("parameters") or []
    products = [
        value for value in (parameters[0] if parameters else [])
        if str(value or "").strip()
    ]
    if not products:
        raise ValidationError("产品代码列表不能为空")

    if str(config.get("kline_source") or "auto").strip().lower() == KLINE_SOURCE_CUSTOM:
        return {
            "estimated_count": _custom_combination_count(products, parameters, config),
            "source": "formula",
        }

    task_id = f"estimate-{uuid.uuid4()}"
    service = (
        service_factory(normalized_type, config, task_id)
        if service_factory
        else service_class(config, task_id)
    )
    # 估算不是任务执行：禁止写随机K线快照，避免产生无主审计数据
    service._persist_random_snapshots = False

    try:
        batch = service._prepare_batch(config)
        total = 0
        for outer_param in products:
            combinations, _column_a_length, _kline_data_map = service._expand_parameters(
                outer_param, parameters, batch
            )
            total += len(combinations)
        return {"estimated_count": total, "source": "server"}
    except (ValidationError,):
        raise
    except Exception as exc:
        logger.warning("组合数精算失败 task_type=%s: %s", normalized_type, exc)
        return {
            "available": False,
            "estimated_count": None,
            "message": str(exc)[:300],
            "source": "server",
        }

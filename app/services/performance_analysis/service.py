"""绩效分析 分析请求的应用服务（docs/design/api-model-query-audit/01 §5.8）。

承担参数解析、结果规整与成败判定；路由只做 HTTP 编排。
返回统一形态：{ok, message, data:{results, metrics}}。
"""

from __future__ import annotations

import asyncio
from typing import Any, Dict

from app.exceptions import ValidationError
from app.repositories import task_repository, task_result_repository
from app.services.performance_analysis.facade import calculate_v1_metrics
from app.services.performance_analysis.request_dto import MetricsRuntimeParamsDTO
from app.services.performance_analysis.analyzer import performance_analyzer
from app.services.performance_analysis.portfolio_combiner import combine_product_returns
from app.utils.formatting import parse_lenient_json
from app.utils.return_series import extract_return_rows, parse_return_series_fields

_EMPTY_RESULT_DATA: Dict[str, Any] = {"results": [], "metrics": {}}

# 公开出口（routes 只允许引用公开符号；2026-09 审计 B3）
EMPTY_RESULT_DATA = _EMPTY_RESULT_DATA


# 组合枚举的规模上限。
# 单次请求实际会枚举的组合数超过此值时直接拒绝，避免 CPU 长时间占用。
# 按"每只 0~cap_units 自由取值"的笛卡尔积上界估算：
#   上界 = (cap_units + 1) ** n
# 该上界 >= 实际组合数（实际还受总和约束），宁可保守。
# 10 万量级在同步接口下约几秒到几十秒，超过则需异步化或缩小参数范围。
MAX_CARTESIAN_SIZE = 100_000


def _parse_runtime_params(payload):
    """解析并校验 runtime_params（市场阶段阈值），非法输入抛 ValidationError。"""
    if payload is None:
        return MetricsRuntimeParamsDTO()
    if not isinstance(payload, dict):
        raise ValidationError("runtime_params 必须是对象")
    try:
        return MetricsRuntimeParamsDTO.from_raw(payload)
    except ValueError as exc:
        raise ValidationError(str(exc))


def _normalize_result(result: Dict[str, Any]) -> Dict[str, Any]:
    """把绩效分析器的 {status, message, results, metrics} 规整为统一形态。"""
    ok = result.get("status") == "success"
    return {
        "ok": ok,
        "message": result.get("message", ""),
        "data": {
            "results": result.get("results", []),
            "metrics": result.get("metrics", {}),
        },
    }


def get_index_annualized_rates(metrics: dict[str, Any]) -> list[dict[str, Any]]:
    """提取组合的指数年化收益率。"""
    value = metrics.get("index_annualized_rates")
    return value if isinstance(value, list) else []


def get_start_max_drawdown(metrics: dict[str, Any]) -> Any:
    """提取组合策略的总最大回撤。"""
    drawdown = metrics.get("start_maximum_drawdown")
    if not isinstance(drawdown, dict):
        return None
    total = drawdown.get("total_maximum_drawdown")
    return total.get("drawdown") if isinstance(total, dict) else None


def _year_max_drawdown(metrics: dict[str, Any], key: str) -> list[dict[str, Any]]:
    value = metrics.get(key)
    return value.get("year_maximum_drawdown", []) if isinstance(value, dict) else []


def _weight_combinations(product_count: int, units: int):
    if product_count == 1:
        yield (units,)
        return
    for weight in range(units + 1):
        for remaining in _weight_combinations(product_count - 1, units - weight):
            yield (weight, *remaining)


def _product_data(task_result: Any) -> dict[str, Any]:
    parameters = parse_lenient_json(getattr(task_result, "parameters", None), {})
    parameters = parameters if isinstance(parameters, dict) else {}
    stock_code = parameters.get("stock_code")
    stock_name = parameters.get("stock_name") or parameters.get("product_name")
    rows = []
    if task_result.return_series_id:
        series = task_result_repository.get_return_entity(task_result.return_series_id)
        if series:
            rows = parse_return_series_fields(series)
            stock_code = series.stock_code or stock_code
            stock_name = series.stock_name or stock_name
    if not rows:
        rows = extract_return_rows(parse_lenient_json(task_result.result, {}))
    return {
        "result_id": task_result.id,
        "stock_code": stock_code,
        "stock_name": stock_name,
        "returns": rows,
    }


class PerformanceAnalysisService:
    """文本 / Google Sheet 两个分析入口的共享编排逻辑。"""

    def analyze_text(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        input_data = payload.get("data", "")
        time_format = payload.get("time_format", "auto")
        runtime_params = _parse_runtime_params(payload.get("runtime_params"))

        result = performance_analyzer.analyze(
            data=input_data,
            time_format=time_format,
            runtime_params=runtime_params,
        )
        return _normalize_result(result)

    def analyze_sheet(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        spreadsheet_id = payload.get("spreadsheet_id", "")
        google_sheet_url = payload.get("google_sheet_url", "")
        google_sheet_name = payload.get("google_sheet_name", "auto")
        runtime_params = _parse_runtime_params(payload.get("runtime_params"))

        result = performance_analyzer.analyze_v1(
            spreadsheet_id=spreadsheet_id,
            google_sheet_name=google_sheet_name,
            runtime_params=runtime_params,
        )
        return _normalize_result(result)

    def weight_combination(self, payload: Dict[str, Any]):
        """逐个产出任务收益序列的独立权重组合。

        设计要点：
        1. 组合枚举以 "unit"（= step%）为最小粒度，避免浮点误差和无法对齐的权重。
        2. 通过 n > 5 的上限 + 枚举范围剪枝，把组合数控制在万级，同步接口可扛。
        3. 全程流式 yield，不物化结果集，避免 OOM。
        4. 元信息（result_id/stock_code/stock_name）提前拆好，循环内只算 ratio。
        """
        # ---------- 1. 参数解析 ----------
        # 注：这些字段已由 WeightCombinationSchema 校验过类型和范围，
        # 这里取默认值只是防御性写法（正常 payload 一定带这些 key）。
        task_id = payload.get("task_id").strip()
        step = payload.get("step", 5)
        max_weight = payload.get("max_weight", 100)
        min_weight = payload.get("min_weight", 50)   # 默认给业务下限，避免大量空仓组合
        single_cap = payload.get("single_cap", 30)

        # ---------- 2. 任务与产品加载 ----------
        task_repository.get_required(task_id)

        products = []
        for result in task_result_repository.list_preview_entities(task_id, success_only=True):
            product = _product_data(result)
            # 提前过滤：收益序列为空的直接剔除，避免进入组合枚举后被反复跳过。
            # 注：这里只判断非空；len >= 2 的兜底放在组合层（见下方 len(returns) < 2）。
            if product["returns"]:
                products.append(product)

        if not products:
            raise ValidationError("任务没有可用于组合的成功收益序列")

        n = len(products)

        # ---------- 3. 组合规模保护 ----------
        # n 直接决定组合数上限（每只 0~cap_units 单元，笛卡尔积规模约 (cap_units+1)^n）。
        # n=5 时最坏约 7^5 ≈ 1.7 万，实测更少；n=6 就会到 10 万级，
        # 单次请求耗时可能超过网关超时，因此暂时硬限制为 5。
        if n > 5:
            raise ValidationError(
                f"暂时不支持超过 5 个产品的组合分析（当前 {n} 个）"
            )

        # ---------- 4. 单元换算 ----------
        # 所有重量换算成 "unit 数"，避免浮点和余数问题。
        # total_units：总权重上限对应的单元数
        # min_units：  总权重下限对应的单元数（向上取整，保证 >= min_weight）
        # cap_units：  单只权重上限对应的单元数
        total_units = max_weight // step
        min_units = -(-min_weight // step)
        cap_units = single_cap // step

        # 无解剪枝：即使每只都顶格，也凑不到 min_weight，直接报错而不是跑空递归。
        if n * cap_units * step < min_weight:
            raise ValidationError(
                f"标的数 {n} × 单只上限 {single_cap} 无法达到最小权重 {min_weight}"
            )

        # ---------- 笛卡尔积规模保护（关键） ----------
        # 实际枚举规模受 n 和 cap_units 共同影响，n 相同但 cap_units 不同差异巨大。
        # 用 (cap_units + 1)^n 作为组合数上界（每只 0~cap_units 自由取值的笛卡尔积），
        # 该上界 >= 实际组合数（实际还受总和 ∈ [min_units, total_units] 约束），
        # 因此保守但安全：宁可提前拒绝，也不让请求跑太久。
        estimated_size = (cap_units + 1) ** n
        if estimated_size > MAX_CARTESIAN_SIZE:
            raise ValidationError(
                f"组合规模过大（估算上界 {estimated_size}，"
                f"上限 {MAX_CARTESIAN_SIZE}）："
                f"请增大 step、减小 single_cap 或减少参与产品数"
            )

        # ---------- 5. 组合枚举 ----------
        def gen_combinations(n_, remaining_units, prefix=None):
            """生成 n_ 只股票、总和恰好 = remaining_units、每只 0~cap_units 的组合。

            返回的元素是 tuple（已拷贝），调用方无需再拷贝。
            使用回溯 + 边界剪枝，避免产生非法中间态：
            - lo/hi 保证每只的取值不会让剩余单元无法分配；
            - 只在叶子节点（n_ == 1）产出，内部节点不 yield。
            """
            if prefix is None:
                # 防御性初始化：允许外部不传 prefix。
                # 注意 gen_all 内部显式传 []，此分支正常不会触发。
                prefix = []

            if n_ == 1:
                # 最后一只：剩余单元必须落在 [0, cap_units] 内才是合法组合
                if 0 <= remaining_units <= cap_units:
                    prefix.append(remaining_units)
                    yield tuple(prefix)   # 拷贝一份，避免暴露内部可变 list
                    prefix.pop()
                return

            # 为第 n_ 只分配 u 个单元，剩余 n_-1 只分 remaining_units - u 个。
            # 下界：剩余单元不能超过 (n_-1) * cap_units，否则后面装不下
            # 上界：不能让后面无单元可分（这里仅约束 u 本身 <= remaining_units）
            lo = max(0, remaining_units - (n_ - 1) * cap_units)
            hi = min(cap_units, remaining_units)

            for u in range(lo, hi + 1):
                prefix.append(u)
                yield from gen_combinations(n_ - 1, remaining_units - u, prefix)
                prefix.pop()   # 回溯：恢复现场

        def gen_all(n_, lo_units, hi_units):
            """生成所有总和在 [lo_units, hi_units] 之间的组合。

            外层对 target（总和）做循环，内层枚举恰好等于 target 的组合。
            这样能保证产出的组合总和天然落在 [min_weight, max_weight] 区间内，
            调用方无需再做总和校验。
            """
            for target in range(lo_units, hi_units + 1):
                yield from gen_combinations(n_, target, [])

        # ---------- 6. 预拆元信息 ----------
        # 每个产品的 result_id/stock_code/stock_name 是恒定的，
        # 只有 ratio 随组合变化。提前拆成元组列表，循环内少做字典查找。
        product_meta = [
            (p["result_id"], p["stock_code"], p["stock_name"])
            for p in products
        ]

        # ---------- 7. 组合遍历 ----------
        # 流式迭代，不物化，避免 OOM。
        # 由 gen_all 的范围保证：sum(weights) 天然落在 [min_weight, max_weight]，
        # 且 sum(units) >= min_units，所以只有 min_weight=0 时才可能出现全零组合。
        for units in gen_all(n, min_units, total_units):
            weights = [u * step for u in units]

            # 仅在 min_weight=0 时可能触发：过滤掉全零组合（无任何持仓，无意义）。
            # 当 min_weight > 0 时，sum(units) >= min_units >= 1，此判断恒为假，属于防御性保留。
            if not any(weights):
                continue

            # 收集非零权重对应的产品与权重。
            # 用一次遍历同时收集，保证 products/weights 顺序天然一致，
            # 避免分成两次列表推导导致顺序错位的隐患。
            active_products = []
            active_weights = []
            for p, w in zip(products, weights):
                if w:
                    active_products.append(p)
                    active_weights.append(w)

            # 加权合成收益序列。
            # 注：这里传的是完整 product dict，因为 combine_product_returns 可能
            # 依赖 returns 之外的字段（如日期对齐、result_id）。若确认只用 returns，
            # 可改为 [{"returns": p["returns"]} for p in active_products] 省内存。
            returns = combine_product_returns(active_products, weights=active_weights)

            # 兜底：组合后序列长度不足 2 无法计算年化/回撤，跳过。
            # 产品过滤阶段只保证单只非空，此处防止对齐后变短。
            if len(returns) < 2:
                continue

            # ---------- 8. 指标计算 ----------
            metrics = performance_analyzer._weight_combination_v1(returns)
            index_annualized_rates = metrics['index_annualized_rates']
            start_annualized_rates = metrics['start_annualized_rates']
            index_maximum_drawdown = metrics['index_maximum_drawdown']
            start_maximum_drawdown = metrics['start_maximum_drawdown']

            # 取首元素作为代表值（约定：index_annualized_rates 首项是组合整体，
            # start_annualized_rates 首项是起始点对齐后的年化）。
            annualized_rates_start = start_annualized_rates[0].get("annualized_return")
            maximum_drawdown_start = start_maximum_drawdown.get(
                "total_maximum_drawdown", {}
            ).get("drawdown")

            # ---------- 9. 组装输出 ----------
            # stocks 用 product_meta 预拆字段 + 当前组合的 ratio 拼装，
            # 避免在循环内反复做 product["xxx"] 字典查找。
            stocks = [
                {
                    "result_id": rid,
                    "stock_code": code,
                    "stock_name": name,
                    "ratio": w,
                }
                for (rid, code, name), w in zip(product_meta, weights)
            ]

            data = {
                "annualized_rates": {
                    "index": index_annualized_rates[0].get("annualized_return"),
                    "start": annualized_rates_start,
                },
                "year_max_drawdown": {
                    "index": index_maximum_drawdown.get("total_maximum_drawdown", {}).get("drawdown"),
                    "start": maximum_drawdown_start,
                },
                "stocks": stocks,
            }
            yield data


performance_analysis_service = PerformanceAnalysisService()

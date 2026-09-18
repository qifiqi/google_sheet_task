"""绩效分析 分析请求的应用服务（docs/design/api-model-query-audit/01 §5.8）。

承担参数解析、结果规整与成败判定；路由只做 HTTP 编排。
返回统一形态：{ok, message, data:{results, metrics}}。
"""

from __future__ import annotations

from typing import Any, Dict

from app.exceptions import ValidationError
from app.repositories import task_repository, task_result_repository
from app.services.backtest_multi_product_service import normalize_ratio_display
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
# 按逐产品取值区间的笛卡尔积上界估算：
#   上界 = prod(max_units_i - min_units_i + 1)
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
    try:
        product_index = int(parameters.get("product_index") or 0)
    except (TypeError, ValueError):
        product_index = 0
    return {
        "result_id": task_result.id,
        "stock_code": stock_code,
        "stock_name": stock_name,
        "returns": rows,
        # 多品任务按 product_index 关联任务配置里的产品（含比例）；单产品任务恒为 0
        "product_index": product_index,
        # 执行时快照的比例，任务配置缺失时兜底（见 _configured_ratio）
        "parameter_ratio": parameters.get("ratio"),
    }


def _task_field(task: Any, name: str, default: Any = None) -> Any:
    """读任务字段：任务既可能是实体（get_entity）也可能是 to_dict 结果（get_required）。"""
    if isinstance(task, dict):
        return task.get(name, default)
    return getattr(task, name, default)


def _task_config_product_ratios(task: Any) -> dict[int, str]:
    """任务配置中"按产品序号索引的已配置比例"（多品任务的权重分配表）。

    只按序号取值、不做多品配置归一化：组合分析面向的是执行结果，
    任务配置仅用于给前端面板提供默认单股范围，配置不合法时静默降级为
    "无已配置比例"（前端回退到单股上限），不应因此让整个请求失败。
    """
    config = parse_lenient_json(_task_field(task, "config"), {})
    if not isinstance(config, dict):
        return {}
    config_products = config.get("products")
    if not isinstance(config_products, list):
        return {}

    ratios: dict[int, str] = {}
    for index, product in enumerate(config_products):
        if not isinstance(product, dict) or product.get("ratio") is None:
            continue
        try:
            ratios[index] = normalize_ratio_display(product.get("ratio"))
        except ValidationError:
            continue
    return ratios


def _configured_ratio(product: dict[str, Any], config_ratios: dict[int, str]) -> str | None:
    """产品已配置比例：优先任务配置（当前值），回退执行结果参数里的快照。"""
    ratio = config_ratios.get(product.get("product_index"))
    if ratio is not None:
        return ratio
    raw = product.get("parameter_ratio")
    if raw is None or str(raw).strip() == "":
        return None
    try:
        return normalize_ratio_display(raw)
    except ValidationError:
        return None


def _load_products(task_id: str) -> list[dict[str, Any]]:
    """装载任务下可用于组合的产品（成功且有收益序列的结果）。

    weight_combination 与产品列表接口共用同一套装载顺序
    （step_index 升序，见 list_preview_entities），前端面板行才能按
    result_id 精确对应到枚举中的产品。
    """
    products = []
    for result in task_result_repository.list_preview_entities(task_id, success_only=True):
        product = _product_data(result)
        # 提前过滤：收益序列为空的直接剔除，避免进入组合枚举后被反复跳过。
        # 注：这里只判断非空；len >= 2 的兜底放在组合层（见下方 len(returns) < 2）。
        if product["returns"]:
            products.append(product)
    return products


def _resolve_stock_bounds(
    products: list[dict[str, Any]],
    stock_ranges: list[dict[str, Any]],
    step: int,
) -> list[tuple[int, int]]:
    """把逐产品单股范围对齐到 products 顺序，并换算成单元数区间。

    换算方向按"不越过用户意图"取整：下限向上取整（不弱于要求）、
    上限向下取整（不超过要求）。返回 [(min_units, max_units), ...]，
    与 products 一一对应。范围未覆盖全部产品 / 含未参与产品时抛 ValidationError。
    """
    by_id: dict[str, dict[str, Any]] = {}
    for item in stock_ranges:
        item_id = str(item.get("result_id"))
        if item_id in by_id:
            raise ValidationError(f"单股范围存在重复的产品: {item_id}")
        by_id[item_id] = item

    product_ids = [str(product["result_id"]) for product in products]
    unknown = [item_id for item_id in by_id if item_id not in set(product_ids)]
    if unknown:
        raise ValidationError(f"单股范围包含未参与组合的产品: {', '.join(unknown)}")
    missing = [item_id for item_id in product_ids if item_id not in by_id]
    if missing:
        raise ValidationError(f"以下产品缺少单股范围配置: {', '.join(missing)}")

    bounds: list[tuple[int, int]] = []
    for item_id in product_ids:
        item = by_id[item_id]
        min_weight = int(item.get("min_weight") or 0)
        max_weight = item.get("max_weight")
        max_weight = int(max_weight) if max_weight is not None else min_weight
        if min_weight > max_weight:
            raise ValidationError(f"单股范围下限不能大于上限（result_id={item_id}）")
        bounds.append((-(-min_weight // step), max_weight // step))
    return bounds


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
        google_sheet_name = payload.get("google_sheet_name", "auto")
        runtime_params = _parse_runtime_params(payload.get("runtime_params"))

        result = performance_analyzer.analyze_v1(
            spreadsheet_id=spreadsheet_id,
            google_sheet_name=google_sheet_name,
            runtime_params=runtime_params,
        )
        return _normalize_result(result)

    def list_weight_combination_products(self, task_id: str) -> Dict[str, Any]:
        """列出任务下可参与权重组合的产品及已配置比例（前端"单股范围"面板数据源）。

        返回列表与 weight_combination 的产品装载顺序一致，每行带 result_id，
        前端勾选/设范围后按 result_id 回传，二者不会错位。
        没有可用收益序列的成功结果也一并返回（has_returns=False），
        让前端能提示"某产品为什么没进组合"，而不是静默消失。
        """
        task = task_repository.get_required(task_id)
        config_ratios = _task_config_product_ratios(task)

        products = []
        for result in task_result_repository.list_preview_entities(task_id, success_only=True):
            product = _product_data(result)
            products.append({
                "result_id": product["result_id"],
                "product_index": product["product_index"],
                "stock_code": product["stock_code"],
                "stock_name": product["stock_name"],
                "has_returns": bool(product["returns"]),
                "ratio": _configured_ratio(product, config_ratios),
            })
        return {
            "task_id": task_id,
            "task_type": _task_field(task, "task_type"),
            "products": products,
        }

    def weight_combination(self, payload: Dict[str, Any]):
        """逐个产出任务收益序列的独立权重组合。

        设计要点：
        1. 组合枚举以 "unit"（= step%）为最小粒度，避免浮点误差和无法对齐的权重。
        2. 组合规模由"逐产品取值范围 + 组合总权重区间"共同约束并做上界保护，
           同步接口可扛；未提供逐产品范围时沿用 n <= 5 的硬限制。
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
        selected_ids = payload.get("result_ids")
        stock_ranges = payload.get("stock_ranges")

        # ---------- 2. 任务与产品加载 ----------
        task_repository.get_required(task_id)

        products = _load_products(task_id)

        if not products:
            raise ValidationError("任务没有可用于组合的成功收益序列")

        # ---------- 3. 产品筛选（可选） ----------
        # 任务下产品可能多于本次想组合的数量，前端勾选后只传选中的结果 ID。
        # 顺序仍按装载顺序固定（不随前端勾选顺序变化），保证结果可复现。
        if selected_ids is not None:
            wanted = [str(item) for item in selected_ids]
            if not wanted:
                raise ValidationError("请至少选择一个参与组合的产品")
            available = {str(product["result_id"]) for product in products}
            missing = [item_id for item_id in wanted if item_id not in available]
            if missing:
                raise ValidationError(
                    f"选中的产品不存在或没有可用收益序列: {', '.join(missing)}"
                )
            wanted_set = set(wanted)
            products = [
                product for product in products if str(product["result_id"]) in wanted_set
            ]

        n = len(products)

        # ---------- 4. 单股范围 / 单股上限 ----------
        if stock_ranges is not None:
            # 逐产品范围：前端按配置比例给出默认值（0 ~ 配置比例），允许自由修改。
            # 提供范围后不再受 n <= 5 的硬限制，规模统一由下方笛卡尔积上界把关。
            bounds = _resolve_stock_bounds(products, stock_ranges, step)
        else:
            # 兼容链路：未提供逐产品范围时沿用全局单只上限。
            # n 直接决定组合数上限（每只 0~cap_units 单元，笛卡尔积规模约 (cap_units+1)^n）：
            # n=5 时最坏约 7^5 ≈ 1.7 万，实测更少；n=6 就会到 10 万级，
            # 单次请求耗时可能超过网关超时，因此此链路保持硬限制 5。
            if n > 5:
                raise ValidationError(
                    f"暂时不支持超过 5 个产品的组合分析（当前 {n} 个）"
                )
            bounds = [(0, single_cap // step)] * n

        # ---------- 5. 单元换算 ----------
        # 所有重量换算成 "unit 数"，避免浮点和余数问题。
        # total_units：总权重上限对应的单元数
        # min_units：  总权重下限对应的单元数（向上取整，保证 >= min_weight）
        # min_units_list / max_units_list：逐产品范围对应的单元数
        total_units = max_weight // step
        min_units = -(-min_weight // step)
        min_units_list = [item[0] for item in bounds]
        max_units_list = [item[1] for item in bounds]

        # 无解剪枝：跑之前先确认区间非空，避免空递归白跑一趟。
        if sum(max_units_list) == 0:
            raise ValidationError("所选产品的单股上限都为 0，无法产生有效组合")
        if sum(max_units_list) * step < min_weight:
            raise ValidationError(
                f"所选产品单股上限之和 {sum(max_units_list) * step}% "
                f"无法达到组合总权重下限 {min_weight}%"
            )
        if sum(min_units_list) * step > max_weight:
            raise ValidationError(
                f"所选产品单股下限之和 {sum(min_units_list) * step}% "
                f"超过组合总权重上限 {max_weight}%"
            )

        # ---------- 笛卡尔积规模保护（关键） ----------
        # 实际枚举规模受逐产品取值区间共同影响，用"各产品区间长度的乘积"作为组合数上界，
        # 该上界 >= 实际组合数（实际还受总和 ∈ [min_units, total_units] 约束），
        # 因此保守但安全：宁可提前拒绝，也不让请求跑太久。
        estimated_size = 1
        for lo_units, hi_units in bounds:
            estimated_size *= hi_units - lo_units + 1
        if estimated_size > MAX_CARTESIAN_SIZE:
            raise ValidationError(
                f"组合规模过大（估算上界 {estimated_size}，"
                f"上限 {MAX_CARTESIAN_SIZE}）："
                f"请增大 step、缩小单股范围或减少参与产品数"
            )

        # ---------- 6. 组合枚举 ----------
        # 后缀和：回溯时用于判断"剩余产品能否吃完剩余单元"（逐产品区间下无法再用 n*cap 估算）。
        suffix_min = [0] * (n + 1)
        suffix_max = [0] * (n + 1)
        for index in range(n - 1, -1, -1):
            suffix_min[index] = suffix_min[index + 1] + min_units_list[index]
            suffix_max[index] = suffix_max[index + 1] + max_units_list[index]

        def gen_combinations(index, remaining_units, prefix):
            """生成第 index..n-1 只股票、总和恰好 = remaining_units、每只落在自身区间内的组合。

            返回的元素是 tuple（已拷贝），调用方无需再拷贝。
            使用回溯 + 边界剪枝，避免产生非法中间态：
            - lo/hi 同时受"该产品自身范围"和"剩余产品能否吃完剩余单元"约束；
            - 只在最后一只（index == n-1）产出，内部节点不 yield。
            """
            if index == n - 1:
                # 最后一只：剩余单元必须落在它自己的范围内才是合法组合
                if min_units_list[index] <= remaining_units <= max_units_list[index]:
                    prefix.append(remaining_units)
                    yield tuple(prefix)   # 拷贝一份，避免暴露内部可变 list
                    prefix.pop()
                return

            # 为第 index 只分配 u 个单元，剩余 n-1-index 只分 remaining_units - u 个。
            # 下界：剩余单元不能超过后面各只的上限之和，否则后面装不下；
            # 上界：不能少于后面各只的下限之和，否则后面会低于自己的下限。
            lo = max(min_units_list[index], remaining_units - suffix_max[index + 1])
            hi = min(max_units_list[index], remaining_units - suffix_min[index + 1])

            for u in range(lo, hi + 1):
                prefix.append(u)
                yield from gen_combinations(index + 1, remaining_units - u, prefix)
                prefix.pop()   # 回溯：恢复现场

        def gen_all(lo_units, hi_units):
            """生成所有总和在 [lo_units, hi_units] 之间的组合。

            外层对 target（总和）做循环，内层枚举恰好等于 target 的组合。
            这样能保证产出的组合总和天然落在 [min_weight, max_weight] 区间内，
            调用方无需再做总和校验。
            """
            for target in range(lo_units, hi_units + 1):
                yield from gen_combinations(0, target, [])

        # ---------- 7. 预拆元信息 ----------
        # 每个产品的 result_id/stock_code/stock_name 是恒定的，
        # 只有 ratio 随组合变化。提前拆成元组列表，循环内少做字典查找。
        product_meta = [
            (p["result_id"], p["stock_code"], p["stock_name"])
            for p in products
        ]

        # ---------- 8. 组合遍历 ----------
        # 流式迭代，不物化，避免 OOM。
        # 由 gen_all 的范围保证：sum(weights) 天然落在 [min_weight, max_weight]，
        # 且 sum(units) >= min_units，所以只有 min_weight=0 时才可能出现全零组合。
        for units in gen_all(min_units, total_units):
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

            # ---------- 9. 指标计算 ----------
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

            # ---------- 10. 组装输出 ----------
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

"""绩效分析域请求 Schema。

分析入参的深度校验由 performance_analysis_service 负责（含多态行格式），
body 边界仅约束为 JSON 对象。
"""

from typing import Any

from pydantic import Field, RootModel, model_validator,BaseModel

class PerformanceAnalysisPayloadSchema(RootModel[dict[str, Any]]):
    """POST /performance_analysis/analyze 与 /performance_analysis/v1/analyze 请求体。"""


class WeightCombinationProductsQuerySchema(BaseModel):
    """GET /performance_analysis/v1/weight_combination/products 查询参数。"""

    task_id: str = Field(..., min_length=1)


class WeightCombinationRangeItem(BaseModel):
    """单只产品的权重范围（%），按 result_id 对应到参与组合的产品。"""

    # TaskResult 主键：同一股票在多参数方案任务中会出现多次，只能按结果 ID 定位
    result_id: str | int

    # 该产品在组合中的权重下限（%），0 表示可以不持有
    min_weight: int = Field(0, ge=0, le=100)

    # 该产品在组合中的权重上限（%）
    max_weight: int = Field(..., ge=0, le=100)


class WeightCombinationSchema(BaseModel):
    """POST /performance_analysis/v1/weight_combination 请求体。

    用于描述"按权重组合多只股票的收益序列"这一请求的参数约束。
    所有权重相关参数都要求是 step 的整数倍，保证内部按"单元(unit)"枚举时
    不会出现无法对齐的权重值。
    """

    # 任务 ID，必填，不能为空字符串
    task_id: str = Field(..., min_length=1)

    # 权重步长（%）。所有权重值必须是它的整数倍。
    # 内部会把 min/max/single_cap 都换算成"单元数"再枚举。
    step: int | None = Field(5, gt=0, le=100)

    # 组合总权重的上限（%），即所有股票权重之和不得超过此值
    max_weight: int | None = Field(100, gt=0, le=100)

    # 组合总权重的下限（%），避免生成大量接近空仓的组合
    min_weight: int | None = Field(50, ge=0, le=100)

    # 单只股票的权重上限（%），防止组合过度集中在某一只。
    # 仅在未提供 stock_ranges 时生效：一旦按产品给定了单股范围，该字段让位于逐产品的范围。
    single_cap: int | None = Field(30, gt=0, le=100)

    # 参与组合的产品（TaskResult 主键）白名单；缺省表示任务下全部可用产品。
    # 任务下产品多于所需时，前端勾选后只把选中的结果 ID 传上来。
    result_ids: list[str | int] | None = None

    # 逐产品权重范围（%）；提供时必须覆盖全部参与组合的产品，缺省表示沿用 single_cap 语义。
    stock_ranges: list[WeightCombinationRangeItem] | None = None

    @model_validator(mode="after")
    def _check(self):
        # 先取默认值，避免后续到处写 `or 默认值`
        step = self.step or 5
        max_weight = self.max_weight if self.max_weight is not None else 100
        min_weight = self.min_weight if self.min_weight is not None else 50
        single_cap = self.single_cap if self.single_cap is not None else 30

        # step 必须能整除 100：
        # 权重以百分比表示，若 step 不能整除 100，则 100% 无法被 step 表示，
        # 会导致总权重上限无法取到、单元换算出现余数。
        if 100 % step:
            raise ValueError("step 必须能整除 100")

        # 三个权重参数都必须是 step 的整数倍：
        # 内部枚举以"单元"为最小粒度（unit = step%），若参数不是 step 的整数倍，
        # 换算单元数时会产生截断/余数，导致边界组合被错误地纳入或排除。
        # single_cap 在提供 stock_ranges 时不再参与枚举（逐产品范围已取代它），
        # 因此它的网格/下限约束只在未提供范围时校验，避免用一个"不生效的字段"卡住请求。
        weight_params = [("max_weight", max_weight), ("min_weight", min_weight)]
        if self.stock_ranges is None:
            weight_params.append(("single_cap", single_cap))
        for name, val in weight_params:
            if val % step:
                raise ValueError(f"{name} 必须是 step 的整数倍")

        # 下界不能大于上界，否则区间为空，枚举无意义
        if min_weight > max_weight:
            raise ValueError("min_weight 不能大于 max_weight")

        # 单只上限必须不小于 step：
        # single_cap 换算成单元数 cap_units = single_cap // step。
        # 若 single_cap < step，则 cap_units = 0，意味着任何股票都无法配置非零权重，
        # 组合枚举恒为空——这是参数配置错误，应提前拦截而不是静默返回空结果。
        # 注：结合"single_cap 必须是 step 的整数倍"，此条件实际等价于 single_cap >= step。
        if self.stock_ranges is None and single_cap < step:
            raise ValueError("single_cap 不能小于 step")

        # 关于 "single_cap >= min_weight" 的说明（此处未强制）：
        # 如果业务要求"必须存在某只股票单独就能撑起总权重下界"，
        # 则应加 `if single_cap < min_weight: raise ...`。
        # 但本接口允许"多只股票共同凑够下界"（如 min_weight=50、single_cap=30，
        # 可由两只各 25% 或 30%+20% 达成），因此不强制该约束。
        # 真正依赖数据规模的下界校验（n * single_cap >= min_weight）
        # 放在 service 层、拿到 products 数量之后再判断。

        # 逐产品范围：与单股上限同源，同样必须落在 step 网格上，
        # 否则换算单元数时会被截断，出现"用户填 8%、实际只搜到 5%"的静默偏差。
        if self.stock_ranges is not None:
            seen_ids = set()
            for item in self.stock_ranges:
                item_id = str(item.result_id)
                if item_id in seen_ids:
                    raise ValueError(f"单股范围存在重复的产品: {item_id}")
                seen_ids.add(item_id)
                if item.min_weight > item.max_weight:
                    raise ValueError(f"单股范围下限不能大于上限（result_id={item_id}）")
                if item.min_weight % step or item.max_weight % step:
                    raise ValueError(f"单股范围必须是 step 的整数倍（result_id={item_id}）")

        return self

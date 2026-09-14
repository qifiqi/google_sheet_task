# 多指数 Word 报告改造方案（引擎不动 · 报告服务层循环）

> 回答两个问题：① 导出 Word 支持多选指数后，报告的表格与图表如何加多指数列？——**把"指数"从单数抽象成基准列表（benchmarks），每个选中指数各跑一次现有 V1 指标引擎，报告层把 N 份结果组装成宽表/多序列图；"不选指数"的默认组合 index 也是列表长度 1，天然单路径**。② 与旧的单指数代码是否切割成两条分支？——**不切割，合并为一条路径**（符合全库"无兼容层、单一执行路径"约定；单指数 = 列表长度 1 的特例）。

## 1. 现状与约束

### 1.1 指数进入报告的唯一注入点

RPT-M 导出链路：

```
前端(index_stock_code) → export_service.export_backtest_word
  → build_multi_product_global_preview_word_payload（products 携带各自 returns）
  → StrategyBacktestReportService.generate_word
      ├─ _resolve_returns: _combine_product_returns 组合出组合收益，
      │    再把选中产品的 start_return 列复制成组合数据的 index_return 列   ← 唯一注入点
      ├─ performance_analyzer.get_calculate_metrics_v1_with_dataframes(returns)
      │    → MetricsV1Result{ metrics(index_*/start_*/excess_*), index_df, start_df, excess_df }
      └─ _build_report_data（8 章表格） + _build_chart_data（6 图） + 权重/相关性/成交量
```

关键事实：

- **基准语义**：指数不是另拉的真实指数行情，而是"选中的那只产品自身的累计收益"充当基准（`_resolve_returns`，strategy_backtest_report_service.py:140-151）。不选指数时，`index_return` = 各产品自身指数列按比例加权组合（portfolio_combiner.combine_product_returns，"组合index"）。
- **单指数契约焊在共享引擎里**：`calculate_v1_metrics`（performance_analysis/facade.py:94）输入固定三列 `{date, index_return, start_return}`，输出固定三组键。该引擎是共享门面（单品页/V2 页/回测报告都在用），**本次不改它**。
- **超额量与基准一一绑定**：`excess_*` = 策略 − 指数。多指数意味着超额列/超额图按指数成对出现，不存在"共同超额列"；而 `start_*`（策略）与基准选择无关，N 次计算结果相同。
- 前端已改造完成：多品全局预览导出弹窗多选，`index_stock_code` 已按 `string[]` 发送（空选时不传字段）。

### 1.2 消费方清单（全部落点）

| 消费方 | 位置 | 指数参与方式 |
|---|---|---|
| 1.1 核心收益 / 1.2 分年度 / 1.3 滚动收益 | `_return_section` | 指数列 + 超额列 |
| 2.1 回撤 / 2.2 分年度回撤 | `_risk_section` | 同上 |
| 3 风险调整收益 | `_risk_adjusted_section` | 指数列 + 超额夏普/索提诺行 |
| 4 月度分布 / 5 日度分布 | `_monthly_section` / `_daily_section` | 指数列 |
| 6 超额收益分析（6.1/6.2/6.3） | `_excess_section` | 纯超额量（按基准） |
| 7.1 下跌 / 7.2 上涨 / 7.3 极端单日 | `_extreme_section` | 指数列 + 阶段超额列 |
| 8 资金曲线特征 | `_capital_curve_section` | 指数列 |
| 累计净值 / 最大回撤 / 超额收益 / 分年度 / 日收益分布 / 月度超额 6 图 | `strategy_backtest_report_charts.generate_report_charts` | 指数序列 / 超额序列 |
| 权重分配表、权重相关性表、成交量、热力图标签 | `_weight_allocation` / `_product_code_label` 等 | `(指数)` 后缀标记 |
| 结论 | `_conclusion` | 指数/超额文字 |

## 2. 方案选型

| 方案 | 结论 | 理由 |
|---|---|---|
| A. 双分支：保留单指数老路径 + 新增多指数路径 | **否决** | 违反"无兼容层、单一执行路径"项目约定；8 章 × 6 图消费逻辑维护两份，单指数分支必然腐化 |
| B. 改引擎：`calculate_v1_metrics` 多基准化 | **否决** | 引擎是共享门面，改契约波及单品/V2/回测全链路，风险远超需求收益 |
| C. 引擎不动，报告服务层循环（本方案） | **采纳** | 每个选中指数各跑一次引擎（组合列不变、只换 index_return 列），报告层组装。N=1 即现状，天然单路径；引擎零改动；N 次纯 pandas 计算开销可忽略（远小于 K 线拉取与 Word 渲染） |

**统一抽象**：报告层内部把"基准"建模为列表，始终至少一个元素——

```
runs = [ 每个"指数"一次引擎调用的结果 ]        # 长度恒 ≥ 1
  · 未选指数   → 1 个 run：组合默认 index_return 列（现状行为，标签"指数"）
  · 选了 N 个  → N 个 run：第 k 个 run 的 index_return = 第 k 个选中产品的累计收益
策略列恒取 runs[0] 的 start_*（同轴同组合列，各 run 的 start_* 完全相同）
每个基准列 = runs[k] 的 index_*；每个超额列 = runs[k] 的 excess_*
```

这样 8 章表格与 6 张图只有一条代码路径：对 runs 循环。现状（N=0/1）就是长度 1。

## 3. 接口与 Schema

### 3.1 字段

`app/schemas/backtest.py:37`：

```python
index_stock_code: list[str] = []   # 字段名不变（前端已按数组发送），类型 str|None → list[str]
```

`export_service.py:308-309` 透传同步改为列表判断（非空列表才覆盖 payload）。

### 3.2 校验规则（Schema 层 + 服务层）

| 规则 | 行为 |
|---|---|
| strip + 去重（保序） | 重复选择同一指数只算一次 |
| 代码必须存在于 products 的 stock_code | 否则 `ValidationError("指数代码 X 不在产品列表中")`（现状 `product_list[0]` 会裸 IndexError，一并修复） |
| 数量上限 3 | 超出 `ValidationError`；理由：1.1 核心收益表有 3+2N 列、图例与版面在 N>3 时不可读 |
| 空列表 / 字段缺省 | 默认组合 index，行为与现状完全一致 |
| 选中比例(ratio)为 0 的产品 | 允许（典型用法：0% 权重的 ETF 充当基准） |
| RPT-S / V2 来源 | 忽略该字段（与现状一致，注入只发生在 RPT-M 分支） |

## 4. 数据流改造

### 4.1 统一日期轴（顺带修复既有错位隐患）

现状 `_resolve_returns` 的注入是**按下标 zip**（`for i in range(len(data)): data[i]["index_return"] = returns[i]...`，strategy_backtest_report_service.py:148-149）。组合序列经过共同日期求交，长度/起始日可能与原始产品收益不一致——跨市场（A股+美股节假日不同）时指数列会**静默错位**。本次必须改为按日期字典对齐：

```
1. combined = _combine_product_returns(...)            # 现状：active 产品共同日期
2. idx_maps = {code: {date: 累计收益}}                  # 每个选中产品的收益转日期字典
3. final_axis = sorted(combined日期 ∩ ⋂ idx_maps 日期)  # 统一日期轴
4. portfolio = [combined[d] for d in final_axis]        # 组合行按轴重切（行为累计值，直接切片安全）
   index_k   = [idx_maps[k][d] for d in final_axis]
5. len(final_axis) < 2 → ValueError("收益数据无法生成回测报告")
```

语义说明：若某指数产品日历与组合不一致，报告整体日期轴收缩为交集——这与 `combine_product_returns` 的交集哲学一致，且保证整份报告（表格/图表/元数据"总交易日"）共用同一条轴、各 run 的策略指标严格相同。

### 4.2 引擎循环与内部结构

```python
@dataclass
class _BenchmarkRun:
    code: str                   # products 中的 stock_code
    label: str                  # 展示标签，见 §5.1
    result: MetricsV1Result     # 该基准下的一次完整引擎输出
```

`generate_word` 编排改为：

```
runs = self._build_benchmark_runs(request)        # §4.1 对齐后，每个基准一次引擎调用
# 未选指数时 runs 含一个"组合默认"run —— 列表长度恒 ≥ 1
result0 = runs[0].result
# 后续全部改为消费 runs / result0：
#   dates/first/last、metadata   ← result0.index_df（各 run 同轴）
#   策略相关                     ← runs[0].metrics 的 start_*
#   各基准列/超额列              ← runs[k].metrics 的 index_* / excess_*
```

`_build_chart_data` 输入从单个 `result` 改为 `runs`；`_build_report_data`、`_sections` 及各 section 构造函数签名增加 `runs` 参数（替换现有 `metrics, result` 双参）。

## 5. 报告组装

### 5.1 命名与标签

| 场景 | 列头/标签 | 说明 |
|---|---|---|
| runs 长度 1（未选或选 1 个） | `指数`、`超额(策略-指数)`、权重表后缀 `(指数)` | **与现状逐字一致，零观感回归** |
| runs 长度 ≥ 2 | `指数1`、`指数2`…；`超额1`、`超额2`…；权重/相关性/热力图标签后缀 `(指数1)` `(指数2)` | metadata 区新增一行 `基准指数：指数1=QQQ.US，指数2=SOXX.US` 自描述 |

`_product_code_label` 的等值判断改为 `code in 选中代码集合`，后缀按序号生成。

### 5.2 各章节表格列布局

统一规则：`[行标签, 指数1..N, 策略, 超额1..N]`（N=1 退化为现状列序）。逐章：

| 章节 | 现状列 | 多指数列（N≥2） |
|---|---|---|
| 1.1 核心收益 | 指标 / 指数 / 策略 / 超额(策略-指数) | 指标 / 指数1 / 指数2 / 策略 / 超额1 / 超额2 |
| 1.2 分年度收益率 | 年份 / 指数 / 策略 / 超额 | 年份 / 指数1..N / 策略 / 超额1..N |
| 1.3 滚动收益 | 滚动周期 / 指数平均收益 / 策略平均收益 / 策略胜率(跑赢指数) | 滚动周期 / 指数1..N 平均收益 / 策略平均收益 / 跑赢指数1胜率..N（各基准独立算窗口胜率） |
| 2.1 回撤指标 | 指标 / 指数 / 策略 | 指标 / 指数1..N / 策略 |
| 2.2 分年度回撤 | 年份 / 指数回撤 / 策略回撤 / 超额回撤 | 年份 / 指数1..N 回撤 / 策略回撤 / 超额回撤1..N |
| 3 风险调整 | 指标 / 指数 / 策略；超额夏普、超额索提诺单行 | 指标 / 指数1..N / 策略；超额夏普/索提诺按基准拆为 N 行（`超额夏普比率(指数N)`） |
| 4.1 / 5.1 / 5.2 / 7.3 / 8 统计总览类 | 指标 / 指数 / 策略 | 指标 / 指数1..N / 策略 |
| 4.2 / 5.3 区间分布 | 区间 / 指数月数 / 指数占比 / 策略月数 / 策略占比 | 区间 / 指数N月数+指数N占比（逐基准）/ 策略月数 / 策略占比 |
| 6.1 超额统计 | 指标 / 数值 | 指标 / 指数1..N（每列一个基准的超额口径值） |
| 6.2 超额区间分布 | 超额区间 / 月数 / 占比 | 超额区间 / 指数N月数+占比（逐基准） |
| 6.3 滚动超额胜率 | 滚动窗口 / 平均超额 / 正超额概率 | 滚动窗口 / 平均超额1..N / 正超额概率1..N |
| 7.1 / 7.2 阶段表现 | 指标 / 指数 / 策略 / 超额 | 指标 / 指数1..N / 策略 / 超额1..N（阶段判定阈值共用，逐基准判定与统计） |

实现方式：各 section 构造函数内把"取 `metrics['index_x']`"的单点取值改为对 runs 的循环取值；列头由 `runs` 长度决定文案（§5.1）。`_table()` 与 Word 模板（`word_export_template`）不需改动，列数增长由 Word 自动排版消化。

### 5.3 结论

N=1 保持现状两句文案；N≥2 逐基准展开（每基准一句"策略相对指数N的累计超额…"），并在首句列出基准清单。

## 6. 图表改造

### 6.1 chart_data 结构

```python
{
  "dates": [...],                        # 统一日期轴（§4.1）
  "strategy_nav / strategy_drawdown / strategy_daily_returns": [...],   # 不变，runs[0]
  "benchmarks": [                        # 新：替代 index_nav / index_drawdown / index_daily_returns
      {"label": "QQQ.US (指数1)", "nav": [...], "drawdown": [...], "daily_returns": [...]},
  ],
  "excess_series": [{"label": "...", "values": [...]}],   # 新：替代单一 excess_nav
  "annual_returns": {"years": [...], "strategy": [...], "benchmarks": [[...], ...]},
  "monthly_excess_by_benchmark": [[...], ...],            # 新：每基准一组月度超额
}
```

### 6.2 逐图处理

| 图 | 现状 | 多指数改法 | 改动量 |
|---|---|---|---|
| 累计净值曲线 | 指数(蓝)+策略(橙)两条线 | 基准 N 条线（调色板取色）+ 策略恒橙；`_draw_line_chart` 本就吃序列列表，只改组装 | 小 |
| 最大回撤曲线 | 指数/策略两块面积 | 同上，序列列表追加 | 小 |
| 超额收益曲线 | 单条红线 | N 条超额线（图例带基准标签）；N=1 保持红色单线现状 | 小 |
| 分年度收益 | 写死 2 组柱（0.36 宽） | 泛化 K=N+1 组柱，宽 0.8/K；`_draw_grouped_bar_chart` 通用化 | 中 |
| 日收益分布 | 写死左右两面板 | 面板=基准数+1（共享分箱逻辑保留）；≤3 面板单行，否则两行网格 | 中 |
| 月度超额分布 | 单序列柱状 | 每基准一张：N=1 标题保持"月度超额分布"，N≥2 标题"月度超额分布（指数N）" | 小 |

### 6.3 调色板

新增 `SERIES_PALETTE`（基准依次取色，策略恒 `ORANGE` 锚定）：N=1 时基准仍取 `BLUE`，与现状逐像素一致。候选：`BLUE、#7030A0(紫)、GREEN、#B45309(棕)、RED`（≥5 基准被 §3.2 上限排除，无需更多）。

## 7. 权重分配 / 相关性 / 成交量

- `_weight_allocation`、`_product_code_label`、`_correlation_matrix` 标签：等值比较 → `in 选中集合`，后缀按 §5.1。
- 成交量、权重相关性、热力图逻辑本身与基准选择无关（产品级），除标签后缀外零改动。

## 8. 边界情况

| 情况 | 行为 |
|---|---|
| 选中产品不在 products / 代码大小写差异 | strip 后精确匹配；不匹配即 ValidationError（§3.2） |
| 指数日历与组合不一致（跨市场节假日） | 统一日期轴取交集（§4.1），整份报告同轴 |
| 交集后 < 2 个交易日 | ValueError（引擎下限，维持现状报错口径） |
| 未选指数 | runs=1（组合默认基准），全报告与现状逐字一致 |
| 选中的指数本身也是权重成分（如 QQQ 30%） | 允许；它既进权重表/相关性，又作基准列 |
| RPT-S | 忽略指数字段，路径不变 |

## 9. 测试计划（tests/unit）

1. **Schema**：列表类型、去重保序、上限 3、未知代码报错、空列表=缺省。
2. **日期轴对齐**：构造日历错位用例（基准多一个节假日）——旧按位置 zip 会错位，新实现按日期取值且轴收缩；断言各序列逐日对齐。
3. **runs 循环**：两个基准时 `runs` 长度 2、`start_*` 各 run 相同、`index_*/excess_*` 各自独立。
4. **表格回归**：N=1 时各 section 列头与行内容与现状**逐字一致**（防回归基线）；N=2 时列头/列序/超额列取对应 run。
5. **标签**：`_product_code_label` N=1 `(指数)`、N=2 `(指数1)/(指数2)`、metadata 基准指数行。
6. **图表**：`generate_report_charts` N=2 时输出图片数量（6+基准数张月度超额）、分年度柱组数、直方图面板数、调色板 N=1 仍为蓝/橙（像素采样，沿用现有 mpimg 断言方式）。
7. 既有单指数用例全部保持绿色（`test_strategy_backtest_report_service.py`、`test_strategy_backtest_report_charts.py`）。

## 10. 实施顺序与工作量

| Commit | 内容 | 规模 |
|---|---|---|
| 1 | Schema 列表化 + export_service 透传 + 校验规则（接口先行，前端已就绪） | ~20 行 |
| 2 | `_resolve_returns` 统一日期轴 + `_build_benchmark_runs` 循环 + 8 章 section 宽列组装 + 标签/结论 | service ~250-350 行 |
| 3 | 图表泛化：chart_data 结构、调色板、分组柱、直方图面板、月度超额多图 | charts ~120-180 行 |
| 4 | 测试补齐 + 本文档索引登记 | tests ~200 行 |

依赖关系：1 与 2/3 可并行开发但需按序合入（后端接口先就位）；2 是 3 的前置（chart_data 结构在 2 定义）。

## 11. 不做的事

- 不接真实指数行情（基准仍是"选中产品自身累计收益"，维持现有语义）。
- 不改 `calculate_v1_metrics` 及 performance_analysis 包的任何契约。
- 不改多品预览页 `SUMMARY_ROW_DEFS` 的"指数"列语义（那是各产品自身回测的基准指标，与导出基准是两个概念）。
- 不做灰度/双轨开关（单路径，旧单指数请求天然兼容）。
- 不限制前端多选 UI 的交互（上限 3 在后端 Schema 兜底即可；前端如需提示另行小改）。

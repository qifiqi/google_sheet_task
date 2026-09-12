"""C 系模板（C3/C4/C5/C7）单元格布局与指标词汇的单一规格表。

历史上同一份"模板单元格 ↔ 指标"知识散落在 model_summary/extractor、
backtest_report_query_service、export_workbook_service、c7_result_normalizer
四处，且键名各不相同（maxdd/max_drawdown、year_rate/turnover_rate 等）。
本文件以 extractor 的英文概念键为规范词汇，一处声明单元格事实，
其余视图（报表摘要键、C7 平移键、导出键序列）全部由此派生。

改模板单元格位置只改本文件；消费方 import 派生名即可。

边界说明：
- 出库载荷键（result_payload.STOCK_PARAM_METRIC_SPECS 的 maxdd/index_rate/
  max_index_dd/max_1y_beats/min_1y_beats 等）已持久化在 TaskResult.result 中，
  属对外契约，本文件只在注释登记对应关系，不改写 result_payload.py
  （AGENTS.md 指定其为透传规格表）。
- 模板参数输入格同时存在运营可调的 DB 配置（SystemConfig 的
  c3_parameter_positions / C3_commission_cell），本表是代码侧消费的静态事实，
  两侧需人工保持一致（见 docs/design/constants-audit-2026-09）。
"""

from __future__ import annotations


# ===========================================================================
# C3 参数输入格：8 槽位（B5 佣金 + 7 业务参数）
# ===========================================================================
# (单元格, 契约字段名, 导出列名, 展示标签)
# - 契约字段名：normalize_c3_parameter_row 产出的参数行顺序（commission 在首位），
#   也是回测报表行键（backtest_report_query_service._build_c3_summary_rows）；
# - 导出列名：C3 结果中持久化的参数命名键（导出时先读单元格、回退命名键）；
#   None 表示该槽位不进导出参数列；
# - 展示标签：回测报表参数表头（backtest_api 的 parameter_fields）。
C3_PARAM_SLOTS = [
    ("B5", "commission", None, "Commission"),
    ("B6", "xm", "xm", "X Multiplier"),
    ("B7", "dbbh1", "tp1", "单边保护1"),
    ("B8", "dbbh2", None, "单边保护2"),
    ("B9", "zlxc", "nl", "中立限仓"),
    ("B10", "zsgz", "if", "指数跟踪"),
    ("B11", "ywf1", "ywfs", "一窝蜂 smoothing"),
    ("B12", "ywf2", "ywb", "一窝蜂 bordering"),
]

# C3 参数行契约（不含佣金）；backtest_parameter_utils / backtest_excel_service 消费。
C3_PARAMETER_KEYS = tuple(
    key for _cell, key, _alias, _label in C3_PARAM_SLOTS if key != "commission"
)

# C3 参数字段（含佣金，参数行顺序）；backtest_api / backtest_report_query_service 消费。
C3_PARAMETER_FIELDS = [(key, label) for _cell, key, _alias, label in C3_PARAM_SLOTS]

# C3 参数列名 → Google Sheet 单元格引用映射（与 _build_stock_param_result_payload 对应）。
C3_PARAM_CELL_MAP = [
    (alias, cell) for cell, _key, alias, _label in C3_PARAM_SLOTS if alias
]
C3_PARAM_NAMES = [name for name, _cell in C3_PARAM_CELL_MAP]


# ===========================================================================
# 结果单元格：概念键 → 单元格
# 概念键 = extractor 词汇，也是 model_summary SUMMARY_COLUMNS 的 key。
# ===========================================================================
C3_METRIC_CELLS = {
    "return_rate": "I15",
    "annualized_rate": "I16",
    "max_drawdown": "I17",
    "index_return": "I18",
    "index_annualized_rate": "I19",
    "index_max_drawdown": "I20",
    "fee_total": "I21",
    "fee_annualized": "I22",
    "turnover_rate": "I23",
}

C4_C5_METRIC_CELLS = {
    "return_rate": "D2",
    "annualized_rate": "D3",
    "max_drawdown": "D4",
    "index_return": "D5",
    "index_annualized_rate": "D6",
    "index_max_drawdown": "D7",
    "fee_total": "D8",
    "fee_annualized": "D9",
    "turnover_rate": "D10",
    "return_beats": "D11",
    "dd_beats": "D12",
    "max_one_year_beats": "D13",
    "min_one_year_beats": "D14",
    "max_theoretical_leverage": "D15",
    "avg_theoretical_leverage": "D16",
    "unit_theoretical_leverage_return": "D17",
    "max_actual_leverage": "D18",
    "avg_actual_leverage": "D19",
    "unit_actual_leverage_return": "D20",
}

# C7.0.2 的结果区域 = C4/C5 布局整体下移 6 行（D2→D8 … D20→D26）；
# C7.0.3 与 C5 布局一致，不做平移。
C7_ROW_SHIFT = 6


def c7_shifted_cell(cell: str) -> str:
    """把 C4/C5 布局的单元格引用平移到 C7.0.2 布局。"""
    return f"D{int(cell[1:]) + C7_ROW_SHIFT}"


# ===========================================================================
# 派生视图（逐值等价于各消费方的历史常量，勿在此处"顺手"改名）
# ===========================================================================
# 回测报表摘要只取 4 个概念；报表词汇把 return_rate 叫 return。
_REPORT_SUMMARY_ALIASES = {"return_rate": "return"}
_REPORT_SUMMARY_CONCEPTS = (
    "return_rate",
    "index_return",
    "max_drawdown",
    "index_max_drawdown",
)


def _report_key(concept: str) -> str:
    return _REPORT_SUMMARY_ALIASES.get(concept, concept)


# 报表摘要概念 → 取数单元格（含 C4=C5 别名与 C7 平移视图）。
SUMMARY_METRIC_CELL_MAP = {
    "C3": {
        _report_key(concept): C3_METRIC_CELLS[concept]
        for concept in _REPORT_SUMMARY_CONCEPTS
    },
    "C5": {
        _report_key(concept): C4_C5_METRIC_CELLS[concept]
        for concept in _REPORT_SUMMARY_CONCEPTS
    },
    "C7": {
        _report_key(concept): c7_shifted_cell(C4_C5_METRIC_CELLS[concept])
        for concept in _REPORT_SUMMARY_CONCEPTS
    },
}
SUMMARY_METRIC_CELL_MAP["C4"] = SUMMARY_METRIC_CELL_MAP["C5"]

# C5 导出取数键序列（c5_model_row 的列顺序）：D11/D12 打头，其余按布局行序。
_C5_EXPORT_METRIC_KEY_CONCEPTS = (
    "return_beats",
    "dd_beats",
    "return_rate",
    "annualized_rate",
    "max_drawdown",
    "index_return",
    "index_annualized_rate",
    "index_max_drawdown",
    "unit_theoretical_leverage_return",
    "unit_actual_leverage_return",
)
C5_EXPORT_METRIC_KEYS = [C4_C5_METRIC_CELLS[key] for key in _C5_EXPORT_METRIC_KEY_CONCEPTS]

# C7 原始结果中按百分数字符串存储、需 ×100 归一的单元格（C7 平移布局下取值）。
_C7_RAW_PERCENT_CONCEPTS = (
    "max_drawdown",
    "fee_annualized",
    "dd_beats",
    "max_one_year_beats",
)
_C7_PERCENT_LEVERAGE_CONCEPTS = (
    "avg_theoretical_leverage",
    "max_actual_leverage",
    "avg_actual_leverage",
)
C7_RAW_PERCENT_CELLS = frozenset(
    c7_shifted_cell(C4_C5_METRIC_CELLS[key]) for key in _C7_RAW_PERCENT_CONCEPTS
)
C7_PERCENT_LEVERAGE_CELLS = frozenset(
    c7_shifted_cell(C4_C5_METRIC_CELLS[key]) for key in _C7_PERCENT_LEVERAGE_CONCEPTS
)


# ===========================================================================
# 单品摘要 6 行（Excel"汇总" sheet 的行序 + 取数概念键）
# ===========================================================================
# 历史名 SUMMARY_ROW_LABELS 与 summary_contract.SUMMARY_ROW_LABELS（21 项契约）
# 同名异义，此处更名单品摘要专用名；metric_key 配合 SUMMARY_METRIC_CELL_MAP 取数，
# excess_return/excess_drawdown 两行由报表侧用相邻概念做差派生。
SINGLE_PRODUCT_SUMMARY_ROW_LABELS = [
    ("index_return", "指数回报"),
    ("return", "模型回报"),
    ("excess_return", "超额回报"),
    ("index_max_drawdown", "指数回撤"),
    ("max_drawdown", "模型回撤"),
    ("excess_drawdown", "超额回撤"),
]

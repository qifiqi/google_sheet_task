"""C 系任务结果的参数配置指标提取（报告“参数配置”表取数入口）。

把 TaskResult.result 里的模板单元格值按 C5/C4、C7.0.2、C7.0.3、C3 布局
归一为浮点指标：C7.0.2 先经 export 域统一归一平移到 C5 键；C3 只有
年换手率（无杠杆列），其余指标缺省。消费方为多品 Word 载荷构建与
RPT-S 单品任务来源，权重聚合由报告服务负责。
"""

from __future__ import annotations

import re
from typing import Any

from app.constants.c_template_layout import C3_METRIC_CELLS, C4_C5_METRIC_CELLS
from app.services.export_workbook_service import normalize_c7_model_metrics
from app.utils.backtest_report_metadata import is_c7_0_3_config
from app.utils.value_parser import parse_percent_like


# 报告“参数配置”表行序（概念键, 展示名, 展示格式）：对应 C5 结果区 D10/D15-D20。
# 年换手率在模板里是普通数值（与 C3 导出“不乘100”口径一致），不按百分比展示。
PARAMETER_CONFIG_ROWS = (
    ("turnover_rate", "年换手率", "number"),
    ("max_theoretical_leverage", "最大理论杠杆率", "number"),
    ("avg_theoretical_leverage", "平均理论杠杆率", "number"),
    ("unit_theoretical_leverage_return", "单位理论杠杆率收益", "percent"),
    ("max_actual_leverage", "最大实际杠杆率", "number"),
    ("avg_actual_leverage", "平均实际杠杆率", "number"),
)

_CELL_REF = re.compile(r"[A-Z]{1,3}\d{1,4}")


def extract_parameter_metrics(result_payload: Any, sheet: Any) -> dict[str, float]:
    """从结果载荷提取参数配置指标；无值的指标不出现在返回字典。

    result_payload 为 TaskResult.result 解析后的字典；sheet 为产品/任务的
    模板配置（title、model_version 决定单元格布局）。
    """
    cells = _cell_values(result_payload)
    if not cells:
        return {}
    sheet_config = sheet if isinstance(sheet, dict) else {}
    title = str(sheet_config.get("title") or "").upper()
    if "C3" in title:
        cell_map = {"turnover_rate": C3_METRIC_CELLS["turnover_rate"]}
    else:
        if "C7" in title and not is_c7_0_3_config({"sheets": [sheet_config]}):
            cells = normalize_c7_model_metrics(cells)
        cell_map = {key: C4_C5_METRIC_CELLS[key] for key, _label, _format in PARAMETER_CONFIG_ROWS}
    metrics: dict[str, float] = {}
    for key, cell in cell_map.items():
        value = parse_percent_like(cells.get(cell))
        if value is not None:
            metrics[key] = value
    return metrics


def _cell_values(result_payload: Any) -> dict[str, Any]:
    """收集结果载荷中的单元格值（兼容多模型键载荷），先到先得。"""
    if not isinstance(result_payload, dict):
        return {}
    cells: dict[str, Any] = {}
    for value in result_payload.values():
        if not isinstance(value, dict):
            continue
        for key, cell_value in value.items():
            key_text = str(key).strip().upper()
            if _CELL_REF.fullmatch(key_text):
                cells.setdefault(key_text, cell_value)
    return cells

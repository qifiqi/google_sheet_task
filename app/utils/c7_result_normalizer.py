from typing import Any


C7_RAW_PERCENT_CELLS = frozenset({"D10", "D15", "D18", "D19"})
C7_PERCENT_LEVERAGE_CELLS = frozenset({"D22", "D24", "D25"})


def normalize_c7_result_metrics(metrics: dict[str, Any]) -> dict[str, Any]:
    """将 C7 格式化指标值规范为 C5 指标单位。"""
    normalized = dict(metrics)
    for cell in C7_RAW_PERCENT_CELLS:
        value = normalized.get(cell)
        if value in (None, "") or str(value).strip().endswith("%"):
            continue
        try:
            normalized[cell] = f"{float(str(value).replace(',', '')) * 100:.2f}%"
        except ValueError:
            continue

    for cell in C7_PERCENT_LEVERAGE_CELLS:
        value = normalized.get(cell)
        if not isinstance(value, str) or not value.strip().endswith("%"):
            continue
        try:
            normalized[cell] = float(value.strip()[:-1]) / 100
        except ValueError:
            continue
    return normalized

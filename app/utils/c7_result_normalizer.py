from typing import Any

from app.constants.c_template_layout import (
    C7_PERCENT_LEVERAGE_CELLS,
    C7_RAW_PERCENT_CELLS,
)


def normalize_c7_result_metrics(metrics: dict[str, Any]) -> dict[str, Any]:
    """Normalize C7 formatted values to the C5 metric units."""
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

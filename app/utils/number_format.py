"""数值缩写展示工具：按中文习惯把大数缩写为 亿/万。"""

from __future__ import annotations

import math
from typing import Any


def abbreviate_number(value: Any) -> str | None:
    """把数值缩写为中文单位文本：≥1亿 → X.XX亿，≥1万 → X.XX万，其余千分位。

    None / 非数值 / 非有限数返回 None，由展示层渲染 "-"；负数保留符号。
    """
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    if abs(number) >= 1e8:
        return f"{number / 1e8:.2f}亿"
    if abs(number) >= 1e4:
        return f"{number / 1e4:.2f}万"
    return f"{number:,.0f}"

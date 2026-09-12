"""结果就绪判定策略公共件（C5/C7 共享的 check_result 核心，2026-09 审计 C4 批次）。

原实现为 `_execute_parameter_combination` 内的嵌套闭包，捕获本地状态；
其核心（有效性校验 → #错误值判定 → 百分数/千分位归一 → '-' 占位剔除）
是纯逻辑，收敛至此便于细粒度测试。C3（检查位校验）/C4（D2D3 变化检测）
的变体语义不同，保留在各自任务文件。
"""

from __future__ import annotations

from typing import Any, Callable

from app.exceptions.sheet_check_error import SheetCheckError
from app.utils.logger import get_logger
from app.utils.result_validator import is_valid_result_value

logger = get_logger(__name__)

# C5 的无效值判定：falsy（None/""/0）或校验器不认可。
def _c5_invalid(value: Any) -> bool:
    return (not value) or (not is_valid_result_value(value))


# C7 的无效值判定：None/纯空白字符串单独识别，0 不视为无效。
def _c7_invalid(value: Any) -> bool:
    return (
        value is None
        or (isinstance(value, str) and not value.strip())
        or (not is_valid_result_value(value))
    )


C5_INVALID = _c5_invalid
C7_INVALID = _c7_invalid


def normalize_check_values(
    check_values: dict[str, Any],
    *,
    log_info: Callable[[str], None] = logger.info,
    invalid_predicate: Callable[[Any], bool] = _c5_invalid,
) -> dict[str, Any]:
    """校验并归一 Sheet 输出的检查位取值。

    - 无效值（由 invalid_predicate 判定）：记日志后抛 Exception（调用方按失败计数）；
    - '#'/'#N/A' 开头：抛 SheetCheckError（模板输出错误信号）；
    - '5.00%' → 0.05；'1,234' → 1234.0；
    - '-' 占位剔除（不进入结果）。
    """
    normalized: dict[str, Any] = {}
    for position, value in check_values.items():
        if invalid_predicate(value):
            log_info(f"结果位置 {position} 值为空或无效，跳过重新检查：{value}")
            raise Exception(f"结果位置 {position} 值为空或无效，跳过重新检查：{value}")

        if str(value).strip().startswith(("#", "#N/A")):
            error_msg = f"获取结果位置 {position} 时出错: {str(value)}"
            raise SheetCheckError(f"检查报错，出现#|#N/A 这种异常错误，联系用户检查 {error_msg}")

        normalized_value = value
        if isinstance(normalized_value, str) and "%" in normalized_value:
            normalized_value = float(normalized_value.replace("%", "").replace(",", "")) / 100
        if isinstance(normalized_value, str) and "," in normalized_value:
            normalized_value = float(normalized_value.replace(",", ""))
        if normalized_value == "-":
            continue

        normalized[position] = normalized_value
    return normalized

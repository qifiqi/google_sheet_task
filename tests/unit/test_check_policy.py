"""C4(2/2) 批次：check_result 闭包核心逻辑的特征测试（check_policy）。

特征基线来自 C5/C7 原嵌套闭包的既有行为（2026-09 审计 C4 批次抽取前）：
- 空值/无效值 → Exception（含位置信息）；
- '#'/'#N/A' 开头 → SheetCheckError；
- '5.00%' → 0.05；'1,234' → 1234.0；
- '-' 占位剔除；普通值原样保留。
"""
import pytest

from app.exceptions.sheet_check_error import SheetCheckError
from app.services.google_sheet_tasks.check_policy import C5_INVALID, C7_INVALID, normalize_check_values


def _capture_logs():
    logs = []

    def log_info(message):
        logs.append(message)

    return log_info, logs


def test_normalizes_percent_and_thousands_and_keeps_plain():
    result = normalize_check_values(
        {"D2": "5.00%", "D3": "1,234", "D4": 0.42, "D5": "-"},
        log_info=lambda _m: None,
    )
    assert result == {"D2": 0.05, "D3": 1234.0, "D4": 0.42}


def test_blank_or_invalid_value_raises_with_position():
    log_info, logs = _capture_logs()
    with pytest.raises(Exception, match="结果位置 D2 值为空或无效"):
        normalize_check_values({"D2": "", "D3": "1"}, log_info=log_info)
    assert logs and "D2" in logs[0]


def test_none_value_raises_under_both_predicates():
    for predicate in (C5_INVALID, C7_INVALID):
        with pytest.raises(Exception, match="值为空或无效"):
            normalize_check_values(
                {"D2": None}, log_info=lambda _m: None, invalid_predicate=predicate
            )


def test_hash_prefixed_value_raises_sheet_check_error():
    """通过有效性校验但以 # 开头的值 → SheetCheckError（#N/A 等标准错误值在
    更早的无效值分支被拦截——特征行为与抽取前闭包一致）。"""
    with pytest.raises(SheetCheckError, match="检查报错"):
        normalize_check_values({"D2": "#模板异常"}, log_info=lambda _m: None)


def test_zero_is_invalid_under_c5_but_valid_under_c7():
    """两任务的真实语义差异：0 在 C5 为无效（按失败计数），在 C7 合法保留。"""
    with pytest.raises(Exception, match="值为空或无效"):
        normalize_check_values({"D2": 0}, log_info=lambda _m: None, invalid_predicate=C5_INVALID)

    result = normalize_check_values({"D2": 0}, log_info=lambda _m: None, invalid_predicate=C7_INVALID)
    assert result == {"D2": 0}


def test_dash_placeholder_is_dropped():
    result = normalize_check_values({"D2": "-", "D3": "1.5"}, log_info=lambda _m: None)
    # 特征行为：无 %/千分位标记的字符串保持字符串（与抽取前一致）
    assert result == {"D3": "1.5"}

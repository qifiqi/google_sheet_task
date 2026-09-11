"""强密码策略 util 测试（app.utils.auth.validate_password_strength）。

策略基线：8-64 位，且同时包含大写字母、小写字母、数字、特殊字符。
"""

from app.utils.auth import (
    PASSWORD_MAX_LENGTH,
    PASSWORD_MIN_LENGTH,
    validate_password_strength,
)


def test_strong_password_passes():
    assert validate_password_strength("Abcdef12!@") is None


def test_min_and_max_boundary_pass():
    # 恰好 8 位（四类各一）
    assert validate_password_strength("Aa1!aaaa") is None
    # 恰好 64 位
    assert validate_password_strength("A" * (PASSWORD_MAX_LENGTH - 3) + "a1!") is None


def test_empty_returns_error():
    assert validate_password_strength("") == "密码不能为空"
    assert validate_password_strength(None) == "密码不能为空"


def test_too_short_rejected():
    assert validate_password_strength("Aa1!") == "密码长度不能少于8位"


def test_too_long_rejected():
    assert validate_password_strength("Aa1!" * (PASSWORD_MAX_LENGTH // 4 + 1)) == (
        f"密码长度不能超过{PASSWORD_MAX_LENGTH}位"
    )


def test_missing_categories_listed():
    assert validate_password_strength("abcdef12") == "密码须包含大写字母、特殊字符"
    assert validate_password_strength("ABCDEF12!") == "密码须包含小写字母"
    assert validate_password_strength("Abcdefgh!") == "密码须包含数字"
    assert validate_password_strength("Abcdef12") == "密码须包含特殊字符"
    # 纯数字：缺大写、小写、特殊字符三类
    assert validate_password_strength("12345678") == (
        "密码须包含大写字母、小写字母、特殊字符"
    )


def test_min_length_constant_upgraded_from_legacy():
    # 旧策略为 6 位，新策略必须更严，防止回归回退。
    assert PASSWORD_MIN_LENGTH >= 8

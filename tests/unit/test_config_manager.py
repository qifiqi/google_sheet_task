"""config_manager 类型往返 / 负缓存 / coerce_bool 行为回归。"""

import pytest

from app.extensions import db
from app.models import SystemConfig
from app.services.config_manager import (
    ConfigManager,
    coerce_bool,
    get_config_manager,
)


@pytest.fixture()
def manager(app_factory):
    """绑定测试应用的独立 ConfigManager 实例。"""
    app = app_factory
    manager = ConfigManager()
    manager.init_app(app)
    with app.app_context():
        yield manager


def _set_raw(manager, key, value):
    with manager._get_app_context():
        db.session.add(SystemConfig(key=key, value=value))
        db.session.commit()
    manager.refresh_cache()


def test_bool_roundtrip_returns_real_bool(manager):
    manager.set_config("feature_enabled", True)
    with manager._get_app_context():
        assert manager.get_config("feature_enabled") is True

    manager.set_config("feature_disabled", False)
    with manager._get_app_context():
        assert manager.get_config("feature_disabled") is False


def test_container_and_number_roundtrip(manager):
    manager.set_config("positions", ["A1", "B2"])
    manager.set_config("retry_count", 3)
    with manager._get_app_context():
        assert manager.get_config("positions") == ["A1", "B2"]
        assert manager.get_config("retry_count") == 3
        assert isinstance(manager.get_config("retry_count"), int)


def test_legacy_str_bool_literals_are_restored(manager):
    _set_raw(manager, "legacy_on", "True")
    _set_raw(manager, "legacy_off", "False")
    with manager._get_app_context():
        assert manager.get_config("legacy_on") is True
        assert manager.get_config("legacy_off") is False


def test_plain_text_is_not_mangled(manager):
    _set_raw(manager, "plain_text", "小心地滑 TrueValue")
    with manager._get_app_context():
        assert manager.get_config("plain_text") == "小心地滑 TrueValue"


def test_negative_cache_stores_sentinel_and_returns_default(manager):
    from app.services.config_manager import _MISSING

    with manager._get_app_context():
        manager.refresh_cache()
        assert manager.get_config("never_configured", "fallback") == "fallback"
        assert manager._cache["never_configured"] is _MISSING, "缺失 key 应记录负缓存哨兵"
        assert manager.get_config("never_configured", "fallback") == "fallback"


def test_coerce_bool_covers_history_formats():
    assert coerce_bool(True) is True
    assert coerce_bool(False) is False
    assert coerce_bool("true") is True
    assert coerce_bool("YES") is True
    assert coerce_bool("1") is True
    assert coerce_bool("0") is False
    assert coerce_bool("") is False
    assert coerce_bool(None, True) is True
    assert coerce_bool("garbage", True) is True
    assert coerce_bool("garbage", False) is False


def test_get_all_configs_hides_negative_sentinels(manager):
    manager.get_config("missing_key_1", None)
    configs = manager.get_all_configs()
    assert "missing_key_1" not in configs


def test_set_config_logs_key_only(manager, caplog):
    import logging

    with manager._get_app_context():
        with caplog.at_level(logging.DEBUG, logger="app.services.config_manager"):
            manager.set_config("api_secret_key", "super-secret-value")
    assert "super-secret-value" not in caplog.text
    assert "api_secret_key" in caplog.text


def test_get_config_manager_is_process_wide_singleton(app_factory):
    app = app_factory
    with app.app_context():
        assert get_config_manager() is get_config_manager()

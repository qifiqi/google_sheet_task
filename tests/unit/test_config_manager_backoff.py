"""配置缓存远端故障退避：避免每次 get 都触发全量拉取。"""
from app.services import config_manager as config_manager_module
from app.services.config_manager import ConfigManager


def test_load_failure_uses_short_backoff(app_factory, monkeypatch):
    calls = {"count": 0}

    def _raise():
        calls["count"] += 1
        raise RuntimeError("remote down")

    monkeypatch.setattr(
        config_manager_module.system_config_repository,
        "list_rows",
        _raise,
    )
    now = {"value": 100.0}
    monkeypatch.setattr(
        config_manager_module.time,
        "monotonic",
        lambda: now["value"],
    )

    manager = ConfigManager()

    assert manager.get_config("missing", "fallback") == "fallback"
    assert manager.get_config("missing", "fallback") == "fallback"
    assert calls["count"] == 1

    now["value"] = 110.0
    assert manager.get_config("missing", "fallback") == "fallback"
    assert calls["count"] == 2

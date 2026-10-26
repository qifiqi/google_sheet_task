import pytest

from app import config


def test_resolve_database_url_reads_env(monkeypatch):
    postgres_url = "postgresql://user:pass@example.test:5432/app"
    monkeypatch.setenv("DATABASE_URL", postgres_url)

    assert config._resolve_database_url() == postgres_url


def test_resolve_database_url_missing_returns_empty(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)

    assert config._resolve_database_url() == ""


def test_init_app_requires_database_url(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)

    with pytest.raises(RuntimeError, match="DATABASE_URL"):
        config.BaseConfig.init_app()

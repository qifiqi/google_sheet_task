from pathlib import Path

from app import config


def test_resolve_sqlite_database_url_uses_absolute_posix_path(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite:///instance/app.db")

    database_url = config._resolve_database_url("sqlite:///fallback.db")

    expected_path = (config.BASE_DIR / "instance" / "app.db").resolve().as_posix()
    assert database_url == f"sqlite:///{expected_path}"
    assert "\\" not in database_url


def test_resolve_sqlite_database_url_keeps_absolute_path(monkeypatch, tmp_path):
    db_path = tmp_path / "dev.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")

    database_url = config._resolve_database_url("sqlite:///fallback.db")

    assert database_url == f"sqlite:///{db_path.resolve().as_posix()}"


def test_resolve_database_url_leaves_non_sqlite_url_unchanged(monkeypatch):
    postgres_url = "postgresql://user:pass@example.test:5432/app"
    monkeypatch.setenv("DATABASE_URL", postgres_url)

    assert config._resolve_database_url("sqlite:///fallback.db") == postgres_url

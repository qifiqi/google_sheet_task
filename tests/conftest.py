import os
import sys
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.utils import ttl_cache


@pytest.fixture(autouse=True)
def _isolated_word_export_cache(tmp_path, monkeypatch):
    """Word 导出缓存指向临时目录并先清再测，用例间互不命中、不污染真实 data/。"""
    monkeypatch.setattr(ttl_cache, "word_export_cache_dir", lambda: tmp_path / "word_export_cache")
    ttl_cache.clear_word_export_cache()
    yield
    ttl_cache.clear_word_export_cache()


@pytest.fixture
def sqlite_test_url(tmp_path):
    return f"sqlite:///{tmp_path / 'test_app.db'}"


@pytest.fixture
def app_factory(monkeypatch, sqlite_test_url):
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("AUTH_ENABLED", "true")
    monkeypatch.setenv("JWT_SECRET_KEY", "test-secret-key-for-pytest")
    monkeypatch.setenv("DATABASE_URL", sqlite_test_url)
    monkeypatch.chdir(PROJECT_ROOT)

    from app import create_app
    from app.extensions import db

    app = create_app()
    app.config.update(TESTING=True)

    with app.app_context():
        db.drop_all()
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()

import os
import sys
import types

import pytest
import requests


# 提前注入一个临时数据库地址，确保导入应用模块时不会连接默认数据库。
os.environ["DATABASE_URL"] = "sqlite:///tests_bootstrap.db"


class _FakeCurlSession(requests.Session):
    """测试环境下替代 curl_cffi Session，忽略 impersonate 参数。"""

    def __init__(self, *args, **kwargs):
        kwargs.pop("impersonate", None)
        super().__init__()


fake_curl_module = types.ModuleType("curl_cffi")
fake_curl_module.requests = types.SimpleNamespace(Session=_FakeCurlSession)
sys.modules.setdefault("curl_cffi", fake_curl_module)

fake_yfinance_module = types.ModuleType("yfinance")
fake_yfinance_module.Ticker = object
fake_yfinance_module.download = lambda *args, **kwargs: None
sys.modules.setdefault("yfinance", fake_yfinance_module)

from app import create_app  # noqa: E402
from app.config import Config  # noqa: E402
from app.extensions import db  # noqa: E402
from app.models import Task, TaskTemplate  # noqa: E402


@pytest.fixture()
def app(tmp_path):
    """创建隔离的 Flask 测试应用。"""
    test_db_path = tmp_path / "test_app.db"
    test_db_uri = f"sqlite:///{test_db_path.as_posix()}"
    original_db_uri = Config.SQLALCHEMY_DATABASE_URI

    # 应用工厂从 Config 类读取数据库地址，因此需要在创建应用前覆写配置。
    Config.SQLALCHEMY_DATABASE_URI = test_db_uri
    app = create_app()
    app.config.update(
        TESTING=True,
        SQLALCHEMY_DATABASE_URI=test_db_uri,
    )

    with app.app_context():
        # 这里只创建当前测试依赖的核心表，避免历史模型中的索引兼容问题影响回归测试。
        Task.__table__.create(bind=db.engine, checkfirst=True)
        TaskTemplate.__table__.create(bind=db.engine, checkfirst=True)

    yield app

    with app.app_context():
        db.session.remove()
        db.engine.dispose()
    Config.SQLALCHEMY_DATABASE_URI = original_db_uri


@pytest.fixture()
def client(app):
    """提供 Flask 测试客户端。"""
    return app.test_client()

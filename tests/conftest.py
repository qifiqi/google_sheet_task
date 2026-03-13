import os

import pytest


# 提前注入一个兜底测试数据库地址，确保导入应用前不会连接到默认实例库。
os.environ["DATABASE_URL"] = "sqlite:///tests_bootstrap.db"

from app import create_app  # noqa: E402
from app.extensions import db  # noqa: E402
from app.models import Task  # noqa: E402


@pytest.fixture()
def app(tmp_path):
    """创建隔离的 Flask 测试应用。"""
    test_db_path = tmp_path / "test_app.db"

    app = create_app()
    app.config.update(
        TESTING=True,
        SQLALCHEMY_DATABASE_URI=f"sqlite:///{test_db_path.as_posix()}",
    )

    with app.app_context():
        # 这里只创建当前测试真正依赖的表，避免历史模型中的重名索引影响阶段 5 起步。
        Task.__table__.drop(bind=db.engine, checkfirst=True)
        Task.__table__.create(bind=db.engine, checkfirst=True)

    yield app

    with app.app_context():
        db.session.remove()
        Task.__table__.drop(bind=db.engine, checkfirst=True)
        db.engine.dispose()


@pytest.fixture()
def client(app):
    """提供 Flask 测试客户端。"""
    return app.test_client()

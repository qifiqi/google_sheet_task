import os
import sys
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# ---- 会话级安全护栏（必须在任何 app 导入之前执行）----
# 仓储后端在 import 期按 DATA_ACCESS_MODE 一次性绑定，而测试模块导入
# app 时 create_app 尚未运行、fixture 还没机会设置环境变量；若保持默认
# http，测试进程会经 create_app 载入的 .env STOCK_BASE_URL 直连远程
# DY.Stock.Api 读写真实数据。这里在导入前固定本地 DB 后端并清空远程
# 地址（键已存在时 .env 不覆盖），确保任何残留的远程调用都快速失败。
os.environ.setdefault("DATA_ACCESS_MODE", "db")
os.environ["STOCK_BASE_URL"] = ""
os.environ.pop("STOCK_API_TOKEN", None)


@pytest.fixture
def sqlite_test_url(tmp_path):
    return f"sqlite:///{tmp_path / 'test_app.db'}"


@pytest.fixture
def app_factory(monkeypatch, sqlite_test_url):
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("AUTH_ENABLED", "true")
    monkeypatch.setenv("JWT_SECRET_KEY", "test-secret-key-for-pytest")
    monkeypatch.setenv("DATABASE_URL", sqlite_test_url)
    # 测试固定使用本地 DB 后端（http 模式依赖远程服务，单测不可达）。
    monkeypatch.setenv("DATA_ACCESS_MODE", "db")
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

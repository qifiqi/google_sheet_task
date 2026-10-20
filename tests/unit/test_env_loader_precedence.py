"""环境文件优先级：真实环境变量 > .env.{APP_ENV} > .env。"""
import os
from unittest.mock import patch

from app.env_loader import load_app_environment


def test_env_file_precedence(tmp_path):
    (tmp_path / ".env").write_text(
        "ENV_LOADER_TEST_BASE=base\nENV_LOADER_TEST_SHARED=base\n",
        encoding="utf-8",
    )
    (tmp_path / ".env.testing").write_text(
        "ENV_LOADER_TEST_SCOPED=scoped\nENV_LOADER_TEST_SHARED=scoped\n",
        encoding="utf-8",
    )

    with patch.dict(
        os.environ,
        {"APP_ENV": "testing", "ENV_LOADER_TEST_REAL": "real"},
        clear=False,
    ):
        load_app_environment(tmp_path)

        assert os.environ["ENV_LOADER_TEST_REAL"] == "real"
        assert os.environ["ENV_LOADER_TEST_SHARED"] == "scoped"
        assert os.environ["ENV_LOADER_TEST_BASE"] == "base"
        assert os.environ["ENV_LOADER_TEST_SCOPED"] == "scoped"

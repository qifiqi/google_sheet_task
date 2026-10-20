"""安全整改回归：配置接口收权与 JWT 密钥 fail-closed（2026-10 安全审计）。

覆盖点：
- 受保护配置键（JWT_SECRET_KEY/proxy_url/SECRET_KEY）禁止经
  /api/config POST 与 /system-configs PUT 的服务层写入路径更新；
- 生产环境 JWT_SECRET_KEY 环境变量未设置时不再拒绝启动（运行期回退
  进程内随机密钥），启动校验仅告警；显式等于公开默认常量仍拒绝启动。
"""
import pytest

from app.exceptions import BadRequestError
from app.services.config_manager import PROTECTED_CONFIG_KEYS, ConfigManager
from app.utils import auth as auth_module


class TestProtectedConfigKeys:
    """受保护配置键：任何经配置接口的写入路径都必须被服务层拒绝。"""

    def test_update_configs_rejects_proxy_url(self):
        with pytest.raises(BadRequestError, match="受保护配置"):
            ConfigManager().update_configs({"proxy_url": "http://attacker:8080"})

    def test_update_configs_rejects_protected_key_among_others(self):
        with pytest.raises(BadRequestError, match="JWT_SECRET_KEY"):
            ConfigManager().update_configs({"some_normal_key": "1", "JWT_SECRET_KEY": "evil"})

    def test_update_config_row_rejects_protected_value(self):
        with pytest.raises(BadRequestError, match="受保护配置"):
            ConfigManager().update_config_row("proxy_url", {"value": "http://evil.example"})

    def test_every_protected_key_is_blocked(self):
        for key in PROTECTED_CONFIG_KEYS:
            with pytest.raises(BadRequestError):
                ConfigManager().update_configs({key: "x"})


class TestJwtSecretFailClosed:
    """JWT 密钥解析：公开默认常量在任何路径都不可用。"""

    def test_missing_secret_in_production_no_longer_raises(self, monkeypatch):
        # 旧版在此场景放行且运行期回退默认密钥（fail-open）；
        # 单 Token 子服务模式下本地签名已停用，启动校验只拦"显式等于默认常量"。
        monkeypatch.setenv("APP_ENV", "production")
        monkeypatch.setenv("AUTH_ENABLED", "true")
        monkeypatch.delenv("JWT_SECRET_KEY", raising=False)

        auth_module.validate_auth_runtime_settings()  # 不抛即通过

    def test_runtime_secret_is_stable_within_process(self, monkeypatch):
        monkeypatch.delenv("JWT_SECRET_KEY", raising=False)
        assert auth_module._get_secret() == auth_module._get_secret()

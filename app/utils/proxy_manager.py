import os
import shutil
import threading
import time
from typing import Any

import certifi
import requests


class SmartProxyManager:
    """Manage a short-lived proxy pool for DFCF requests."""

    def __init__(self, logger=None):
        self.lock = threading.Lock()
        self.proxy_size = 0
        self.logger = logger
        self.max_proxy_size = 50
        self.proxy = {}
        self.proxy_time = time.time()
        self.proxy_config = {
            "base_username": "9DFBAAA4",
            "password": "9BA6FBC6AA65",
            "url": "https://share.proxy.qg.net/get?key=9DFBAAA4&num=1&area=&isp=0&format=json&distinct=false",
        }
        self.cert_path = self._get_persistent_cert_path()

    @staticmethod
    def _redact_proxy(proxy: dict[str, str] | dict[Any, Any]):
        redacted = {}
        for key, value in proxy.items():
            proxy_url = str(value)
            if "@" in proxy_url:
                scheme, rest = proxy_url.split("://", 1) if "://" in proxy_url else ("", proxy_url)
                _, host = rest.rsplit("@", 1)
                redacted[key] = f"{scheme}://***:***@{host}" if scheme else f"***:***@{host}"
            else:
                redacted[key] = proxy_url
        return redacted

    def _get_persistent_cert_path(self):
        user_cert_dir = os.path.join(
            os.path.expanduser("~"),
            ".stockvolume",
            "cert",
        )
        os.makedirs(user_cert_dir, exist_ok=True)

        cert_file = os.path.join(user_cert_dir, "cacert.pem")
        if not os.path.exists(cert_file):
            try:
                shutil.copy2(certifi.where(), cert_file)
            except Exception:
                return certifi.where()
        return cert_file

    def _get_proxy(self) -> dict[str, str]:
        response = requests.get(
            self.proxy_config["url"],
            timeout=20,
            verify=self.cert_path,
        )
        response.raise_for_status()
        payload = response.json()
        proxy_data = payload.get("data") or []
        if not proxy_data:
            raise ValueError(f"代理池返回为空: {payload}")

        server = proxy_data[0]["server"]
        proxy_url = "http://%(user)s:%(password)s@%(server)s" % {
            "user": self.proxy_config["base_username"],
            "password": self.proxy_config["password"],
            "server": server,
        }
        return {
            "http": proxy_url,
            "https": proxy_url,
        }

    def update_proxy(self):
        with self.lock:
            self.proxy = self._get_proxy()
            self.proxy_size = 0
            self.proxy_time = time.time()
            if self.logger:
                self.logger.info("更新代理: %s", self._redact_proxy(self.proxy))

    def invalidate_proxy(self):
        with self.lock:
            self.proxy = {}
            self.proxy_size = 0
            self.proxy_time = 0

    def get_best_proxy(
        self,
        force_refresh: bool = False,
    ) -> dict[str, str] | dict[Any, Any]:
        with self.lock:
            should_refresh = (
                force_refresh
                or not self.proxy
                or self.proxy_size >= self.max_proxy_size
                or (time.time() - self.proxy_time) > 30
            )
            if should_refresh:
                self.proxy = self._get_proxy()
                self.proxy_time = time.time()
                self.proxy_size = 0
                if self.logger:
                    self.logger.info("获取新代理: %s", self._redact_proxy(self.proxy))
                return self.proxy

            self.proxy_size += 1
            return self.proxy


_proxy_manager = None
_proxy_manager_lock = threading.Lock()


def get_smart_proxy_manager(logger=None) -> SmartProxyManager:
    global _proxy_manager
    with _proxy_manager_lock:
        if _proxy_manager is None:
            _proxy_manager = SmartProxyManager(logger=logger)
        elif logger is not None and _proxy_manager.logger is None:
            _proxy_manager.logger = logger
        return _proxy_manager

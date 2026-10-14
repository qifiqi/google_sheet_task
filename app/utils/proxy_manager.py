import threading
import time
from typing import Any

from app.remote_api import stock_api


class SmartProxyManager:
    """Manage a short-lived proxy pool for DFCF requests."""

    def __init__(self, logger=None):
        self.lock = threading.Lock()
        self.proxy_size = 0
        self.logger = logger
        self.max_proxy_size = 50
        self.proxy = {}
        self.proxy_time = time.time()

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

    def _get_proxy(self) -> dict[str, str]:
        # 主站调用统一出口（app/remote_api）：代理获取走 stock_dic 控制器，
        # 返回值已是统一信封解包后的 ret_obj。
        proxy = stock_api.stock_dic.get_proxy_list_by_one()
        proxy_url = "http://%(username)s:%(password)s@%(url)s:%(port)s" % {
            "username": proxy["username"],
            "password": proxy["password"],
            "url": proxy["url"],
            "port": proxy["port"],
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

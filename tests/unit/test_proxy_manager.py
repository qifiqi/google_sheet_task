import app.remote_api as remote_api_module
from app.utils.proxy_manager import SmartProxyManager


def test_proxy_manager_fetches_proxy_via_remote_api(monkeypatch):
    recorded = {}

    class FakeStockDicApi:
        def get_proxy_list_by_one(self, payload=None):
            recorded["payload"] = payload
            return {
                "username": "user",
                "password": "password",
                "url": "127.0.0.1",
                "port": 8080,
            }

    monkeypatch.setattr(
        remote_api_module.stock_api,
        "stock_dic",
        FakeStockDicApi(),
    )

    assert SmartProxyManager()._get_proxy() == {
        "http": "http://user:password@127.0.0.1:8080",
        "https": "http://user:password@127.0.0.1:8080",
    }
    assert recorded["payload"] is None

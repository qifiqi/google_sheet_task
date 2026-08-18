from app.utils.proxy_manager import SmartProxyManager
import app.utils.proxy_manager as proxy_manager


def test_proxy_manager_uses_stockapi_proxy_endpoint(monkeypatch):
    request_args = {}

    class Response:
        def raise_for_status(self):
            pass

        def json(self):
            return {
                "ret_obj": {
                    "username": "user",
                    "password": "password",
                    "url": "127.0.0.1",
                    "port": 8080,
                }
            }

    def post(url, **kwargs):
        request_args["url"] = url
        request_args.update(kwargs)
        return Response()

    monkeypatch.setattr(proxy_manager.requests, "post", post)

    assert SmartProxyManager()._get_proxy() == {
        "http": "http://user:password@127.0.0.1:8080",
        "https": "http://user:password@127.0.0.1:8080",
    }
    assert request_args == {
        "url": "http://stockapi.stplan.cn/api/StockDic/GetProxyListByOne",
        "headers": {"accept": "text/plain"},
        "data": "",
        "timeout": 20,
    }

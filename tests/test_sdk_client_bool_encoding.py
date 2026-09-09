"""SDK 出站载荷布尔编码回归测试。

远端数据服务的布尔字段以 0/1 整型承载，JSON ``true``/``false`` 会在远端
模型绑定阶段解析失败（HTTP 400）。此处验证 ``StockSdkAdapter.call`` 在
唯一出站出口统一完成布尔到 0/1 的编码。
"""

from app.repositories.sdk_client import StockSdkAdapter


class _CaptureClient:
    """记录实际请求体并返回成功信封的假客户端。"""

    def __init__(self):
        self.bodies = []

    def request(self, method, path, body):
        self.bodies.append(body)
        return {"ret_code": 200, "ret_msg": "ok", "ret_obj": None}


def _adapter_with_capture():
    adapter = StockSdkAdapter()
    client = _CaptureClient()
    adapter._clients = {None: client}
    return adapter, client


def test_call_encodes_boolean_fields_to_integers():
    adapter, client = _adapter_with_capture()
    adapter.call(
        "param_google_sheet_tokens",
        "modify_or_add",
        {"name": "t", "is_active": True, "max_usage_count": 0},
    )
    assert client.bodies[0]["is_active"] == 1
    assert isinstance(client.bodies[0]["is_active"], int)


def test_call_encoding_is_recursive():
    adapter, client = _adapter_with_capture()
    adapter.call(
        "param_google_sheet_tokens",
        "modify_or_add",
        {
            "is_active": False,
            "nested": {"is_in_use": True, "items": [True, "true", 1]},
        },
    )
    body = client.bodies[0]
    assert body["is_active"] == 0
    assert body["nested"]["is_in_use"] == 1
    # 字符串 "true" 与数字 1 不受编码影响。
    assert body["nested"]["items"] == [1, "true", 1]


def test_encode_remote_body_keeps_non_bool_types():
    encoded = StockSdkAdapter._encode_remote_body(
        {"a": 0, "b": "true", "c": None, "d": [{"e": False}]}
    )
    assert encoded == {"a": 0, "b": "true", "c": None, "d": [{"e": 0}]}

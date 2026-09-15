"""远程调用器出站载荷布尔编码与具体接口函数分发回归测试。

远端数据服务的布尔字段以 0/1 整型承载，JSON ``true``/``false`` 会在远端
模型绑定阶段解析失败（HTTP 400）。此处验证布尔到 0/1 的编码在统一调用器
唯一出站出口（``StockApiClient.request`` → ``RemoteTransport``）完成，
各具体接口函数无需各自处理；同时验证控制器具体函数按端点准确分发。
"""

from app.remote_api import StockApiClient, encode_remote_body


class _CaptureTransport:
    """记录实际请求体并返回成功信封的假传输。"""

    def __init__(self):
        self.calls = []

    def request(self, method, path, body):
        self.calls.append((method, path, body))
        return {"ret_code": 200, "ret_msg": "ok", "ret_obj": None, "ret_count": 3}


def _client_with_capture():
    client = StockApiClient()
    transport = _CaptureTransport()
    client._transports = {None: transport}
    return client, transport


def test_request_encodes_boolean_fields_to_integers():
    client, transport = _client_with_capture()
    client.request(
        'POST',
        '/api/ParamGoogleSheetTokens/ModifyOrAdd',
        {"name": "t", "is_active": True, "max_usage_count": 0},
    )
    _, _, body = transport.calls[0]
    assert body["is_active"] == 1
    assert isinstance(body["is_active"], int)
    assert not isinstance(body["is_active"], bool)


def test_request_encoding_is_recursive():
    client, transport = _client_with_capture()
    client.request(
        'POST',
        '/api/ParamGoogleSheetTokens/ModifyOrAdd',
        {
            "is_active": False,
            "nested": {"is_in_use": True, "items": [True, "true", 1]},
        },
    )
    _, _, body = transport.calls[0]
    assert body["is_active"] == 0
    assert not isinstance(body["is_active"], bool)
    assert body["nested"]["is_in_use"] == 1
    # 字符串 "true" 与数字 1 不受编码影响。
    assert body["nested"]["items"] == [1, "true", 1]


def test_encode_remote_body_keeps_non_bool_types():
    encoded = encode_remote_body(
        {"a": 0, "b": "true", "c": None, "d": [{"e": False}]}
    )
    assert encoded == {"a": 0, "b": "true", "c": None, "d": [{"e": 0}]}


def test_concrete_endpoint_function_dispatches_method_and_path():
    """具体接口函数应把方法/路径/载荷原样交给统一调用器并解包信封。"""
    client, transport = _client_with_capture()
    raw, count = client.param_tasks.get_data_by_page_list({"page_index": 2})
    assert raw is None
    assert count == 3
    method, path, body = transport.calls[0]
    assert (method, path) == ('POST', '/api/ParamTasks/GetDataByPageList')
    assert body == {"page_index": 2}


def test_identity_endpoint_forwards_user_token_to_dedicated_transport():
    """身份接口把用户 Token 路由到独立传输（Token 请求头由传输层注入）。"""
    client = StockApiClient()
    service_transport = _CaptureTransport()
    user_transport = _CaptureTransport()
    client._transports = {None: service_transport, "user-token": user_transport}

    client.sys_user.get_user_info(token="user-token")

    assert service_transport.calls == []
    method, path, body = user_transport.calls[0]
    assert (method, path) == ('POST', '/api/SysUser/GetUserInfo')
    assert body == {}

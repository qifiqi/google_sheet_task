"""远程统一调用器的业务码 → 异常映射回归（含 409 唯一键冲突）。"""
import pytest

from app.remote_api.client import StockApiClient
from app.remote_api.exceptions import (
    RemoteApiDuplicateKeyError,
    RemoteApiNotFoundError,
)


class _FakeTransport:
    def __init__(self, envelope):
        self._envelope = envelope

    def request(self, method, path, payload, timeout=None):
        return dict(self._envelope)


def _client_with(envelope):
    client = StockApiClient()
    client._transport_for = lambda token: _FakeTransport(envelope)
    return client


def test_duplicate_key_code_maps_to_typed_exception():
    client = _client_with({"ret_code": 409, "ret_msg": "DUPLICATE_KEY"})

    with pytest.raises(RemoteApiDuplicateKeyError):
        client.request_with_count("POST", "/api/param_tasks/ModifyOrAdd", {})


def test_not_found_code_maps_to_typed_exception():
    client = _client_with({"ret_code": 404, "ret_msg": "not found"})

    with pytest.raises(RemoteApiNotFoundError):
        client.request_with_count("GET", "/api/param_tasks/GetInfoById", {})

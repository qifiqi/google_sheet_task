"""请求域用户 Token 透传与任务线程隔离回归（db-to-http 统一携带语义）。

主站所有接口都要携带 ``Token`` 请求头且按角色鉴权（param_* 业务接口实测
按角色 403）。契约：
- 请求线程内业务数据调用（token=None 的服务级签名）优先采用网关登记的
  请求域用户 Token，以实际用户身份过主站鉴权；
- 请求域外（任务 worker/调度器/启动钩子）回退服务级 STOCK_API_TOKEN；
- 任务 worker 经 facade 空上下文提交，不继承提交请求的 Token；
- 服务级调用 401 触发自动重登换新，请求域 401 不触发（用户须重新登录）。
"""

import ipaddress
import socket

import pytest

from app.remote_api import RemoteApiOperationError, StockApiClient
from app.remote_api.client import (
    _validate_remote_host,
    clear_request_user_token,
    get_request_user_token,
    set_request_user_token,
)
from app.remote_api.exceptions import RemoteApiConfigError
from app.services.task.facade import TaskManager


class _EnvelopeTransport:
    """按 path 脚本返回信封的假传输，记录全部请求。"""

    def __init__(self, script=None):
        self.calls = []
        self._script = script or {}

    def request(self, method, path, body, timeout=None):
        self.calls.append((method, path, body, timeout))
        action = self._script.get(path)
        if action is None:
            return {"ret_code": 200, "ret_msg": "ok", "ret_obj": {"ok": True}, "ret_count": 1}
        return action


@pytest.fixture(autouse=True)
def _clean_request_token():
    clear_request_user_token()
    yield
    clear_request_user_token()


def test_request_in_request_scope_uses_user_token_transport():
    client = StockApiClient()
    service_transport = _EnvelopeTransport()
    user_transport = _EnvelopeTransport()
    client._transports = {None: service_transport, "user-tok": user_transport}

    set_request_user_token("user-tok")
    client.param_tasks.get_data_by_page_list({"page_index": 1})

    # 业务调用路由到用户 Token 的独立传输，服务级传输未被触碰。
    assert service_transport.calls == []
    assert user_transport.calls[0][1] == "/api/ParamTasks/GetDataByPageList"


def test_request_outside_request_scope_falls_back_to_service_transport():
    client = StockApiClient()
    service_transport = _EnvelopeTransport()
    user_transport = _EnvelopeTransport()
    client._transports = {None: service_transport, "user-tok": user_transport}

    assert get_request_user_token() == ""
    client.param_tasks.get_data_by_page_list({"page_index": 1})

    assert user_transport.calls == []
    assert service_transport.calls[0][1] == "/api/ParamTasks/GetDataByPageList"


def test_clear_request_user_token_reverts_to_service_transport():
    client = StockApiClient()
    service_transport = _EnvelopeTransport()
    client._transports = {None: service_transport}

    set_request_user_token("user-tok")
    clear_request_user_token()
    client.param_tasks.get_data_by_page_list({})

    assert service_transport.calls and service_transport.calls[0][1].endswith("GetDataByPageList")


def test_explicit_token_wins_over_request_scope(monkeypatch):
    client = StockApiClient()
    explicit_transport = _EnvelopeTransport()
    scoped_transport = _EnvelopeTransport()
    client._transports = {"explicit-tok": explicit_transport, "scoped-tok": scoped_transport}

    set_request_user_token("scoped-tok")
    client.sys_user.get_user_info(token="explicit-tok")

    assert scoped_transport.calls == []
    assert explicit_transport.calls[0][1] == "/api/SysUser/GetUserInfo"


def test_request_scope_401_does_not_trigger_service_relogin(monkeypatch):
    """请求域用户 Token 失效必须原样 401 抛出，不得拿服务级凭据静默换新。"""
    monkeypatch.setenv("STOCK_API_USERNAME", "svc-user")
    monkeypatch.setenv("STOCK_API_PASSWORD", "svc-pass")
    client = StockApiClient()
    service_transport = _EnvelopeTransport(
        {"/api/SysUser/Login": {"ret_code": 200, "ret_msg": "ok",
                                "ret_obj": {"token": "fresh"}, "ret_count": 0}}
    )
    user_transport = _EnvelopeTransport(
        {"/api/ParamTasks/GetDataByPageList": {"ret_code": 401, "ret_msg": "登录已失效",
                                               "ret_obj": None, "ret_count": 0}}
    )
    client._transports = {None: service_transport, "user-tok": user_transport}

    set_request_user_token("user-tok")
    with pytest.raises(RemoteApiOperationError):
        client.param_tasks.get_data_by_page_list({})

    # 服务级传输（含登录端点）全程未被触碰。
    assert service_transport.calls == []
    assert len(user_transport.calls) == 1


def test_service_scope_401_still_triggers_relogin(monkeypatch):
    """无请求域 Token 时保持原契约：服务级 401 → 自动重登换新并重试成功。"""
    monkeypatch.setenv("STOCK_API_USERNAME", "svc-user")
    monkeypatch.setenv("STOCK_API_PASSWORD", "svc-pass")
    client = StockApiClient()
    service_transport = _EnvelopeTransport(
        {
            "/api/ParamTasks/GetDataByPageList": {"ret_code": 401, "ret_msg": "登录已失效",
                                                  "ret_obj": None, "ret_count": 0},
            "/api/SysUser/Login": {"ret_code": 200, "ret_msg": "ok",
                                   "ret_obj": {"token": "fresh"}, "ret_count": 0},
        }
    )
    fresh_transport = _EnvelopeTransport()
    client._transports = {None: service_transport}
    monkeypatch.setattr(
        StockApiClient, "_build_transport", classmethod(lambda cls, token=None: fresh_transport)
    )

    raw, count = client.param_tasks.get_data_by_page_list({})

    assert raw == {"ok": True}
    assert fresh_transport.calls and fresh_transport.calls[0][1] == "/api/ParamTasks/GetDataByPageList"
    assert client._transports[None] is fresh_transport


def _addr_entry(address):
    return (socket.AF_INET, socket.SOCK_STREAM, 0, "", (address, 0))


@pytest.mark.parametrize(
    "address",
    ["127.0.0.1", "10.1.2.3", "192.168.0.9", "172.16.5.5", "169.254.3.4", "::1", "0.0.0.0"],
)
def test_validate_remote_host_rejects_restricted_addresses(monkeypatch, address):
    monkeypatch.setattr(
        socket, "getaddrinfo", lambda host, port: [_addr_entry(str(address))]
    )
    with pytest.raises(RemoteApiConfigError):
        _validate_remote_host("https://stockapi.example.com")


def test_validate_remote_host_allow_private_optin(monkeypatch):
    """内网部署显式放行：STOCK_BASE_URL_ALLOW_PRIVATE=true 时私网地址可用。"""
    monkeypatch.setattr(
        socket, "getaddrinfo", lambda host, port: [_addr_entry("172.18.20.20")]
    )
    # 默认仍拒绝。
    with pytest.raises(RemoteApiConfigError):
        _validate_remote_host("https://stockapi.example.com")
    _validate_remote_host("https://stockapi.example.com", allow_private=True)


def test_validate_remote_host_accepts_public_address(monkeypatch):
    public_ip = str(ipaddress.ip_address("93.184.216.34"))
    monkeypatch.setattr(socket, "getaddrinfo", lambda host, port: [_addr_entry(public_ip)])
    _validate_remote_host("https://stockapi.jaspil.cn")


def test_validate_remote_host_unresolvable_raises(monkeypatch):
    def _raise(host, port):
        raise socket.gaierror("name resolution failure")

    monkeypatch.setattr(socket, "getaddrinfo", _raise)
    with pytest.raises(RemoteApiConfigError):
        _validate_remote_host("https://nonexistent.invalid")


def test_facade_submits_task_worker_in_empty_context():
    """任务 worker 不继承提交线程的请求域 Token（统一回退服务级凭据）。"""
    set_request_user_token("leaky-token")
    manager = TaskManager()
    observed = {}

    def _runner(task_id, app):
        observed["token"] = get_request_user_token()

    handle = manager.submit_task_execution("t-token-scope", None, _runner)
    handle.join(timeout=10)

    assert observed == {"token": ""}

    # 提交线程自身不受影响（后续请求域语义保持）。
    assert get_request_user_token() == "leaky-token"


def test_facade_task_exception_propagates_to_future():
    """空上下文包装不吞异常：任务失败仍可经 Future 观测（join 保持 Thread 兼容不抛）。"""
    manager = TaskManager()

    def _runner(task_id, app):
        raise RuntimeError("boom")

    handle = manager.submit_task_execution("t-token-boom", None, _runner)
    handle.join(timeout=10)

    assert isinstance(handle.future.exception(), RuntimeError)


def test_request_scope_helpers_roundtrip():
    assert get_request_user_token() == ""
    set_request_user_token("  tok-1  ")
    assert get_request_user_token() == "tok-1"
    set_request_user_token("")
    assert get_request_user_token() == ""
    clear_request_user_token()
    assert get_request_user_token() == ""

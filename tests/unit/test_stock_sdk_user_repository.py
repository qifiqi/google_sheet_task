"""stock_sdk 用户信息仓储：GetUserInfo 外部 Token 校验。"""

from stock_sdk import ResponseDto

from app.repositories.stock_sdk import user_repository


class _FakeSysUser:
    def __init__(self, response):
        self._response = response

    def get_user_info(self):
        return self._response


class _FakeStockClient:
    response = None
    last_kwargs = None

    def __init__(self, *, token=None, base_url=None, timeout=10.0, session=None):
        type(self).last_kwargs = {'token': token, 'base_url': base_url, 'timeout': timeout}
        self.sys_user = _FakeSysUser(type(self).response)
        self.closed = False

    def close(self):
        self.closed = True


def _install(monkeypatch, response):
    _FakeStockClient.response = response
    monkeypatch.setattr(user_repository, 'StockClient', _FakeStockClient)


def test_get_user_info_returns_identity_and_passes_token(monkeypatch):
    _install(monkeypatch, ResponseDto(ret_code=200, ret_obj={'username': 'fuqing', 'userid': '280566'}))

    identity = user_repository.get_user_info('tok', base_url='http://127.0.0.1:7070', timeout=3)

    assert identity == {'username': 'fuqing', 'userid': '280566'}
    assert _FakeStockClient.last_kwargs == {
        'token': 'tok',
        'base_url': 'http://127.0.0.1:7070',
        'timeout': 3,
    }


def test_get_user_info_returns_none_on_business_failure(monkeypatch):
    _install(monkeypatch, ResponseDto(ret_code=401, ret_msg='token invalid'))

    assert user_repository.get_user_info('tok', base_url='http://127.0.0.1:7070') is None


def test_get_user_info_returns_none_without_username(monkeypatch):
    _install(monkeypatch, ResponseDto(ret_code=200, ret_obj={'userid': '280566'}))

    assert user_repository.get_user_info('tok', base_url='http://127.0.0.1:7070') is None

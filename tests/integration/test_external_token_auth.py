"""外部 Token 鉴权：Token 头非本站 JWT 时回落 stock_sdk GetUserInfo。"""

from flask import g

from app.extensions import db
from app.models import User
from app.utils import auth as auth_module
from app.utils.auth import create_access_token


def _create_user(app, username='local-user'):
    with app.app_context():
        user = User(username=username, password_hash='x', is_active=True)
        db.session.add(user)
        db.session.commit()
        return user.id


def _register_protected_route(app):
    if '/__test_external_token' in {rule.rule for rule in app.url_map.iter_rules()}:
        return

    @app.route('/__test_external_token')
    @auth_module.login_required
    def _protected():
        return {'username': g.current_user.username, 'id': g.current_user.id}


def test_token_header_accepts_local_jwt(app_factory):
    app = app_factory
    _register_protected_route(app)
    user_id = _create_user(app)

    resp = app.test_client().get(
        '/__test_external_token',
        headers={'Token': create_access_token(user_id)},
    )

    assert resp.status_code == 200
    assert resp.get_json()['id'] == user_id


def test_token_header_falls_back_to_get_user_info(app_factory, monkeypatch):
    app = app_factory
    _register_protected_route(app)
    calls = []

    def fake_get_user_info(token, *, base_url, timeout=5.0):
        calls.append((token, base_url))
        return {'username': 'ext-user', 'userid': '280566'}

    monkeypatch.setattr(auth_module, 'get_user_info', fake_get_user_info)

    resp = app.test_client().get(
        '/__test_external_token',
        headers={'Token': 'external-token'},
    )

    assert resp.status_code == 200
    body = resp.get_json()
    assert body == {'username': 'ext-user', 'id': None}
    assert calls == [('external-token', app.config['STOCK_AUTH_BASE_URL'])]


def test_token_header_rejected_when_external_check_fails(app_factory, monkeypatch):
    app = app_factory
    _register_protected_route(app)
    monkeypatch.setattr(auth_module, 'get_user_info', lambda token, **_kwargs: None)

    resp = app.test_client().get(
        '/__test_external_token',
        headers={'Token': 'bad-token'},
    )

    assert resp.status_code == 401


def test_token_header_denied_when_external_check_raises(app_factory, monkeypatch):
    app = app_factory
    _register_protected_route(app)

    def boom(token, **_kwargs):
        raise RuntimeError('network down')

    monkeypatch.setattr(auth_module, 'get_user_info', boom)

    resp = app.test_client().get(
        '/__test_external_token',
        headers={'Token': 'bad-token'},
    )

    assert resp.status_code == 401


def test_no_token_returns_401(app_factory):
    app = app_factory
    _register_protected_route(app)

    assert app.test_client().get('/__test_external_token').status_code == 401


def test_invalid_bearer_does_not_fall_back_to_token_header(app_factory, monkeypatch):
    app = app_factory
    _register_protected_route(app)
    called = []
    monkeypatch.setattr(
        auth_module,
        'get_user_info',
        lambda token, **_kwargs: called.append(token),
    )

    resp = app.test_client().get(
        '/__test_external_token',
        headers={'Authorization': 'Bearer not-a-local-jwt', 'Token': 'external-token'},
    )

    assert resp.status_code == 401
    assert called == []


def test_missing_stock_auth_base_url_skips_external_check(app_factory, monkeypatch):
    app = app_factory
    app.config['STOCK_AUTH_BASE_URL'] = ''
    _register_protected_route(app)
    called = []
    monkeypatch.setattr(
        auth_module,
        'get_user_info',
        lambda token, **_kwargs: called.append(token),
    )

    resp = app.test_client().get(
        '/__test_external_token',
        headers={'Token': 'external-token'},
    )

    assert resp.status_code == 401
    assert called == []

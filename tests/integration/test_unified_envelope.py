"""统一响应信封 / 全局错误处理器 / 请求校验行为测试（docs/design/data-layer-refactor/04）。

B0 验收口径：自 B0 起全库仅一种响应格式；
AppException → 全局处理器 → API 路径 JSON 信封，页面路由保持 Flask 默认。
"""
import pytest

from app.exceptions import NotFoundError, ValidationError
from app.utils.request_validation import require_query, validate_body


@pytest.fixture()
def client(app_factory):
    return app_factory.test_client()


class TestUnifiedEnvelope:
    def test_meta_versions_success_envelope(self, client):
        resp = client.get("/api/meta/versions")
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["status"] == "success"
        assert body["code"] == 0
        assert body["message"] == ""
        assert isinstance(body["data"], list) and body["data"]

    def test_login_error_envelope_code_equals_http_status(self, client):
        resp = client.post("/api/auth/login", json={})
        assert resp.status_code == 400
        body = resp.get_json()
        assert body["status"] == "error"
        assert body["code"] == 400
        assert body["message"] == "用户名和密码不能为空"
        assert body["data"] is None

    def test_app_exception_becomes_envelope_on_api_path(self, app_factory, client):
        app = app_factory

        @app.route("/api/_test/not-found")
        def _not_found():
            raise NotFoundError("资源不存在")

        resp = client.get("/api/_test/not-found")
        assert resp.status_code == 404
        body = resp.get_json()
        assert body == {
            "status": "error",
            "code": 404,
            "message": "资源不存在",
            "data": None,
        }

    def test_http_exception_envelope_on_api_path(self, client):
        resp = client.get("/api/_definitely/missing")
        assert resp.status_code == 404
        body = resp.get_json()
        assert body["status"] == "error"
        assert body["code"] == 404

    def test_page_route_keeps_flask_default_html(self, client):
        resp = client.get("/admin/_definitely/missing")
        assert resp.status_code == 404
        assert resp.content_type.startswith("text/html")

    def test_unexpected_exception_maps_to_500_without_leaking(self, app_factory, client):
        app = app_factory

        @app.route("/api/_test/boom")
        def _boom():
            raise RuntimeError("secret sqlalchemy detail")

        resp = client.get("/api/_test/boom")
        assert resp.status_code == 500
        body = resp.get_json()
        assert body["status"] == "error"
        assert body["code"] == 500
        assert "secret" not in body["message"]


class TestRequestValidation:
    def test_validate_body_required_missing(self, app_factory):
        app = app_factory
        with app.test_request_context("/", json={"name": ""}):
            with pytest.raises(ValidationError) as exc:
                validate_body(required=["name"])
            assert "name" in exc.value.message

    def test_validate_body_type_mismatch(self, app_factory):
        app = app_factory
        with app.test_request_context("/", json={"page": "not-int"}):
            with pytest.raises(ValidationError):
                validate_body(types={"page": int})

    def test_validate_body_bool_is_not_int(self, app_factory):
        app = app_factory
        with app.test_request_context("/", json={"page": True}):
            with pytest.raises(ValidationError):
                validate_body(types={"page": int})

    def test_validate_body_ok_returns_data(self, app_factory):
        app = app_factory
        with app.test_request_context("/", json={"name": "x", "page": 2}):
            data = validate_body(required=["name"], types={"page": int})
            assert data == {"name": "x", "page": 2}

    def test_require_query_cast_and_default(self, app_factory):
        app = app_factory
        with app.test_request_context("/?page=3&bad=xx"):
            assert require_query("page", default=1, cast=int) == 3
            assert require_query("missing", default=7) == 7
            with pytest.raises(ValidationError):
                require_query("bad", default=1, cast=int)

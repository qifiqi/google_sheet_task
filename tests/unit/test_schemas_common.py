"""通用 Schema 与请求解析入口测试（docs/design/api-model-query-audit/05 §2.4）。

四类用例基线：合法 / 缺字段 / 类型错 / 越界。
"""

import pytest
from pydantic import ValidationError as PydValidationError

from app.exceptions import ValidationError
from app.schemas.auth import ChangePasswordSchema, CreateUserSchema, CreateRoleSchema
from app.schemas.common import PageQuery
from app.schemas.template import TemplateCreateSchema
from app.utils.request_parsing import parse_body, parse_query


class TestPageQuery:
    def test_defaults(self):
        q = PageQuery()
        assert q.page == 1 and q.per_page == 20

    def test_valid(self):
        q = PageQuery(page=3, per_page=50)
        assert (q.page, q.per_page) == (3, 50)

    def test_page_below_min_rejected(self):
        with pytest.raises(PydValidationError):
            PageQuery(page=0)

    def test_per_page_over_max_rejected(self):
        with pytest.raises(PydValidationError):
            PageQuery(per_page=101)


class TestAuthSchemas:
    def test_change_password_valid(self):
        s = ChangePasswordSchema(old_password="a", new_password="b")
        assert s.old_password == "a"

    def test_change_password_missing_rejected(self):
        with pytest.raises(PydValidationError):
            ChangePasswordSchema(old_password="a")

    def test_change_password_empty_string_rejected(self):
        # 对齐 request_validation "空串视为缺失" 语义
        with pytest.raises(PydValidationError):
            ChangePasswordSchema(old_password="a", new_password="")

    def test_create_user_defaults(self):
        s = CreateUserSchema(username="alice", password="pw")
        assert s.is_active is True and s.role_ids == []

    def test_create_user_wrong_type_rejected(self):
        with pytest.raises(PydValidationError):
            CreateUserSchema(username="alice", password="pw", role_ids="not-a-list")

    def test_create_role_valid(self):
        s = CreateRoleSchema(name="R", code="r1")
        assert s.description == ""


class TestTemplateSchema:
    def test_config_accepts_dict(self):
        s = TemplateCreateSchema(name="t", config={"task_type": "google_sheet"})
        assert s.config["task_type"] == "google_sheet"

    def test_config_accepts_json_string(self):
        s = TemplateCreateSchema(name="t", config='{"task_type": "google_sheet"}')
        assert isinstance(s.config, str)

    def test_config_missing_rejected(self):
        with pytest.raises(PydValidationError):
            TemplateCreateSchema(name="t")

    def test_extra_fields_ignored(self):
        s = TemplateCreateSchema(name="t", config={}, unknown_key="x")
        assert not hasattr(s, "unknown_key")


class TestParseBodyAndQuery:
    def test_parse_body_validates_and_strips(self, app_factory):
        app = app_factory
        with app.test_request_context("/", json={"name": "  x  ", "config": {}}):
            data = parse_body(TemplateCreateSchema)
            assert data.name == "x"

    def test_parse_body_missing_field_raises_app_validation_error(self, app_factory):
        app = app_factory
        with app.test_request_context("/", json={}):
            with pytest.raises(ValidationError):
                parse_body(TemplateCreateSchema)

    def test_parse_query_applies_page_query(self, app_factory):
        app = app_factory
        with app.test_request_context("/?page=2&per_page=50"):
            q = parse_query(PageQuery)
            assert (q.page, q.per_page) == (2, 50)

    def test_parse_query_out_of_range_raises(self, app_factory):
        app = app_factory
        with app.test_request_context("/?per_page=999"):
            with pytest.raises(ValidationError):
                parse_query(PageQuery)

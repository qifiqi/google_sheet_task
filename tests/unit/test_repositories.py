"""repository 层单元测试（内存 SQLite + app context）。

覆盖 docs/design/data-layer-refactor/02 各 repository 契约的基础读写与异常路径；
测试代码不受"业务层禁 ORM"约束（02 §4）。
"""
import pytest

from app.exceptions import NotFoundError
from app.extensions import db
from app.models import (
    BacktestSheetRunLock,
    NavigationMenuItem,
    Role,
    StockMetadata,
    SystemConfig,
    Task,
    TaskLog,
    TaskResult,
    TaskResultReturn,
    TaskTemplate,
    User,
)
from app.repositories import (
    backtest_repository,
    google_sheet_repository,
    google_sheet_token_repository,
    navigation_repository,
    rbac_repository,
    scheduled_task_repository,
    stock_metadata_repository,
    system_config_repository,
    task_log_repository,
    task_repository,
    task_result_repository,
    task_template_repository,
)


@pytest.fixture()
def task_row(app_factory):
    task = Task(id="t-1", name="示例任务", status="pending", task_type="google_sheet")
    db.session.add(task)
    db.session.commit()
    return task


# ==================== task_repository ====================


class TestTaskRepository:
    def test_create_and_get_roundtrip(self, app_factory, task_row):
        data = task_repository.get("t-1")
        assert data["id"] == "t-1"
        assert data["config"] == {}
        assert task_repository.get("missing") is None

    def test_get_required_raises(self, app_factory):
        with pytest.raises(NotFoundError):
            task_repository.get_required("missing")

    def test_update_fields_commit_and_missing(self, app_factory, task_row):
        updated = task_repository.update_fields("t-1", status="running", current_step=2)
        assert updated["status"] == "running"
        assert task_repository.update_fields("missing", status="running") is None

    def test_summary_counts_and_recent(self, app_factory, task_row):
        task_repository.create({"id": "t-2", "name": "完成", "status": "completed"})
        counts = task_repository.summary_counts()
        assert counts == {"total": 2, "completed": 1, "running": 0, "error": 0}
        assert [t["id"] for t in task_repository.recent(limit=1)] == ["t-2"]

    def test_distinct_task_types_and_list_by_ids(self, app_factory, task_row):
        assert task_repository.distinct_task_types() == ["google_sheet"]
        assert [t["id"] for t in task_repository.list_by_ids(["t-1", "missing"])] == ["t-1"]
        assert task_repository.list_by_ids([]) == []

    def test_list_paginated_filters(self, app_factory, task_row):
        task_repository.create({"id": "t-2", "name": "other", "status": "error", "task_type": "google_sheet_C4"})
        page = task_repository.list_paginated(1, 10, task_type="google_sheet")
        assert page["total"] == 1 and page["items"][0]["id"] == "t-1"
        page = task_repository.list_paginated(1, 10, status="error")
        assert page["items"][0]["id"] == "t-2"
        page = task_repository.list_paginated(1, 10, keyword="示例")
        assert page["items"][0]["id"] == "t-1"

    def test_clear_created_by(self, app_factory, task_row):
        Task.query.filter_by(id="t-1").update({"created_by_user_id": 7})
        db.session.commit()
        assert task_repository.clear_created_by(7, commit=True) == 1
        assert db.session.get(Task, "t-1").created_by_user_id is None

    def test_delete(self, app_factory, task_row):
        assert task_repository.delete("missing") is False
        assert task_repository.delete("t-1") is True
        assert task_repository.get("t-1") is None

    def test_transaction_context_rolls_back(self, app_factory, task_row):
        with pytest.raises(RuntimeError):
            with task_repository.transaction():
                task_repository.update_fields("t-1", name="changed", commit=False)
                raise RuntimeError("boom")
        assert task_repository.get("t-1")["name"] == "示例任务"


# ==================== task_result_repository ====================


class TestTaskResultRepository:
    def _make_result(self, task_id="t-1", success=True):
        return task_result_repository.create(
            {"task_id": task_id, "step_index": 1, "success": success, "parameters": "{}", "result": "{}"}
        )

    def test_create_and_get_with_task_type(self, app_factory, task_row):
        created = self._make_result()
        fetched = task_result_repository.get_with_task_type(created["id"])
        assert fetched["task_type"] == "google_sheet"
        assert fetched["parameters"] == {}
        assert task_result_repository.get_with_task_type(9999) is None

    def test_count_by_task_success(self, app_factory, task_row):
        self._make_result(success=True)
        self._make_result(success=False)
        counts = task_result_repository.count_by_task_success("t-1")
        assert counts == {"total_success": 1, "total_failed": 1}

    def test_list_paginated_slim_keys(self, app_factory, task_row):
        self._make_result()
        page = task_result_repository.list_paginated(1, 20, task_id="t-1")
        assert page["total"] == 1
        item = page["results"][0]
        assert set(item.keys()) == {"id", "task_id", "step_index", "success", "timestamp"}

    def test_list_paginated_missing_task_empty(self, app_factory, task_row):
        page = task_result_repository.list_paginated(1, 20, task_id="missing")
        assert page == {"results": [], "total": 0, "pages": 0, "current_page": 1}

    def test_returns_crud_and_delete_older_than(self, app_factory, task_row):
        created = self._make_result()
        task_result_repository.create_return(
            {"task_id": "t-1", "stock_code": "sh600000", "stock_name": "x", "return_length": 2}
        )
        assert task_result_repository.get_returns(created["id"]) == []
        assert [r["task_id"] for r in task_result_repository.get_returns_by_task("t-1")] == ["t-1"]

        from datetime import datetime, timedelta

        future = datetime.now() + timedelta(days=1)
        assert task_result_repository.delete_older_than(future) >= 1
        assert task_result_repository.get(created["id"]) is None

    def test_bulk_create(self, app_factory, task_row):
        count = task_result_repository.bulk_create(
            [
                {"task_id": "t-1", "step_index": 1},
                {"task_id": "t-1", "step_index": 2},
            ]
        )
        assert count == 2
        assert task_result_repository.count_by_task_success("t-1")["total_success"] == 2


# ==================== task_log_repository ====================


class TestTaskLogRepository:
    def test_add_normalizes_message(self, app_factory, task_row):
        log = task_log_repository.add("t-1", "info", "x" * 5000)
        assert len(log["message"]) == 4000
        assert log["message"].endswith("...（日志已截断）")

    def test_get_last_and_list_by_task_order(self, app_factory, task_row):
        task_log_repository.add("t-1", "info", "first")
        task_log_repository.add("t-1", "error", "second")
        assert task_log_repository.get_last("t-1")["message"] == "second"
        rows = task_log_repository.list_by_task("t-1")
        assert [r["message"] for r in rows] == ["first", "second"]
        assert task_log_repository.count_by_task("t-1") == 2

    def test_delete_by_task(self, app_factory, task_row):
        task_log_repository.add("t-1", "info", "log")
        assert task_log_repository.delete_by_task("t-1") == 1
        assert task_log_repository.count_by_task("t-1") == 0


# ==================== task_template_repository ====================


class TestTaskTemplateRepository:
    def test_create_list_filter_update_delete(self, app_factory):
        import json

        created = task_template_repository.create(
            name="tpl", description="d", config_str=json.dumps({"task_type": "google_sheet"})
        )
        task_template_repository.create(
            name="tpl2", description="d", config_str=json.dumps({"task_type": "google_sheet_C4"})
        )
        assert len(task_template_repository.list_all()) == 2
        assert [t["name"] for t in task_template_repository.list_all(task_type="google_sheet")] == ["tpl"]

        updated = task_template_repository.update(created["id"], {"name": "renamed"})
        assert updated["name"] == "renamed"
        assert task_template_repository.update(9999, {"name": "x"}) is None

        with pytest.raises(NotFoundError):
            task_template_repository.get_required(9999)

        assert task_template_repository.delete(created["id"]) is True
        assert task_template_repository.delete(created["id"]) is False


# ==================== system_config_repository ====================


class TestSystemConfigRepository:
    def test_get_row_keeps_raw_value(self, app_factory):
        db.session.add(SystemConfig(key="raw_key", value="True", description="d"))
        db.session.commit()
        row = system_config_repository.get_row("raw_key")
        assert row["value"] == "True"  # 保持入库原样字符串，解析留给 config_manager
        assert system_config_repository.get_row("missing") is None

    def test_upsert_and_delete(self, app_factory):
        system_config_repository.upsert("k", "v1", description="d1")
        system_config_repository.upsert("k", "v2")
        row = system_config_repository.get_row("k")
        assert row["value"] == "v2" and row["description"] == "d1"
        assert [{"key": "k", "description": "d1"}] == system_config_repository.list_key_descriptions()
        assert system_config_repository.delete("k") is True
        assert system_config_repository.delete("k") is False

    def test_list_rows_ordered(self, app_factory):
        db.session.add(SystemConfig(key="b", value="2"))
        db.session.add(SystemConfig(key="a", value="1"))
        db.session.commit()
        assert [r["key"] for r in system_config_repository.list_rows()] == ["a", "b"]


# ==================== navigation_repository ====================


class TestNavigationRepository:
    def test_create_flush_get_key(self, app_factory):
        created = navigation_repository.create({"key": "home", "label": "首页", "sort_order": 1})
        assert created["id"] is not None
        assert navigation_repository.get_by_key("home")["id"] == created["id"]
        assert navigation_repository.exists_key("home") is True
        assert navigation_repository.exists_key("nope") is False

    def test_count_children_update_delete(self, app_factory):
        parent = navigation_repository.create({"key": "p", "label": "P"})
        navigation_repository.create({"key": "c", "label": "C", "parent_key": "p"})
        assert navigation_repository.count_children("p") == 1
        updated = navigation_repository.update(parent["id"], {"label": "P2"})
        assert updated["label"] == "P2"
        assert navigation_repository.delete(parent["id"]) is True

    def test_list_visible(self, app_factory):
        navigation_repository.create({"key": "vis", "label": "V", "is_visible": True})
        navigation_repository.create({"key": "hid", "label": "H", "is_visible": False})
        keys = [item["key"] for item in navigation_repository.list_visible()]
        assert keys == ["vis"]


# ==================== rbac_repository ====================


class TestRbacRepository:
    def test_user_crud_with_roles(self, app_factory):
        role = rbac_repository.create_role(code="dev", name="开发者")
        user = rbac_repository.create_user(
            "alice", "hash", role_ids=[role["id"]], is_active=True
        )
        assert [r["code"] for r in user["roles"]] == ["dev"]
        assert rbac_repository.username_exists("alice") is True

        updated = rbac_repository.update_user(user["id"], {"mobile": "123"}, role_ids=[])
        assert updated["mobile"] == "123" and updated["roles"] == []
        assert rbac_repository.delete_user(user["id"]) is True
        assert rbac_repository.get_user(user["id"]) is None

    def test_get_user_credentials(self, app_factory):
        rbac_repository.create_user("bob", "hash123", is_active=False)
        creds = rbac_repository.get_user_credentials("bob")
        assert creds["password_hash"] == "hash123"
        assert "mobile" not in creds
        assert rbac_repository.get_user_credentials("nobody") is None

    def test_delete_role_clears_join_tables(self, app_factory):
        from app.models import Permission

        perm = Permission(name="p", code="page:x", group="page")
        db.session.add(perm)
        db.session.commit()
        role = rbac_repository.create_role(code="r1", name="R", permission_ids=[perm.id])
        user = rbac_repository.create_user("carl", "hash", role_ids=[role["id"]])

        assert rbac_repository.delete_role(role["id"]) is True
        db.session.expire_all()
        assert db.session.get(User, user["id"]) is not None  # 用户仍在
        assert db.session.get(Role, role["id"]) is None

    def test_role_code_exists_and_list_permissions_order(self, app_factory):
        from app.models import Permission

        db.session.add(Permission(name="b", code="z", group="page"))
        db.session.add(Permission(name="a", code="a", group="admin"))
        db.session.commit()
        assert rbac_repository.role_code_exists("r-nope") is False
        codes = rbac_repository.list_permission_codes()
        assert set(codes) == {"z", "a"}
        grouped_first = rbac_repository.list_permissions()[0]
        assert grouped_first["group"] == "admin"


# ==================== google_sheet / token ====================


class TestGoogleSheetRepository:
    def test_create_list_filter_get_required(self, app_factory):
        google_sheet_repository.create(
            {"name": "s1", "spreadsheet_id": "ss1", "table_type": "c3", "registry_scope": "c_series"}
        )
        google_sheet_repository.create(
            {"name": "s2", "spreadsheet_id": "ss2", "table_type": "backtest_training", "registry_scope": "backtest_training"}
        )
        assert len(google_sheet_repository.list_all()) == 2
        assert len(google_sheet_repository.list_all(table_type="c3")) == 1
        with pytest.raises(NotFoundError):
            google_sheet_repository.get_required(9999)
        updated = google_sheet_repository.update(1, {"remark": "r"})
        assert updated["remark"] == "r"


class TestGoogleSheetTokenRepository:
    def test_create_list_include_context_bulk_import(self, app_factory):
        google_sheet_token_repository.create(
            {"name": "tok", "token_file": "data/t.json", "token_context": '{"a":1}'}
        )
        plain = google_sheet_token_repository.list_all(include_context=False)[0]
        assert "token_context" not in plain
        with_ctx = google_sheet_token_repository.list_all(include_context=True)[0]
        assert with_ctx["token_context"] == '{"a":1}'

        count = google_sheet_token_repository.bulk_import(
            [
                {"name": "t2", "token_file": "data/t2.json", "token_context": "{}"},
                {"name": "t3", "token_file": "data/t3.json", "token_context": "{}"},
            ]
        )
        assert count == 2
        assert len(google_sheet_token_repository.list_all()) == 3
        with pytest.raises(NotFoundError):
            google_sheet_token_repository.get_required(9999)


# ==================== scheduled_task ====================


class TestScheduledTaskRepository:
    def test_crud_find_due_stats(self, app_factory):
        from datetime import datetime, timedelta

        scheduled_task_repository.create(
            {
                "name": "job",
                "cron_expression": "* * * * *",
                "task_function": "cleanup",
                "is_active": True,
                "is_running": False,
                "next_run_time": datetime.now() - timedelta(minutes=1),
            }
        )
        scheduled_task_repository.create(
            {
                "name": "job2",
                "cron_expression": "* * * * *",
                "task_function": "cleanup",
                "is_active": False,
                "next_run_time": datetime.now() - timedelta(minutes=1),
            }
        )
        stats = scheduled_task_repository.stats()
        assert stats == {"total": 2, "active": 1}
        due = scheduled_task_repository.find_due(datetime.now())
        assert [row["name"] for row in due] == ["job"]

        with pytest.raises(NotFoundError):
            scheduled_task_repository.get_required(9999)
        assert scheduled_task_repository.delete(1) is True


# ==================== stock_metadata ====================


class TestStockMetadataRepository:
    def test_upsert_insert_then_update(self, app_factory):
        payload = {
            "stock_code": "600000",
            "stock_name": "浦发银行",
            "market_type": "cn",
        }
        created = stock_metadata_repository.upsert(dict(payload))
        updated = stock_metadata_repository.upsert({**payload, "stock_name": "新名称"})
        assert created["id"] == updated["id"]
        assert updated["stock_name"] == "新名称"
        assert stock_metadata_repository.count() == 1
        # get 为字面查询：标准化由调用方完成（服务层 normalize + 旧代码回退）。
        assert stock_metadata_repository.get("600000.SS", "cn")["stock_name"] == "新名称"
        assert stock_metadata_repository.get("600000.SS", "us") is None


# ==================== backtest_repository ====================


class TestBacktestRepository:
    def test_lock_acquire_idempotent_and_conflict(self, app_factory):
        ok, holder = backtest_repository.acquire_lock("ss1", "t-1", "backtest_training")
        assert (ok, holder) == (True, None)
        ok, holder = backtest_repository.acquire_lock("ss1", "t-1", "backtest_training")
        assert (ok, holder) == (True, None)  # 同任务幂等
        ok, holder = backtest_repository.acquire_lock("ss1", "t-2", "backtest_training")
        assert (ok, holder) == (False, "t-1")  # 他任务冲突

    def test_lock_release_guards_owner(self, app_factory):
        backtest_repository.acquire_lock("ss1", "t-1", "backtest_training")
        assert backtest_repository.release_lock("ss1", "t-2") is False
        assert backtest_repository.release_lock("ss1", "t-1") is True
        assert backtest_repository.get_lock("ss1") is None
        assert backtest_repository.release_lock("ss1", "t-1") is False

    def test_release_locks_by_task(self, app_factory):
        backtest_repository.acquire_lock("ss1", "t-1", "backtest_training")
        backtest_repository.acquire_lock("ss2", "t-1", "backtest_training")
        assert backtest_repository.release_locks_by_task("t-1") == 2

    def test_summary_index_upsert(self, app_factory):
        created = backtest_repository.upsert_summary_index(
            101,
            "default",
            {"task_id": "t-1", "task_type": "backtest_training", "market_type": "us"},
        )
        again = backtest_repository.upsert_summary_index(
            101, "default", {"task_id": "t-1", "best_metric_value": 1.5}
        )
        assert created["id"] == again["id"]
        assert again["best_metric_value"] == 1.5
        assert len(backtest_repository.get_summary_index("t-1")) == 1
        assert backtest_repository.delete_summary_index("t-1") == 1

    def test_product_cache_upsert_and_delete_by_task(self, app_factory):
        backtest_repository.upsert_product_cache(
            "batch-1", "key-1",
            {"result_json": "{}", "source_task_id": "t-9"},
        )
        cached = backtest_repository.get_product_cache("batch-1", "key-1")
        assert cached["source_task_id"] == "t-9"
        assert backtest_repository.delete_product_cache_by_task("t-9") == 1

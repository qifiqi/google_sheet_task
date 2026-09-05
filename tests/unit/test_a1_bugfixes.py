"""A1 批次（BUG-01 ~ BUG-07）修复验收测试。

对应 docs/design/code-audit-2026-09/01-bugs-and-fixes.md 的各"验收标准"。
"""
import json
from datetime import datetime

import pytest
from sqlalchemy.exc import OperationalError

from app.exceptions import NotFoundError, ValidationError
from app.exceptions.sheet_check_error import SheetCheckError
from app.extensions import db
from app.models import Task, TaskLog, User
from app.repositories import task_repository
from app.services.task.facade import TaskManager
from app.utils.db_retry import DatabaseLockError, db_retry_manager


def _task(task_id="task-1", *, status="pending", task_type="google_sheet", config=None):
    return Task(
        id=task_id,
        name=task_id,
        description="",
        task_type=task_type,
        status=status,
        config=json.dumps(config or {}, ensure_ascii=False),
        created_at=datetime.now(),
    )


# ---------------------------------------------------------------------------
# BUG-01 create_restart_task 的 dict 属性访问
# ---------------------------------------------------------------------------

def test_create_restart_task_survives_dict_task_row(app_factory, monkeypatch):
    """BUG-01：task_repository.get 返回 dict，create_restart_task 不得做属性访问。"""
    app = app_factory
    with app.app_context():
        original = _task("origin-1", task_type="google_sheet", config={"parameters": [["1"]]})
        db.session.add(original)
        db.session.commit()

        manager = TaskManager()
        occupancy_calls = []
        monkeypatch.setattr(
            manager,
            "ensure_google_sheet_occupancy",
            lambda task_id, config: occupancy_calls.append((task_id, config)),
        )

        new_task_id = manager.create_restart_task("origin-1")

        created = task_repository.get(new_task_id)
        assert created is not None
        assert created["status"] == "pending"
        assert "重启" in created["name"]
        assert created["task_type"] == "google_sheet"
        assert occupancy_calls and occupancy_calls[0][0] == new_task_id


def test_create_restart_task_skips_occupancy_for_backtest(app_factory, monkeypatch):
    app = app_factory
    with app.app_context():
        original = _task("origin-bt", task_type="backtest_training", config={})
        db.session.add(original)
        db.session.commit()

        manager = TaskManager()
        occupancy_calls = []
        monkeypatch.setattr(
            manager,
            "ensure_google_sheet_occupancy",
            lambda task_id, config: occupancy_calls.append(task_id),
        )

        new_task_id = manager.create_restart_task("origin-bt")

        assert task_repository.get(new_task_id) is not None
        assert occupancy_calls == []


# ---------------------------------------------------------------------------
# BUG-02 task.error = e 无效赋值（SheetCheckError 分支补 error_message 落库）
# ---------------------------------------------------------------------------

def test_c5_checkforerrors_branch_records_error_message(app_factory, monkeypatch):
    """BUG-02：SheetCheckError 失败分支现在必须把错误摘要写入 Task.error_message。"""
    app = app_factory
    with app.app_context():
        from app.services.google_sheet_service_C5 import C5Service as C5GoogleSheetService

        task = Task(
            id="c5-sheet-error-task",
            name="c5 sheet error task",
            task_type="google_sheet_C5",
            status="running",
            current_step=0,
            config=json.dumps({
                "c5_input_column_a": "A",
                "c5_input_column_b": "B",
            }),
        )
        db.session.add(task)
        db.session.commit()

        service = C5GoogleSheetService({}, task.id, app=app)

        class BrokenSheet:
            title = "sheet"
            spreadsheet_id = "spreadsheet"

            def get_last_row(self, _column):
                return 0

        service.google_sheets = [BrokenSheet()]
        monkeypatch.setattr(
            service,
            "_get_all_parameters",
            lambda *_args, **_kwargs: (
                [{"stock_code": "600000", "Kline_key": "2026-2025"}],
                10,
                {
                    "2026-2025": [
                        {"stock_date": "2025-01-01", "stock_val": 10},
                        {"stock_date": "2025-01-02", "stock_val": 11},
                    ],
                },
            ),
        )
        monkeypatch.setattr(service, "_interruptible_sleep", lambda _seconds: True)
        monkeypatch.setattr(
            service,
            "_execute_parameter_combination",
            lambda *_args, **_kwargs: (_ for _ in ()).throw(
                SheetCheckError("检查报错，出现#|#N/A 这种异常错误，联系用户检查")
            ),
        )

        success_count, failed_count, status = service.get_bdl(
            task,
            task.name,
            [[["outer"]]],
            {
                "c5_input_column_a": "A",
                "c5_input_column_b": "B",
                "market_type": "cn",
            },
        )

        refreshed = db.session.get(Task, task.id)
        # 原分支语义：failed_count 不自增，仅以 error 状态终止。
        assert (success_count, failed_count, status) == (0, 0, "error")
        # 修复前该分支只写日志，error_message 恒为 None。
        assert refreshed.error_message is not None
        assert "SheetCheckError" in refreshed.error_message
        assert "Traceback" not in refreshed.error_message


def test_no_task_error_attribute_assignments_remain():
    """BUG-02 收尾：全库不允许再出现 task.error = ... 的无效赋值（Task 无 error 列）。"""
    import pathlib
    import re

    pattern = re.compile(r"\.error\s*=\s*e(xc)?\b")
    offenders = []
    for path in pathlib.Path("app").rglob("*.py"):
        for lineno, line in enumerate(
            path.read_text(encoding="utf-8", errors="ignore").splitlines(), start=1
        ):
            if pattern.search(line):
                offenders.append(f"{path}:{lineno}")
    assert offenders == []


# ---------------------------------------------------------------------------
# BUG-03 start_task 前置失败路径回滚
# ---------------------------------------------------------------------------

def test_start_task_unregistered_type_rolls_back_occupancy(app_factory, monkeypatch):
    app = app_factory
    with app.app_context():
        task = _task("t-unknown", task_type="definitely_not_a_type", config={})
        db.session.add(task)
        db.session.commit()

        manager = TaskManager()
        released = []
        monkeypatch.setattr(
            manager, "ensure_google_sheet_occupancy", lambda *_a, **_k: None
        )
        monkeypatch.setattr(
            manager,
            "release_google_sheet_occupancy",
            lambda task_id: released.append(task_id),
        )

        assert manager.start_task(task.id) is False
        assert released == [task.id]
        assert "不支持的任务类型" in manager.get_start_error(task.id)

        refreshed = db.session.get(Task, task.id)
        assert refreshed.status == "pending"
        assert refreshed.error_message and "不支持的任务类型" in refreshed.error_message
        assert (
            TaskLog.query.filter(
                TaskLog.task_id == task.id,
                TaskLog.message.contains("任务启动被拒绝"),
            ).count()
            == 1
        )


def test_start_task_backtest_concurrency_full_reverts_running_and_locks(
    app_factory, monkeypatch
):
    """BUG-03 最重场景：回测任务并发满时必须回滚 running 状态与 sheet 锁。"""
    app = app_factory
    with app.app_context():
        task = _task("t-bt-full", task_type="backtest_training", config={})
        db.session.add(task)
        db.session.commit()

        manager = TaskManager()
        monkeypatch.setattr(manager, "_get_config", lambda _key, default=None: 5)
        monkeypatch.setattr(manager, "_is_backtest_task_type", lambda _tt: True)
        monkeypatch.setattr(
            manager,
            "_extract_backtest_spreadsheet_ids_to_lock",
            lambda *_a, **_k: ["sheet-1"],
        )
        monkeypatch.setattr(
            manager,
            "_find_running_backtest_task_for_spreadsheets",
            lambda *_a, **_k: None,
        )
        monkeypatch.setattr(
            manager,
            "_acquire_backtest_sheet_run_locks",
            lambda *_a, **_k: (True, None, ["sheet-1"]),
        )
        monkeypatch.setattr(
            manager, "_config_for_spreadsheet_locks", lambda config, _ids: config
        )
        released = []
        monkeypatch.setattr(
            manager,
            "release_google_sheet_occupancy",
            lambda task_id: released.append(task_id),
        )
        monkeypatch.setattr(
            manager, "count_running_executions", lambda: 999
        )

        assert manager.start_task(task.id) is False
        assert "并发已满" in manager.get_start_error(task.id)

        # 修复前：任务卡在 running、占用不释放。
        refreshed = db.session.get(Task, task.id)
        assert refreshed.status == "pending"
        assert released == [task.id]
        assert task.id not in manager.task_token_occupancy
        assert (
            TaskLog.query.filter(
                TaskLog.task_id == task.id,
                TaskLog.message.contains("任务启动被拒绝"),
            ).count()
            == 1
        )


def test_start_task_build_runner_failure_rolls_back_backtest_state(app_factory, monkeypatch):
    app = app_factory
    with app.app_context():
        task = _task("t-bt-runner", task_type="backtest_training", config={})
        db.session.add(task)
        db.session.commit()

        manager = TaskManager()
        monkeypatch.setattr(manager, "_get_config", lambda _key, default=None: 5)
        monkeypatch.setattr(manager, "_is_backtest_task_type", lambda _tt: True)
        monkeypatch.setattr(
            manager,
            "_extract_backtest_spreadsheet_ids_to_lock",
            lambda *_a, **_k: ["sheet-1"],
        )
        monkeypatch.setattr(
            manager,
            "_find_running_backtest_task_for_spreadsheets",
            lambda *_a, **_k: None,
        )
        monkeypatch.setattr(
            manager,
            "_acquire_backtest_sheet_run_locks",
            lambda *_a, **_k: (True, None, ["sheet-1"]),
        )
        monkeypatch.setattr(
            manager, "_config_for_spreadsheet_locks", lambda config, _ids: config
        )
        monkeypatch.setattr(
            manager, "ensure_google_sheet_occupancy", lambda *_a, **_k: None
        )
        monkeypatch.setattr(
            "app.services.task.runtime.build_runner",
            lambda *_a, **_k: (_ for _ in ()).throw(LookupError("no runner")),
        )

        assert manager.start_task(task.id) is False
        assert "no runner" in manager.get_start_error(task.id)

        refreshed = db.session.get(Task, task.id)
        assert refreshed.status == "pending"
        assert task.id not in manager.task_stop_events


# ---------------------------------------------------------------------------
# BUG-05 User 时间基准与全库一致
# ---------------------------------------------------------------------------

def test_user_created_at_default_uses_local_now(app_factory):
    """BUG-05：User.created_at 默认值必须与全库一致用本地时间，而非 utcnow（差 8 小时）。"""
    app = app_factory
    with app.app_context():
        user = User(username="tz-check-user", password_hash="x")
        db.session.add(user)
        db.session.flush()

        assert user.created_at is not None
        delta = abs((user.created_at - datetime.now()).total_seconds())
        assert delta < 60, f"created_at 偏离本地时间 {delta} 秒，疑似 utcnow"


# ---------------------------------------------------------------------------
# BUG-06 db_retry commit 重试
# ---------------------------------------------------------------------------

class _FakeSession:
    def __init__(self, fail_times=1, error_message="database is locked"):
        self.fail_times = fail_times
        self.error_message = error_message
        self.commit_calls = 0
        self.rollback_calls = 0

    def commit(self):
        self.commit_calls += 1
        if self.commit_calls <= self.fail_times:
            raise OperationalError(
                "COMMIT", None, Exception(self.error_message)
            )

    def rollback(self):
        self.rollback_calls += 1


def test_commit_with_retry_replays_operation_after_transient_lock():
    session = _FakeSession(fail_times=1)
    replayed = []

    def operation(sess):
        replayed.append(True)
        return "written"

    result = db_retry_manager.commit_with_retry(session, operation)

    assert result is None
    assert len(replayed) == 2          # 第一次失败后重放成功
    assert session.commit_calls == 2
    assert session.rollback_calls == 1


def test_commit_with_retry_without_operation_raises_lock_error_and_rolls_back():
    session = _FakeSession(fail_times=99)

    with pytest.raises(DatabaseLockError):
        db_retry_manager.commit_with_retry(session)

    assert session.rollback_calls == 1
    assert session.commit_calls == 1   # 不做无意义的无效重试


def test_commit_with_retry_passes_through_non_transient_error():
    session = _FakeSession(fail_times=99, error_message="syntax error at")

    with pytest.raises(OperationalError):
        db_retry_manager.commit_with_retry(session)

    assert session.rollback_calls == 1


# ---------------------------------------------------------------------------
# BUG-07 meta 版本值大小写
# ---------------------------------------------------------------------------

def test_meta_versions_values_are_lowercase(app_factory):
    app = app_factory
    with app.test_client() as client:
        resp = client.get("/api/meta/versions")
        assert resp.status_code == 200
        payload = resp.get_json()
        values = [item["value"] for item in payload["data"]]
        assert "c7" in values
        assert all(value == value.lower() or value in ("backtest_training", "backtest_multi_product")
                   for value in values)


# ---------------------------------------------------------------------------
# BUG-04 多品任务加载器命名与 404 语义
# ---------------------------------------------------------------------------

def test_load_multi_product_task_or_raise_not_found(app_factory):
    app = app_factory
    with app.app_context():
        from app.routes.backtest_api import _load_multi_product_task_or_raise

        with pytest.raises(NotFoundError):
            _load_multi_product_task_or_raise("missing-task")


def test_load_multi_product_task_or_raise_type_mismatch(app_factory):
    app = app_factory
    with app.app_context():
        from app.routes.backtest_api import _load_multi_product_task_or_raise

        task = _task("t-c3", task_type="google_sheet", config={})
        db.session.add(task)
        db.session.commit()

        with pytest.raises(ValidationError):
            _load_multi_product_task_or_raise("t-c3")

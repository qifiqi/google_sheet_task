"""A2 批次（BUG-08 / BUG-09 / BUG-12）修复验收测试。

对应 docs/design/code-audit-2026-09/01-bugs-and-fixes.md：
- BUG-08 运行态并发保护（代际 worker id、提交窗口、原子 detach）；
- BUG-09 调度子进程输出重定向 + 陈旧锁接管；
- BUG-12 repository 写方法 commit 参数统一。
"""
import json
import threading
from datetime import datetime, timedelta

from app.extensions import db
from app.models import ScheduledTask, Task
from app.repositories import backtest_repository, task_result_repository
from app.services.model_summary.jobs import SummaryJobMixin
from app.services.scheduler_service import SchedulerService
from app.services.task.facade import TaskManager


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


def _scheduled_task(**overrides):
    data = {
        "name": "cleanup",
        "description": "",
        "cron_expression": "0 0 * * *",
        "task_type": "cleanup",
        "task_function": "cleanup_old_data",
        "task_params": json.dumps({"days": 10}),
        "is_active": True,
    }
    data.update(overrides)
    return ScheduledTask(**data)


# ---------------------------------------------------------------------------
# BUG-08 运行态并发保护
# ---------------------------------------------------------------------------

def test_cleanup_runtime_state_preserves_foreign_worker_id(app_factory):
    """被替换的老一代线程不得误删新一代线程登记的 worker id。"""
    app = app_factory
    with app.app_context():
        manager = TaskManager()
        task_id = "t-generation"
        manager.running_tasks[task_id] = None
        manager.task_stop_events[task_id] = threading.Event()
        manager.task_execution_types[task_id] = "google_sheet"
        manager._active_worker_ids[task_id] = 999_999_999  # 新一代线程 id

        manager._cleanup_runtime_state(task_id)

        # 其余运行态已清理；worker id 属于别的线程，保留。
        assert task_id not in manager.running_tasks
        assert task_id not in manager.task_stop_events
        assert task_id not in manager.task_execution_types
        assert manager._active_worker_ids[task_id] == 999_999_999


def test_submit_task_execution_registers_handle_before_runner(app_factory):
    """提交窗口修复：runner 开始执行时 running_tasks 必须已包含本任务。"""
    app = app_factory
    with app.app_context():
        manager = TaskManager()
        observed = {}

        def runner(task_id, _app):
            observed[task_id] = task_id in manager.running_tasks

        handle = manager.submit_task_execution("t-submit", app, runner)
        handle.join(timeout=5.0)

        assert observed["t-submit"] is True
        assert handle.is_alive() is False


def test_force_detach_running_task_atomic(app_factory):
    app = app_factory
    with app.app_context():
        manager = TaskManager()
        task_id = "t-detach"
        manager.running_tasks[task_id] = None
        manager.task_stop_events[task_id] = threading.Event()

        detached = manager.force_detach_running_task(task_id)

        assert detached is None
        assert task_id not in manager.running_tasks
        assert task_id not in manager.task_stop_events


def test_facade_mixed_operations_stress_no_state_leak(app_factory):
    """并发压测（100 轮 × 4 线程混合提交/detach/快照统计）：无异常、无状态残留。

    说明：façade 级压测覆盖锁与代际逻辑本身；带 DB 的 start/cancel/restart 并发
    在 SQLite 文件库下易受锁等待抖动影响，由现有 lifecycle 单测覆盖单线程语义。
    """
    app = app_factory
    with app.app_context():
        manager = TaskManager()
        errors = []

        def runner(task_id, _app):
            manager._cleanup_runtime_state(task_id)

        def worker(round_index):
            try:
                task_id = f"t-stress-{round_index}"
                handle = manager.submit_task_execution(task_id, app, runner)
                manager.get_runtime_snapshot()
                manager.count_running_executions()
                manager.force_detach_running_task(task_id)
                handle.join(timeout=10.0)
                assert handle.is_alive() is False
            except Exception as exc:  # pragma: no cover - 失败时收集断言
                errors.append(exc)

        for round_index in range(100):
            threads = [threading.Thread(target=worker, args=(round_index,)) for _ in range(4)]
            for t in threads:
                t.start()
            for t in threads:
                t.join(timeout=30.0)

        assert errors == []
        assert manager.running_tasks == {}
        assert manager.task_stop_events == {}


# ---------------------------------------------------------------------------
# BUG-09 子进程输出重定向 + 陈旧锁接管
# ---------------------------------------------------------------------------

def test_acquire_run_lock_takes_over_stale_lock(app_factory):
    app = app_factory
    with app.app_context():
        task = _scheduled_task(
            is_running=True,
            running_instance_id="dead-instance",
            last_run_time=datetime.now() - timedelta(hours=10),
        )
        db.session.add(task)
        db.session.commit()

        stale_before = datetime.now() - timedelta(hours=6)
        rows = task_repo_acquire(task.id, stale_before)

        assert rows == 1
        refreshed = db.session.get(ScheduledTask, task.id)
        assert refreshed.running_instance_id == "this-instance"


def task_repo_acquire(task_id, stale_before):
    from app.repositories import scheduled_task_repository

    return scheduled_task_repository.acquire_run_lock(
        task_id, "this-instance", datetime.now(), stale_before=stale_before
    )


def test_acquire_run_lock_respects_fresh_lock(app_factory):
    app = app_factory
    with app.app_context():
        task = _scheduled_task(
            is_running=True,
            running_instance_id="live-instance",
            last_run_time=datetime.now() - timedelta(minutes=1),
        )
        db.session.add(task)
        db.session.commit()

        stale_before = datetime.now() - timedelta(hours=6)
        rows = task_repo_acquire(task.id, stale_before)

        assert rows == 0
        refreshed = db.session.get(ScheduledTask, task.id)
        assert refreshed.running_instance_id == "live-instance"


def test_execute_task_takes_over_timed_out_lock(app_factory, monkeypatch):
    app = app_factory
    launched = []
    with app.app_context():
        task = _scheduled_task(
            is_running=True,
            running_instance_id="dead-instance",
            last_run_time=datetime.now() - timedelta(hours=10),
        )
        db.session.add(task)
        db.session.commit()

        service = SchedulerService()
        service.app = app
        monkeypatch.setattr(
            service, "_run_task_in_subprocess", lambda scheduled_task: launched.append(scheduled_task.id)
        )

        service._execute_task(task.id)

        assert launched == [task.id]
        db.session.expire_all()
        refreshed = db.session.get(ScheduledTask, task.id)
        assert refreshed.running_instance_id == service.instance_id


def test_subprocess_output_redirects_to_log_file(app_factory, monkeypatch, tmp_path):
    """PIPE 必须消失：stdout 重定向到文件，stderr 合并，父进程不留管道句柄。"""
    app = app_factory
    with app.app_context():
        import os

        task = _scheduled_task()
        db.session.add(task)
        db.session.commit()

        monkeypatch.chdir(tmp_path)

        captured = {}

        class _FakeProcess:
            pid = 424242

        def fake_popen(cmd, **kwargs):
            captured["stdout"] = kwargs.get("stdout")
            captured["stderr"] = kwargs.get("stderr")
            return _FakeProcess()

        monkeypatch.setattr("app.services.scheduler_service.subprocess.Popen", fake_popen)

        service = SchedulerService()
        service.app = app
        service._run_task_in_subprocess(task)

        import subprocess as _subprocess

        assert captured["stderr"] is _subprocess.STDOUT
        stdout = captured["stdout"]
        assert stdout is not _subprocess.PIPE
        assert stdout is not _subprocess.DEVNULL
        assert "scheduled_task_" in stdout.name
        # 父进程侧文件句柄应已关闭（可再次打开说明没有句柄泄漏断言意义，改为检查路径）。
        assert str(stdout.name).replace("\\", "/").endswith(
            f"logs/scheduled_task_{task.id}.log"
        )


def test_run_lock_timeout_hours_configurable(app_factory, monkeypatch):
    app = app_factory
    with app.app_context():
        from app.services import config_manager as config_manager_module

        monkeypatch.setattr(
            config_manager_module.get_config_manager(),
            "get_config",
            lambda _key, default=None: "2.5",
        )
        assert SchedulerService._run_lock_timeout_hours() == 2.5

        monkeypatch.setattr(
            config_manager_module.get_config_manager(),
            "get_config",
            lambda _key, default=None: "not-a-number",
        )
        assert SchedulerService._run_lock_timeout_hours() == 6.0


# ---------------------------------------------------------------------------
# BUG-12 repository 写方法 commit 参数
# ---------------------------------------------------------------------------

def test_task_result_create_commit_param_wiring(app_factory, monkeypatch):
    app = app_factory
    with app.app_context():
        repo = task_result_repository
        commits = []
        monkeypatch.setattr(repo, "_commit", lambda: commits.append(True))

        repo.create({"task_id": "t-x", "step_index": 0, "parameters": "{}", "result": "{}"})
        assert len(commits) == 1

        repo.create(
            {"task_id": "t-x", "step_index": 1, "parameters": "{}", "result": "{}"},
            commit=False,
        )
        assert len(commits) == 1  # 未新增提交

        from app.models import TaskResult

        assert TaskResult.query.filter_by(task_id="t-x").count() == 2


def test_delete_legacy_performance_analysis_jobs_missing_table_does_not_commit(app_factory, monkeypatch):
    app = app_factory
    with app.app_context():
        commits = []
        monkeypatch.setattr(backtest_repository, "_commit", lambda: commits.append(True))

        # 测试库不存在 xpl_analysis_jobs 表 → 早退路径不得提交。
        backtest_repository.delete_legacy_performance_analysis_jobs(task_id="t-none")
        assert commits == []


def test_jobs_dedupe_passes_commit_false(monkeypatch):
    recorded = {}

    def fake_dedupe(*_args, **kwargs):
        recorded.update(kwargs)
        return 0

    monkeypatch.setattr(backtest_repository, "dedupe_best_per_task", fake_dedupe)

    SummaryJobMixin()._dedupe_best_per_task(task_type="backtest_training", task_id="t-1")

    assert recorded.get("commit") is False

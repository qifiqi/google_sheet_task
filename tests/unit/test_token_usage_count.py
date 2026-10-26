# -*- coding: utf-8 -*-
"""token 占用计数回归：increment_usage 活扫描必须排除调用方任务自身。

start_task 先 mark_running 再 increment_usage（task/runtime.py），活扫描若不
排除自身会把任务计入快照再 +1 落库 2；释放只减 1，每次启动净残留 +1
（2026-10-26 真实环境实测暴露，见 2026-10 月度汇总"发现登记"）。
"""

import json

import pytest

from app.models import GoogleSheetToken, Task, TaskStatus
from app.services.google_sheet_token_service import GoogleSheetTokenService


@pytest.fixture
def running_task_with_token(app_factory):
    from app.extensions import db

    token = GoogleSheetToken(
        name="占用计数回归",
        token_file="data/token_usage_regtest.json",
        token_context="{}",
        is_active=True,
        max_usage_count=0,
    )
    db.session.add(token)
    db.session.flush()

    task = Task(
        id="regtest-task-1",
        name="占用计数回归任务",
        task_type="google_sheet_c7",
        status=TaskStatus.RUNNING.value,
        config=json.dumps(
            {"token_id": token.id, "token_type": "file"},
            ensure_ascii=False,
        ),
    )
    db.session.add(task)
    db.session.commit()
    yield token, task


def test_live_snapshot_counts_running_task_by_token(running_task_with_token):
    token, _task = running_task_with_token
    service = GoogleSheetTokenService()

    snapshot = service._build_live_usage_snapshot()

    assert snapshot["token_usage"] == {token.id: 1}
    assert snapshot["current_total"] == 1


def test_live_snapshot_excludes_self_for_increment(running_task_with_token):
    token, task = running_task_with_token
    service = GoogleSheetTokenService()

    snapshot = service._build_live_usage_snapshot(exclude_task_id=task.id)

    assert snapshot["token_usage"] == {}
    assert snapshot["current_total"] == 0


def test_increment_usage_does_not_double_count_self(running_task_with_token):
    token, task = running_task_with_token
    service = GoogleSheetTokenService()

    service.increment_usage(token.id, exclude_task_id=task.id)
    assert token.current_in_use_count == 1

    service.release_usage(token.id)
    assert token.current_in_use_count == 0


def test_increment_without_exclude_keeps_reconcile_semantics(running_task_with_token):
    """不传排除（对账/旧调用方语义）：快照含全部 running 任务，行为不变。"""
    token, _task = running_task_with_token
    service = GoogleSheetTokenService()

    service.increment_usage(token.id)
    assert token.current_in_use_count == 2

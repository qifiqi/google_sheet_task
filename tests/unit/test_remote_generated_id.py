"""远端生成主键契约回归（2026-10-19 远端插入修复后）。

远端 ``ModifyOrAdd`` 插入回执为**主键字符串**（如 ``"0f88d30c59ea4685..."``），
任务新建不再携带本地 uuid。契约：
- ``save`` 把字符串回执回填为 ``id``，按仓储 ``normalize_id`` 规则定类型；
- ``id`` 为 None 的插入载荷剔除主键（交由远端生成）；
- 任务 ``create``/``add_entity`` 不发送本地 uuid，返回/回写远端 id；
- 业务层（创建任务/重启任务/汇总重建）一律以返回记录 id 为准。
"""

import json
from types import SimpleNamespace

import pytest

from app.repositories.http_backend.base import HttpRepositoryBase
from app.repositories.http_backend.task_repository import TaskHttpRepository
from app.repositories.http_backend.task_result_repository import TaskResultHttpRepository


class _ModifyApi:
    """记录出站载荷并按脚本返回回执的 ModifyOrAdd 替身。"""

    def __init__(self, returns):
        self.calls = []
        self._returns = list(returns)

    def modify_or_add(self, payload):
        self.calls.append(dict(payload))
        return self._returns.pop(0) if self._returns else None


def _task_repo(returns):
    return TaskHttpRepository(api=SimpleNamespace(param_tasks=_ModifyApi(returns)))


def test_save_backfills_string_id_for_task_repository():
    repo = _task_repo(["0f88d30c59ea4685948d8fd6b65af1f1"])

    saved = repo.create({"name": "t", "task_type": "google_sheet_C7", "status": "pending",
                         "config": "{}", "created_by_user_id": 1})

    assert saved["id"] == "0f88d30c59ea4685948d8fd6b65af1f1"
    assert saved["name"] == "t"
    assert saved["config"] == {}


def test_save_coerces_numeric_string_id_for_numeric_repository():
    controller = _ModifyApi(["123"])
    repo = TaskResultHttpRepository(api=SimpleNamespace(param_task_results=controller))

    saved = repo.create({"task_id": "t1", "step_index": 0, "success": True})

    assert saved["id"] == 123
    assert isinstance(saved["id"], int)


def test_save_strips_null_id_from_insert_payload():
    controller = _ModifyApi(["9f00"])
    repo = TaskResultHttpRepository(api=SimpleNamespace(param_task_results=controller))

    repo.create({"id": None, "task_id": "t1", "step_index": 0})

    assert "id" not in controller.calls[0]


def test_save_still_accepts_object_receipt():
    controller = _ModifyApi([{"id": 7, "task_id": "t1", "success": True}])
    repo = TaskResultHttpRepository(api=SimpleNamespace(param_task_results=controller))

    saved = repo.create({"task_id": "t1", "success": True})

    assert saved["id"] == 7
    assert saved["success"] is True


def test_task_create_drops_local_uuid_and_returns_remote_id():
    repo = _task_repo(["remote-generated-id"])

    saved = repo.create({"id": "local-uuid-placeholder", "name": "t",
                         "task_type": "google_sheet_C7", "status": "pending",
                         "config": "{}", "created_by_user_id": 1})

    # 出站载荷不携带本地 uuid（远端生成主键）
    assert "id" not in repo.api.param_tasks.calls[0]
    assert saved["id"] == "remote-generated-id"


def test_task_add_entity_writes_remote_id_back_to_entity():
    repo = _task_repo(["remote-entity-id"])

    class _Column:
        def __init__(self, key):
            self.key = key

    class _Table:
        columns = [_Column(k) for k in ("id", "name", "task_type", "status", "config")]

    class _TaskEntity:
        __table__ = _Table()
        id = "local-uuid"
        name = "重建任务"
        task_type = "model_summary_rebuild"
        status = "pending"
        config = json.dumps({"batch_size": 20})

    entity = _TaskEntity()
    repo.add_entity(entity)

    assert "id" not in repo.api.param_tasks.calls[0]
    assert entity.id == "remote-entity-id"


def test_base_default_normalize_id_coerces_numeric_string():
    class _NumericRepo(HttpRepositoryBase):
        group_name = "x"

    assert _NumericRepo.normalize_id("456") == 456
    with pytest.raises(ValueError):
        _NumericRepo.normalize_id("abc")

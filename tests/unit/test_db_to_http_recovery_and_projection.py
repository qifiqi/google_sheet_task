"""db-to-http 审查问题收敛回归：http 孪生新增方法（2026-10-17）。

覆盖三类此前仅在本地 ORM 仓储存在、http 模式 AttributeError 的缺口，以及
启动期占用复位/死任务清理的 http 孪生实现：
- task_result.list_by_task_fields（fields 投影 + return_date_range 计算字段）；
- task/task_log/backtest.add_entity（model_summary 重建作业消费）；
- token.reset_all_usage_counts / sheet.clear_all_occupancy /
  backtest.delete_stale_run_locks / task.list_running_task_entities。
"""

from datetime import datetime
from types import SimpleNamespace

import pytest

from app.models import TaskLog
from app.remote_api import RemoteApiNotFoundError
from app.repositories.http_backend.backtest_repository import BacktestHttpRepository
from app.repositories.http_backend.google_sheet_repository import GoogleSheetHttpRepository
from app.repositories.http_backend.google_sheet_token_repository import (
    GoogleSheetTokenHttpRepository,
)
from app.repositories.http_backend.task_log_repository import TaskLogHttpRepository
from app.repositories.http_backend.task_repository import TaskHttpRepository
from app.repositories.http_backend.task_result_repository import TaskResultHttpRepository


class _FakeController:
    """远端标准 CRUD 最小替身：内存行集 + 记录保存/删除调用。"""

    def __init__(self, rows=None, by_id=None):
        self.rows = list(rows or [])
        self.by_id = dict(by_id or {})
        self.saved = []
        self.deleted = []

    def get_data_by_page_list(self, body):
        rows = self.rows
        statuses = body.get("statuses")
        if statuses:
            rows = [row for row in rows if row.get("status") in statuses]
        size = int(body.get("page_size") or 200)
        return rows[:size], len(rows)

    def get_info_by_id(self, payload):
        key = payload.get("id")
        if key in self.by_id:
            return self.by_id[key]
        raise RemoteApiNotFoundError(f"记录不存在: {key}")

    def modify_or_add(self, payload, timeout=None):
        self.saved.append(payload)
        return dict(payload, id=payload.get("id") or "generated-id")

    def delete(self, payload):
        self.deleted.append(payload.get("id"))
        return {}


def _api(**controllers):
    return SimpleNamespace(**controllers)


# ---- list_by_task_fields（fields 投影） ----


def test_list_by_task_fields_projects_requested_keys_and_ranges():
    results = _FakeController(rows=[
        {"id": 2, "task_id": "t1", "step_index": 1, "parameters": '{"a": 1}',
         "result": '{"v": 2}', "return_series_id": 11, "success": True,
         "error_message": None, "timestamp": "2026-10-01T10:00:00"},
        {"id": 1, "task_id": "t1", "step_index": 0, "parameters": '{"b": 2}',
         "result": None, "return_series_id": None, "success": False,
         "error_message": "boom", "timestamp": "2026-10-01T09:00:00"},
    ])
    returns = _FakeController(by_id={
        11: {"id": 11, "start_return_date": "2024-01-02", "end_return_date": "2024-06-28"},
    })
    repo = TaskResultHttpRepository(
        api=_api(param_task_results=results, param_task_results_return=returns)
    )

    items = repo.list_by_task_fields(
        "t1", ["id", "step_index", "parameters", "return_date_range"]
    )

    # step 升序（step 0 在前）；parameters 解析为 dict；return_date_range 取
    # 落库首末日期，无收益序列的行该字段为 None。
    assert items[0] == {
        "id": 1, "step_index": 0,
        "parameters": {"b": 2},
        "return_date_range": None,
    }
    assert items[1] == {
        "id": 2, "step_index": 1,
        "parameters": {"a": 1},
        "return_date_range": {"start": "2024-01-02", "end": "2024-06-28"},
    }
    # 未请求的 result 大字段不进投影。
    assert "result" not in items[0]


def test_list_by_task_fields_range_falls_back_to_stock_dates():
    results = _FakeController(rows=[
        {"id": 5, "task_id": "t1", "step_index": 0, "return_series_id": 7,
         "parameters": None, "result": None, "success": True, "timestamp": None},
    ])
    returns = _FakeController(by_id={
        # 落库首末日期为 NULL：回退解析 stock_date JSON。
        7: {"id": 7, "start_return_date": None, "end_return_date": None,
            "stock_date": '["2023-01-03", "2023-01-04", "2023-02-01"]'},
    })
    repo = TaskResultHttpRepository(
        api=_api(param_task_results=results, param_task_results_return=returns)
    )

    items = repo.list_by_task_fields("t1", ["return_date_range"])

    assert items[0]["return_date_range"] == {"start": "2023-01-03", "end": "2023-02-01"}


# ---- add_entity（model_summary 重建作业消费） ----


class _Column:
    def __init__(self, key):
        self.key = key


class _Table:
    def __init__(self, keys):
        self.columns = [_Column(key) for key in keys]


def test_task_http_add_entity_serializes_columns_and_drops_none_id():
    controller = _FakeController()
    repo = TaskHttpRepository(api=_api(param_tasks=controller))

    class _TaskEntity:
        def __init__(self):
            self.__table__ = _Table(["id", "name", "status", "config", "current_step"])
            self.id = None
            self.name = "单模型汇总索引重建"
            self.status = "pending"
            self.config = '{"batch_size": 20}'
            self.current_step = 0

    entity = _TaskEntity()
    repo.add_entity(entity)

    assert len(controller.saved) == 1
    payload = controller.saved[0]
    # None 自增主键剔除，交由远端生成；其余列直传。
    assert "id" not in payload
    assert payload["name"] == "单模型汇总索引重建"
    assert payload["config"] == '{"batch_size": 20}'
    assert payload["current_step"] == 0
    # 远端回显 id 回写到实体。
    assert entity.id == "generated-id"


def test_task_log_http_add_entity_normalizes_message():
    controller = _FakeController()
    repo = TaskLogHttpRepository(api=_api(param_task_logs=controller))

    class _LogEntity:
        def __init__(self):
            self.__table__ = _Table(["task_id", "level", "message", "timestamp"])
            self.task_id = "t1"
            self.level = "info"
            self.message = "x" * (TaskLog.MAX_MESSAGE_LENGTH + 100)
            self.timestamp = datetime(2026, 10, 17, 8, 0, 0)

    repo.add_entity(_LogEntity())

    payload = controller.saved[0]
    assert len(payload["message"]) == TaskLog.MAX_MESSAGE_LENGTH
    assert payload["timestamp"] == "2026-10-17T08:00:00"


def test_backtest_http_add_entity_saves_summary_index():
    controller = _FakeController()
    repo = BacktestHttpRepository(api=_api(param_task_result_summary_index=controller))

    class _SummaryEntity:
        def __init__(self):
            self.__table__ = _Table(
                ["id", "task_id", "task_result_id", "task_type", "model_key",
                 "parameter_summary", "best_metric_value", "result_timestamp", "is_best"]
            )
            self.id = None
            self.task_id = "t1"
            self.task_result_id = 42
            self.task_type = "google_sheet_C5"
            self.model_key = "default"
            self.parameter_summary = '{"p": 1}'
            self.best_metric_value = 1.5
            self.result_timestamp = datetime(2026, 10, 17, 9, 30, 0)
            self.is_best = True

    repo.add_entity(_SummaryEntity())

    payload = controller.saved[0]
    assert "id" not in payload
    assert payload["task_result_id"] == 42
    assert payload["result_timestamp"] == "2026-10-17T09:30:00"
    assert payload["is_best"] is True


# ---- 启动期占用复位 / 死任务清理孪生 ----


def test_token_repo_reset_all_usage_counts_zeroes_nonzero_rows():
    controller = _FakeController(rows=[
        {"id": 1, "current_in_use_count": 2},
        {"id": 2, "current_in_use_count": 0},
        {"id": 3, "current_in_use_count": 5},
    ])
    repo = GoogleSheetTokenHttpRepository(api=_api(param_google_sheet_tokens=controller))

    assert repo.reset_all_usage_counts() == 2
    assert [payload["id"] for payload in controller.saved] == [1, 3]
    assert all(payload["current_in_use_count"] == 0 for payload in controller.saved)


def test_sheet_repo_clear_all_occupancy_clears_in_use_rows():
    controller = _FakeController(rows=[
        {"id": 1, "is_in_use": True, "current_task_id": "t9"},
    ])
    repo = GoogleSheetHttpRepository(api=_api(param_google_sheet=controller))

    assert repo.clear_all_occupancy() == 1
    payload = controller.saved[0]
    assert payload["is_in_use"] is False
    assert payload["current_task_id"] is None


def test_backtest_repo_delete_stale_run_locks_keeps_alive_tasks():
    controller = _FakeController(rows=[
        {"id": 1, "task_id": "t-running"},
        {"id": 2, "task_id": "t-dead"},
        {"id": 3, "task_id": "t-missing"},
    ])
    repo = BacktestHttpRepository(api=_api(param_backtest_sheet_run_locks=controller))

    def _running(task_id):
        return task_id == "t-running"

    assert repo.delete_stale_run_locks(_running) == 2
    assert sorted(controller.deleted) == [2, 3]


def test_task_repo_list_running_task_entities_filters_and_exposes_attributes():
    controller = _FakeController(rows=[
        {"id": "t-run", "status": "running"},
        {"id": "t-pending", "status": "pending"},
    ])
    repo = TaskHttpRepository(api=_api(param_tasks=controller))

    entities = repo.list_running_task_entities()

    assert [entity.id for entity in entities] == ["t-run"]


# ---- 服务级凭据配置缺省行为（红线：凭据仅环境变量） ----


def test_log_entity_missing_timestamp_passes_through():
    controller = _FakeController()
    repo = TaskLogHttpRepository(api=_api(param_task_logs=controller))

    class _LogEntity:
        def __init__(self):
            self.__table__ = _Table(["task_id", "level", "message", "timestamp"])
            self.task_id = "t1"
            self.level = "error"
            self.message = "no ts"
            self.timestamp = None

    repo.add_entity(_LogEntity())

    assert controller.saved[0]["timestamp"] is None

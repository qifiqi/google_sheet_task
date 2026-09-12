"""C4(2/2) 批次：C3/C4/C5/C7 的 get_bdl 外层网络异常统一打 [NETWORK_RETRYABLE]。

对应 docs/design/code-audit-2026-09/03-task-code-refactor.md §3.4 与
01-bugs-and-fixes.md 的验收要求：C3/C4/C5 补齐 `_raise_retryable_network_error`
调用，网络失败可被看门狗按前缀识别自动重启。
"""
import pytest
from requests.exceptions import SSLError

from app.extensions import db
from app.models import Task
from app.utils.task_error_utils import (
    NETWORK_ERROR_PREFIX,
    RetryableNetworkTaskError,
    is_retryable_network_error,
)


def _network_error():
    return SSLError("connection reset by peer")


def _make_task(task_id, task_type):
    import json
    from datetime import datetime

    return Task(
        id=task_id,
        name=task_id,
        description="",
        task_type=task_type,
        status="running",
        current_step=0,
        config=json.dumps({"market_type": "cn"}, ensure_ascii=False),
        created_at=datetime.now(),
    )


def _service_with_failing_expansion(app_factory, service_class, task_id, extra_sheets=False):
    app = app_factory
    task = _make_task(task_id, task_type)
    db.session.add(task)
    db.session.commit()

    service = service_class({}, task.id, app=app)
    service.google_sheets = []

    def _raise_network(*_args, **_kwargs):
        raise _network_error()

    monkeypatched = getattr(service, "_get_all_parameters", None)
    service._get_all_parameters = _raise_network
    return service, task


@pytest.mark.parametrize(
    "module_name,class_name,task_type",
    [
        ("app.services.google_sheet_tasks.c3", "C3Service", "google_sheet"),
        ("app.services.google_sheet_tasks.c4", "C4Service", "google_sheet_C4"),
        ("app.services.google_sheet_tasks.c5", "C5Service", "google_sheet_C5"),
        ("app.services.google_sheet_tasks.c7", "C7Service", "google_sheet_C7"),
    ],
)
def test_get_bdl_outer_marks_network_errors_retryable(
    app_factory, monkeypatch, module_name, class_name, task_type
):
    """网络异常从 get_bdl 外层逃逸时必须包成 RetryableNetworkTaskError。"""
    import importlib

    module = importlib.import_module(module_name)
    service_class = getattr(module, class_name)

    app = app_factory
    with app.app_context():
        task = _make_task(f"t-{class_name.lower()}", task_type)
        db.session.add(task)
        db.session.commit()

        service = service_class({}, task.id, app=app)
        service.google_sheets = []
        if class_name == "C3Service":
            # C3 的批量流程不经 _get_all_parameters：单表 + cell_kline_data 取K线
            class _Sheet:
                title = "sheet"

                def get_last_row(self, _column):
                    return 5  # ≤10 → 跳过清空，直达 cell_kline_data

                def clear_range(self, _a1):
                    return None

            service.google_sheet = _Sheet()
            monkeypatch.setattr(
                service, "cell_kline_data", lambda *a, **k: (_ for _ in ()).throw(_network_error())
            )
        else:
            monkeypatch.setattr(
                service, "_get_all_parameters", lambda *a, **k: (_ for _ in ()).throw(_network_error())
            )
        monkeypatch.setattr(service, "_interruptible_sleep", lambda _s: True)

        # 各任务输入列键不同，但都在参数展开之前被提取——补齐避免无关 AttributeError
        config = {
            "market_type": "cn",
            "c3_input_column_d": "D", "c3_input_column_e": "E",
            "c4_input_column_a": "A", "c4_input_column_b": "B",
            "c5_input_column_a": "a", "c5_input_column_b": "b",
            "stock_code": "600000",
        }
        parameters = [["outer-1"], ["inner-1"]]

        with pytest.raises(RetryableNetworkTaskError, match="批量数据处理网络请求失败"):
            service.get_bdl(task, task.name, parameters, config)


def test_retryable_wrapper_error_is_watchdog_detectable():
    """整链自检：_raise_retryable_network_error 抛出的包装异常
    （原异常在 __cause__ 链上）能被 is_retryable_network_error 识别，
    从而经 record_task_exception 打上 [NETWORK_RETRYABLE] 前缀。"""
    inner = _network_error()
    wrapped = RetryableNetworkTaskError("批量数据处理网络请求失败: connection reset")
    wrapped.__cause__ = inner

    assert is_retryable_network_error(wrapped)
    assert is_retryable_network_error(inner)

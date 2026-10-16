"""TaskLog HTTP 仓储 create_logs best-effort 回灌语义测试（2026-10-16）。

远端无批量端点（E9 裁定不提供）：逐行 ModifyOrAdd 慢写 + 单次 2 秒超时，
失败仅抛弃当前一条并继续写剩余。FakeApi 记录每次调用的 timeout 以断言管线传参。
"""
from datetime import datetime
from types import SimpleNamespace

from app.repositories.http_backend.task_log_repository import TaskLogHttpRepository


class _FakeTaskLogsApi:
    """modify_or_add 最小替身：按脚本逐次返回成功或抛错，记录 timeout 传参。"""

    def __init__(self, script):
        self.calls = []
        self._script = script  # [("ok", value) | ("err", exception), ...]

    def modify_or_add(self, payload, timeout=None):
        self.calls.append((payload, timeout))
        action = self._script[len(self.calls) - 1]
        if action[0] == "err":
            raise action[1]
        return action[1]


def _make_repo(script):
    api = SimpleNamespace(param_task_logs=_FakeTaskLogsApi(script))
    return TaskLogHttpRepository(api=api), api.param_task_logs


def _logs(count):
    return [
        {"level": "info", "message": f"m-{index}", "timestamp": datetime.now()}
        for index in range(count)
    ]


def test_create_logs_all_success_passes_short_timeout():
    repo, fake = _make_repo([("ok", {"id": index}) for index in range(3)])

    created = repo.create_logs("t1", _logs(3))

    assert len(created) == 3
    assert all(timeout == TaskLogHttpRepository.LOG_WRITE_TIMEOUT_SECONDS for _, timeout in fake.calls)
    assert fake.calls[0][0]["task_id"] == "t1"


def test_create_logs_skips_failed_line_and_continues():
    repo, fake = _make_repo(
        [
            ("ok", {"id": 1}),
            ("err", RuntimeError("remote down")),
            ("ok", {"id": 3}),
        ]
    )

    created = repo.create_logs("t1", _logs(3))

    # 仅抛弃失败的第二行，第三行继续写入。
    assert len(created) == 2
    assert [record["id"] for record in created] == [1, 3]
    assert len(fake.calls) == 3


def test_create_logs_empty_input_is_noop():
    repo, fake = _make_repo([])

    assert repo.create_logs("t1", []) == []
    assert fake.calls == []

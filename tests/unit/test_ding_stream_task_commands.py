from app.exceptions import ConflictError
from ding_stream_service.task_commands import (
    ParsedBatchRestartCommand,
    ParsedRestartCommand,
    TaskCommandService,
    extract_task_id,
    format_batch_restart_reply,
    parse_cached_restart_index,
    parse_batch_restart_command,
    parse_list_command,
    parse_restart_command,
)


def test_parse_restart_command_by_task_id():
    command = parse_restart_command("重启任务 abcdef12-3456-7890-abcd-ef1234567890")

    assert command is not None
    assert command.target == "abcdef12-3456-7890-abcd-ef1234567890"
    assert command.target_type == "id"
    assert command.resume_from_checkpoint is True


def test_parse_restart_command_by_task_name():
    command = parse_restart_command("断点重启 股票复盘任务")

    assert command is not None
    assert command.target == "股票复盘任务"
    assert command.target_type == "name"


def test_extract_task_id_from_current_dingtalk_alert_markdown():
    text = """断点重启
### 告警

- **任务状态**：执行失败
- **任务名称**：AAPL回测
- **任务ID**：abcdef12-3456-7890-abcd-ef1234567890
- **任务类型**：google_sheet
"""

    command = parse_restart_command(text)

    assert command is not None
    assert command.target == "abcdef12-3456-7890-abcd-ef1234567890"
    assert command.target_type == "id"


def test_extract_task_id_from_detail_url():
    assert (
        extract_task_id(
            "重启 [查看详情](http://localhost:5000/google-sheet/detail?task_id=abc12345)"
        )
        == "abc12345"
    )


def test_parse_restart_command_requires_explicit_restart_action():
    command = parse_restart_command("- **任务ID**：abcdef12")

    assert command is None


def test_parse_running_task_list_command_with_page():
    command = parse_list_command("查看运行任务 第2页 每页10条")

    assert command is not None
    assert command.status_group == "running"
    assert command.page == 2
    assert command.per_page == 10


def test_parse_stopped_task_list_command_with_project_wording():
    command = parse_list_command("查看停止的项目 第3页 每页8条")

    assert command is not None
    assert command.status_group == "stopped"
    assert command.page == 3
    assert command.per_page == 8


def test_parse_batch_restart_error_tasks_command_with_limit():
    command = parse_batch_restart_command("重启异常任务 数量10")

    assert command is not None
    assert command.status == "error"
    assert command.limit == 10
    assert command.resume_from_checkpoint is True


def test_parse_batch_restart_error_tasks_command_caps_limit():
    command = parse_batch_restart_command("重启异常任务 数量999")

    assert command is not None
    assert command.limit == 20


def test_parse_cached_restart_index_command():
    assert parse_cached_restart_index("重启第1个") == 1
    assert parse_cached_restart_index("重启1") == 1


def test_cached_index_restart_resolves_task_id():
    service = TaskCommandService()
    service.cache_list_result("conversation-1", [{"id": "task-1"}, {"id": "task-2"}])

    command = service.parse_cached_index_restart_command("重启第2个", "conversation-1")

    assert command is not None
    assert command.target == "task-2"
    assert command.target_type == "id"
    assert command.source == "cached_index"


def test_cached_index_restart_has_priority_over_task_name_restart():
    service = TaskCommandService()
    service.cache_list_result("conversation-1", [{"id": "task-1"}])

    captured = {}

    def fake_restart_task(command):
        captured["command"] = command
        return {
            "status": "success",
            "message": "任务重启成功",
            "task_id": command.target,
            "task_name": "测试任务",
        }

    service.restart_task = fake_restart_task

    result = service.handle_message("重启第1个", "符青", "conversation-1")

    assert result.handled is True
    assert captured["command"].target == "task-1"
    assert captured["command"].target_type == "id"
    assert captured["command"].source == "cached_index"


class _FakeTaskRepository:
    def __init__(self, tasks):
        self._tasks = tasks

    def list_by_status_ordered(self, status, limit):
        return self._tasks[:limit]

    def count_by_status(self, status):
        return len(self._tasks)

    def get(self, task_id):
        return next((t for t in self._tasks if t["id"] == task_id), None)

    def list_by_name(self, name, limit=2):
        matches = [t for t in self._tasks if t.get("name") == name]
        return matches[:limit]


class _FakeTaskManager:
    """按 task_id 派发结果：Exception 实例模拟新契约的领域异常失败。"""

    def __init__(self, outcomes):
        self.outcomes = outcomes
        self.calls = []

    def restart_task(self, task_id, resume_from_checkpoint=True):
        self.calls.append((task_id, resume_from_checkpoint))
        outcome = self.outcomes[task_id]
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def _make_command_service(app_factory, monkeypatch, tasks, manager):
    service = TaskCommandService()
    service._app = app_factory
    monkeypatch.setattr(
        "ding_stream_service.task_commands.task_repository",
        _FakeTaskRepository(tasks),
    )
    monkeypatch.setattr("ding_stream_service.task_commands.task_manager", manager)
    return service


def test_batch_restart_isolates_domain_failures_and_maps_status(app_factory, monkeypatch):
    """回归：restart_task 新契约失败抛领域异常，批量重启须逐任务隔离且正确标记成败。"""
    tasks = [
        {"id": "task-1", "name": "坏任务", "task_type": "google_sheet_C3", "status": "error"},
        {"id": "task-2", "name": "好任务", "task_type": "google_sheet_C3", "status": "error"},
    ]
    manager = _FakeTaskManager({
        "task-1": ConflictError(
            "任务重启失败: 所选 Google Sheet 正在被其他任务使用，无法启动"
        ),
        "task-2": {
            "message": "任务重启成功",
            "restart_from_step": 12,
            "restart_reason": "任务执行出错",
        },
    })
    service = _make_command_service(app_factory, monkeypatch, tasks, manager)

    result = service.restart_error_tasks(
        ParsedBatchRestartCommand(status="error", limit=5)
    )

    assert result["status"] == "success"
    assert result["processed"] == 2
    by_id = {item["task_id"]: item for item in result["results"]}
    assert by_id["task-1"]["restart_status"] == "error"
    assert "Google Sheet" in by_id["task-1"]["message"]
    assert by_id["task-2"]["restart_status"] == "success"
    assert by_id["task-2"]["restart_from_step"] == 12
    assert manager.calls == [("task-1", True), ("task-2", True)]


def test_batch_restart_marks_queued_item(app_factory, monkeypatch):
    """回测 sheet 被占时 restart_task 返回 queued，批量项标记为 queued 而非失败。"""
    tasks = [
        {"id": "task-q", "name": "排队任务", "task_type": "backtest_training", "status": "error"},
    ]
    manager = _FakeTaskManager({
        "task-q": {
            "message": "同一个 Google Sheet 已有回测任务正在运行，当前任务保持待执行: other",
            "start_error": "同一个 Google Sheet 已有回测任务正在运行，当前任务保持待执行: other",
            "task_id": "task-q",
            "queued": True,
            "restart_from_step": 3,
        },
    })
    service = _make_command_service(app_factory, monkeypatch, tasks, manager)

    result = service.restart_error_tasks(
        ParsedBatchRestartCommand(status="error", limit=5)
    )

    assert result["status"] == "success"
    assert result["results"][0]["restart_status"] == "queued"


def test_single_restart_maps_new_contract_to_reply_status(app_factory, monkeypatch):
    """单任务重启：成功 dict 无 status 键，命令层须补 status 供回复渲染判定。"""
    tasks = [
        {"id": "task-1", "name": "单任务", "task_type": "google_sheet", "status": "error"},
    ]
    manager = _FakeTaskManager({
        "task-1": {
            "message": "任务重启成功",
            "restart_from_step": 7,
            "restart_reason": "用户手动重启",
        },
    })
    service = _make_command_service(app_factory, monkeypatch, tasks, manager)

    result = service.restart_task(
        ParsedRestartCommand(target="task-1", target_type="id")
    )

    assert result["status"] == "success"
    assert result["restart_from_step"] == 7
    assert result["task_name"] == "单任务"


def test_single_restart_reports_domain_failure(app_factory, monkeypatch):
    tasks = [
        {"id": "task-1", "name": "单任务", "task_type": "google_sheet", "status": "error"},
    ]
    manager = _FakeTaskManager({
        "task-1": ConflictError("任务重启失败: queue full"),
    })
    service = _make_command_service(app_factory, monkeypatch, tasks, manager)

    result = service.restart_task(
        ParsedRestartCommand(target="task-1", target_type="id")
    )

    assert result["status"] == "error"
    assert "queue full" in result["message"]


def test_format_batch_restart_reply_counts_queued_as_success():
    command = ParsedBatchRestartCommand(status="error", limit=5)
    result = {
        "status": "success",
        "target_status": "error",
        "total": 2,
        "processed": 2,
        "results": [
            {
                "task_id": "a",
                "task_name": "排队任务",
                "task_type": "backtest_training",
                "restart_status": "queued",
                "message": "排队中",
                "restart_from_step": 1,
            },
            {
                "task_id": "b",
                "task_name": "冲突任务",
                "task_type": "google_sheet",
                "restart_status": "error",
                "message": "冲突",
                "restart_from_step": None,
            },
        ],
    }

    message = format_batch_restart_reply(result, command, "测试用户")

    assert "- **结果**：已排队" in message
    assert "- **结果**：失败" in message
    assert "- **结果**：成功" not in message

from ding_stream_service.task_commands import (
    extract_task_id,
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

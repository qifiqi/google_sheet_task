from ding_stream_service.handler import DingStreamEventHandler


def test_process_message_returns_help_menu_when_only_mentioned():
    handler = DingStreamEventHandler()

    reply = handler.process_message("@测试机器人", "张三")

    assert "### 任务助手菜单" in reply
    assert "- **用户**：张三" in reply
    assert "查看运行任务" in reply
    assert "查看停止任务" in reply
    assert "创建项目" not in reply

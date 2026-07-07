from ding_stream_service.handler import build_dingtalk_reply_payload


def test_build_dingtalk_reply_payload_uses_markdown_for_markdown_reply():
    payload = build_dingtalk_reply_payload("### 任务助手菜单\n\n- **用户**：张三")

    assert payload["msgtype"] == "markdown"
    assert payload["markdown"]["title"] == "任务助手菜单"
    assert payload["markdown"]["text"].startswith("### 任务助手菜单")


def test_build_dingtalk_reply_payload_wraps_plain_reply_as_markdown():
    payload = build_dingtalk_reply_payload("【当前运行任务】\n用户：张三")

    assert payload["msgtype"] == "markdown"
    assert payload["markdown"]["title"] == "任务助手"
    assert "【当前运行任务】" in payload["markdown"]["text"]

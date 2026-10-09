"""钉钉回复消息格式化（实现已上移 app.utils.ding_talk_notifier，此处再导出）。

ding_stream_service 虽为独立进程，但本就依赖 app（create_app/仓储层），
消息格式单一来源收敛到 app/utils/ding_talk_notifier.build_markdown_message。
"""

from __future__ import annotations

from app.utils.ding_talk_notifier import Field, build_markdown_message

__all__ = ["Field", "build_markdown_message"]

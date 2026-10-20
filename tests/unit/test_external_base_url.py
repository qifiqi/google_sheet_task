"""外部通知链接基地址解析回归（钉钉"查看详情"域名）。

优先级 DING_TALK_DETAIL_BASE_URL > PUBLIC_BASE_URL > BASE_URL；末尾斜杠统一
去掉；非 http/https 或缺主机的值被拒绝（展示链接不接受 javascript: 等 scheme）。
该地址只用于生成通知正文里的链接，服务端不请求它（无 SSRF 面）。
"""

import pytest

from app.utils.ding_talk_notifier import (
    get_external_base_url,
    resolve_external_base_url,
)


def _config(**values):
    base = {"BASE_URL": "http://localhost:5000",
            "PUBLIC_BASE_URL": "",
            "DING_TALK_DETAIL_BASE_URL": ""}
    base.update(values)
    return base


def test_detail_base_url_wins_over_public_and_base():
    config = _config(
        DING_TALK_DETAIL_BASE_URL="http://param.jaspil.cn",
        PUBLIC_BASE_URL="https://public.example.com",
        BASE_URL="http://internal:5000",
    )
    assert resolve_external_base_url(config) == "http://param.jaspil.cn"


def test_public_base_url_used_when_detail_missing():
    config = _config(PUBLIC_BASE_URL="https://public.example.com")
    assert resolve_external_base_url(config) == "https://public.example.com"


def test_base_url_fallback():
    assert resolve_external_base_url(_config()) == "http://localhost:5000"


def test_trailing_slash_is_stripped():
    config = _config(DING_TALK_DETAIL_BASE_URL="http://param.jaspil.cn/")
    assert resolve_external_base_url(config) == "http://param.jaspil.cn"


@pytest.mark.parametrize("value", ["javascript:alert(1)", "ftp://example.com", "param.jaspil.cn", "/relative"])
def test_invalid_scheme_or_host_rejected(value):
    assert resolve_external_base_url(_config(DING_TALK_DETAIL_BASE_URL=value)) == ""


def test_none_config_returns_empty():
    assert resolve_external_base_url(None) == ""


def test_no_app_context_returns_empty():
    assert get_external_base_url() == ""


def test_task_detail_link_shape_with_new_domain():
    """钉钉链接拼接形态：基地址 + 任务详情路径（去掉末尾斜杠后单斜杠拼接）。"""
    config = _config(DING_TALK_DETAIL_BASE_URL="http://param.jaspil.cn/")
    base = resolve_external_base_url(config)
    link = f"{base}/google-sheet/detail?task_id=abc123"
    assert link == "http://param.jaspil.cn/google-sheet/detail?task_id=abc123"

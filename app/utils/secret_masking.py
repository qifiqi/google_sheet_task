"""对外展示用的敏感内容脱敏；内部读取使用原始值。"""
from __future__ import annotations

import json

MASK = "***"
_MASK_MARKERS = ("***", "…")
_SENSITIVE_KEYS = (
    "private_key",
    "refresh_token",
    "client_secret",
    "access_token",
    "id_token",
    "token",
    "password",
)


def _truncate(value, head=8, tail=4):
    text = str(value or "")
    if not text:
        return ""
    if len(text) <= head + tail + 3:
        return MASK
    return f"{text[:head]}…{text[-tail:]}"


def mask_token_context(raw):
    """把 Token JSON 中的敏感字段截断；非敏感字段保留，便于前端识别类型。"""
    if isinstance(raw, dict):
        data = dict(raw)
    else:
        text = str(raw or "")
        if not text:
            return ""
        try:
            data = json.loads(text)
        except (TypeError, ValueError):
            return _truncate(text, head=12, tail=6)

    if not isinstance(data, dict):
        return _truncate(data, head=12, tail=6)

    masked = dict(data)
    for key in _SENSITIVE_KEYS:
        if masked.get(key):
            masked[key] = _truncate(masked[key])
    return json.dumps(masked, ensure_ascii=False, indent=2)


def is_masked_token_context(raw) -> bool:
    """判断提交值是否是脱敏回显（不能写回覆盖真实 Token）。"""
    if isinstance(raw, dict):
        text = json.dumps(raw, ensure_ascii=False)
    else:
        text = str(raw or "")
    return any(marker in text for marker in _MASK_MARKERS)

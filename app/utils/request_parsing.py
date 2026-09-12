"""请求解析入口（Pydantic v2，替代 request_validation）。

parse_body/parse_query 在解析入口就地把 pydantic.ValidationError 转为
app.exceptions.ValidationError，复用现有 400 信封链（errors.py 零改动）。
"""

from __future__ import annotations

from flask import g, request
from pydantic import ValidationError as PydValidationError

from app.exceptions import ValidationError


def _format_errors(exc: PydValidationError) -> str:
    """首条错误转中文消息（字段位置 + 原始 msg）。"""
    first = exc.errors()[0] if exc.errors() else {}
    loc = ".".join(str(part) for part in first.get("loc", ())) or "body"
    return f"请求参数错误: {loc} {first.get('msg', '校验失败')}"


def parse_body(schema):
    """解析 JSON body 为 schema 实例；失败抛 ValidationError → 400 信封。"""
    payload = request.get_json(silent=True)
    if payload is None:
        payload = request.form.to_dict() or {}
    try:
        validated = schema.model_validate(payload)
    except PydValidationError as exc:
        raise ValidationError(_format_errors(exc)) from exc
    g.validated = validated
    return validated


def parse_query(schema):
    """解析 query 参数为 schema 实例；失败抛 ValidationError。"""
    try:
        return schema.model_validate(request.args.to_dict())
    except PydValidationError as exc:
        raise ValidationError(_format_errors(exc)) from exc

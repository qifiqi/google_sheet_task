"""轻量请求校验（见 docs/design/data-layer-refactor/04 §2.2）。

校验失败抛 ValidationError → 全局错误处理器统一转 400 信封；
路由内不再手写参数错误分支。不引入 pydantic 等重依赖。
"""
from flask import request

from app.exceptions import ValidationError


def _get_body():
    data = request.get_json(silent=True)
    if data is None:
        data = request.form.to_dict() or {}
    if not isinstance(data, dict):
        raise ValidationError("请求体必须是 JSON 对象")
    return data


def validate_body(required=None, types=None):
    """校验 JSON body 必填字段与类型，返回 body dict。

    required: 必填字段名列表（None、空串视为缺失）；
    types:    {字段名: 期望类型}，字段存在且非 None 时校验 isinstance
              （bool 是 int 子类型，声明 int 时显式拒绝 bool）。
    """
    data = _get_body()
    for name in required or []:
        value = data.get(name)
        if value is None or (isinstance(value, str) and value == ""):
            raise ValidationError(f"缺少必填字段: {name}")
    for name, expected in (types or {}).items():
        if name not in data or data[name] is None:
            continue
        if expected is int and isinstance(data[name], bool):
            raise ValidationError(f"字段 {name} 类型应为 int")
        if not isinstance(data[name], expected):
            raise ValidationError(f"字段 {name} 类型应为 {expected.__name__}")
    return data


def require_query(name, default=None, cast=None):
    """读取 query 参数；缺失返回 default，存在但转换失败抛 ValidationError。"""
    value = request.args.get(name)
    if value is None or value == "":
        return default
    if cast is not None:
        try:
            return cast(value)
        except (TypeError, ValueError):
            raise ValidationError(f"参数 {name} 格式错误")
    return value

"""orjson 统一 JSON 出入口（全库序列化/反序列化唯一封装）。

- ``dumps`` 返回 str（对齐 json.dumps 的字符串语义，便于日志拼接、LIKE 匹配与入库）；
- ``loads`` 接受 str/bytes/bytearray；
- ``JSONDecodeError`` 重导出 stdlib 异常类（orjson.JSONDecodeError 是其子类），
  既有 ``except json.JSONDecodeError`` 的捕获语义不变；
- ``ensure_ascii``/``separators`` 仅为兼容既有调用点而接受后忽略：
  orjson 恒为 UTF-8 非转义紧凑输出，解析结果等价。

保留 stdlib json 的两个场景（文件里出现 ``import json`` 即例外，均有注释说明）：
1. ``allow_nan=False`` 的 NaN/Inf 守卫（``app/utils/return_series.py``、
   ``app/services/backtest_multi_product_service.py``）：orjson 会把 NaN/Infinity
   静默序列化为 null，无法等价表达"遇 NaN 抛错"的数据完整性语义；
2. ``json.loads(..., parse_constant=...)`` 解析钩子（``app/services/config_manager.py``）：
   orjson 不支持解析钩子，保留 stdlib 以维持"非法 JSON 常量"的原文案与拦截点。

与 stdlib 的已知行为差异（均为可接受的标准格式收敛）：
- datetime 不再走 ``default=str`` 的 ``str()`` 文案，orjson 原生输出 ISO 8601（带 T）；
- dict/list 混入 numpy 标量/数组时，orjson 输出真实 JSON 数值/数组，
  而 stdlib + ``default=str`` 会把整体 stringify 成字符串。
- Flask 侧经 OrjsonJSONProvider 后，响应中文不再转义为 ``\\uXXXX``（解析结果等价）。
"""
from __future__ import annotations

from json import JSONDecodeError  # noqa: F401  重导出：orjson.JSONDecodeError 的父类

import orjson
from flask.json.provider import DefaultJSONProvider

__all__ = ["dumps", "loads", "JSONDecodeError", "OrjsonJSONProvider"]


def dumps(
    data,
    *,
    default=None,
    sort_keys: bool = False,
    indent=None,
    ensure_ascii=None,  # 兼容旧调用点，忽略；orjson 恒为非转义 UTF-8
    separators=None,  # 兼容旧调用点，忽略；orjson 恒为紧凑分隔符
) -> str:
    """序列化为 JSON 字符串；indent 传入真值时按 2 空格缩进（orjson 仅支持 2）。"""
    option = orjson.OPT_SERIALIZE_NUMPY
    if sort_keys:
        option |= orjson.OPT_SORT_KEYS
    if indent:
        option |= orjson.OPT_INDENT_2
    return orjson.dumps(data, default=default, option=option).decode("utf-8")


def loads(data):
    """反序列化；接受 str/bytes/bytearray/memoryview。"""
    return orjson.loads(data)


class OrjsonJSONProvider(DefaultJSONProvider):
    """Flask jsonify / request.get_json 的 orjson 实现。

    default 沿用 Flask DefaultJSONProvider 语义（datetime→http_date、UUID、
    dataclass…），保持既有 API 响应的序列化行为；sort_keys 沿用 Flask 默认 True。
    """

    sort_keys = True

    def dumps(self, obj, **kwargs):  # Flask 内部透传的编码参数由 option 固定，不透传
        return orjson.dumps(
            obj, default=self.default, option=orjson.OPT_SERIALIZE_NUMPY
        ).decode("utf-8")

    def loads(self, s, **kwargs):
        return orjson.loads(s)

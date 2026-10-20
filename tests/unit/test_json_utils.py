"""orjson 统一封装（app/utils/json_utils.py）行为测试。"""

import json as stdlib_json
from datetime import datetime

import pytest

from app.utils.json_utils import JSONDecodeError, OrjsonJSONProvider, dumps, loads


def test_dumps_returns_str_compact_utf8():
    assert dumps({"a": 1, "name": "中文"}) == '{"a":1,"name":"中文"}'


def test_dumps_accepts_legacy_kwargs():
    # ensure_ascii/separators 接受后忽略：orjson 恒为 UTF-8 非转义紧凑输出
    assert dumps({"a": 1}, ensure_ascii=False, separators=(",", ":")) == '{"a":1}'


def test_dumps_sort_keys_and_indent():
    assert dumps({"b": 1, "a": 2}, sort_keys=True) == '{"a":2,"b":1}'
    assert dumps({"a": [1, 2]}, indent=4) == '{\n  "a": [\n    1,\n    2\n  ]\n}'


def test_dumps_default_str_fallback():
    class Unknown:
        def __str__(self):
            return "U"

    assert dumps({"x": Unknown()}, default=str) == '{"x":"U"}'


def test_dumps_datetime_native_iso():
    # 与 stdlib + default=str 的已知差异：orjson 原生序列化 datetime 为 ISO 8601（带 T），不调用 default
    assert dumps(datetime(2026, 1, 2, 3, 4, 5)) == '"2026-01-02T03:04:05"'


def test_dumps_numpy_roundtrip():
    np = pytest.importorskip("numpy")
    payload = {"v": np.float64("1.5"), "arr": np.array([1, 2])}
    assert loads(dumps(payload)) == {"v": 1.5, "arr": [1, 2]}


def test_dumps_non_str_keys_fallback_to_stdlib():
    # stdlib 静默把非字符串键转字符串；orjson 严格拒绝，封装回退 stdlib 保持语义
    assert dumps({2024: [1, 2], "a": 1}) == '{"2024":[1,2],"a":1}'
    assert dumps({2024: 1}, sort_keys=True) == '{"2024":1}'


def test_dumps_tuple_fallback_to_stdlib():
    assert loads(dumps({"t": (1, 2)})) == {"t": [1, 2]}


def test_dumps_big_int_fallback_to_stdlib():
    # orjson 整数上限 64bit，超出抛 TypeError；stdlib 任意精度，封装回退保持语义
    big = 2**70
    assert loads(dumps({"id": big})) == {"id": big}
    with pytest.raises(TypeError):
        import orjson

        orjson.dumps(big)


def test_dumps_unserializable_type_still_raises():
    class Unknown:
        pass

    with pytest.raises(TypeError):
        dumps({"x": Unknown()})


def test_flask_provider_non_str_keys_fallback():
    from flask import Flask, jsonify

    app = Flask(__name__)
    app.json = OrjsonJSONProvider(app)
    with app.test_request_context():
        body = jsonify({2024: {"a": 1}, 2025: {"a": 2}}).get_data(as_text=True)
    assert stdlib_json.loads(body) == {"2024": {"a": 1}, "2025": {"a": 2}}


def test_loads_accepts_bytes():
    assert loads(b'{"a":1}') == {"a": 1}


def test_jsondecodeerror_reexport_catches_orjson_error():
    # 重导出的就是 stdlib 类；orjson.JSONDecodeError 是其子类，既有 except 语义不变
    assert JSONDecodeError is stdlib_json.JSONDecodeError
    with pytest.raises(JSONDecodeError):
        loads("{bad json")
    try:
        loads("{bad json")
    except stdlib_json.JSONDecodeError:
        pass
    else:
        pytest.fail("orjson 解析错误应可被 stdlib json.JSONDecodeError 捕获")


def test_flask_provider_jsonify_and_get_json():
    from flask import Flask, jsonify, request

    app = Flask(__name__)
    app.json = OrjsonJSONProvider(app)
    with app.test_request_context(json={"a": 1}):
        assert request.get_json() == {"a": 1}
        body = jsonify({"name": "中文", "b": 1, "a": 2}).get_data(as_text=True)
    assert stdlib_json.loads(body) == {"name": "中文", "b": 1, "a": 2}
    assert body.index('"a"') < body.index('"b"')  # sort_keys 与 Flask 默认一致
    assert "中文" in body  # 非转义 UTF-8 输出

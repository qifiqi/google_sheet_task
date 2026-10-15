# 2026-10-15 orjson 统一 JSON 序列化

## 背景

全库 JSON 序列化/反序列化从 stdlib `json` 切换到 orjson（Rust 实现，序列化约 5-10x 提速），
收敛到唯一封装 `app/utils/json_utils.py`，并让 Flask `jsonify`/`request.get_json` 同步走 orjson。

## 改动范围

- 新增 `app/utils/json_utils.py`：
  - `dumps()` 返回 str（对齐 `json.dumps` 字符串语义），`ensure_ascii`/`separators`
    参数接受后忽略（orjson 恒为 UTF-8 非转义紧凑输出）；`sort_keys`/`indent`/`default` 透传；
  - `loads()` 接受 str/bytes/bytearray；
  - `JSONDecodeError` 重导出 stdlib 类（orjson.JSONDecodeError 是其子类，
    既有 `except json.JSONDecodeError` 语义不变）；
  - `OrjsonJSONProvider`（Flask DefaultJSONProvider 子类）在 `create_app()` 注册，
    jsonify/get_json 走 orjson，`sort_keys=True` 保持 Flask 默认键序；
- 批量转换 app/ 全部 38 个含 `import json` 的文件 + `scripts/` 2 个脚本
  （`json.dumps/loads/JSONDecodeError` → `dumps/loads/JSONDecodeError`）；
- `requirements.txt` 新增 `orjson`（3.13.0）；
- 新增 `tests/unit/test_json_utils.py`（13 个用例：紧凑输出、旧参数兼容、
  sort_keys/indent、default 回退、numpy、bytes、异常子类、Provider jsonify/get_json、
  非字符串键回退）。

## dumps 契约：stdlib 兼容语义 + orjson 快路径

orjson 严格模式拒绝的类型（非字符串 dict 键、tuple 等，stdlib 静默容忍）在封装内
回退 stdlib `json.dumps`（紧凑、非转义），调用点不因换库产生新 500/TypeError。
回退仅发生在少数怪类型 payload；常规大 payload（K线、指标、结果 JSON）走 orjson 快路径。

### 保留纯 stdlib json 的例外（文件内有注释）

| 文件 | 位置 | 原因 |
| --- | --- | --- |
| `app/utils/return_series.py` | 收益序列 3 列 | `allow_nan=False` NaN/Inf 守卫：orjson 把 NaN 静默序列化为 null，无法等价"遇 NaN 抛错" |
| `app/services/backtest_multi_product_service.py` | `_build_returns_json`、`result_json` | 同上 |
| `app/services/google_sheet_tasks/base.py` | `_save_task_result` 的 parameters/result | 同上（结果落库守卫） |
| `app/services/config_manager.py` | `_deserialize_config_value` ×2 | `parse_constant` 解析钩子 orjson 不支持，保留"非法 JSON 常量"拦截点 |

其余例外：`migrations/`（版本化历史不回改）、`tests/`（行为基线保持 stdlib 独立）、
`ding_stream_service/`、`stock_sdk/`（本就无 json 使用）。

## 与 stdlib 的已知行为差异（均为主格式收敛，解析结果等价）

1. `default=str` 不再被 datetime 触发：orjson 原生输出 ISO 8601（`2026-01-01T00:00:00`，
   带 T），原为 `str()` 的空格分隔文案；
2. numpy 标量/数组混入 dict/list 时输出真实 JSON 数值/数组（原 stdlib+default=str
   会整体 stringify 成字符串）；封装恒开 `OPT_SERIALIZE_NUMPY`；
3. 响应体中文不再转义为 `\uXXXX`（orjson 恒 UTF-8，解析结果等价，payload 更小）；
4. indent 只支持 2 空格（原 `indent=4` 的 debug 日志变为 2 空格）。

## 兼容性核查记录

- **Task.config LIKE 匹配**：`task_repository.py:80-81` 已同时匹配带空格与紧凑两种
  `"stock_code"` 形态，orjson 紧凑输出命中第二种，无需改动；
- `_hash_text`（多品种固定产品缓存键）：sha1 输入从带空格变为紧凑 JSON，历史缓存
  一次性 miss 后重算重建，无正确性影响；
- `parameter_signature` 仅单次请求内用于排序/分组，不落库，无跨版本比对；
- Pydantic v2 请求校验走 pydantic-core（Rust），不在本次范围；
- `requests`/`gspread` 等三方库内部 json 不在范围。

## 修复过程中发现并解决的回归

1. `OrjsonJSONProvider` 初版未把 `sort_keys` 映射为 `OPT_SORT_KEYS`，响应键序漂移（单测捕获）；
2. `base.py` 的 `allow_nan=False` 调用点被机械替换后运行时 TypeError（封装按设计不接受
   该参数、报错显式），导致 16 个集成/unit 测试失败——已恢复 stdlib 守卫并登记例外；
3. 非字符串 dict 键（metrics 年份键）在 orjson 严格模式下抛 `Dict key must be str`，
   HTTP 边界 500——封装与 Provider 增加回退路径解决。注意：**混合 int/str 键的字典在
   换库前 jsonify（sort_keys=True）也无法序列化**，纯 int 键才是合法存量场景。

## 全局审查记录（2026-10-15 迁移后复审）

经验性边界对照（orjson 3.13.0 vs stdlib，见 `tests/unit/test_json_utils.py`）：

- 超出 64bit 的整数：orjson 抛 `TypeError`（"Integer exceeds 64-bit range"），
  封装 TypeError 回退链可兜住，stdlib 任意精度保持语义（已加测试锁定）；
- tuple：orjson 原生序列化为 JSON 数组，无需回退；
- float 输出：`1e20`/`0.1`/`-0.0`/长尾小数与 stdlib 逐字节一致（均为最短往返表示）；
- **loads 侧 NaN/Infinity 字面量从严**：stdlib `json.loads` 接受 `NaN`/`Infinity`
  （返回 nan/inf），orjson 抛 JSONDecodeError。历史数据风险评估：落库写侧
  （result/parameters/returns）一直带 `allow_nan=False` 守卫不会产生 NaN 字面量；
  读侧 `parse_lenient_json`、`models._json_object_or_empty` 等的
  `except JSONDecodeError` 均能接住（orjson.JSONDecodeError 是其子类），
  降级路径与既有畸形数据处理一致；
- 全库 `loads` 解析钩子仅 config_manager 的 `parse_constant`（已登记例外），
  无 `parse_float`/`object_hook`/`cls` 用法；无 `ensure_ascii=True` 显式依赖；
- `c5/c7/base` 的 `kline_range` dumps 未过 `sanitize_json_value`：经查 kline 原始
  数据来自 SQLite/API（缺失为 None 非 NaN），`None→null` 两种序列化行为一致，
  numpy 数值 orjson 原生支持，不构成行为差异，保持原样（避免热路径全量遍历）；
- `ttl_cache` Word 导出缓存键含序列化摘要：格式紧凑化导致 sha256 变化，存量磁盘
  缓存一次性 miss 后按新键重建，旧文件由 mtime TTL 清扫自愈；
- `hashlib` 其他用途（dfcf ut、钉钉签名）与 JSON 序列化无关。

## 测试结果

`python -m pytest tests/unit tests/integration`：**876 passed, 1 failed, 10 skipped**。
唯一失败 `test_template_result_api.py::test_template_crud_envelope` 为**存量问题**
（在改动前提交 e9a06e65 用 git worktree 复跑同样失败）：测试 POST 的模板 config 无
`sheets` 键，而任务配置统一后 `validate_task_config_shape` 要求 sheets 必填。
该用例期望需按配置统一的新规范更新（与本次 orjson 迁移无关）。

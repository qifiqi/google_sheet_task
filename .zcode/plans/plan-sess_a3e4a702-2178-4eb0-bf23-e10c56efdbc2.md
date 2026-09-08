修复系统配置体系（app/services/config_manager.py 及直接关联消费方）

## 一、config_manager.py 核心修复（主要改动）

1. **统一类型序列化/反序列化（修布尔反转 bug）**
   - 写路径 `set_config`：bool 用 `json.dumps`（"true"/"false"），None → "null"，int/float 用 `json.dumps`，dict/list 保持 json.dumps，str 原样。
   - 读路径：抽出公共 `_deserialize_value()`，对字符串先尝试 `json.loads`，失败保持原样；并加**旧数据兼容层**：`"True"/"False"` → bool、`"None"/"null"` → None（存量库里的历史字符串自动纠正）。
   - 实施时先 grep 校验所有 `get_config` 消费方没有依赖 `== "True"` 字符串比较的写法（重点看 task_watchdog、dfcf_api、backtest_multi_product_service、google_sheet_* 服务），确认返回真 bool 对它们安全。
2. **负缓存**：`get_config` 查库确认 key 不存在时，向缓存写入哨兵值 `_MISSING`，后续调用直接返回 default，不再反复查库（修 auth 每请求查库、google_sheet_client 每次建连查库）。`set_config` 写入时覆盖哨兵，保证一致性。
3. **线程安全**：`_cache` 增加 `threading.RLock`，`_load_configs/get_config/set_config/delete_config` 持锁访问。
4. **去掉冗余全表刷新**：
   - `get_all_configs()` 和 `get_google_sheet_config()` 增加参数 `force_refresh=False`，默认只读缓存；config_api 需要强一致的入口显式传 True。
   - `update_configs()` 末尾的一次 `_load_configs()` 保留，`set_config` 单条写入本就更新缓存。
5. **日志脱敏**：`set_config` 成功日志只打 key 不打 value；value 打印降为 debug 并对疑似敏感 key（含 token/secret/password/key 字样）打码。

## 二、直接关联消费方小改

6. **app/routes/config_api.py**：
   - GET /config 去掉 `refresh_cache()`（保留 `get_all_configs(force_refresh=True)` 一次加载），消除双倍全表查询。
   - `logger.debug(f"返回配置数据: {configs}")` 改为不打印完整配置值。
   - PUT /system-configs/<key> 的直接 ORM 写路径保持不动（管理端行为不变），仅依赖 refresh_cache（已有）。
7. **统一布尔解析助手**：在 `config_manager.py` 增加 `coerce_bool(value, default)` 模块函数，替换 `task_watchdog.py:137` 的裸 `bool(...)`；其余 7-8 处布尔解析写法（dfcf_api、backtest_multi_product_service 等）本次**不改**（行为等价、避免扩大改动面），仅在 AGENTS.md 记录规范。
8. **app/config.py**：`init_config()` 种子补充 `google_sheet_http_timeout: 30`（google_sheet_client.py:122 已在消费但从未播种）；`JWT_SECRET_KEY` 不入库（安全考虑，保持 env 提供）。

## 三、明确不做（仅建议，涉行为/部署变更）

- google_sheet_client.py 运行期写进程级 `os.environ['HTTP_PROXY']` 的并发问题（改为 session 级代理需回归测试 Google 连通性）。
- auth.py 运行期读 env `AUTH_ENABLED`（疑似有意的安全兜底）、kline_service STOCK_BASE_URL 双源与硬编码内网 IP、恢复 startup.py 启动期 init_config 播种、admin/admin123 默认密码、死导入清理——在最终报告中列出建议，不在本次代码中改动。

## 四、验证

- 定向测试：`pytest tests/test/test_p0_p1_refactor.py`；若 config_manager 有专属测试文件则一并跑。
- 手工验证脚本（python -c）：set_config(True) → refresh_cache → get_config 返回 True（bool 而非 "True"）；set 不存在的 key 后 get 不再触发 SQL（可通过开启 SQLALCHEMY_ECHO 或 mock 计数验证）。
- 确认 watchdog_enabled=False 场景：设 False → refresh → 重启读回为 False，看门狗不再误启。

## 五、文档

- 按仓库规范更新 AGENTS.md「配置系统」小节：记录类型往返规则（bool/None json 化）、负缓存行为、布尔解析统一入口 `coerce_bool`。
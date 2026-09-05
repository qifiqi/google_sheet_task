# Google Sheet 执行链路

## 客户端（app/services/google_sheet_client.py）

`GoogleSheet` 类是所有 Sheet 网络 IO 的底层封装：

- 凭证：`Credentials.from_authorized_user_file(token_file)` → `gspread.authorize` → `open_by_key` → 选 worksheet（大小写不敏感回退匹配）。
- 代理：`_apply_proxy_settings()` 写 `HTTP_PROXY/HTTPS_PROXY` 环境变量 + session.proxies（来源 SystemConfig `proxy_url`，用于 Google 访问）。
- 超时：`google_sheet_http_timeout`（默认 30s），优先 `client.set_timeout`，否则 patch requests session。
- **网络错误识别** `_is_network_error`：gspread APIError status≥500 或 429，或消息关键词（connection/timeout/502/503/504/429 等）。
- **重试与重连** `_retry_network_operation`：指数退避（delay×2^attempt），每次失败 `_reconnect()`（关旧连接、重载凭证、重建 client）；重试耗尽抛 **`RetryableNetworkTaskError`**（app/utils/task_error_utils.py）。
- 任务层通过 `is_retryable_network_error(exc)` 遍历异常链识别该类型，写 `[NETWORK_RETRYABLE]` 前缀供看门狗自动重启。

> 网络问题的修改优先落在这里，其次才是 google_sheet_service*.py 和 task 层；不要在上层散乱加 try/except。

读写 API：`get_cell / get_range / get_ranges / get_range_2d / get_cells_batch / update_cell / update_jumped_cells / update_row(s) / clear_range / clear_jumped_cells / get_trade_count_with_retry`（重试参数来自 `api_retry_max_attempts=10`、`api_retry_delay=30`）。`calculate_stock_column` 按每股票间隔 9 列从 M 列起定位。

## Token 池（google_sheet_token_service.py）

- Token 存 `GoogleSheetToken` 表：`token_file`（唯一）、`token_context`（内容，运行时经 `ensure_token_file` 落地为文件）、`task_usage_count` / `current_in_use_count` / `max_usage_count`（0 不限）、`is_active`、`task_type`（google_sheet / backtest_training）。
- `prepare_task_config`：支持 `token_selection="__random__"`（`RANDOM_TOKEN_VALUE`）随机挑可用 token。
- `validate_task_start` + `increment_usage` / `release_usage` 维护占用；全局上限 `google_sheet_token_global_max_usage`（0 不限）。
- 启动时 `reset_google_sheet_token_occupancy()` 清零计数（内存态不跨进程持久）。

## Sheet 注册表（google_sheet_registry_service.py）

`GoogleSheet` 表按 `spreadsheet_id + registry_scope` 唯一：C 系列（c3/c4/c5/c7）共用 scope `c_series`，`backtest_training` 独立 scope。`table_type` 标记用途。执行前 `acquire_for_task`（is_in_use / current_task_id），结束释放；单品回测必须使用 `table_type=backtest_training` 的 Sheet（`validate_backtest_training_sheet`）。

## C 系列执行器

全部继承 `google_sheet_service_base.py::BaseGoogleSheetService`，公共能力：

- `_init_google_sheet`（兼容单表/多表/嵌套 sheet 配置）、可中断睡眠 `_interruptible_sleep`（响应取消）、轮询延迟 `execution_delay_min/max`（20~30s）
- 日志（任务日志 + DB TaskLog）、钉钉通知（`error_dd` / `task_ok_to_dd`）
- 收益序列落库 `send_stock_param_result_data`（→ `TaskResultReturn`）、模型汇总索引刷新 `_refresh_model_summary_index`
- JSON 安全化 `_sanitize_json_value`、结果摘要 `_summarize_result_for_log`

| 服务 | 文件 | 要点 |
|---|---|---|
| C3 | google_sheet_service.py | `execute_task` → `get_bdl`（支持 current_step 断点续跑）；写参数格（`c3_parameter_positions`，佣金格 `C3_commission_cell=B5`）→ 触发校验格（I15/I16）→ 轮询 → 读输出（`c3_output_range_1/2`、K/O 列）；`cell_kline_data` 本地计算 K 线输入，优先 `config.end_date` |
| C4 | _C4.py | 列驱动模板（`c4_input_column_a/b`，输出 range_1/2 + J/L 列）；无断点参数 |
| C5 | _C5.py | 断点续跑（`_get_resume_start_index`）、自定义 K 线（`_get_custom_kline_data`）、参数去重、百分比归一 `_to_decimal_ratio` |
| C7 | _C7.py | 多模型版本（c7_0_3 与 legacy layout）；C7.0.3 直接读 Sheet OHLC 列（CC..CG，`c7_0_3_kline_start_row=2`）本地算指数收益；随机价格扩展（price_mode / random_price_range / random_group_count） |

C5 专用异常体系在 `app/exceptions/c5_exceptions.py`（Network/RateLimit/Execution/Validation/Timeout/Data 六类，带 error_code）。C7 结果归一在 `app/utils/c7_result_normalizer.py`。

### custom K 线模式（C5/C7）

`config.kline_source = custom` 表示用户已在 Sheet 输入列维护好 K 线，任务级约定：

- 只在 `get_bdl()` 预计算阶段读一次现有输入列，构造 `Kline_key=custom` 组合；执行时只写 xm/ml 等参数，**不清空、不重写 K 线输入列**。
- 仍读取现有 K 线行数以确定收益读取范围和结果的 K 线首尾日期。
- `TaskCreationMixin._normalize_task_config_for_type()` 会把 `market_type` 归一为 `custom` 并禁用 price_mode/kline_adjustment/date_range_mode/exclude_recent_years/start_date/end_date。
- **不要**把 custom 分支放进 `_get_all_parameters()` 内部判断——那会重新进入自动行情获取/转换链路，违背任务级语义。

## C31 批量拆分

`google_sheet_C31` 不是独立执行器，而是前端批量创建页；最终在 `TaskCreationMixin.batch_create_and_start_task()` 中拆成多个 C3 子任务：

1. 输入 `{base_task_name, sheets[], stock_codes[], parameters[][]}` → `_normalize_c31_parameter_groups` + `itertools.product` 生成组合。
2. 校验组合数与 Sheet 数相等或整数倍（`_is_count_compatible`）；sheet title 形如 `策略A-1y-3]`，按 `year_n` 分组。
3. 每个股票 × 参数组合 × 年份 Sheet 生成一个 C3 子任务（`_materialize_c31_parameter_combo`），`end_date` 默认昨天；未指定 token 时用 `RANDOM_TOKEN_VALUE` 随机选取。
4. 逐个 `create_task` + `start_task`（间隔 0.5s），股票元数据 upsert 到 `StockMetadata`；返回 created / started / failed_to_start 明细。

C31 页面市场值传英文：`A股→cn`、`美股→en`。新增 C31 字段必须三层同步：前端提交到 config → `batch_create_and_start_task` 透传到 child_config → service 消费。

## K 线获取与东方财富

- **K 线字段标准命名**（全项目统一英文 schema，无兼容层）：数据行使用 `open` 开盘、`high` 最高、`low` 最低、`close` 收盘、`volume` 成交量、`amount` 成交额、`vwap` 加权平均价；`stock_date`/`stock_code`/`stock_name` 保留。推送远程的 wire 字段名不变（`stock_open`/`stock_max`/`stock_min`/`stock_close`/...），由 `KlineService.read_internal_kline_data`/`write_internal_kline_data` 负责两套命名翻译。
- **价格类型唯一映射入口**：`app/services/kline_service.py::get_kline_price_field()`（`kp_price→open`、`sp_price→close`、`vwap_price→vwap`、`ohlc_price→close`，未知兜底 `vwap`）；按价格取序列统一走 `KlineService.build_price_rows()`（取价 + 年份/区间过滤 + 投影 stock_val，可选 OHLC/随机价），不要在 service 里再写取价/投影包装。C4 不走 price_mode，固定按市场取价（A股 `open`、美股 `close`）直传字段。
- 统一入口 `app/services/kline_service.py`（装配 DFCF/腾讯 `qq_api.py`/Yahoo `yf_api.py`）；K 线服务自身持有 `StockClient`（地址单一来源 `STOCK_BASE_URL` 环境变量，未配置用 SDK 默认）；复权映射 `app/utils/kline_adjustment.py`；行数校验 `kline_validation.py::require_kline_rows`。
- `app/utils/dfcf_api.py::DFCJStockApi`：
  - K 线 `get_stock_kline_data`（push2his.eastmoney.com，fqt 由 kline_adjustment 映射）；tenacity `@retry(stop_after_attempt(5), wait_exponential(1,2,30))`；是否走代理由 SystemConfig `dfcf_kline_proxy_enabled` 控制，失败时 `_refresh_proxy_after_failure` 重建 session。
  - 搜索：先 codetable（search-codetable.eastmoney.com JSONP），失败回退 suggest（searchapi.eastmoney.com）；结果归一为 `{source, code, shortName, securityTypeName, market, marketType, isExactMatch, ...}`。
  - A 股成交量"手→股"换算（`_is_a_share_market` 区分港股）。
- `app/utils/proxy_manager.py::SmartProxyManager`：单例；代理源 `stockapi.stplan.cn`；30s TTL / 单代理最多复用 50 次；日志脱敏 `_redact_proxy`。
- 回测任务的股票搜索接口在 `app/routes/stock_api.py::search_stocks`（`/api/search-stocks`）；`market_type` 统一规范为 `cn` / `en`（`app/utils/market.py`）。

"股票搜索不到 / K 线拉取失败 / 美股与 A 股市场代码错传"类问题：先查 dfcf_api / proxy_manager / market.py，再看上层页面和 service。

# B4 复验报告

> 复验日期：2026-09-06。对应提交：A1~A3、B1、B2、B3 批次。
> 断言来源：`02-api-spec.md` §12 B4 与 §10 自查清单。

## 1. grep 断言结果

| 断言 | 目标 | 结果 |
|---|---|---|
| routes 中手拼 `{"status": ...}` 信封（api_response 之外） | 0 | ✅ 0（剩余 3 处命中均为读取 `task.get("status")` 业务字段） |
| routes 中 `request.get_json(` | 0 | ⚠️ 21 处 / 10 文件（见 §3 偏差 D-2） |
| routes 中 `paginated(` 使用 | >0 | ✅ 3 文件（result_api、scheduler_api；task_api 走 service 组装的规范键） |
| routes 中 `str(exc)` / `str(e)` | 0 | ⚠️ 24 处，均为 `ValueError→BadRequestError(str(exc))` 翻译链（见 §3 偏差 D-1） |
| routes 中 ORM / repository 直连 | 0 | ✅ 0 |
| 全库裸 `except:` | 0 | ✅ 0 |
| `logging.getLogger` 白名单外模块 logger | 0 | ✅ 0（白名单：task_watchdog 专用 handler、app/__init__ 第三方日志开关、logger.py 自身） |
| `task.error = ` 无效赋值 | 0 | ✅ 0（test_a1_bugfixes 常驻守卫） |
| `c5_exceptions` / `db_optimizer` / `security` / `log_reader` / `task/types` | 文件不存在 | ✅ 已删 |
| `checkForErrors` 符号 | 0 | ✅ 0（改名 `SheetCheckError`，仅 docstring 提及改名历史） |

## 2. 已收敛项（对照 02 §11 违规清单）

- **信封旁路 5/5**：POST /api/tasks、batch-create、PUT config、restart、admin dashboard/overview 全部经 `success()`；service 层手拼源头（creation/update_task_config/restart_task）改为"返回数据或抛领域异常"。
- **分页统一 3.5/4**：`/api/tasks`、`/api/results`、`/api/admin/scheduler/tasks`、backtest bt/bmp task-results 列表全部输出 `{items,total,pages,current_page,per_page}`；`paginated()` 投入使用。
- **debug_message 注入**：已删除。
- **静默吞异常 4 处**：已补 debug/warning 日志。
- **裸 except 15 处**：收窄为 `except Exception`。
- **写操作审计日志**：rbac_service（登录/登出/改密/用户 CUD/角色 CUD/权限同步）、navigation_service（CUD）、task_api（删除/取消/重启）、admin_api（rebuild/cleanup）、database vacuum 已补。
- **鉴权**：`admin_required` 落地（auth_api CUD ×6、vacuum、rebuild）；全部页面路由挂 `page_login_required`（匿名 302 登录页）；`access_token` cookie 回退 + 前端同步写入；xpl analyze 挂 `login_required` 且限流 key 恢复按用户。
- **其他**：xpl 数据级失败 200→400；`/api/config`、`/api/config/validate` 配置值脱敏；`/api/google-sheet-tokens` GET 只读化（reconcile 收敛为显式 POST）；dashboard RBAC 语义诚实化（07 文档同步更新）。
- **路由层下沉**：日志解析三份拷贝 → `log_query_service`；worksheets TTL 缓存 → registry 服务；导航权限树 → navigation_service；scheduler 异步摘要 → scheduler_service；backtest_api 死 workbook 构建器（98 行零调用）删除。
- **同语义双端点**：`/api/admin/scheduler/status` 已删除（保留 `/admin/api/scheduler/status` 丰富形状）。

## 3. 偏差与延期项（诚实登记）

| 编号 | 内容 | 原因 | 归宿 |
|---|---|---|---|
| D-1 | `ValueError→BadRequestError(str(exc))` 翻译链残留 24 处（export_api 13、google_sheet_api 6、backtest_api 3、stock_api 2） | 需先在 service 层把 ValueError 校验改为带用户文案的领域异常，属服务层契约改造；现残留文案均为面向用户的校验文案，泄露风险低 | 随 C6（api_service 改名/领域异常化）一并完成 |
| D-2 | routes 中 `request.get_json(` 残留 21 处；`request.args` 手读残留（次要列表端点） | 多数 body 为 RootModel 透传型或操作型小负载，schema 化需逐端点设计 | B 系列后续滚动收敛；新端点由 §10 清单约束 |
| D-3 | `/api/tasks/<task_id>/results` 的 `results` 键未翻转为 `items` | 该端点为条件分页（page/per_page 可选），前端 5 个 C 系详情页消费，翻转需同批改 5 处模板 JS | 与 C5（C 系拆包后详情页改造）同批 |
| D-4 | `_load_backtest_task` 已公开化，但路由内 `_load_multi_product_task_or_raise`、`_build_excel_download_name`、`_build_word_report_payload`、`_infer_product_export_model_name` 仍为路由文件内函数 | 前两者耦合路由上下文，下沉目标（backtest_report_query_service）在 C6 才创建 | C6 |
| D-5 | `tests/test/`（tests 根残留目录）与 archive 不在清理范围 | pytest norecursedirs 已排除，不影响收集 | 保持现状 |

## 4. 已知存量失败（非本方案引入，基线即失败）

1. `test_kline_adjustment.py::test_c4_us_market_uses_yahoo_adjustment` — 测试桩数据量与校验阈值不匹配；
2. `test_kline_sheet_guardrails.py::test_c3_rejects_end_date_after_latest_kline_without_writing_sheet` — 报错文案与断言正则不一致；
3. `test_value_parser_and_task_types.py::test_parse_date_supports_iso_shapes` — `parse_date` 对斜杠日期的约定分歧。

> 三者均为"测试期望 vs 实现"的历史分歧，修复属独立小任务，未夹带进本方案。

## 5. 最终回归

- `python -m pytest tests/unit tests/integration`：**531 passed, 10 skipped, 3 failed（均为上列存量）**；
- 新增守卫测试：`tests/unit/test_a1_bugfixes.py`（14）、`tests/unit/test_a2_concurrency_scheduler.py`（12）、`tests/unit/test_a3_hardening.py`（15）。

## 6. C 系列（任务代码重构）执行状态

| 批次 | 状态 | 落地内容 |
|---|---|---|
| C1 | ✅ 完成 | C4/C5/C7 逐字相同的 execute_task（97行×3）上移为基类唯一模板实现；四类改名 C3/C4/C5/C7Service（15 引用文件同步）；C3 stock_param 死分支删除 |
| C2 | ✅ 完成 | kline_prep 公共件（validate_raw_kline / project_and_validate_write_ready）；C5/C7 流水线尾段收敛；C4 四处硬编码价格字段改经 get_kline_price_field 统一映射 |
| C3 | ✅ 完成 | 断点起点（逐字×2）与去重器（C5/C7 差4行→钩子）收敛基类；get_bdl 批量执行模板（C5 198行/C7 225行→唯一实现）经 5 钩子合并，差异地图固化 §3.3 |
| C4 | ✅ 完成 | result_payload 公共件（19 项指标规格 + 30 项 analyze 透传）C5/C7 收敛；check_policy.py 落地（normalize_check_values + C5/C7_INVALID 谓词）配特征测试；_raise_retryable_network_error 上移基类，C3/C4/C5 get_bdl 外层补 [NETWORK_RETRYABLE]（_retryable_outer）并配测试；SheetSession 引导序列随基类 get_bdl 模板落地 |
| C5 | ✅ 完成 | google_sheet_tasks/ 包落地：base/c3/c4/c5/c7/kline_prep/result_payload/check_policy 全部迁入，旧 google_sheet_service*.py 六文件删除，runtime/routes/registry/测试引用全部切换 |
| C6 | ✅ 完成 | ✅ summary_contract.py 单一契约（multi_product 消费契约表、api_service 21 行摘要按契约标签对齐）；✅ backtest_training_api_service 改名 backtest_report_query_service（全库引用同步）；✅ 预览拆出：backtest_multi_product_preview.py 承载两个公开构建器（依赖方向 preview → exec 单向，持久化钩子及其加权指标依赖保留执行侧，天然解耦），执行侧仅保留 BacktestMultiProductService 类 |

**C 系列核心度量（实测）**：execute_task 97行×3 → 1；get_bdl C5 198行/C7 225行 → 模板+钩子；kline 流水线尾段 ×2 收敛；去重器/断点起点 ×2 收敛；payload 字段块 49行×2 → 规格表 20 行 + 构建器；check_result 闭包核心 ×2 → 策略函数；四个同名 GoogleSheetService 消失；旧 google_sheet_service* 六文件删除。

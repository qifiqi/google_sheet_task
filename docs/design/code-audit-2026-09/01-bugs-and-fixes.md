# Bug 与缺陷清单（含修复需求与验收标准）

> 级别定义：
> - **P0**：功能性 bug，当前必然/极易触发的错误行为，立即修；
> - **P1**：高风险缺陷，特定条件下导致资源泄漏 / 500 / 数据不一致 / 安全暴露；
> - **P2**：清理项（死代码、注释尸体、风格失真），随批次顺手清理。
>
> 每条统一格式：现象 → 根因 → 位置 → 修复需求 → 验收标准。修复不允许引入兼容层，修完即切换。

---

## P0 功能性 Bug

### BUG-01 重启任务 API 必然失败（dict 属性访问）

- **现象**：`POST /api/tasks/<task_id>/create-restart` 调用 `create_restart_task` 时抛 AttributeError，任务重启功能整体不可用。
- **根因**：`task_repository.get()` 返回 dict（`to_dict()`），而 `creation.py:689` 写了 `original_task.task_type`（属性访问）。同函数 673~686 行全部用 `original_task["config"]` 等下标访问，风格分裂掩盖了这一行。
- **位置**：`app/services/task/creation.py:689`；调用方 `app/routes/task_api.py:204`。
- **修复需求**：
  1. `original_task.task_type` 改为 `original_task["task_type"]`；
  2. 全文件 grep `original_task.` 确认无其他属性访问残留；
  3. 顺手统一该函数内的取值风格（全部下标或先 `get_required_task_entity` 拿实体，二选一，不留混用）。
- **验收**：pytest 新增用例——对一个 backtest_training 任务和一个 google_sheet 任务各调用一次 `create_restart_task`，断言创建成功且 config 归一化生效；`tests/unit` 回归全绿。

### BUG-02 `task.error = e` 无效赋值，失败根因未落库

- **现象**：回测任务失败时错误摘要没有写入 Task 行，前端与 watchdog 看不到根因。
- **根因**：`Task` 模型（`app/models.py`）没有 `error` 列，`task.error = e` 是 Python 属性赋值 no-op。疑似想写 `error_message`。
- **位置**：`app/services/backtest_training_service.py:462, 468, 497`。
- **修复需求**：
  1. 三处改为写入 `error_message`，且必须走统一工具 `app/utils/task_error_utils.py` 的记录函数（保持"用户可见摘要 + 看门狗信号"的结构约定，不写裸 traceback）；
  2. grep 全库 `\.error\s*=` 确认无同类 no-op 残留。
- **验收**：模拟任务失败路径，断言 `Task.error_message` 含预期摘要；三处对应的失败分支各有单测覆盖。

### BUG-03 start_task 四条失败路径不回滚已占资源

- **现象**：任务启动在前置检查阶段失败时，回测任务卡在 DB `running` 状态、回测 sheet 锁残留、同 sheet 排队任务被无限阻塞；非回测任务的 google_sheet 占用与 token 计数泄漏直到进程重启。
- **根因**：`start_task` 中 token 校验失败路径（`runtime.py:496-506`）有完整释放逻辑，但其后四条失败路径没有对齐：
  1. 未注册任务类型 `runtime.py:514-520`（不释放占用/sheet 锁/token，不 revert running）；
  2. 全局并发满 `runtime.py:525-529`（同上）；
  3. 分类型并发满 `runtime.py:540-546`（同上）；
  4. `build_runner` LookupError `runtime.py:553-560`（释放了 token/占用/stop_event，但漏了 `reserved_backtest_spreadsheet_ids` 和 `revert_running_to_pending`）。
- **位置**：`app/services/task/runtime.py`。
- **修复需求**：
  1. 抽一个 `_rollback_start_reservation(task_id, config_data, reserved_backtest_spreadsheet_ids, backtest_marked_running)` 私有方法，五条失败路径（含 496-506）统一调用，消除复制；
  2. "并发满"两条路径按现有注释语义本意是"保持 pending 等下次调度"，修复后必须保证 backtest 任务的 DB 状态回到 `pending`、sheet 锁全部释放；
  3. 每条失败路径补一条 task_log（前端任务详情可见被拒原因），当前只有 logger + start_errors 内存。
- **验收**：单测分别模拟四条路径，断言：`google_sheet` 占用清零、回测锁释放、`task_token_occupancy` 无残留、backtest 任务 DB 状态回 pending。

### BUG-04 `_load_multi_product_task_or_none` 命名撒谎，孤儿结果 500

- **现象**：访问结果行存在但任务行已被清理的 detail 接口时 AttributeError → 500。
- **根因**：`backtest_api.py:569` 的 `_load_multi_product_task_or_none` docstring 声称"不存在返回 None"，实际类型不符抛 ValidationError、不存在返回 None；调用点 `:503`（`bmp_get_task_result_detail`）假定非 None 直接 `task.get("config")`。
- **位置**：`app/routes/backtest_api.py:569`（定义）、`:503`（调用）。
- **修复需求**：
  1. 函数改名为 `_load_multi_product_task_or_raise`，语义对齐 bt 侧同构函数 `_load_backtest_task`（不存在抛 NotFoundError → 404）；
  2. 所有调用点适配，"None 分支"删除。
- **验收**：用不存在的 task_id 请求 `GET /backtest-multi-product/api/task-result/<id>`，得到 404 信封而非 500。

### BUG-05 User 表时区双轨（utcnow vs now）

- **现象**：部署在东八区时，`t_param_user` 的 `created_at`/`last_login` 与其他所有表时间相差 8 小时。
- **根因**：`app/models.py:58-59` User 模型 default 用 `datetime.utcnow`，其余全部模型用 `datetime.now`。
- **位置**：`app/models.py:58-59`。
- **修复需求**：统一为 `datetime.now`（与全库一致；本项目不引入 UTC 化大改造，那是另一个议题）。
- **验收**：grep `utcnow` 全库为 0；新建用户后 DB 时间与同批次 Task 行时间在同一时区基准。**注意：不改历史数据、不做迁移。**

### BUG-06 db_retry 的 commit 重试不 rollback，重试机制在最核心路径失效

- **现象**：commit 遇到锁等待/连接抖动时，`commit_with_retry` 的重试几乎必然二次抛错，最终抛 DatabaseLockError——重试形同虚设。它是 repository 执行链写出口（`base.py:66`）依赖的组件。
- **根因**：`app/utils/db_retry.py:163-175`，commit 抛 OperationalError 后 session 处于失效事务态，`_retry_operation` 直接二次 commit，中间不 `rollback()`。
- **位置**：`app/utils/db_retry.py:45-65, 163-175`。
- **修复需求**：重试前先 `db.session.rollback()` 再重放 commit（重放需要重新 flush 目标对象——若直接重放 commit 不可行，则改为"rollback + 重新执行注入的提交闭包"，由调用方传入可重放的 commit 动作）；补 rollback 不得吞原始异常链（裸 `raise`）。
- **验收**：单测模拟第一次 commit 抛 OperationalError、第二次成功，断言重试路径生效且最终提交成功。

### BUG-07 meta_api 版本值大小写笔误

- **现象**：前端传 `?version=C7` 时落到默认模板分支。
- **根因**：`app/routes/meta_api.py:25` 的 value 写成 `"C7"`，同列表其它项为小写，且 `google_sheet.py:16-21` 用 `== 'c7'` 小写比较。
- **位置**：`app/routes/meta_api.py:25`。
- **修复需求**：改为 `"c7"`；grep 前端模板确认无依赖大写 `C7` 的消费方。
- **验收**：`GET /api/meta/versions` 返回全小写 value；`/google-sheet/create?version=c7` 正确命中 C7 模板。

---

## P1 高风险缺陷

### BUG-08 运行态共享 dict 无锁跨 6 文件读写

- **现象**：并发场景下 `running_tasks` / `task_stop_events` / `task_token_occupancy` / `_active_worker_ids` 的 check-then-act 存在竞态；随并发量增大必然触雷。
- **根因/位置**：
  - 读写点分布：runtime.py（十余处）、restart.py:36-213、occupancy.py:66、query.py:145（还穿透读私有 `self._task_manager._get_config`）、runtime_view.py:114-115、task_watchdog.py:194-403；仅 `backtest_sheet_start_lock` 一把锁；
  - `facade.py:68-78`：`_wrapped` 的 finally 按 key pop `_active_worker_ids`，watchdog detach 的**老线程**退出会误删**新一代**线程的 worker id；
  - `runtime.py:565-568`：submit 已执行但 `running_tasks[task_id]` 未赋值的窗口，worker 抢先运行 `_is_active_generation()` 会误判自己被替换而跳过收尾。
- **修复需求**：
  1. 引入一把可重入运行态锁（`threading.RLock`），所有对四个 dict 的复合操作（check-then-act、pop-while-iterate）持锁完成；单次 get/set 可不加锁（GIL 下原子）但要写成约定注释；
  2. `_active_worker_ids` 改为 `task_id -> set(generation_id)` 或带代际校验后再 pop，杜绝跨代误删；
  3. `submit_task_execution` 先赋 `running_tasks[task_id]` 再返回，或在 `_wrapped` 开头等待"注册完成"事件；
  4. `query.py:145` 对 `_get_config` 的私有穿透改为门面公开方法。
- **验收**：并发压测脚本（多线程 start/cancel/restart 同一批任务）跑 100 轮无异常、无状态残留。

### BUG-09 调度子进程 PIPE 不读 + 锁无超时回收

- **现象**：定时任务子进程输出超管道缓冲区会死锁；子进程被杀后 `is_running` 锁永久残留，该定时任务从此每次被跳过。
- **根因**：`app/services/scheduler_service.py:293-316` `Popen(stdout=PIPE, stderr=PIPE)` 后从不读取；锁由子进程（scheduled_task_worker.py:127）释放，无兜底。
- **修复需求**：stdout/stderr 改为重定向到日志文件（或 DEVNULL）；`acquire_run_lock` 增加 started_at 时间戳，`run_task_now`/worker 入口发现锁超时（> 单次执行合理上限）时强制接管并告警日志。
- **验收**：单测模拟锁残留行，断言超时后能重新执行；手动 kill 子进程不产生死锁。

### BUG-10 config_manager 类型往返漂移 + 数字字符串静默转型

- **现象**：同一 key 在 set 后与缓存刷新后 get 返回类型不同（如 `"True"`(str) → `True`(bool)）；历史字符串配置 `"100"`/`"0"` 被静默转 int，`"null"` 变 None，`"NaN"` 产生 float('nan')。
- **根因**：`app/services/config_manager.py:211` set_config 缓存原始值 vs `:129` _load_configs 缓存反序列化值；`:55-63` `_deserialize_config_value` 对所有数字/JSON 形字符串尝试 json.loads。
- **修复需求**：
  1. set_config 统一缓存反序列化后的值（与读回一致），删除注释里"缓存原始值"的分支；
  2. `_deserialize_config_value` 收窄：仅对**写入时由 set_config/update_configs 序列化产生的 JSON**（bool/None/数字/容器）做还原；纯数字字符串若要当数字，必须由写入方显式用 `json.dumps` 落库——存量纯数字字符串 key 在文档里列出并人工确认（grep 现有 SystemConfig 行）；
  3. json.loads 禁用 NaN/Infinity（`parse_constant` 拒绝）。
- **验收**：对 bool/数字/字符串/None 四类值做 set → get → refresh_cache → get 四步断言类型恒定；`tests/unit` 现有 config 用例全绿。

### BUG-11 models.py 四处裸 json.loads，坏 JSON 即 500

- **现象**：`Task.config` / `TaskResult.parameters/result` / `TaskTemplate.config` / `ScheduledTask.task_params` 任一坏 JSON 行导致相关接口 500。
- **根因**：`app/models.py:382, 472-473, 733, 965` 用裸 `json.loads`；同文件 `:13` 已有安全版本 `_json_object_or_empty` 却未复用。
- **修复需求**：四处统一改用 `_json_object_or_empty`。
- **验收**：向测试库塞一行坏 JSON 的 Task.config，`GET /api/tasks/<id>` 返回 200 + 空 config（或按约定的空 dict），不 500。

### BUG-12 repository 写方法事务边界不统一

- **现象**：`backtest_repository.delete_xpl_analysis_jobs` / `dedupe_best_per_task` 既无 commit 参数也从不提交（依赖调用方 commit，漏了即静默丢写）；`task_result_repository` 的 create / bulk_create / create_return / bulk_create_returns 无条件提交、无法参与 `base.transaction()` 原子组合。
- **位置**：`backtest_repository.py:65-83, 184-224`；`task_result_repository.py:271-275, 298-302, 424-428, 430-434`。
- **修复需求**：按 AGENTS.md 数据层约定补齐——写方法默认 `commit: bool = True`、异常 rollback 后裸 `raise`；`backtest_repository.py:139-141` 的 `NotImplementedError` 占位方法删除。
- **验收**：四个写方法均带 commit 参数并可参与 `with xxx.transaction()`；涉及调用点（data_cleanup、model_summary/jobs）行为不变，回归全绿。

### BUG-13 xpl 分析接口错误信封配 200 状态码

- **现象**：`POST /xpl/analyze`、`POST /xpl/v1/analyze` 数据级失败返回 `error()` 信封但 HTTP 200。
- **位置**：`app/routes/xpl.py:73-76`（有注释声称保留语义）。
- **修复需求**：错误一律配 4xx/5xx；前端若依赖 200 判断，同步修改前端判断为 `status` 字段。同时修复：限流 key 恒为 `user:anon`（无 login_required 导致 g.current_user 未注入，全员共享一个限流桶）——给 xpl analyze 挂 `login_required` 或改用 IP key。
- **验收**：错误响应 HTTP 状态码非 2xx；两个匿名用户并发触发限流各自独立计数。

### BUG-14 `/api/config/validate` 配置明文泄露

- **现象**：诊断端点直接下发 `db_configs` / `cache_configs` 全部配置值，未走 `_mask_config_value` 脱敏（token/secret/password 类 key 明文外泄）。
- **位置**：`app/routes/config_api.py` get_config/validate_config。
- **修复需求**：所有下发配置值统一过 `config_manager._mask_config_value`（提为公开方法 `mask_config_value`）；`GET /api/config` 的 force_refresh 语义保留但同样过脱敏。
- **验收**：用敏感 key（含 token 字样）实测响应值为打码形态。

### BUG-15 google-sheet-tokens 列表 GET 内隐式写库 ×2

- **现象**：`GET /api/google-sheet-tokens` 单次请求触发两次 reconcile（list_tokens 与 get_usage_summary 各一次），GET 语义端点内做数据库写。
- **位置**：`app/services/google_sheet_token_service.py`（reconcile_in_use_counts）+ `app/routes/google_sheet_api.py`。
- **修复需求**：reconcile 从两个读路径中移除，收敛为显式维护（token 增删改时 + 任务占用 acquire/release 时同步更新），或提供单独的 `POST /api/google-sheet-tokens/reconcile` 手动触发端点；GET 只读。
- **验收**：GET 端点单次请求期间无 UPDATE/INSERT 语句（SQLAlchemy 事件计数断言）。

### BUG-16 dashboard RBAC 过滤形同虚设

- **现象**：`TaskDashboardQueryService.get_allowed_task_types(user, action)` 两个参数完全未使用、直接返回全库类型，"权限内任务类型"是假象。
- **位置**：`app/services/task/dashboard_query.py:15-20`；消费方 `runtime_view.py:237`。
- **修复需求**：鉴于项目已决策"RBAC 不再新增建设、随主服务接入统一解决"（AGENTS.md 鉴权边界），本条做**诚实化处理**：删除未使用的 user/action 参数与误导性命名（改 `list_all_task_types`），runtime_view 不再宣称"权限内"；真正的权限过滤登记到 `docs/design/api-model-query-audit/07-public-deployment-and-subservice.md` §1 的既有缺口清单。
- **验收**：签名与实现一致；07 文档缺口清单含本条。

### BUG-17 鉴权体系缺口：无 admin_required + 页面裸奔

- **现象**：全库不存在 `admin_required` 装饰器；`/admin/*` 13 个管理页面（含用户/角色管理页）、backtest 系全部页面（含 legacy 双注册共 24 条）、xpl/yule/eastmoney 页面全部无鉴权；`/api/admin/users` 等管理 API 仅 `login_required`。`AUTH_ENABLED=true` 时管理后台对任何登录用户开放，页面甚至对匿名开放。
- **位置**：`app/utils/auth.py`（只有 login_required）、`app/routes/admin.py` 全部、backtest 页面路由、`app/__init__.py`（无全局 before_request）。
- **修复需求**（与"随主服务接入"决策衔接的最小动作，非新権限建设）：
  1. 页面路由统一挂 `login_required`（与 API 策略对齐，一行装饰器的事，不属于"权限类新建设"）；
  2. `/api/admin/*`、`/admin/users`、`/admin/roles` 等管理面增加最小角色判断（复用现有 rbac role 查询，提供一个 `admin_required` 装饰器，实现只做"是否管理员角色"单一判断）；
  3. 缺口同时登记到 `07-public-deployment-and-subservice.md` §1。
- **验收**：匿名访问 `/admin/` 与 `/backtest-training/list` 被重定向登录页；非管理员登录用户调用 `DELETE /api/admin/users/<id>` 得到 403。

---

## P2 清理项（随批次顺手做，不单独立批）

| 编号 | 内容 | 位置 |
|---|---|---|
| CLN-01 | 删除 `c5_exceptions.py` 整文件（7 个类 0 引用，仅 `__init__.py` 转出口）+ 同步清 `app/exceptions/__init__.py` | `app/exceptions/c5_exceptions.py` |
| CLN-02 | 删除死文件 `app/utils/db_optimizer.py`、`app/utils/security.py`、`app/utils/log_reader.py`、`app/services/task/types.py` | 同左 |
| CLN-03 | 删除 `global_preview.py:137-173` 死函数 `export_preview`（无路由无引用）；`_preview_status` 与 global_preview_api.py 重复定义二选一保留 | `app/routes/global_preview.py` |
| CLN-04 | `checkForErrors` 空壳异常改名为 `SheetCheckError`（保留任务域语义），同步 6 个 service 引用；文件改 snake_case `sheet_check_error.py` | `app/exceptions/checkForErrors.py` |
| CLN-05 | 删除注释尸体：C3 L646-673 / C4 L570-577 / C5 L755-785 / C7 L1030-1060（旧 DFCF/Yahoo 分支）、C5 L872-903 / C7 L1140-1170（旧参数展开）、C3 L176-191、base L435-444、backtest_training L807-838 / L645-649、multi_product L247-258 / L436-455 / L1187-1195 | 各 service 文件 |
| CLN-06 | 删除 `if __name__ == '__main__'` 调试块（含硬编码 spreadsheet_id）：C4 L678-679、C5 L1024-1052、C7 L1301-1329、google_sheet_client.py:763-765 | 各文件 |
| CLN-07 | `task_error_utils.py` 零调用函数 `is_retryable_google_sheet_execution_error` / `is_retryable_c3_execution_error`；`google_sheet_client.py` 零引用常量 `NETWORK_EXCEPTIONS`；`google_sheet_client.py:730-734` 不可达兜底 raise | 同左 |
| CLN-08 | `multi_product.py` 死代码：`_use_legacy_cumulative_return_weighting` / `_result_weighting_mode` / `_cumulative_returns_to_daily_returns` / `_daily_returns_to_cumulative_returns` / `RATIO_BASE`；payload 冗余键 `metrics`/`product_metrics`、`weighted_metrics`/`weighted_product_metrics` 二选一 | `app/services/backtest_multi_product_service.py` |
| CLN-09 | `models.py:479-492` TaskResult.to_dict 的 7 个 hasattr 幽灵列分支（模型无这些列，恒 False） | `app/models.py` |
| CLN-10 | `utils/database.py` 已 deprecated 且 0 调用的 safe_delete/safe_update/safe_create/DatabaseManager（约 190 行；`transaction_required` 仍活，只删死段）；`@db_retry` 误装饰装饰器工厂的问题一并修正 | `app/utils/database.py:14-15, 42-233` |
| CLN-11 | 8 处绕过 `get_logger` 的 `logging.getLogger` 改统一入口（export_service:359、word_export_template:21、task_watchdog:43、kline_service:29、task/error_handling:21、qq_api:83、db_stock_api:14、yf_api:21），否则这些模块日志不落文件 | 同左 |
| CLN-12 | 死 import 清理：yule.py、google_sheet.py、creation.py(db, Task)、restart.py(db, Task)；函数体内局部 import 上移（logs_api、task_api、auth_api、query.py:175） | 各文件 |
| CLN-13 | `_build_task_result_persistence_payload` 死钩子（无子类重写）删除或落地一个真实重写 | `google_sheet_service_base.py:305-309` |

---

## 批次划分

| 批次 | 内容 | 涉及文档 |
|---|---|---|
| **A1 止血（P0）** | BUG-01 ~ BUG-07 | 本文档 |
| **A2 高风险（P1·并发与资源）** | BUG-03 复验、BUG-08、BUG-09、BUG-12 | 本文档 |
| **A3 高风险（P1·数据与安全）** | BUG-10、BUG-11、BUG-13、BUG-14、BUG-15、BUG-16、BUG-17 + 全部 CLN 项 | 本文档 |

> 执行提示词见 `EXECUTION_PROMPT.md` 第 1 节。

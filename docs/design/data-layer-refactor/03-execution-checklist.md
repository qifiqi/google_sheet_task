# 03 - 执行清单

> 每批一个 git commit；全量 `pytest` 通过才进下一批。执行偏差记录到文末"执行记录"。

## 0. 总则（每批铁律）

1. URL、请求结构、HTTP 状态码不得变化；响应体按 04 统一信封调整（业务数据键移入 `data`、键名不变），**同批更新对应前端读取与 integration 断言**；
2. 事务 commit 粒度不得变化（断点续跑语义红线）；
3. 保留原始异常链（`raise`，不 `raise e`）；
4. 替换 = 数据层迁移 + try/except 样板移除 + `api_response` 采用 + 前端/测试同步，一次做完、一次验证；
5. **无兼容层**：不保留旧响应格式分支、不加灰度/回退开关、不设过渡双轨 API；每批合入后，代码中只存在统一后的形态；
6. **不涉及数据库修改**：不改 schema、不写迁移、不动表数据，全部变更仅限代码。

## P1 快车道（独立小改动，可先于 B0 执行）

- [ ] **P1-3 MySQL 连接池参数补齐**：`app/config.py` `_build_engine_options()` 当前仅 `pool_pre_ping + pool_recycle`（`config.py:34-37`），MySQL 分支补齐 `pool_size`（默认 10）/ `max_overflow`（默认 20）/ `pool_timeout`（默认 30），全部支持环境变量覆盖；SQLite 分支保持现状。验证：默认值冒烟 + `.env` 覆盖生效。
- [ ] **P1-1 新接口规范写入 AGENTS.md**：随 B0 产物落成后在 `AGENTS.md` 增补"接口规范"章节：统一 envelope、全局 errorhandler、`api_response` 唯一出口、`ValidationError` 请求校验、repository 分层规则（routes/services 禁 ORM）。另写入两条总原则：**全程不涉及数据库修改**（不改 schema/迁移/数据）；**全库无兼容层**（单一响应格式、单一异常体系、单一执行路径，无灰度/回退/双轨）。

## B0 数据层与基础设施（纯新增，不改现有行为）

- [ ] `app/repositories/` 全部 14 个文件（契约见 02；异常从 `app.exceptions` import，见 04）
- [ ] `app/exceptions/base.py` 统一异常层级（04 §3）
- [ ] `app/errors.py` 全局错误处理器 + `create_app()` 注册（04 §4）
- [ ] `app/utils/api_response.py` 重写：统一信封（数据一律在 `data`，无 `**top_level` 平铺参数）+ `paginated`（04 §2）；同批迁移其仅有的两个消费方 `meta_api.py`/`auth_api.py`（仅响应调用，ORM 不动），自 B0 起全库仅一种响应格式
- [ ] `app/utils/request_validation.py` 轻量请求校验（04 §2.2）：`validate_body(required=..., types=...)`，失败抛 `ValidationError`
- [ ] **AGENTS.md 接口规范章节**（P1-1 交付物）
- [ ] 验证：`pytest` 全绿；`python -c "from app import create_app; create_app()"` 冒烟；meta_api/auth_api 响应仅新增 `status` 键、其余行为零变化（此时无人抛 AppException）

## B1 路由层（每文件：数据层替换 + 删 try/except + api_response + 同批更新前端读取/集成测试断言；2-3 文件一个 commit）

- [x] 1.1 `template_api.py` → 模板接口走 `task_template_repository`；`/api/results*` 三接口归位到新文件 `routes/result_api.py`（URL 不变）走 `task_result_repository`
- [x] 1.2 `auth_api.py` → `rbac_repository`；删用户流程用 `transaction()` 保持原子（`user_roles` 清理 + `task_repository.clear_created_by`）
- [x] 1.3 `utils/auth.py`（热路径：`list_permission_codes`/`get_user`，缓存逻辑保留）+ `meta_api.py`（0 ORM，响应已随 B0 切换，仅复核）
- [x] 1.4 `config_api.py` → `system_config_repository` + `navigation_repository`
- [x] 1.5 `scheduler_api.py` → `scheduled_task_repository`；4 处 `get_or_404` → `get_required` + NotFoundError 映射
- [x] 1.6 `google_sheet_api.py` → token/sheet repository
- [x] 1.7 `admin.py` → `task_repository.summary_counts()/recent()`；页面与 API 路由本批不拆文件（拆分属接口归位二期，另行立项）
- [x] 1.8 `task_api.py` → `task_repository`/`task_result_repository`
- [x] 1.9 少量文件：`backtest_multi_product.py`、`backtest_training.py`、`export_api.py`、`global_preview.py`、`google_sheet.py`、`yule.py`（核对无用 import）+ `database_api.py`、`stock_api.py`（0 ORM，仅统一响应格式）
- [x] B1 收尾验证：`grep -rEn "db\.session|\.query\." app/routes --include="*.py"` 为空（枚举常量 import 例外）；`grep -rn '"status": "error"' app/routes` 为 0；B1 范围端点的前端读取已切至 `resp.data.*`（integration + 手动冒烟覆盖）；`pytest` 全绿

## B2 服务层常规（顺序执行，每文件一验）

config_manager（**负缓存刷新留在本层**）→ stock_metadata_service → task/results → task/query → task/logs → task/dashboard_query → export_service → backtest_training_api_service → scheduler_service → scheduled_task_worker → google_sheet_token_service → google_sheet_registry_service → task_watchdog

- [ ] 每文件替换后 `pytest` 定向 + 批量后全量
- [ ] `utils/database.py` 的 `safe_create/safe_update` 调用点（creation/restart/stock_metadata）随对应批次改调 repository

## B3 任务执行核心（红线：断点 commit 语义、锁原子性、异常链）

顺序：task/occupancy → task/error_handling → task/creation（去 `safe_create`）→ task/restart（去 `safe_update`）→ task/runtime_view → task/data_cleanup → **task/runtime 最后**

- [ ] `backtest_repository` 锁语义按 runtime/occupancy 现状定形（acquire/release 原子）
- [ ] 替换后冒烟：创建任务 → 取消 → 重启 → 看门狗单周期通过

## B4 执行链与报表

顺序：google_sheet_service_base → google_sheet_service(C3) → C4 → C5 → C7 → backtest_training_service → strategy_backtest_report_service → backtest_multi_product_service → model_summary_service

- [ ] `task_log_repository.add` 热路径性能与原直写等价
- [ ] `pytest` 全绿 + 手动跑一个 C3 任务冒烟

## B5 外围与收尾

- [ ] `utils/auth.py` 401 改抛 `UnauthorizedError`（若 1.3 未做）
- [ ] `utils/ding_talk_notifier.py`、`ding_stream_service/task_commands.py`
- [ ] `utils/database.py` 标记 deprecated（调用点清零后）
- [ ] 确认 `get_entity` 仅任务执行域调用（正式契约，长期保留，无移除计划）
- [ ] 文档更新：`AGENTS.md`（任务/数据层章节重写）、`docs/架构总览.md`、`docs/数据库模型.md`
- [ ] **终验**：
  ```bash
  grep -rEn "db\.session|\.query\." app/routes app/services --include="*.py"   # 为空
  grep -rn '"status": "error"' app/routes --include="*.py"                     # 为空
  grep -rn "except Exception" app/routes --include="*.py"                      # 仅极少数有理由场景
  ```
  + 手动冒烟：登录 / 任务创建取消重启 / 模板 CRUD / 配置管理 / admin 仪表盘

## P1-2 任务执行池化 + 任务类型注册表

- [x] 设计见 `05-task-runtime-pooling.md`；**前置依赖：B3 完成**（runtime.py 已走数据层）
- [ ] 步骤：注册表化（纯重构，行为不变）→ 全局线程池 + 并发上限 → 分类型上限 → 配置化；**单一路径，不保留裸线程回退分支**（无灰度开关）

## 回滚策略

- 每批独立 commit，出问题 `git revert` 单批；
- B3/B4 若某文件替换后发现语义风险，允许该文件单独回退 ORM 版本，并在下方"执行记录"标注豁免理由（同步更新 `01-db-inventory.md`）。

## 执行记录

| 日期 | 批次/文件 | 结果 | 偏差与说明 |
|---|---|---|---|
| 2026-09-04 | 基线预登记（全程有效） | 豁免 | 已知存量失败 3 个（基线 HEAD `44101bd` 复现，非重构引入）："全量 pytest 通过"门槛按 `408+ passed / 3 个已知失败` 解释——这 3 个失败若仍存在不阻塞进批；一旦某个被修复不得回退。清单：`tests/unit/test_kline_adjustment.py::test_c4_us_market_uses_yahoo_adjustment`（C4 美股 K 线行数不足 30 校验）、`tests/unit/test_kline_sheet_guardrails.py::test_c3_rejects_end_date_after_latest_kline_without_writing_sheet`（C3 K 线守卫同类）、`tests/unit/test_value_parser_and_task_types.py::test_parse_date_supports_iso_shapes`（ISO 日期解析）。另有 10 个既有 `@pytest.mark.skip` 属正常跳过。重构批次内新增任何失败仍视为阻塞。 |
| 2026-09-04 | P1-3（commit 5f2e9b8） | 通过 | `_build_engine_options()` MySQL 分支补 pool_size/max_overflow/pool_timeout（环境变量 `DB_POOL_SIZE`/`DB_MAX_OVERFLOW`/`DB_POOL_TIMEOUT`，默认 10/20/30）；SQLite 分支不变。默认值+覆盖冒烟通过；全量 pytest 与基线一致（416 passed/3 豁免/10 skipped）。 |
| 2026-09-04 | B0 | 通过 | 新增 app/repositories/ 14 文件、app/exceptions/base.py（层级并入既有 `app/exceptions/__init__.py` 导出）、app/errors.py（create_app 注册）、重写 api_response.py（success/error/paginated，信封 `{status, code, message, data}`）、app/utils/request_validation.py；AGENTS.md 增补"接口规范"章节（P1-1 交付物）。meta_api/auth_api 调用签名兼容、无需改动，自 B0 起全库仅一种响应格式。新增 tests/unit/test_repositories.py + tests/integration/test_unified_envelope.py。验证：465 passed/3 豁免/10 skipped，`create_app()` 冒烟 OK，路由 150 条不变。偏差：① 兜底 Exception/AppException 处理器在页面路径显式返回 InternalServerError（errorhandler 返回 None 会被 Flask 判无效响应）；② stock_metadata_repository.upsert 内做与模型事件一致的 stock_code 标准化，否则二次 upsert 撞唯一约束；③ 全量 pytest 入口固定为 `pytest tests/unit tests/integration`（tests/ 根目录历史同名测试文件致 bare `pytest` 收集冲突，属存量问题，已登记 AGENTS.md）。 |
| 2026-09-04 | B1（9646be7/f42093e/7f3b0d5/ff98783/本批） | 通过 | 路由层 16 文件全部完成四合一迁移；收尾 grep：routes 内 `db.session|.query` 与手写 `"status": "error"` 均为 0，路由 150 条不变。偏差：① API 判定由 startswith("/api") 扩为"路径含 /api 段或 Accept 优先 JSON"（/tasks、/config、/meta/nav、/admin/api/* 等均为纯 JSON 端点但不以 /api 开头）；② utils/auth 401 改抛 UnauthorizedError（B5 项提前于 B1-2 完成）；③ navigation_repository 提供 list_all_entities/list_visible_entities 实体形态（范围外的 app/navigation.py sync/build 依赖实体属性，二期收敛）；④ admin.py 的 dashboard/overview 与 model-summary 查询为服务层契约 payload 保持透传（B3/B4 收敛）；⑤ google_sheet_api/export_api/task_api 对服务层 ValueError 保持显式翻译 BadRequestError（B2/B3 后移除）；⑥ 本批修正一处漏读：backtest_multi_product.py 原文件 399 行后仍有 _build_global_preview_workbook/export_global_preview/batch_export_global_preview（集成测试依赖），已在 B1-5 补回；⑦ 对应集成测试断言同批更新（global_preview/backtest_multi_product/backtest_training_result_storage 取 data.*）。 |
| 2026-09-04 | B2（9f67f05） | 通过 | 常规服务 13 文件 + stock_search 全部迁移（详见提交说明）。关键点：config_manager 负缓存/序列化留本层；scheduler 乐观锁 acquire/release_run_lock；token 占用记账沿用实体语义（实体经仓储获取、提交经 base.commit 出口，登记偏差）；watchdog 前缀常量参数传入仓储（防 services→repo 反向依赖）；test_stock_metadata_service 断言同批更新为 dict 访问。验证：468 passed / 3 豁免 / 10 skipped，冒烟 OK。 |
| 2026-09-04 | B3 | 通过 | task/ 七文件按序迁移完成：occupancy（sheet 查重/校验走仓储）、error_handling（事务出口 transaction/rollback）、creation（去 safe_create，create(commit=False) 交 transaction_required 统一提交）、restart（去 safe_update，中途 commit 点改 task_repository.commit 保留断点粒度）、runtime_view、data_cleanup（xpl 遗留表删除与汇总索引条件删除下沉 backtest_repository，清理窗口条件全部压 SQL 层）、runtime 最后（锁 acquire/release 走 backtest_repository 保持 IntegrityError 竞态回查；pending/running 条件更新收敛为 mark_running_if_pending/mark_running_if_not_running/revert_running_to_pending；finalize 用 update_fields）。任务实体经 get_entity/get_entity_fresh 访问（执行域正式契约）。偏差：执行域服务保留实体属性写法（status 等经 update_fields 者除外），get_entity 实体访问按 02 契约长期保留。冒烟（本地 SQLite）：创建→取消→重启（真实拉起线程，无 token 快速失败写 error_message）→删除→看门狗单周期 全部通过。验证：468 passed / 3 豁免 / 10 skipped。 |
| 2026-09-04 | B4 | 通过 | 执行链与报表 9 文件全部迁移：google_sheet_service_base/C3/C4/C5/C7、backtest_training_service、strategy_backtest_report_service、backtest_multi_product_service、model_summary_service。任务实体经 task_repository.get_entity；结果/收益写入经 task_result_repository.add_entity+flush+commit_with_retry（保留 db_retry_manager 重试语义）；取消检查热路径收敛 task_repository.get_status_value；固定产品缓存查重 product_cache_exists/get_product_cache；model_summary 的候选对查询、汇总索引差分 upsert（add_entity/delete_entity）、窗口函数去重 dedupe_best_per_task（group 表达式由服务层传入）全部下沉 backtest_repository。至本批 services+routes 的 db.session/.query 归零。C3 执行链冒烟：start_task→快速失败→error_message 落库 通过。验证：468 passed / 3 豁免 / 10 skipped。 |
| 2026-09-04 | B5 | 通过 | utils/auth（B1-2 已提前完成：401 改抛 UnauthorizedError + 仓储实体访问 + 缓存留 auth 层）、utils/ding_talk_notifier（值班用户实体经 rbac_repository.list_alert_oncall_active_entities、任务经 task_repository.get_entity）、ding_stream_service/task_commands（状态/名称查询走仓储）全部迁移；utils/database.py 的 safe_create/safe_update 标记 deprecated（调用点清零；transaction_required 仍被 creation/restart/stock_metadata 使用，提交重试语义，登记为遗留）；文档更新 AGENTS.md/docs/架构总览.md/docs/数据库模型.md。手动冒烟（test_client 组合）：登录→模板 CRUD→配置管理（PUT/列表）→admin 仪表盘→任务列表 全部通过。清单偏差：xpl.py 存在 3 处单引号手写错误信封（含 str(e) 下发），01 清点误标为无信封——因前端错误路径依赖其 results/metrics 键且 01 明确范围外，本批不改，建议随 xpl 子服务化处理。终验 grep 三连全部达标（ORM 空/手写信封空/except Exception 13 处均为有理由场景：日志解析回退、缓存写失败告警、非致命刷新告警、流式导出守护日志等）。 |
| 2026-09-04 | P1-2（2ef2d91/4a8c1be/e3a0ebd/本批） | 通过 | ① 注册表：app/services/task/registry.py（TaskTypeSpec+TASK_TYPE_REGISTRY+register_task_type），runtime if/elif×6 → registry，未注册类型拒绝启动并写 error_message；② 全局池：facade 持 ThreadPoolExecutor（task_max_workers=8，进程内固定）+ _TaskExecution 句柄（is_alive=not future.done()、join 兼容），启动前全局配额检查，超限安静保持 pending；活跃代际按 worker ident 跟踪；③ 分类型上限 task_concurrency_*（配额冒烟：上限 2 时第 3 个同类型被拒保持 pending，释放后可启动）；④ scheduler 统一入口：实测 scheduler_service 任务执行为 APScheduler+独立子进程+乐观锁分布式锁模型（非 05 文档所述裸线程——两处线程仅包装延时启动与子进程拉取状态跟踪），改造为进程内池会破坏隔离与锁语义，故保持现状并登记偏差（以实际代码为准）。验收：并发压测 burst 4 任务全部入池分发快速失败；取消/重启/看门狗冒烟通过；runtime.py threading.Thread 分发残留 0。 |
| 2026-09-05 | 批 0（735f829） | 通过 | 审计前置：批 9 回归修复 + 批 10 dto 收编 schemas 的工作区遗留变更整体落库（30 文件，含 tests 根目录 7 个死文件删除）；内容与 api-model-query-audit README 批 9/批 10 登记一致，工作区归零。验证：489 passed / 3 豁免 / 10 skipped（审计批次基线）。 |
| 2026-09-05 | 审计批 A | 通过 | backtest_training_api_service 3 个响应元组函数改统一异常：_load_backtest_task 抛 NotFoundError("任务不存在")/ValidationError("当前接口仅支持回测任务")，_load_backtest_task_result 抛 NotFoundError("任务结果不存在")，message 文案全部不变；backtest_api.py 7 处调用点收敛，`if error_response: return error_response` 清零。死代码清理：服务版 _validate_batch_global_preview_task_ids（仅被遮蔽 import 引用）、路由版同名死函数（无调用点）、无路由装饰器死函数 download_task_result_export_preview（全仓库零调用，对应 2 个"待注册"skip 测试维持跳过）、被本地 def 遮蔽的 4 个 import、重复 _sanitize_json_value 定义、孤儿导入（datetime/BytesIO/ZipFile/jsonify/error/BATCH_GLOBAL_PREVIEW_EXPORT_MAX_TASKS/TaskResultReturn）。服务层 flask import 整行删除（该服务零 Flask 依赖）。偏差：① 2 个错误端点响应体由缺 code/data 的手写形状变为统一信封（404/400 语义不变，无测试锁死旧形状）；② 该文件 pyflakes 仅剩存量 header_fill 未清（非本批上下文，保留）。验证：489 passed / 3 豁免 / 10 skipped。 |
| 2026-09-05 | R1（commit 60cb18a） | 通过 | 新批次系列：routes→services 单向分层收编（路由不再 import/call repository；逐接口处理）。本批 10 个小文件：meta_api（新建 services/navigation_service.py 模块函数形态）、global_preview/global_preview_api/export_api（TaskQueryService 新增 get_task/get_required_task/get_task_result，4 处重复 _load_* 样板删除）、admin.py（TaskDashboardQueryService 新增 get_dashboard_counts/get_recent_tasks）、admin_api（TaskRuntimeViewService 新增 get_runtime_detail，get_entity 收进任务运行态域服务）、google_sheet（get_task）、google_sheet_api（token_service 新增 delete_token）、backtest_training/backtest_multi_product 页面（resolve_result_task_id 归属解析收敛）。偏差：① 3 个端点 404 message 由"任务不存在"统一为仓储既有契约"任务不存在: {task_id}"（get_required 复用，更可诊断，无测试锁定旧文案）；② runtime-detail 404 文案英文 'task not found' 统一为"任务不存在"；③ google_sheet_api 头注释同步更新，ValueError→BadRequestError 翻译保留（服务层仍以 ValueError 表达校验失败，随 R 后续批次处理）；④ runtime_view.py 重复 import json 顺带清理；⑤ 工作区存在他会在途未提交变更（task_repository/task_result_repository 3 个新方法），未纳入本批提交。验证：grep R1 十文件 repository 残留为空；create_app 冒烟 149 路由不变；全量 pytest 489 passed / 3 豁免 / 10 skipped 与基线一致。 |
| 2026-09-05 | 审计批 B | 通过 | 服务层残留 ORM 查询全部下沉 repository：① backtest_repository 新增 delete_summary_index_by_scope（rebuild reset 双条件删除）、page_summary_index（动态过滤+股票窗口函数+with_entities 汇总+分页，吸收 _apply_market_type_filter/_apply_stock_keyword_filter/_stock_summary_query 三个服务层 helper）、insert_product_cache_if_absent（check-then-insert+IntegrityError 回滚吞竞态，与 upsert 覆盖语义区分）；② task_repository 新增 get_latest_task_id_by_type（created_at desc,id desc，合并 _active_rebuild_job/latest_rebuild_job 两处查询，后者原仅 created_at 排序，补 id 决胜登记偏差）；③ task_result_repository 新增 get_export_entity（导出四列实体，规避 to_dict 预解析+json.loads 双重解析静默空 payload 陷阱，对齐 list_preview_entities 实体流先例）、list_preview_entities 加 success_only 参数；④ dedupe_best_per_task 的 group 表达式默认值下沉 repository（B4 遗留的"服务层传表达式"接缝收口，_summary_index_group_expression 删除）。消费方：model_summary_service 5 处、backtest_multi_product_service 3 处（含缓存写入 try/except 收编）、backtest_training_api_service 2 处、export_service get_entity 挪用改 get_export_entity。死导入清理：google_sheet_service_base/C3/C4/C5/C7 的 db+Task（C 系）、task_watchdog and_/not_/or_+TaskLog、backtest_repository load_only、task_result_repository NotFoundError、db_retry_manager×5、model_summary sqlalchemy func/or_/Load。偏差：model_summary_service 保留 TaskResultSummaryIndex 实体构造（B4 登记的差分更新实体流，非查询）；google_sheet 系 f-string/未用变量等存量 pyflakes 项未动（非导入类，超范围）。验证：ORM 精确 grep（db.session/.query./filter_by）routes+services 为 0；489 passed / 3 豁免 / 10 skipped。 |
| 2026-09-05 | R2（commit 7d9b201） | 通过 | config_api/task_api/result_api/template_api 去直连（17 调用点）。服务层新增：TaskQueryService.get_required_task_entity/get_distinct_task_types/get_empty_tasks_page、TaskResultMixin.get_results_paginated/get_result_detail/delete_result、TaskTemplateService（新建，_serialize_config_str 自路由下沉）、config_manager.get_db_config_rows/update_config_row（写+缓存刷新收敛配置层）。偏差：① task_api 删除 3 个无路由注册死函数（export_task_results/export_c7_results_by_stock_code/batch_export_task_results，210 行含注释的历史 xlsx 导出实现，export 域已归位 export_api+export_service，全仓库零引用，批 A 同模式）；② config_api 删除未使用 import sync_navigation_permissions；③ /tasks 空态响应字面量（24 行）收敛为 get_empty_tasks_page，键逐一核对不变；④ create-restart 端点实体消费改经门面 get_required_task_entity，get_entity 契约不变。验证：grep 四文件 repository 残留为空；冒烟 149 路由不变；489 passed / 3 豁免 / 10 skipped 与基线一致。 |
| 2026-09-05 | R3（commit 32d44bf） | 通过 | backtest_api(7 点)/navigation_api(10 点) 去直连。TaskResultMixin 新增 get_task_results_page_raw/get_required_result_entity/get_return_entity；多品比例保存编排下沉 backtest_multi_product_service.update_task_ratios（服务侧 ValueError→ValidationError，400 不变）；navigation_service 扩展为完整菜单服务（CRUD+权限同步+序列化），navigation_api 158→44 行。偏差：① 管理端 payload 校验由路由元组返回改服务内抛 ValidationError（400+文案不变）；② 本地 _coerce_bool 替换为 config_manager.coerce_bool 统一布尔入口；③ _load_multi_product_task_or_none 类型不符 BadRequestError→ValidationError（对齐批 A 词汇，400 不变）；④ 过程记录：首跑 2 个集成测试失败（normalize_multi_product_config 在 _build_word_report_payload 仍有使用，import 误删，已恢复）；全量验证期间 .pytest_tmp 出现文件锁环境抖动（每轮报错用例漂移、最多 131 errors），换干净 basetemp 复跑与基线完全一致。验证：grep 残留为空；冒烟 149 路由不变；489 passed / 3 豁免 / 10 skipped。 |
| 2026-09-05 | 审计批 C | 通过 | 执行链结果落库收编：① task_result_repository 新增 create_with_return（TaskResult+TaskResultReturn 两表原子写入、flush 后回链 return_series_id、异常 rollback 裸 raise，按 02 §1 规则 1 补齐；原服务实现 flush 失败重试时脏 session 可致重复插入的隐患顺带消除）；② BaseGoogleSheetService 收编 _save_task_result，6 个执行服务（C3/C4/C5/C7/backtest_training/backtest_multi_product）约 40 行重复 session 编排删除，差异以钩子保留：_build_task_result_persistence_payload（多品加权指标叠加）、_get_return_series_stock_name（training 回退 name、多品回退 product_name）；return_date 语义收敛：显式传入（含空列表）为收益序列唯一行来源，None 才从 result 提取（多品 result 载荷含 _return_date 键，语义不可混用）。偏差：① 多品保存失败日志文案"保存多品任务结果失败"统一为"保存任务结果失败"；② C3 的 isinstance 守卫为死代码（_normalize_result_parameters 恒返回 dict）随收编删除；③ 多品 TaskResult 预 flush 冗余删除；④ 6 文件死导入清理（TaskResult/TaskResultReturn/build_return_series_fields/extract_return_rows/db_retry_manager/safe_db_operation 按文件实际残留）。验证：定向结果存储 25 单测通过；全量 489 passed / 3 豁免 / 10 skipped 与基线一致（3 豁免为存量项，HEAD worktree 复现确认非本批引入）；.pytest_tmp 文件锁环境抖动按 R3 方式换 basetemp 复跑。 |
| 2026-09-05 | R4（commit 见上） | 通过 | scheduler_api(14 点) 去直连：CRUD+调度同步编排全部下沉 scheduler_service（stats/分页响应结构、create/update/delete/toggle、run_task_now、执行状态聚合、get_required_task 前置检查）。偏差：① cron/params 校验自路由下沉并 BadRequestError→ValidationError（400+文案不变）；② update 端点保留"存在性检查先于 parse_body"的原顺序语义（路由先调 get_required_task 再 parse，双故障场景 404 优先于 400）；③ toggle 的 is_active 缺省取反逻辑原样保留（data.get('is_active', not task.is_active)，显式 null 行为不变）。验证：grep 残留为空；489 passed / 3 豁免 / 10 skipped 与基线一致。 |

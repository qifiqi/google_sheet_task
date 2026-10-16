# 全量接口调用链条分析（148 端点）

> 审计日期：2026-09-06。覆盖全部 25 个路由文件、148 个端点（任务域 41 / 回测导出域 50 / 管理认证域 57）。
> 每条记录：方法+完整路径 → handler → 鉴权 → 调用链（service → repository）→ 响应出口 → 问题标记。
> 调用链均经实读 service/repository 文件确认方法名；"问题标记"只记事实，修复归属见 `01-bugs-and-fixes.md` 与 `02-api-spec.md`。
>
> **问题标记处置登记（2026-09 整改完成后）**：下文各表"问题标记"列的处置结果统一登记于
> `B4-verification.md` §1（grep 断言结果）/ §2（已收敛项）/ §3（偏差 D-1~D-5 与延期项），
> 鉴权类缺口另见 `api-model-query-audit/07-public-deployment-and-subservice.md` §1（主服务接入清单）。
> 本文件为审计时点快照，端点计数与形状以整改后代码为准（对照表见 `README.md` §4）。

## 0. 蓝图注册总表（app/routes/__init__.py，28 次注册）

`admin_api_bp` 与 `scheduler_api_bp` 在蓝图构造函数中已带 `url_prefix`，注册时又二次传入（注册值覆盖，两处一致）；其余蓝图均只在一处定义前缀。

| 蓝图名 | 定义处自有 url_prefix | 注册时二次传 | 生效前缀 |
|---|---|---|---|
| auth_pages | 无 | 否 | （空） |
| xpl | 无 | 是 | /xpl |
| yule | 无 | 是 | /yule |
| admin | 无 | 是 | /admin |
| admin_api | /admin（构造函数） | 是（值一致） | /admin |
| task_api / config_api / logs_api / navigation_api / template_api / result_api / google_sheet_api / database_api / stock_api / meta_api / auth_api | 无 | 是 | /api |
| eastmoney_kline | 无 | 否 | （空） |
| google_sheet | 无 | 是 | /google-sheet |
| scheduler_api | /api（构造函数） | 是（值一致） | /api |
| backtest_training (bp) | /backtest-training | 否 | /backtest-training |
| backtest_training_legacy (legacy_bp) | /backtest | 否 | /backtest |
| backtest_training_api (bt_api_bp) | /backtest-training | 否 | /backtest-training |
| backtest_multi_product (bp) | /backtest-multi-product | 否 | /backtest-multi-product |
| backtest_multi_product_legacy | /backtest-multi | 否 | /backtest-multi |
| backtest_multi_product_api (bmp_api_bp) | /backtest-multi-product | 否 | /backtest-multi-product |
| global_preview (bp) / global_preview_api (gp_api_bp) | /global-preview | 否 | /global-preview |
| export_api | 无 | 是 | /api/exports |

**关键事实**：`app/utils/auth.py` 只存在 `login_required`，**不存在 `admin_required`**；app 工厂无 `before_request` 全局鉴权钩子。

---

## 1. 任务域（41 端点）

蓝图前缀：`task_api_bp`、`config_api_bp`、`logs_api_bp`、`template_api_bp`、`result_api_bp`、`google_sheet_api_bp`、`meta_api_bp` 均注册于 `/api`；`google_sheet_bp` 注册于 `/google-sheet`。

### task_api.py（11 个端点，前缀 /api）

| 方法+完整路径 | handler | 鉴权 | 调用链（service方法 → repository方法） | 响应出口 | 问题标记 |
|---|---|---|---|---|---|
| GET+POST /api/tasks | task_api.py:tasks | login_required | GET: `task_manager.get_distinct_task_types`(task/query.py) → task_repository.list_distinct_task_types；空态走 `get_empty_tasks_page`（纯内存）；`get_tasks_paginated`(task/query.py) → task_repository.list_paginated_with_statistics。POST: `create_and_start_task`(task/creation.py) → create_task → task_repository.create + occupancy.ensure_google_sheet_occupancy → google_sheet_registry_service.acquire_for_task → google_sheet_repository.occupy；start_task(task/runtime.py) → task_repository.get_entity / mark_running_if_pending + google_sheet_token_service.increment_usage → google_sheet_token_repository | GET: success()；POST: jsonify手拼（透传 service 手拼 dict） | 混合出口；POST 分支信封旁路；service 启动失败 message 含内部 start_error 原文 |
| POST /api/tasks/batch-create | task_api.py:batch_create_tasks | login_required | `batch_create_and_start_task`(task/creation.py) → 循环 create_task → task_repository.create + start_task；stock_metadata upsert（session 内） | jsonify手拼（透传 service dict） | 信封旁路；200 时路由层注入 `debug_message` 占位文案下发；ValueError→BadRequestError(str(exc))；service 内子任务间 `time.sleep(0.5)` 同步阻塞请求 |
| GET+DELETE /api/tasks/<task_id> | task_api.py:task_detail | login_required | 前置 `get_required_task`(task/query.py) → task_repository.get_required。GET: `get_task_status` → task_repository.get。DELETE: `delete_task`(task/restart.py) → task_repository.get_entity / update_fields / delete + data_cleanup.clear_task_execution_data → task_result/task_log/backtest repository 多表清理 + occupancy 释放 → google_sheet_repository.release_by_task | GET/DELETE 均 success() | delete_task `except Exception` 吞异常仅 return False，路由只回笼统"删除任务失败" |
| PUT /api/tasks/<task_id>/config | task_api.py:update_task_config | login_required | 前置 get_required_task；`update_task_config`(task/creation.py) → task_repository.get / update_fields + add_task_log → task_log_repository.create_log + google_sheet_repository.occupy/release_by_task（换表时） | jsonify手拼（service dict，成功 200 / 失败 400） | 信封旁路；service `except Exception` message=`f"更新任务配置失败: {exc}"`（str(exc) 下发）；请求体手读 `request.get_json()` 未走 schema |
| POST /api/tasks/<task_id>/cancel | task_api.py:cancel_task | login_required | 前置 get_required_task；`cancel_task`(task/restart.py) → task_repository.get_entity / update_fields + occupancy 释放 + add_task_log → task_log_repository.create_log | success() | — |
| GET /api/tasks/<task_id>/logs | task_api.py:get_task_logs | login_required | 前置 get_required_task；`get_task_logs`(task/logs.py) → task_log_repository.list_by_task | success() | get_task_logs `except Exception` 吞异常返回 []（有 logger.error） |
| GET /api/tasks/<task_id>/status-check | task_api.py:check_task_status | login_required | 前置 get_required_task；`check_local_task_status`(task/query.py) → task_repository.get + task_log_repository.list_by_task + task_result_repository.latest_time_by_task + config_manager.get_config → system_config_repository.get_row | success() | check_local_task_status 内日志时间解析 `except Exception: pass` 静默吞 |
| GET /api/tasks/<task_id>/stop-confirmation | task_api.py:get_task_stop_confirmation | login_required | 前置 get_required_task；`runtime_view_service.build_stop_confirmation`(task/runtime_view.py) → check_local_task_status（同上三个 repo）+ task_repository.get_entity | success() | — |
| POST /api/tasks/<task_id>/restart | task_api.py:restart_task | login_required | 前置 get_required_task；`restart_task`(task/restart.py) → task_repository.get_entity / update_fields / commit + cancel_task + start_task + clear_task_execution_data → task_result/task_log/backtest repository | jsonify手拼（service dict，成功 200 / 失败 400） | 信封旁路；service 顶层 `except Exception` 返回 str(exc) 下发 |
| POST /api/tasks/<task_id>/create-restart | task_api.py:create_restart_task_api | login_required | `get_required_task_entity`(task/query.py) → task_repository.get_entity；`create_restart_task`(task/creation.py) → task_repository.get / create（**BUG-01：689 行 dict 属性访问必然 AttributeError，API 实际不可用**）；`start_task`(task/runtime.py)；`get_start_error`(task/restart.py，读内存 dict) | success() / error() | error() 的 data 下发 start_error 原文 |
| GET /api/tasks/<task_id>/system-logs | task_api.py:get_task_system_logs | login_required | 前置 get_required_task；其余为路由内直接读 Config.LOG_FILE 并正则解析（全量 readlines） | success() | 层间越界：路由内联 ~60 行日志解析；全量 readlines 无上限；datetime 解析静默吞；与 logs_api 解析逻辑重复 |

### result_api.py（4 个端点，前缀 /api）

| 方法+完整路径 | handler | 鉴权 | 调用链 | 响应出口 | 问题标记 |
|---|---|---|---|---|---|
| GET /api/tasks/<task_id>/results | result_api.py:get_task_results | login_required | get_required_task → task_repository.get_required；`get_task_results`(task/results.py) → 分页：task_result_repository.count_by_task_success + list_by_task_paginated；非分页：list_by_task | success() | — |
| GET /api/results | result_api.py:get_results | login_required | `get_results_paginated`(task/results.py) → task_result_repository.list_paginated | success()（data 透传 service 字典） | — |
| GET /api/results/<int:result_id> | result_api.py:get_result | login_required | `get_result_detail` → task_result_repository.get_with_task_type | success() | — |
| DELETE /api/results/<int:result_id> | result_api.py:delete_result | login_required | `delete_result` → task_result_repository.delete | success() | 未级联清理结果依赖表（对照 data_cleanup.delete_task_result_dependencies 链路，此处仅删主行） |

### logs_api.py（2 个端点，前缀 /api）

| 方法+完整路径 | handler | 鉴权 | 调用链 | 响应出口 | 问题标记 |
|---|---|---|---|---|---|
| GET /api/logs | logs_api.py:get_logs | login_required | 读日志文件（Config.LOG_FILE 全量 readlines 后取尾部，路由内正则解析） | success() | 路由层读文件（模块 docstring 自证"留在路由层"）；datetime 解析静默吞；未匹配行包装成 level=info/source=unknown 下发 |
| GET /api/logs/latest | logs_api.py:get_latest_logs | login_required | 读日志文件（同上） | success() | 同上；与 get_logs 解析逻辑重复 |

### google_sheet.py（4 个端点，前缀 /google-sheet，页面蓝图）

| 方法+完整路径 | handler | 鉴权 | 调用链 | 响应出口 | 问题标记 |
|---|---|---|---|---|---|
| GET /google-sheet/ | google_sheet.py:index | 无 | 模板渲染 | render_template | 无鉴权页面 |
| GET /google-sheet/create | google_sheet.py:create | 无 | 无 version 参数时 `_resolve_task_version` → `task_manager.get_task` → task_repository.get；随后模板渲染 | render_template | 无鉴权页面且含 DB 查询（未登录可借任意 task_id 探测任务存在性与类型） |
| GET /google-sheet/merge-export | google_sheet.py:merge_export | 无 | 模板渲染 | render_template | 无鉴权页面 |
| GET /google-sheet/detail | google_sheet.py:detail | 无 | `_resolve_task_version('task_id')` → task_manager.get_task → task_repository.get；模板渲染 | render_template | 同 create：无鉴权 + DB 查询探测 |

### google_sheet_api.py（7 个端点，前缀 /api）

| 方法+完整路径 | handler | 鉴权 | 调用链 | 响应出口 | 问题标记 |
|---|---|---|---|---|---|
| POST /api/google-sheet/worksheets | google_sheet_api.py:get_worksheets | login_required | 路由内模块级缓存 `_worksheets_cache`（进程内 dict，TTL 5 天）→ 未命中时 `GoogleSheetService.get_worksheets`(google_sheet_service_base.py，直接调 Google API) | success() | 模块级可变全局缓存无锁、无失效手段；token_file 硬编码 `data/token.json`，请求中 token 身份被忽略；缓存写入 `except Exception` 仅 warning；ValueError→BadRequestError(str(e)) |
| GET+POST /api/google-sheets | google_sheet_api.py:google_sheets | login_required | GET: `service.list_sheets` → google_sheet_repository.list_filtered。POST: `service.create_sheet` → get_duplicate_row / create | success() | GET 的 table_type 在路由与 service 被 normalize 两次；POST ValueError→BadRequestError(str(e)) |
| GET+PUT+DELETE /api/google-sheets/<int:sheet_id> | google_sheet_api.py:google_sheet_detail | login_required | GET: `service.get_sheet` → google_sheet_repository.get。PUT: `update_sheet` → get / get_duplicate_row / update。DELETE: `delete_sheet` → get / delete | success() | service"不存在"用 ValueError 表达而非 NotFoundError（404 语义降级为 400）；GET/PUT/DELETE 三语义合一 |
| GET /api/google-sheet-tokens | google_sheet_api.py:list_google_sheet_tokens | login_required | `list_tokens` → reconcile_in_use_counts → task_repository.list_id_config_by_status + google_sheet_token_repository.apply_in_use_counts（写库），再 list_entities_ordered；`get_usage_summary` → 再次 reconcile + sum_field×2 / count_active / list_active_entities | success() | GET 端点内执行数据库写且单次请求触发两次 reconcile；同一 handler 内取两次 service 实例 |
| GET+PUT /api/google-sheet-tokens/<int:token_id> | google_sheet_api.py:google_sheet_token_detail | login_required | GET: `get_token` → google_sheet_token_repository.get_entity（不存在抛 ValueError）。PUT: `update_token` → get_entity + flush + ensure_token_file（写文件）+ commit | success() | 不存在用 ValueError（400 而非 404）；PUT 内含文件系统写 |
| POST /api/google-sheet-tokens/import | google_sheet_api.py:import_google_sheet_token | login_required | `import_token` → get_by_context / add_entity / flush / commit + ensure_token_file（写文件） | success() | 内含文件系统写；ValueError→BadRequestError(str(e)) |
| DELETE /api/google-sheet-tokens/<int:token_id> | google_sheet_api.py:delete_google_sheet_token | login_required | `delete_token` → google_sheet_token_repository.delete | success() | — |

### template_api.py（5 个端点，前缀 /api）

| 方法+完整路径 | handler | 鉴权 | 调用链 | 响应出口 | 问题标记 |
|---|---|---|---|---|---|
| GET /api/templates | template_api.py:get_templates | login_required | `task_template_service.list_templates` → task_template_repository.list_all | success() | — |
| POST /api/templates | create_template | login_required | `create_template` → task_template_repository.create | success() | — |
| GET /api/templates/<int:template_id> | get_template | login_required | `get_template` → task_template_repository.get_required | success() | — |
| PUT /api/templates/<int:template_id> | update_template | login_required | `update_template` → get / update | success() | — |
| DELETE /api/templates/<int:template_id> | delete_template | login_required | `delete_template` → task_template_repository.delete | success() | — |

### config_api.py（5 个端点，前缀 /api）

| 方法+完整路径 | handler | 鉴权 | 调用链 | 响应出口 | 问题标记 |
|---|---|---|---|---|---|
| GET /api/config | config_api.py:get_config | login_required | `config_manager.get_all_configs(force_refresh=True)` → system_config_repository（全量重载） | success() | 每次请求强制全量重载并绕过缓存 |
| POST /api/config | update_config | login_required | `config_manager.update_configs` → 逐项 set_config → system_config_repository.upsert + 刷新 | success() / ServiceError | update_configs 吞异常仅返回 False，路由只回笼统"配置更新失败"，失败 key 不下发 |
| GET /api/config/validate | validate_config | login_required | `get_db_config_rows` → system_config_repository.list_rows；`get_cache_snapshot`（内存）；`get_google_sheet_config`（缓存） | success() | 诊断端点下发全部配置明文（db_configs/cache_configs 未脱敏）——BUG-14 |
| GET /api/system-configs | list_system_configs | login_required | `get_db_config_rows` → system_config_repository.list_rows | success() | — |
| PUT /api/system-configs/<string:key> | update_system_config | login_required | `config_manager.update_config_row` → system_config_repository.update + refresh_cache | success() | — |

### meta_api.py（3 个端点，前缀 /api）

| 方法+完整路径 | handler | 鉴权 | 调用链 | 响应出口 | 问题标记 |
|---|---|---|---|---|---|
| GET /api/meta/versions | meta_api.py:get_versions | 无 | 纯静态硬编码列表 | success() | `value: "C7"` 大写笔误——BUG-07（`?version=C7` 落默认模板分支）；无鉴权 |
| GET /api/meta/enums | get_enums | 无 | 读 model 枚举 choices()（内存） | success() | 无鉴权暴露全部枚举 |
| GET /api/meta/nav | get_nav | login_required | `navigation_service.list_visible_entities` → navigation_repository.list_visible_entities；排序、build_navigation_tree、权限过滤（g.current_user 权限集）均内联路由层 | success() | 权限过滤/树构建/排序业务逻辑内联路由（含两个嵌套闭包） |

---

## 2. 回测/导出/行情域（50 端点）

### backtest_api.py（12 个端点；bt_api_bp=/backtest-training、bmp_api_bp=/backtest-multi-product）

| 方法+完整路径 | handler | 鉴权 | 调用链 | 响应出口 | 问题标记 |
|---|---|---|---|---|---|
| POST /backtest-training/api/import-excel | import_excel | login_required（+heavy 限流） | BacktestExcelService().import_uploaded_excel → 无 repository（openpyxl 解析；上传文件落盘 data/backtest_excel/） | success() | BadRequestError(str(exc))；私有函数 import（从 backtest_training_api_service 引 7 个 `_` 前缀函数） |
| GET /backtest-training/api/task-results/<task_id> | get_task_results_by_task_id | login_required | _load_backtest_task → task_repository.get_entity；task_manager.get_task_results_page_raw → task_result_repository.list_by_task_paginated_raw_parameters | success() | 分页参数路由内手工 clamp |
| GET /backtest-training/api/task-result/<int:task_result_id> | get_task_result_detail | login_required | _load_backtest_task_result → task_result_repository.get_export_entity + task_repository.get_entity；_build_backtest_result_export_data（service 内计算）；task_manager.get_return_entity → task_result_repository.get_return_entity | success() | word_report_payload 在路由内拼装 |
| GET /backtest-training/api/task-result/<int:id>/export-preview | get_task_result_export_preview | login_required（+export 限流） | _load_backtest_task_result；_build_backtest_result_export_data；_build_backtest_result_export_rows → xpl_analyzer.format_export_file_data（pandas） | success() | 裸 `except Exception` 转 BadRequestError("预览数据生成失败")（吞具体异常） |
| GET /backtest-training/api/task-summary/<task_id> | get_task_summary | login_required | _load_backtest_task → task_repository.get_entity；_build_c3_summary_rows → task_result_repository.list_preview_entities(success_only=True) + get_return_entity | success() | 路由内手工校验 model_version 抛 BadRequest |
| GET /backtest-training/api/global-preview/<task_id> | get_global_preview | login_required | _load_backtest_task → task_repository.get_entity；_build_global_preview_payload → task_repository.get_entity + task_result_repository.list_preview_entities + list_return_entities | success() | 私有函数 import |
| POST /backtest-multi-product/api/import-excel | bmp_import_excel | login_required（+heavy 限流） | BacktestExcelService().import_uploaded_excel → 无 repository（文件落盘） | success() | BadRequestError(str(exc)) |
| GET /backtest-multi-product/api/task-results/<task_id> | bmp_get_task_results_by_task_id | login_required | _load_multi_product_task_or_none → task_manager.get_task → task_repository.get；task_manager.get_task_results_page_raw → task_result_repository.list_by_task_paginated_raw_parameters | success() | — |
| GET /backtest-multi-product/api/task-result/<int:id> | bmp_get_task_result_detail | login_required | task_manager.get_required_result_entity → task_result_repository.get_entity；_load_multi_product_task_or_none → task_repository.get（**BUG-04：返回 None 时调用点 AttributeError→500**）；extract_core_metrics（performance_analysis 包）；task_manager.get_return_entity | success() | 路由内大量 payload 解析/模型名推断逻辑（私有函数定义于路由文件） |
| GET /backtest-multi-product/api/global-preview/<task_id> | bmp_get_global_preview | login_required | _load_multi_product_task_or_none → task_repository.get；build_multi_product_global_preview_payload → task_repository.get_entity + list_preview_entities（+进程内缓存） | success() | — |
| POST /backtest-multi-product/api/global-preview/<task_id>/calculate-ratios | bmp_calculate_ratios | login_required（+heavy 限流） | _load_multi_product_task_or_none；parse_body(CalculateRatiosSchema)；build_multi_product_global_preview_payload | success() | BadRequestError(str(exc)) |
| PUT /backtest-multi-product/api/global-preview/<task_id>/ratios | bmp_update_ratios | login_required | _load_multi_product_task_or_none；update_task_ratios → task_repository.update_fields；build_multi_product_global_preview_payload | success() | 手拼校验（get_json+isinstance ratios，未走 schema，与兄弟端点不一致） |

### backtest_training.py（12 个端点 = 6 视图 × bp/legacy_bp 双注册）

| 方法+完整路径 | handler | 鉴权 | 调用链 | 响应出口 | 问题标记 |
|---|---|---|---|---|---|
| GET /backtest-training/create | create_page | 无 | 无（直出模板） | render_template | 无鉴权 |
| GET /backtest-training/list | list_page | 无 | 无 | render_template | 无鉴权 |
| GET /backtest-training/detail/<task_id> | detail_page | 无 | 无 | render_template | 无鉴权 |
| GET /backtest-training/global-preview/<task_id> | global_preview_page | 无 | 无 | render_template | 无鉴权 |
| GET /backtest-training/result/<int:result_id> | result_page | 无 | task_manager.resolve_result_task_id → task_result_repository.get + task_repository.get | render_template | 无鉴权 |
| GET /backtest-training/result/<int:id>/export-preview | result_export_preview_page | 无 | 无 | render_template | 无鉴权 |
| GET /backtest/create（+list/detail/global-preview/result/export-preview 共 6 条） | 同上（add_url_rule legacy 双注册） | 无 | 同上 | render_template | 无鉴权；legacy 双注册 |

### backtest_multi_product.py（10 个端点 = 5 视图 × 双注册）

| 方法+完整路径 | handler | 鉴权 | 调用链 | 响应出口 | 问题标记 |
|---|---|---|---|---|---|
| GET /backtest-multi-product/create、/list、/detail/<task_id>、/global-preview/<task_id> | create_page/list_page/detail_page/global_preview_page | 无 | 无 | render_template | 无鉴权 |
| GET /backtest-multi-product/result/<int:result_id> | result_page | 无 | task_manager.resolve_result_task_id(result_id, BACKTEST_MULTI_PRODUCT_TASK_TYPE) → task_result_repository.get + task_repository.get | render_template | 无鉴权 |
| GET /backtest-multi/*（5 条 legacy 双注册） | 同上 | 无 | 同上 | render_template | 无鉴权；legacy 双注册 |

### global_preview.py（2 个端点；gp 域页面）

| 方法+完整路径 | handler | 鉴权 | 调用链 | 响应出口 | 问题标记 |
|---|---|---|---|---|---|
| GET /global-preview | page | 无 | 无 | render_template | 无鉴权 |
| GET /global-preview/single_product | page（同函数双 rule） | 无 | 无 | render_template | 无鉴权 |

文件内事实：`export_preview(task_id)`（原 `/global-preview/<task_id>/export` 导出流）**无路由无引用，未注册死代码**；其内部保留路由层 ZIP 流实现（`_stream_stock_export_zip`：线程+Queue 流式写 ZipFile、`_build_global_preview_workbook` openpyxl 构建）并 import 私有函数；`_preview_status` 与 global_preview_api.py 重复定义。

### global_preview_api.py（2 个端点；gp_api_bp=/global-preview）

| 方法+完整路径 | handler | 鉴权 | 调用链 | 响应出口 | 问题标记 |
|---|---|---|---|---|---|
| GET /global-preview/api/tasks/<task_id> | get_preview | login_required | task_manager.get_required_task → task_repository.get_required；_build_global_preview_initial_payload → task_repository.get_entity + task_result_repository.list_preview_index_rows + list_preview_entities + list_return_entities | success() | 私有函数 import；_preview_status 重复实现 |
| POST /global-preview/api/tasks/<task_id>/preview-group | get_preview_group | login_required | task_manager.get_required_task；_build_global_preview_group_payload → task_repository.get_entity + list_preview_entities | success() | 手拼校验（get_json(silent=True) 手工取/校验 result_ids）；私有函数 import |

### export_api.py（10 个端点；/api/exports；全部 login_required + rate_limit_export 限流）

| 方法+完整路径 | handler | 调用链 | 响应出口 | 问题标记 |
|---|---|---|---|---|
| GET /api/exports/tasks/<task_id> | export_task_results | get_required_task → task_repository.get_required；_require_completed_task（路由内状态校验）；export_service.export_task_results → task_repository.get_entity + task_result_repository.list_by_task + export_file_service.build_task_export（openpyxl） | 文件流(Excel) | BadRequestError(str(exc)) |
| GET /api/exports/tasks/<task_id>/stocks | export_task_results_by_stock | get_required_task；export_service.export_task_results_by_stock → task_result_repository.list_by_task + build_c7_stock_code_export_archive（openpyxl+ZIP） | 文件流(ZIP) | BadRequestError(str(exc)) |
| POST /api/exports/tasks/batch | export_task_results_batch | export_service.export_task_results_batch → task_repository.list_by_ids + task_result_repository.list_export_rows + build_c3_worksheets + csv.writer | 文件流(CSV) | 手拼校验（task_ids）；LookupError→NotFoundError(str(exc))、ValueError→BadRequestError(str(exc)) |
| GET /api/exports/global-previews/<task_id> | export_global_preview | get_required_task；_parse_ratios_query（路由内手工解析）；export_service.export_global_preview → _build_global_preview_payload + _build_global_preview_workbook（openpyxl） | 文件流(Excel) | 手拼校验；BadRequestError(str(exc)) |
| GET /api/exports/global-previews/<task_id>/stocks | export_global_preview_by_stock | get_required_task；_parse_ratios_query；export_service.export_global_preview_by_stock → 多品 build_multi_product_global_preview_payload / 单品 _build_global_preview_payload + _stream_stock_zip（service 内 ZipFile 流式） | 文件流(ZIP 流式) | BadRequestError(str(exc)) |
| POST /api/exports/global-previews/batch | export_global_preview_batch | export_service.export_global_preview_batch → 逐任务 get_entity + payload + workbook + 内存 ZipFile | 文件流(ZIP) | 手拼校验（task_ids）；str(exc) 两类 |
| GET /api/exports/backtest-results/<int:result_id> | export_backtest_result | task_manager.get_task_result → task_result_repository.get；get_required_task；export_service.export_backtest_result → get_export_entity + _build_backtest_result_export_data + xpl_analyzer.export_file（pandas→CSV） | 文件流(CSV) | BadRequestError(str(exc)) |
| POST /api/exports/xpl | export_xpl | export_service.export_xpl → xpl_analyzer.export_file（无 repository） | 文件流(CSV) | BadRequestError(str(exc)) |
| POST /api/exports/backtest-reports/word | export_backtest_word_report | parse_body(StrategyBacktestReportSchema)；export_service.export_backtest_word → build_multi_product_global_preview_word_payload → task_repository.get_entity + list_preview_entities(success_only=True)；strategy_backtest_report_service.generate_word → get_return_entity / list_return_series_ids_by_task + matplotlib + python-docx | 文件流(DOCX) | BadRequestError(str(exc))；RPT-M 二次校验手写在 service |
| GET /api/exports/model-summary | export_model_summary | export_service.export_model_summary → model_summary_service.export_csv → SummaryQueryMixin.query → backtest_repository.page_summary_index / list_task_ids_by_visible_types / list_task_result_pairs_by_filters → CSV 文本 | 文件流(CSV) | BadRequestError(str(exc))；路由显式传 ignore_permissions=True 绕过权限过滤 |

### stock_api.py（1 个端点；/api）

| 方法+完整路径 | handler | 鉴权 | 调用链 | 响应出口 | 问题标记 |
|---|---|---|---|---|---|
| GET /api/search-stocks | search_stocks | login_required | StockSearchService().search_stocks → DFCJStockApi.get_search_list_by_stock_code（东财外部搜索 API）；save_metadata → stock_metadata_repository.bulk_upsert | success() | BadRequestError(str(exc))；ServiceError(str(exc), 502)（上游错误文本直发）；分页参数路由内手工 clamp |

### eastmoney_kline.py（1 个端点）

| 方法+完整路径 | handler | 鉴权 | 调用链 | 响应出口 | 问题标记 |
|---|---|---|---|---|---|
| GET /eastmoney-kline | index | 无 | 无 | render_template | 无鉴权 |

---

## 3. 管理认证域（57 端点）

### admin.py（13 个端点）

| 方法+完整路径 | handler | 鉴权 | 调用链 | 响应出口 | 问题标记 |
|---|---|---|---|---|---|
| GET /admin/ | dashboard | **无** | TaskDashboardQueryService.get_dashboard_counts → task_repository.summary_counts；get_recent_tasks → task_repository.list_recent | render_template | **管理首页无鉴权** |
| GET /admin/tasks、/config、/navigation、/logs、/templates、/results、/model-summary、/eastmoney-kline、/google-sheets、/scheduler | 对应 handler | **无** | 模板渲染（部分引 model 枚举 choices） | render_template | **页面无鉴权** |
| GET /admin/users、/admin/roles | 对应 handler | **无** | 模板渲染 | render_template | **用户/角色管理页面无鉴权** |

### admin_api.py（7 个端点；/admin）

| 方法+完整路径 | handler | 鉴权 | 调用链 | 响应出口 | 问题标记 |
|---|---|---|---|---|---|
| GET /admin/api/scheduler/status | scheduler_status | login_required | scheduler_service.get_async_task_status（直连 running_tasks 内存字典，无 repository） | success() | 直连服务内部内存对象 |
| GET /admin/api/dashboard/overview | dashboard_overview | login_required | TaskRuntimeViewService.build_dashboard_overview → TaskDashboardQueryService（task_repository.list_distinct_task_types / count_grouped_by_status / count_grouped_by_task_type / count_daily_created / count_daily_completed / list_recent_entities）+ serialize_task_runtime（task_log/task_result repository + task_manager 内存态） | **jsonify手拼** | **绕过统一信封**；直连 task_manager.running_tasks / task_stop_events |
| GET /admin/api/model-summary | model_summary_api | login_required | model_summary_service.query → backtest_repository.page_summary_index | success() | — |
| POST /admin/api/model-summary/rebuild | rebuild_model_summary_api | login_required + limiter | model_summary_service.start_rebuild_job → task_repository.add_entity + task_log_repository.add_entity + task_result_repository.commit；后台线程 _run_rebuild_job → backtest_repository.list_finished_task_ids / list_task_result_pairs_for_rebuild / delete_summary_index_by_task_ids / add_entity / delete_entity | success() | 写操作日志以 TaskLog 落库，路由层无 logger；无 admin_required |
| GET /admin/api/model-summary/rebuild/status | model_summary_rebuild_status_api | login_required | model_summary_service.get_rebuild_job / latest_rebuild_job（内存 _jobs + task_repository.get_latest_task_id_by_type） | success() | — |
| GET /admin/api/tasks/<task_id>/runtime-detail | task_runtime_detail | login_required | TaskRuntimeViewService.get_runtime_detail → task_repository.get_entity（NotFoundError→404）+ serialize_task_runtime（task_log/task_result repository + check_local_task_status） | success() | 直连 task_manager 内存对象 |
| POST /admin/api/scheduler/cleanup | cleanup_completed_tasks | login_required | scheduler_service.cleanup_completed_tasks（直连 running_tasks 内存字典删除，无 repository） | success() | 写（删）操作仅及内存，非空才记日志 |

### auth_api.py（13 个端点；/api）

| 方法+完整路径 | handler | 鉴权 | 调用链 | 响应出口 | 问题标记 |
|---|---|---|---|---|---|
| POST /api/auth/login | login | **无** | rbac_service.login_user → rbac_repository.get_user_credentials / update_last_login / get_user；auth.create_access_token / create_refresh_token | success()（校验失败 ValidationError→400） | 登录入口无鉴权属合理；**无限流**；`request.get_json()` 未走 schema |
| POST /api/auth/refresh | refresh | **无** | rbac_service.refresh_tokens → auth.decode_token / rbac_repository.get_user / get_user_state | success()（无效令牌→401） | 无鉴权属合理；无限流 |
| GET /api/auth/me | get_me | login_required | g.current_user.to_dict（装饰器内 rbac_repository.get_user_entity） | success() | — |
| POST /api/auth/logout | logout | login_required | rbac_service.logout_user → rbac_repository.update_user（token_version+1） | success() | **写操作零日志** |
| PUT /api/auth/password | change_password | login_required | rbac_service.change_password → rbac_repository.update_user | success() | **写操作零日志** |
| GET /api/admin/users | list_users | login_required | rbac_service.list_users → rbac_repository.list_users | success() | 无 admin_required（不存在该装饰器） |
| POST /api/admin/users | create_user | login_required | rbac_service.create_user → rbac_repository.username_exists / list_roles_by_ids / create_user | success() | **无 admin_required；写操作零日志** |
| PUT /api/admin/users/<int:user_id> | update_user | login_required | rbac_service.update_user → get_user / get_user_state / update_user（可重置任意用户密码） | success() | **无 admin_required；写操作零日志** |
| DELETE /api/admin/users/<int:user_id> | delete_user | login_required | rbac_service.delete_user → get_user_state + transaction（task_repository.clear_created_by + rbac_repository.delete_user） | success() | **无 admin_required；写操作零日志（删除用户）** |
| GET /api/admin/roles | list_roles | login_required | rbac_service.list_roles → rbac_repository.list_roles | success() | 无 admin_required |
| POST /api/admin/roles | create_role | login_required | rbac_service.create_role → role_code_exists / create_role | success() | **无 admin_required；写操作零日志** |
| PUT /api/admin/roles/<int:role_id> | update_role | login_required | rbac_service.update_role → get_role / update_role | success() | **无 admin_required；写操作零日志** |
| DELETE /api/admin/roles/<int:role_id> | delete_role | login_required | rbac_service.delete_role → get_role / delete_role | success() | **无 admin_required；写操作零日志（删除角色）** |
| GET /api/admin/permissions | list_permissions | login_required | rbac_service.list_permissions_grouped → transaction + sync_navigation_permissions（navigation_repository.list_all_entities，**直写 Permission 表**）+ list_permissions | success() | GET 语义端点内含写操作，零日志 |

### auth_pages.py（1 个端点）

| 方法+完整路径 | handler | 鉴权 | 调用链 | 响应出口 | 问题标记 |
|---|---|---|---|---|---|
| GET /login | login_page | 无 | 模板渲染（`next` 参数原样透传模板） | render_template | 登录页豁免合理；next 透传需防 open redirect |

### navigation_api.py（4 个端点；/api）

| 方法+完整路径 | handler | 鉴权 | 调用链 | 响应出口 | 问题标记 |
|---|---|---|---|---|---|
| GET /api/navigation-menu-items | list_navigation_menu_items | login_required | navigation_service.list_menu_items → navigation_repository.list_all_entities | success() | — |
| POST /api/navigation-menu-items | create_navigation_menu_item | login_required | navigation_service.create_menu_item → _validate_menu_payload（get_by_key）+ transaction：create_entity + sync_navigation_permissions（直写 Permission 表） | success() | **写操作零日志**（navigation_service 整文件无 logger） |
| PUT /api/navigation-menu-items/<int:item_id> | update_navigation_menu_item | login_required | update_menu_item → get_entity + transaction：setattr 实体 + sync_navigation_permissions | success() | **写操作零日志** |
| DELETE /api/navigation-menu-items/<int:item_id> | delete_navigation_menu_item | login_required | delete_menu_item → get_entity / count_children / delete | success() | **写操作零日志** |

### scheduler_api.py（9 个端点；/api）

| 方法+完整路径 | handler | 鉴权 | 调用链 | 响应出口 | 问题标记 |
|---|---|---|---|---|---|
| GET /api/admin/scheduler/stats | get_scheduler_stats | login_required | scheduler_service.get_scheduler_stats → scheduled_task_repository.get_stats + is_running 内存标志 | success() | — |
| GET /api/admin/scheduler/tasks | get_scheduled_tasks | login_required | scheduler_service.list_tasks_page → scheduled_task_repository.list_paginated | success()（内嵌手拼 pagination） | 未走 paginated() |
| POST /api/admin/scheduler/tasks | create_scheduled_task | login_required | scheduler_service.create_task → scheduled_task_repository.create + add_job（**直连 APScheduler**）+ update_next_run | success() | 直连 APScheduler；service 层有日志 |
| PUT /api/admin/scheduler/tasks/<int:task_id> | update_scheduled_task | login_required | get_required_task → get_required；update_task → update + remove_job/add_job（直连 APScheduler） | success() | 直连 APScheduler |
| DELETE /api/admin/scheduler/tasks/<int:task_id> | delete_scheduled_task | login_required | delete_task → get_required + remove_job + scheduled_task_repository.delete | success() | 直连 APScheduler |
| POST /api/admin/scheduler/tasks/<int:task_id>/toggle | toggle_scheduled_task | login_required | toggle_task → get_required / update + remove_job/add_job | success() | 直连 APScheduler |
| POST /api/admin/scheduler/tasks/<int:task_id>/run | run_scheduled_task_now | login_required | run_task_now → get_required + get_async_task_status（内存）+ run_job_once → _execute_task_async（起线程）→ _execute_task → acquire_run_lock / refresh_entity / record_run + **subprocess.Popen**（scheduled_task_worker.py） | success() | 直连 APScheduler/线程/子进程（PIPE 死锁与锁残留见 01 文档 BUG-09） |
| GET /api/admin/scheduler/tasks/<int:task_id>/status | get_task_execution_status | login_required | get_task_execution_status → get_required + get_async_task_status + get_job_status（直连 scheduler.get_job） | success() | 直连 APScheduler |
| GET /api/admin/scheduler/status | get_scheduler_status | login_required | **scheduler_service.scheduler.get_jobs() 直连** | success() | 直连 APScheduler 内部对象 |

### database_api.py（3 个端点；/api）

| 方法+完整路径 | handler | 鉴权 | 调用链 | 响应出口 | 问题标记 |
|---|---|---|---|---|---|
| GET /api/database/status | get_database_status | login_required | DatabaseMonitor.get_full_report → 直读 db.engine.url / 各模型 .query.count()（**绕过 repository 直连 ORM/引擎**）/ db.engine.pool / sqlalchemy inspect | success() | 层间越界；子方法异常时 str(e) 写入返回 data |
| POST /api/database/vacuum | vacuum_database | login_required | DatabaseMonitor.vacuum_database（**桩方法，恒返回 success=False 固定文案，不执行任何 DB 操作**） | success() / 全局 error() 400 | **POST 写操作实为空操作**；路由零日志；无 admin_required |
| GET /api/database/suggestions | get_optimization_suggestions | login_required | DatabaseMonitor.suggest_optimizations（ORM .query.count() 直连） | success() | 绕过 repository；异常时 str(e) 进入 suggestions data |

### xpl.py（5 个端点；/xpl）

| 方法+完整路径 | handler | 鉴权 | 调用链 | 响应出口 | 问题标记 |
|---|---|---|---|---|---|
| GET /xpl/、/xpl/v1、/xpl/v2 | index 系列 | **无** | 模板渲染 | render_template | 页面无鉴权 |
| POST /xpl/analyze | analyze_data | **无**（仅 limiter） | xpl_analysis_service.analyze_text → xpl_analyzer.analyze（纯内存 pandas 计算） | success() / error() | **API 无鉴权**；限流 key 恒为 `user:anon`（无 login_required 导致全员共享一个限流桶）；ValidationError 分支 str(exc) 下发；数据级失败 **error(http_status=200)**——BUG-13；路由 try/except 重复全局兜底 |
| POST /xpl/v1/analyze | analyze_data_v1 | **无**（仅 limiter） | analyze_sheet → analyze_v1 → _init_google_sheet（读 config_manager，含硬编码默认路径）→ GoogleSheet（外部 Google Sheets API 读取） | success() / error() | 同上全部问题 |

### yule.py（2 个端点；/yule）

| 方法+完整路径 | handler | 鉴权 | 调用链 | 响应出口 | 问题标记 |
|---|---|---|---|---|---|
| GET /yule/、/yule/sjxz | index / sjxz | **无** | 模板渲染 | render_template | 页面无鉴权；死 import 一批 |

---

## 4. 全库统计

| 指标 | 数值 |
|---|---|
| 端点总数 | 148（任务域 41 / 回测导出域 50 / 管理认证域 57） |
| success()/error() 出口 JSON 端点占比 | 约 89%（任务域 33/37）；违规 5 端点（task_api ×4 + admin_api ×1） |
| paginated() 使用 | 0 |
| BadRequestError(str(exc)) 类端点 | 14（export_api 10 + backtest_api 3 + stock_api 1）+ xpl/task_api 零散 4 处 |
| 无鉴权端点 | 页面 25+（admin 13、backtest 系 24 条含 legacy、global_preview 2、xpl 3、yule 2、eastmoney 1、google_sheet 4）+ API 4（xpl analyze ×2 不合理；login/refresh 合理豁免） |
| 写操作零日志端点 | 13 |
| admin_required | 全库不存在（管理端点鉴权上限为 login_required） |
| 层间越界（路由内业务/基础设施） | 6 处（openpyxl 构建、ZIP 编排、日志解析 ×3 份、TTL 缓存、权限树、payload 推断） |

> 问题修复归属：信封/分页/校验/鉴权/日志 → `02-api-spec.md` §12 B 系列；功能 bug → `01-bugs-and-fixes.md`；任务服务内部 → `03-task-code-refactor.md`。

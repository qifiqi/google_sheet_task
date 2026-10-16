# 全库可删减代码审计（2026-10）

审查方式：`ocr`（OpenCodeReview）delegate 模式（LLM provider 未配置，按审查规则由 4 路并行审查 + 逐条全仓 grep 核实）。范围：app/ 全部、stock_sdk/、ding_stream_service/、scripts/、根入口文件；frontend/ 按约定排除；templates/static 仅做引用核对。所有"零引用"结论均含 `self.` 调用与动态派发（getattr/字符串方法名）排查；仓库内唯一动态派发点是 `registry.build_runner` 的 `_execute_*` 方法名，与下列候选无交集。

> **status: partial**（2026-10-15 复核）。审计时点本文"只登记未删除"；此后大批次已执行：`tests/archive/` 整目录删除、§1 高置信死代码（db_monitor.py、TTLCache、scheduler `_cleanup_old_logs`、text_analysis `get_performance_analysis`、export_workbook 3 个死常量等）、§3-2 C3Service.execute_task 并入基类、startup `_start_background_components` 恢复调用（执行记录见 `docs/model_update/2026-10-月度汇总.md` 同日条目）。**尚未完成**：§2 stock_sdk 裁剪批（待上游确认）、§3-3 C4 get_bdl 合并、§3-4 C5/C7 三处同构、§3-6 21 项汇总指标三处、§3-8/9 JSON 清洗多份、§4 分页双轨（PageQuery vs parse_pagination）等。下文"未删除任何代码"为审计时点表述，已过时。

## 结论速览

| 类别 | 规模 | 说明 |
|---|---|---|
| `tests/archive/` 整目录 | **约 12,895 行 / 119 个入库文件** | 已被 `norecursedirs` 排除收集，全是 xpl_service 等历史拷贝（含同名 3 份 `xpl_service.py`），git 历史可随时找回，可整目录删除 |
| 高置信死代码 | 约 550 行 | 零引用，可立即删（见 §1） |
| 中置信死代码 | 约 1,500 行 | 主要是 stock_sdk 生成代码的未用 API 面，需产品决策（见 §2） |
| 重复代码 | 约 700 行可合并 | 见 §3 |
| 可删减/简化 | 约 100 行 | 间接层、恒真条件、注释残留等（见 §4） |

## 0. `metrics.py` 不可移除（重点核实项）

`app/services/performance_analysis/metrics.py`（1851 行）**是全库唯一的 V1 指标公式引擎，删除即瘫痪核心业务**，未执行删除。证据链：

- 唯一 import 点 `analyzer.py:2`（`PerformanceMetricsMixin` 组合进 `PerformanceAnalyzer`）；全部 27 个方法均在 `_calculate_metrics_v1`（metrics.py:895）/ `_weight_combination_v1`（:1625）内部经 `self.` 调用，方法级零死代码。
- 消费方（grep 实证，134 处引用中绝大多数是结果字典字符串键而非重复实现，公式实现全库仅此一份）：
  - `facade.calculate_v1_metrics` ← `result_mapper.py`（`get_return_analysis_v1`，被 `google_sheet_tasks/c3.py:368、c4.py:385、c5.py:225` 消费）、`text_analysis.py:96`、`historical_metrics.py:183`、`backtest_training_service.py:721`、`scripts/backfill_metrics_payload.py:40`
  - 直接调用：`backtest_multi_product_service.py:510/529`（`get_calculate_metrics_v1`）、`strategy_backtest_report_service.py:297/318`、`backtest_report_query_service.py:256`（`format_export_file_data`）、`export_service.py:278/285`（`export_file`）、`model_summary/extractor.py:871`、`performance_analysis/service.py:247/260/289/514`
  - 路由在线：`/api/performance-analysis/analyze`、`/weight-combination`（`app/routes/performance_analysis_api.py`）
- `historical_metrics.py`（212 行）不是公式重复：它是旧指标 JSON 读取兼容层（别名升级 + 缺失字段按 V1 口径重算），删除前提是确认库内旧数据已全部迁移。
- 已登记的 metrics.py 已知缺陷（`tests/unit/test_xpl_service.py` 的 skip 项，非本次范围）：日度收益分布误用月度 DataFrame（:62 skip）、`calculate_monthly_return_data` 首月基准硬编码为 1（:445 skip）。

## 1. 高置信死代码（可立即删，约 550 行）

| 位置 | 内容 | 行数 | 证据 |
|---|---|---|---|
| `tests/archive/` | 整目录历史拷贝 | ~12,895 | 119 个 git 跟踪文件，pytest 已排除收集 |
| `app/utils/db_monitor.py` | 整个 `DatabaseMonitor` 模块 | ~212 | 生产零引用，仅 `tests/test_database_portability.py` 与 archive 引用 |
| `app/services/scheduler_service.py:339-409` | `_cleanup_old_logs`/`_cleanup_old_results` | ~71 | 实际执行体是 `scheduled_task_worker.py` 同名函数（见 §3-1），scheduler 侧零调用 |
| `app/services/performance_analysis/text_analysis.py:22` | `get_performance_analysis`（旧 V0 入口） | ~46 | 全仓仅定义处 |
| `app/utils/ttl_cache.py:37-69` | `TTLCache` 类（同模块的 word 导出磁盘缓存函数是活的，勿动） | ~33 | 类仅 `tests/unit/test_ttl_cache.py` 使用，可连同测试一起删 |
| `app/startup.py:776-780,801` | `_start_background_components` 及被注释的调用点；连带不可达 `init_scheduler`(:702)/`init_task_watchdog`(:719) | ~35 | 调用已注释；注意 `tests/test_startup_orchestration.py:39` 仍断言该阶段被调用（该文件在 tests 根目录、不在统一回归入口内，故断言过时未暴露）——删除时同步修测试，或决策恢复调用 |
| `app/services/export_workbook_service.py:80-92,190-210` | `C3_PARAM_COUNT`/`C3_METRIC_CELL_MAP`/`METRIC_DISPLAY_NAME_MAP` | ~33 | 已被 `app/constants/c_template_layout.py` 取代，`docs/design/constants-audit-2026-09/01-常量审计报告.md` 已判定无消费方 |
| `app/routes/backtest_api.py:167-180` | `_build_zip_member_name` | ~14 | 生产用 `backtest_report_query_service.py:52` 同名实现 |
| `app/services/performance_analysis/service.py:21-24,68,74` | `_EMPTY_RESULT_DATA`/`EMPTY_RESULT_DATA`/`get_index_annualized_rates`/`get_start_max_drawdown` | ~15 | 全仓零引用（注释自称"公开出口"但无任何 import） |
| `app/services/backtest_report_query_service.py:70-78,721-727,716` | `_sanitize_json_value`（含 1459-1468 失效别名表）、内嵌 `_normalize_display_value`、死参数 `model_name` | ~18 | 函数体内从未调用 |
| `app/services/strategy_backtest_report_charts.py:458-464` | `_histogram_limits` | ~7 | 实际分箱走 `_symmetric_histogram_limit` |
| `app/services/model_summary/jobs.py:378` | `_keep_only_best_for_task` | ~11 | upsert/rebuild 均走仓储层 `dedupe_best_per_task` |
| `app/services/task/dashboard_query.py:24,28` | `get_dashboard_counts`/`get_recent_tasks` | ~6 | 消费方走 `get_status_distribution`/`get_recent_task_models` |
| `app/services/task/query.py:76,214` | `get_all_tasks` ×2 | ~15 | 全仓仅内部委托一行 |
| `app/services/google_sheet_tasks/base.py:272-279` | `_format_log_message` 的 `'progress'`/`'api'` 分支 | ~8 | 全仓 log_type 实参只有 `step`/`api_error`/默认，分支不可达 |
| `app/services/task/runtime.py:429-445` | start_task 第一段"同 sheet 运行中"检查 | ~16 | 与 :460-475 持锁段逐字重复（diff -w 为 0），第一段冗余 |
| `app/schemas/scheduler.py:32-37` | `SchedulerTaskListQuery` | ~6 | 路由实际用 `parse_pagination` |
| `app/config.py:21,62` | `CONFIG_DIR` | ~2 | 零消费 |

## 2. 中置信死代码（需决策，约 1,500 行）

- **stock_sdk 生成代码的未用 API 面（约 1,440 行）**：SDK 是为上游 DY.Stock.Api 全量 Swagger 面生成的客户端（文件头 "Generated, Do not edit by hand"），仓内唯一消费者 `kline_service.py` 只用 `stock_data/stock_data_us` 各 2 个方法。未用的 18 个 API 组（`api/param_*.py`×14 + `sys_user/sys_role/sys_model/sys_log`，约 764 行）+ 对应 models（约 511 行）+ 导入绑定（约 88 行）+ 两组内 13 个未用 endpoint（约 78 行）。**若团队刻意保留"全 API 面镜像"则不删**；裁剪前建议与上游 Swagger 同步机制确认。
- `google_sheet_client.py`：`update_cell`(:258，仅 archive 引用)、`get`(:192)、`get_row`(:196)；批量写入走 `update_jumped_cells`。
- `task_watchdog.py:572` `_restart_retryable_error_task` 纯转发别名（仅测试引用）。
- `kline_service.py:119` `register_source`（生产源固定 5 项，仅测试引用）。
- `strategy_backtest_report_charts.py:368` `_draw_excess_line_bar_chart`（生产调用已注释，仅测试引用，删需同步删测试）。
- `run_smoke.py`（17 行）：自述临时冒烟文件，`ponytail` P11 剩余子批仍要用，P11 收尾后删。
- `scripts/backfill_metrics_payload.py`（243 行）：2026-08 一次性回填脚本，幂等可重跑，迁移确认完成后归档。

## 3. 重复代码（约 700 行可合并）

1. **调度清理 4 份拷贝（~128 行）**：`scheduler_service.py:339-409`（死代码，见 §1）与 `scheduled_task_worker.py:28-90` 几乎逐行相同，且 scheduler 侧两函数互为复制。以 worker 版为准，删 scheduler 版。
2. **C3Service.execute_task 覆盖基类（~85 行）**：`google_sheet_tasks/c3.py:436-537` vs `base.py:902-997`，diff 仅 20 行（2 处取消检查 + log_warning 传参）。基类加"执行前取消检查"钩子后删整个覆盖。违反"禁止复制骨架"约定的现行实例。
3. **C4Service.get_bdl 重复批量骨架（~100 行）**：`c4.py:97-261` vs `base.py:734-900`。真实语义差异 3 处（断点下标 `current_step-1` vs `_get_resume_start_index` 钳制、`_execute_parameter_combination` 签名、保存/推送顺序）——**resume 下标差异是行为，合并时不可静默统一**。
4. **C5/C7 三处同构（~55 行）**：`_get_custom_parameters`（c5.py:286 vs c7.py:577，差一次去重）、`_prepare_batch`（c7.py:28 vs base.py:426）、`_get_custom_kline_data`（c5.py:256 vs c7.py:519）。上提基类加 `dedupe`/`start_row`/`ohlc_columns` 参数。`_validate_check_values` 同构为 low 置信（C7 有 0.3 版本分支，只抽 `_return_data` 组装小函数即可）。
5. **model_summary/extractor.py 内部重复（~55 行）**：:708-743 与 :798-833 的"年最大超额回撤"块 36 行逐字相同（diff -w 为 0）；20 项指标格式化映射同值异键（slug vs 中文 label）。`_fallback_rows` 改由 `_extract_backtest_metric_values()` + 反查表生成。
6. **21 项汇总指标组装 3 处（~80-120 行）**：`backtest_multi_product_service._derive_metrics`(:535)、`backtest_report_query_service._build_fallback_rows`(:739)、`model_summary/extractor.py:685-890`。都基于 `collect_summary_all_entries` + SUMMARY_ROW_CONTRACT 做同一映射；以 multi_product 版 + contract 为基准程序化生成。
7. **Excel sheet 唯一命名循环 4 处（~55 行）**：`export_workbook_service.unique_sheet_name`(:763) vs 同文件 :336 内联 vs `backtest_report_query_service.py:1360`（逐字符复制）与 :52；`sanitize_sheet_name` 亦有两份。以 workbook 版为准共用。
8. **NaN/Inf→null JSON 清洗 5 份（~40 行）**：`google_sheet_tasks/base.py:78`、`routes/backtest_api.py:59`、`backtest_report_query_service.py:70`（已是死代码）、`text_analysis.py:200`、`scripts/backfill_metrics_payload.py:68`。收敛为一份（base.py 版或提为 util）。
9. **宽容 JSON 解析 5-7 份（~50 行）**：`utils/formatting.parse_lenient_json` 为共享版；`backtest_api.py:69` 与其逐字符相同、`backtest_multi_product_service._parse_json`(:264) 纯别名、`model_summary/extractor.py:138`、`task/runtime_view.py:18`、另有 `models._json_object_or_empty` 与 `task_result_repository._json_dict` 两个 dict 变体。
10. **google_sheet_client 内部重复（~50 行）**：`_reconnect`(:514) 复用 `_connect_and_select_worksheet`(:64)；`get_ranges`/`get_range` 的展开循环与"回退逐个获取"提取 `_expand_range_values`。
11. **钉钉 markdown 消息两份（~15 行）**：`ding_stream_service/message_format.py:11` vs `app/utils/ding_talk_notifier.py:76`。ding 服务本就 import app（`task_commands.py:13`），上移共用。
12. 其余小项：`_year_key`/`_metric_year_key`（~10）、月超额均值 3 处（各 ~8，可下沉 historical_metrics）、`_is_c7_0_3` 两份（~8）、`EXCEL_MIMETYPE`/`ZIP_MIMETYPE` 双定义（2）、`_preview_runtime_params_query` 两路由同体（8）、`down/upturn_rows` 参数化（9）、`ratios_override` 校验块同文件 3 次（14）、`@提及剔除`正则内联重复（2）、`stock_sdk` client.py 与 http_client.py 默认 base_url 字面量重复（1）。

## 4. 可删减/简化（约 100 行）

- `backtest_training_service.py:341,358-359,398`：`precomputed_params` 只 append 一次、外层 enumerate 只迭代一轮且索引未用。
- `google_sheet_tasks/c4.py:298-301`、`c5.py:121-124`：`if i <= len(kline)` 恒真条件 + 多余 `item = {}`。
- `google_sheet_tasks/c5.py:166,175`：同函数内 `_check_values` 重复赋值（首次未读即覆盖）；:161-165 注释块。
- `model_summary/extractor.py:627` `_extract_c5` 纯别名、:145 `_fmt_percent_like` 单行包装——内联。
- `model_summary/query.py:134`：`_query_all_results` 对 `query` 已解析参数原样重解析。
- `routes/google_sheet_api.py:73` `_normalize_table_type` 单调用点透传包装；`repositories/google_sheet_token_repository.py:57` `add_entity` 覆盖仅为默认 flush=True。
- `task/runtime.py:24,26` `import X as X` 无效自别名。
- `performance_analysis/portfolio_combiner.py:36` `normalize_weighting_mode` 恒返回常量（10+ 调用方仍传参，先清调用方再收敛）。
- 分页双轨：`schemas/common.PageQuery` vs `utils/request_parsing.parse_pagination` 并存（docstring 已自认），长期收敛为一种。
- 注释残留约 30 行（c3/c4/c5/c7/base/sheet_reader/strategy_backtest_report_service/config_manager/backtest_training_service 内若干处）。

## 5. 顺带发现的存量问题（非死代码，登记）

- `ding_stream_service/task_commands.py:282,286,297`：使用 `Task.query` 但未导入 `Task`，"查看运行/停止任务"指令执行即 NameError（`docs/model_update/2026-09-月度汇总.md` 同日条目已登记单独修复）。
- `tests/test_startup_orchestration.py:39` 断言 `_start_background_components` 被调用，与 `startup.py:801` 注释掉调用矛盾；该文件在 tests 根目录不在统一回归入口内，未暴露。
- 根目录 `frontend_source_backup_20260930.zip`、`google_task_*.tar` 未入 git（本地清理项，非仓库债务）。

## 建议执行顺序

1. 无争议批：§1 表（除 startup 一项）+ §4 注释残留 + `tests/archive/` 整目录——一次提交。
2. startup 决策批：恢复 `_start_background_components` 调用或删函数修测试——需确认调度器/看门狗当前为何被注释。
3. 重复合并批：按 §3 编号逐项小步提交（先 1/7/8/9/10 机械合并，再 2/3/4/5/6 需要钩子与行为核对的）。
4. SDK 裁剪批：与上游 Swagger 同步机制确认后裁 stock_sdk 未用面。

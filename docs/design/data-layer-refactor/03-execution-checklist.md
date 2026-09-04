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

- [ ] 1.1 `template_api.py` → 模板接口走 `task_template_repository`；`/api/results*` 三接口归位到新文件 `routes/result_api.py`（URL 不变）走 `task_result_repository`
- [ ] 1.2 `auth_api.py` → `rbac_repository`；删用户流程用 `transaction()` 保持原子（`user_roles` 清理 + `task_repository.clear_created_by`）
- [ ] 1.3 `utils/auth.py`（热路径：`list_permission_codes`/`get_user`，缓存逻辑保留）+ `meta_api.py`（0 ORM，响应已随 B0 切换，仅复核）
- [ ] 1.4 `config_api.py` → `system_config_repository` + `navigation_repository`
- [ ] 1.5 `scheduler_api.py` → `scheduled_task_repository`；4 处 `get_or_404` → `get_required` + NotFoundError 映射
- [ ] 1.6 `google_sheet_api.py` → token/sheet repository
- [ ] 1.7 `admin.py` → `task_repository.summary_counts()/recent()`；页面与 API 路由本批不拆文件（拆分属接口归位二期，另行立项）
- [ ] 1.8 `task_api.py` → `task_repository`/`task_result_repository`
- [ ] 1.9 少量文件：`backtest_multi_product.py`、`backtest_training.py`、`export_api.py`、`global_preview.py`、`google_sheet.py`、`yule.py`（核对无用 import）+ `database_api.py`、`stock_api.py`（0 ORM，仅统一响应格式）
- [ ] B1 收尾验证：`grep -rEn "db\.session|\.query\." app/routes --include="*.py"` 为空（枚举常量 import 例外）；`grep -rn '"status": "error"' app/routes` 为 0；B1 范围端点的前端读取已切至 `resp.data.*`（integration + 手动冒烟覆盖）；`pytest` 全绿

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

- [ ] 设计见 `05-task-runtime-pooling.md`；**前置依赖：B3 完成**（runtime.py 已走数据层）
- [ ] 步骤：注册表化（纯重构，行为不变）→ 全局线程池 + 并发上限 → 分类型上限 → 配置化；**单一路径，不保留裸线程回退分支**（无灰度开关）

## 回滚策略

- 每批独立 commit，出问题 `git revert` 单批；
- B3/B4 若某文件替换后发现语义风险，允许该文件单独回退 ORM 版本，并在下方"执行记录"标注豁免理由（同步更新 `01-db-inventory.md`）。

## 执行记录

| 日期 | 批次/文件 | 结果 | 偏差与说明 |
|---|---|---|---|
| 2026-09-04 | 基线预登记（全程有效） | 豁免 | 已知存量失败 3 个（基线 HEAD `44101bd` 复现，非重构引入）："全量 pytest 通过"门槛按 `408+ passed / 3 个已知失败` 解释——这 3 个失败若仍存在不阻塞进批；一旦某个被修复不得回退。清单：`tests/unit/test_kline_adjustment.py::test_c4_us_market_uses_yahoo_adjustment`（C4 美股 K 线行数不足 30 校验）、`tests/unit/test_kline_sheet_guardrails.py::test_c3_rejects_end_date_after_latest_kline_without_writing_sheet`（C3 K 线守卫同类）、`tests/unit/test_value_parser_and_task_types.py::test_parse_date_supports_iso_shapes`（ISO 日期解析）。另有 10 个既有 `@pytest.mark.skip` 属正常跳过。重构批次内新增任何失败仍视为阻塞。 |

# 接口与数据访问审计整改 · 执行提示词（目标模式入口）

> 本文件是 `docs/design/api-model-query-audit/` 六份文档的执行摘要，可直接整段复制给执行代理作为目标提示词。冲突裁决顺序：本提示词红线 > 六份文档 > 实际调用点代码。

---

你是在 `C:\Users\fuqing\Desktop\google_sheet_task` 仓库（Flask 长时任务执行平台，dev_vue 分支，生产数据库 **MySQL**，PostgreSQL 为历史在用库）执行**接口与数据访问审计整改**的代理。完整方案已定稿于 `docs/design/api-model-query-audit/`，共 6 份文档：

- `README.md` —— 范围、引擎口径、核心结论、优先级汇总（P1/P2/P3）
- `01-api-audit.md` —— 101 个 API 端点清点：信封/鉴权/职能位置审计
- `02-index-audit.md` —— 索引全景逐条判定：移除 14 / 补回 2 / 可选 2
- `03-orm-query-audit.md` —— ORM 查询问题清单与"不能动的正确设计"
- `04-db-engine-config.md` —— MySQL/PostgreSQL/SQLite 三态引擎与连接池配置
- `05-api-split-and-pydantic.md` —— API 文件级拆分蓝图（URL 不变）+ Pydantic v2 校验设计
- `06-rate-limiting.md` —— API 保护性限流（Flask-Limiter，重计算/导出端点；明确不做全局限流；登录项过渡期可选）

## 第 0 步（强制）

开工前通读上述 6 份文档；索引类操作动手前重读 `02`（判定与证据）并跑 §7 EXPLAIN 复核；行号若有偏移以实际代码为准，偏差登记到 `README.md` 文末"执行记录"表（首次执行时创建）。注意：仓库含大量中文，PowerShell 读写文件显式 UTF-8。

## 目标

1. **索引**：一个 Alembic 迁移移除 `02` §3 的 14 个无效/冗余索引，另一个迁移补回 §4 的 2 个误删索引（`scheduled_tasks(is_active,next_run_time)`、`backtest_product_result_cache(source_task_id)`）；`ix_task_results_return_series_id` 移除时**同步删除 `app/startup.py:162` 的 `_ensure_model_index` 调用与 models 对应 `index=True`**；终验：`information_schema.STATISTICS` 与 `02` §2 判定表逐条一致；
2. **限流**：引入 **Flask-Limiter**（新增依赖，`memory://` 存储，**不自行实现限流算法**），按 `06` §3 清单挂载——重计算/导出端点按 user 键（callable limit 阈值经 config_manager 运行时可调）；login 项**过渡期可选、默认不挂载**（登录体系将迁移主服务，`07` §1.2）；`errors.py` 增加 `RateLimitExceeded` → 429 中文信封专用 handler；`default_limits=[]` **不设全局限流，前端轮询路径不挂**；装饰器顺序强制 `route → login_required → limiter.limit → parse_body`；
2. **引擎配置**（`app/config.py:34-46`）：池容量参数分支从 `startswith('mysql')` 扩为**非 sqlite 即生效**（PG 同享）；mysql 分支补 `connect_args={'charset': 'utf8mb4'}`；`requirements.txt` PyMySQL 重复登记去重并加驱动矩阵注释；
3. **ORM**：`google_sheet_token_service.py:26` 与 `:67` 改 `with_entities` 投影（不得触碰 `is_available()` 等整实体路径）；
4. **xpl**：`/analyze`、`/v1/analyze` 补 `@login_required` + 统一信封（`success()/error()`），计算逻辑抽 `xpl_analysis_service.py`，路由只留 HTTP 编排；
5. **API 文件级拆分**（URL/方法/响应结构逐字节不变）：新建 `admin_api.py`（7 端点）、`backtest_api.py`（bt/bmp 两蓝图共存一文件，12 端点）、`global_preview_api.py`（2）、`logs_api.py`（2）、`navigation_api.py`（4）；`config_api.py`/`task_api.py`/`admin.py` 瘦身；`scheduler_api_bp` 注册补 `url_prefix='/api'`（路由改短路径，最终 URL 不变）；`result_api.py` 承接 `/tasks/<task_id>/results`；终验 `01` §1 表中"❌ 寄宿"清零；
6. **Pydantic v2 请求校验**：新增 `app/schemas/`（APIModel 基类 + PageQuery + 按域模块）与 `app/utils/request_parsing.py`（`parse_body/parse_query`，就地转 `app.exceptions.ValidationError` 进 400 信封，**不改 `errors.py`**）；按 `05` §2.3 V1→V4 迁移；终验 `app/utils/request_validation.py` 已删除且无引用。

## 红线（任何批次不得违反）

- **URL / HTTP 方法 / 请求响应结构零变化**（拆分与 schema 批均适用）；前端与 `template-auth.js` 豁免清单零改动；
- **参数绑定红线**：全库禁止拼接/format/f-string SQL，外部输入一律 ORM 绑定参数或 pydantic 解析（现状合规，保持）；
- **无兼容层**：校验体系唯一（Pydantic 落地后删 `request_validation.py`，不留双轨）；拆分不留旧文件别名/转发路由；
- **schema 边界纪律**：schema 只做请求边界校验，不含业务规则、不 import ORM/service；`extra="ignore"` 全局默认，import 类端点单独 forbid；
- **不得"优化"掉的既有正确设计**（`03` §3）：`bulk_create` 的 `add()` 循环（模型 `before_insert` 事件依赖）、删除统一 `synchronize_session=False`、`populate_existing()`、`paginate(error_out=False)`；
- 索引迁移：一个迁移只做一组；执行前 EXPLAIN 复核（`02` §7）；downgrade **不回补陈旧定义**（沿用 20260811 先例，注释依据）；禁止启动期 `_ensure_model_index` 私自补建与迁移冲突的索引；
- 时间基准混用（`03` §6）只登记**不修**；model_summary stock 汇总 GROUP BY（P3）与 tasks `(task_type,created_at)` 索引（P3 可选）默认不做，除非用户点名；
- 每批一个 git commit，**全量 `pytest` 通过才进下一批**。

## 关键契约速记

- 响应信封唯一出口 `success()/error()/paginated()`，xpl 迁移时 `{"status": ...}` 手写结构整体改写，字段名进 `data`；
- pydantic 语义对齐：`validate_body` 把缺失/null/空串都视为缺失——必填字符串用 `Field(min_length=1)`，可选字段显式 `| None`；差异逐端点登记；
- `PageQuery`：`page>=1`、`1<=per_page<=100`（对齐现有 clamp）；`extra="ignore"` 全局默认；
- 索引依据速记：`idx_status_created`=watchdog/选占热路径；`ix_task_results_timestamp`、`ix_task_logs_timestamp`=清理窗口；`idx_best_metric`/`ix_result_timestamp`=汇总范围过滤——这些**保留**，见 `02` §2 完整表；
- 拆分后蓝图注册：`app/routes/__init__.py` 统一显式 `url_prefix`；`/api` 下多蓝图共存合法，route 规则字符串不得重复（迁移时逐条对照 `01` §1 路径表）。

## 执行顺序（每批详见对应文档）

1. **批 1（P1 小改，先行）**：xpl 信封+service 抽取（鉴权不补，移交主服务，`01` §5 / `07` §1.3）→ 补回 2 个误删索引迁移（`02` §4）→ `startup.py:162` 删除 + `ix_task_results_return_series_id` 移除 → `config.py` 池化分支扩展 + charset + `MAX_CONTENT_LENGTH`（`04` §2 / `07` §2.2）→ requirements 去重 + **新增 Flask-Limiter 依赖**。
2. **批 2（索引主迁移）**：`02` §3 其余 12 个移除（一迁移一索引组）；EXPLAIN 前置 + 迁移后 `information_schema` 比对。
3. **批 3（ORM 投影）**：token service 两处 `with_entities`；回归任务启动/取消冒烟。
4. **批 4（schema 基建）**：`app/schemas/` + `request_parsing.py` + V3（7 处 `validate_body/require_query` 替换）；新增 `tests/unit/test_schemas_common.py`。
5. **批 5（V1/V2 schema）**：按 `05` §2.3 表逐端点迁移，每端点一 commit。
6. **批 6（文件拆分）**：按 `05` §1 蓝图逐文件归位（每文件一 commit）；`register_blueprints` 调整；`01` §1 表"❌"清零验证；**limiter 初始化（extensions）+ 429 handler + 归位端点随批挂载 `06` §3 限流**（analyze/重计算/导出按 user 键）。
7. **批 7（收尾）**：删 `request_validation.py` → AGENTS.md 接口规范/校验章节更新 → `errors.py` `_wants_json` 注释更新（不删启发式）→ 双引擎冒烟（本地 PG 连接 + MySQL EXPLAIN 记录归档）。

## 每批完成动作（固定循环）

1. `python -m pytest tests/unit tests/integration` 全绿；
2. 该批 grep 验证（各文档"终验"条目）；
3. git commit（单批一提交，问题 `git revert` 单批回滚）；
4. 在 `README.md` 文末"执行记录"表登记：日期 / 批次 / 结果 / 偏差说明。

## 新增测试

- `tests/unit/test_schemas_common.py` + 按域 schema 测试（每模型四类用例：合法/缺字段/类型错/越界）；
- 限流集成：`TestingConfig` 置 `RATELIMIT_ENABLED=False` 保证既有用例不受影响；挂载批单独验证超限请求返回 429 中文信封；
- 索引迁移测试：SQLite 内存库执行 upgrade/downgrade 不报错（可移植性冒烟，MySQL 真实验证以 EXPLAIN 归档为准）。

# 接口与数据访问审计方案（总览）

> 状态：审计完成，整改待执行。本目录是三域审计的事实底座与整改清单：
>
> - `README.md` —— 范围、引擎口径、核心结论、优先级汇总（本文件）
> - `01-api-audit.md` —— 全量 API 端点清点：响应信封 / 鉴权 / 职能位置合规审计
> - `02-index-audit.md` —— 模型索引审计：现存索引 × 实际查询逐条判定，移除/补回/新增清单
> - `03-orm-query-audit.md` —— ORM 查询问题清单（大字段加载、N+1、Python 层聚合等）
> - `04-db-engine-config.md` —— 数据库引擎与连接池配置：MySQL（主力）/ PostgreSQL（历史在用）/ SQLite（本地回退）三态优化
> - `05-api-split-and-pydantic.md` —— API 文件级拆分蓝图（URL 不变）与 Pydantic v2 请求校验设计
> - `06-rate-limiting.md` —— API 保护性限流（重计算/导出端点，明确不做全局限流；登录项过渡期可选）
> - `07-public-deployment-and-subservice.md` —— 公网部署加固与**子服务化边界**（鉴权域移交主服务清单 + 本项目保留项）
> - `EXECUTION_PROMPT.md` —— 执行提示词（目标模式入口，可整段复制给执行代理）

## 1. 范围与引擎口径

- **MySQL 是当前统一使用的生产数据库**，索引与查询优化的判定一律按 MySQL/InnoDB 口径（最左前缀、布尔低基数、utf8mb4 索引长度、在线 DDL）；
- **PostgreSQL 是历史使用且仍在运行的数据库**（`.env` 开发环境当前即 `postgresql://…`），必须保持可用并获得同等连接池配置；涉及 MySQL 专有判定的结论都标注 PG 差异；
- SQLite 仅作本地回退（`app/config.py:55` 默认值），不在优化范围；
- 红线（沿用数据层重构约定 + 本审计新增）：**全库不写拼接 SQL，外部输入一律参数绑定**（已扫描确认现状合规，见 `03` §7）。

## 2. 审计对象与数据量

| 对象 | 规模 | 来源 |
|---|---|---|
| 路由文件 | 20 个 / 4,850 行 | `app/routes/` |
| API 端点 | 101 个（另有 37 个页面路由） | 逐文件 `@*.route` 清点 |
| 数据模型 | 15 个表模型 + 2 张关联表 | `app/models.py`（977 行） |
| 索引定义 | 复合 15 + 单列 21 + 唯一约束 11（明细见 `02` §2） | models + migrations 全量比对 |
| 数据访问层 | repositories 14 文件 / 1,566 行；services ORM 散布 20 文件 | grep 清点 |
| 迁移 | 17 个版本（校准 2026-09-05 实测；含 `20260811_remove_unused_indexes` 上轮索引清理，删 32 个） | `migrations/versions/` |

## 3. 核心结论

1. **响应信封与鉴权总体合规，职能位置是主要问题**：101 个 API 中 **23 个（23%）寄宿在页面蓝图里**（`/admin/api/*`、`/backtest-training/api/*` 等 5 处），`/api` 命名空间碎片化为 5 种 URL 形态；`xpl.py` 整文件游离在信封与鉴权体系之外（`01` §3/§4/§5）。
2. **索引存在 14 个移除候选 + 2 个误删需补回**：上一轮清理（20260811）方向正确但有遗漏——删掉了调度器热路径 `idx_active_next_run` 和缓存失效 `source_task_id` 索引，却留下了 `TaskResult.return_series_id` 这类"零查询引用、还被 `startup.py:162` 启动期自动重建"的无效索引（`02` §4/§5/§6）。
3. **ORM 查询总体健康**（分页/投影/批量删除模式已普及），剩余问题集中在 token 占用链路的全表大字段加载（`config`/`token_context` TEXT 整行加载）和 model_summary 的 Python 层全量聚合（`03`）。
4. **连接池配置 MySQL 有、PostgreSQL 没有**：`config.py:40` 池化参数只在 `mysql` 前缀分支生效，PG 走 SQLAlchemy 默认（5+10），长任务多线程场景有耗尽风险；MySQL 侧还缺 `charset=utf8mb4` 显式声明（`04`）。
5. **架构前提（用户决策 2026-09-05）**：本项目后续作为子服务接入主服务，路由网关、鉴权、权限、角色、登录**整体迁移主服务**——因此接口级授权缺失（admin API 仅校验登录）、登录无防爆破等发现**登记为移交项，本项目不做权限类整改**；公网加固只保留与鉴权无关的部分（`07`）。

## 4. 优先级汇总

| 优先级 | 事项 | 文档 |
|---|---|---|
| **P1** | 补回 `scheduled_tasks(is_active, next_run_time)` 索引（调度 worker `find_due` 热路径） | `02` §6 |
| **P1** | 补回 `backtest_product_result_cache(source_task_id)` 索引（缓存失效查询在用，20260811 误删） | `02` §6 |
| **P1（公网前）** | 请求体/上传大小限制：`MAX_CONTENT_LENGTH=50MB` + nginx `client_max_body_size`（当前完全未设） | `07` §2.2 |
| **P1（公网前）** | 部署形态：nginx TLS + 安全响应头 + Gunicorn，禁 `app.run` 直暴 | `07` §2.1 |
| **P2** | 移除 14 个无效/冗余索引（清单见 `02` §5；其中 `ix_task_results_return_series_id` 需同步删除 `startup.py:162` 的启动重建逻辑） | `02` §5 |
| **P2** | 连接池参数分支扩展到 PostgreSQL；MySQL 显式 `charset=utf8mb4`；`requirements.txt` PyMySQL 重复登记去重 | `04` §2/§3 |
| **P2** | token 占用链路两处大字段整行加载改投影（`03` §2.1/§2.2）；模型时间戳 `utcnow`/`now` 混用登记（`03` §6） | `03` |
| **P2** | Pydantic v2 请求校验落地（基建 + V1~V3 迁移，最终删除 `request_validation.py`）；API 文件级拆分（`admin_api/backtest_api/logs_api/navigation_api` 等，URL 不变） | `05` |
| **P2** | 保护性限流挂载：重计算/导出端点（**Flask-Limiter**，内存存储，429 中文信封 handler，无自写限流算法）；登录限流**过渡期可选**（登录将迁移主服务） | `06` §2/§3 |
| **P2** | xpl 信封收敛 + 计算逻辑抽 service（**不含鉴权**——`login_required` 补挂移交主服务） | `01` §5 / `07` §1.3 |
| **P3（独立立项）** | bt/bmp 重复端点家族的**行为级**合并（文件级归位已提前至 `05` P2 批）；`errors.py` `_wants_json` 简化评估 | `01` §6 / `05` |
| **P3** | model_summary stock 汇总改 SQL GROUP BY；其余微优化 | `03` §4 |
| **移交主服务（登记，本项目不实现）** | 接口级授权（admin API 任何登录用户可调，含用户/角色 CRUD、vacuum、rebuild）、登录防爆破、RBAC/登录体系迁移、页面服务端守卫 | `07` §1 |

## 5. 执行原则

1. 索引变更走 **Alembic 迁移**（MySQL InnoDB 加删索引默认 online DDL，不锁写；SQLite 本地回退不受影响），禁止启动期 `ensure_index` 私自补建与迁移冲突的索引；
2. 每个索引移除在迁移前用 `EXPLAIN` 复核（`02` §7 给出验证 SQL），并保留 downgrade 说明（沿用 20260811 "不回补陈旧定义" 的约定）；
3. API 归位类改动**必须保持 URL 不变**（前端 101 处调用点零改动），仅动代码归属与蓝图注册；
4. 改动逐项可回滚：索引迁移一迁移一索引组；API 归位按文件为单位。

## 执行记录

| 日期 | 批次 | 结果 | 偏差说明 |
|---|---|---|---|
| 2026-09-05 | 批 0 文档校准 | 完成 | 执行前审计发现 4 处文档与代码不符并先修文档：① 03 §3.1/3.2 token service 两处 ORM 已在数据层 B2 迁入仓储，整改点移到仓储层（list_entities_by_status 投影 / apply_in_use_counts）；② 02 补登 startup.py:357-358 两个 navigation 索引补建调用（对应索引移除须同步删）；③ 05 validate_body 调用点 7→5（auth ×3 + template ×2，require_query 无调用点）；④ README 迁移版本 19→17。另登记：README/07 与目标提示词第 4 条矛盾（xpl 是否补 login_required）——按 README §4 P2 与 07 §1.3 执行"鉴权不补，移交主服务"。 |

| 2026-09-05 | 批 1 P1 小改（89b8337） | 通过 | xpl 信封收敛+计算抽 xpl_analysis_service（鉴权不补，前端零改动——v1/v2 自带信封感知解析；死函数 export_file 移除）；restore_active_idx 补回 2 误删索引；drop_return_series_idx 移除零引用索引并同步删 startup.py:162 与 models index=True；config 池化分支扩为非 sqlite+mysql charset+MAX_CONTENT_LENGTH=50MB；requirements 去重+Flask-Limiter/pydantic 依赖。偏差：迁移物理表名带 t_param_ 前缀（20260811 先例所写的无前缀表名在本仓库模型下不可复跑）；EXPLAIN 复核无本地 MySQL，归档为生产/预发执行项。 |
| 2026-09-05 | 批 2 索引主迁移（be4293e） | 通过 | 02 §3 其余 13 个索引移除（一迁移一组）；models index=True/__table_args__ 同步摘除；startup.py:357-358 补建调用删除（批 0 校准补充项）。SQLite 冒烟：stamp 上一版→upgrade→14 陈旧清零+2 补回+保留在位→downgrade。偏差：EXPLAIN 逐条复核待 MySQL 环境。 |
| 2026-09-05 | 批 3 ORM 投影（64d8257） | 通过 | 按批 0 校准后的仓储层方案：list_id_config_by_status 投影（id+config）、apply_in_use_counts 按主键 UPDATE 对账；is_available() 整实体路径未触碰。启动/取消回归冒烟通过。 |
| 2026-09-05 | 批 4 schema 基建（8bd7de7） | 通过 | app/schemas/（APIModel/PageQuery）+ request_parsing（就地转 ValidationError，errors.py 零改动）+ 5 处 validate_body 迁移 + test_schemas_common 12 用例。 |
| 2026-09-05 | 批 5 V1/V2 schema（45090a3） | 通过 | 按域分组提交（裁量偏差：未逐端点一 commit，回滚粒度为域级）。偏差登记：/auth/login 保持原手动合并校验（UX 文案不变+登录域移交主服务）；import-excel 为 multipart 不在 JSON body 校验域；navigation 复合业务校验留路由。 |
| 2026-09-05 | 批 6 拆分+限流（068d5b9/74eed3d/9a35e06/c0dcc19/00bb32a） | 通过 | admin_api（7 端点+rebuild 限流）/backtest_api（bt+bmp 12 端点+heavy 限流）/global_preview_api（2）/logs_api（2）/navigation_api（4）归位；config/task/admin 瘦身；scheduler url_prefix=/api+短路径（最终 URL 逐字节不变，全站 150 条路由数不变）；limiter 基建（extensions+429 中文 handler+TestingConfig 关闭+rate_limit_* 播种）；xpl analyze 挂 rate_limit_analyze。01 §1 ❌寄宿清零。测试导入路径与 monkeypatch 目标同批更新。 |
| 2026-09-05 | 批 7 收尾（本批） | 通过 | request_validation.py 删除（引用清零；test_unified_envelope 校验用例迁移到 parse_body/parse_query）；AGENTS.md 请求校验章节改 Pydantic；errors.py _wants_json 注释更新（Accept 启发式保留）。双引擎冒烟：PG 池化/MySQL charset/SQLite 默认 断言通过；MySQL 真库 EXPLAIN 归档仍需生产环境（同批 1/2 登记）。终验：488 passed / 3 豁免 / 10 skipped。 |
| 2026-09-05 | 批 8 补挂 rate_limit_export（验证器复核发现） | 通过 | 终验复核发现 06 §3 清单有一项遗漏：export_api.py 的 10 个导出端点未挂限流。补齐：/tasks/<id>、/tasks/<id>/stocks、/tasks/batch、/global-previews/<id>、/global-previews/<id>/stocks、/global-previews/batch、/backtest-results/<id>、/xpl、/backtest-reports/word、/model-summary 统一挂 rate_limit_export（10/min，user 键，阈值经 config_manager 运行时可调；模块级 _export_limit + _rate_limit/_user_key helper）；backtest_api 的 /api/task-result/<id>/export-preview 同步补挂。装饰器顺序 route → login_required → limiter.limit 全部合规。新增 test_rate_limiting.py 真实导出路由用例（前 10 次 404、第 11 次 429 中文信封）。终验：489 passed / 3 豁免 / 10 skipped。 |
| 2026-09-05 | 批 9 交付核查与回归修复（独立复核） | 通过 | 150 条路由规则+方法与拆分前（44101bd）逐字节比对一致（legacy 回测页除外）；unit+integration 489 passed / 10 skipped 复现。核查发现并修复 4 处本批执行引入的回归：① 批 6b 将 backtest_multi_product_legacy url_prefix 误由 /backtest-multi 改为 /backtest（与 backtest_training_legacy 撞车，/backtest-multi/* 5 个旧版页面 404，startup.py:607-608 页面权限映射仍指旧前缀），改回；②③ backtest_training.py / backtest_multi_product.py 的 result_page 迁仓储后漏 import task_repository/task_result_repository/normalize_task_type（页面 500 NameError），补齐；④ 批 5 backtest_api.py 使用 CalculateRatiosSchema 未 import（bmp /calculate-ratios 端点 500），补 import。另修复数据层批次引入的 2 处：⑤ B4 google_sheet_service_base.py._save_to_database 漏 import task_log_repository（C3 系 TaskLog 写入路径 NameError）；⑥ B2 stock_search_service.save_metadata 丢失旧 normalize_stock_payload 的 raw→raw_json 归一化（StockMetadata(**payload) TypeError，/api/search-stocks 有结果即 500），恢复 raw_json JSON 序列化，并同步把 tests/test_stock_search_service.py 断言更新为统一信封 data.results。工程清理：删 tests/ 根 7 个死文件（6 个 import 已删模块无法收集 + test_p0_p1_refactor 与 tests/unit 同名冲突致根目录 `pytest` 收集失败），根目录 pytest 恢复可用；venv 补装 requirements 已声明的 Flask-Limiter（此前缺失致应用无法启动）；global_preview.py 补 normalize_task_type/stream_with_context import（export_preview 为拆分前既有无路由死代码，是否接线另行立项）。遗留登记：根目录存量测试尚有 10 个历史失败（postgres→mysql 迁移工具 / market_support / startup_orchestration，44101bd 上同样失败，非本批引入）；task_api/admin_api 共 8 处 jsonify 直传未收敛（01 §2 既有待办）。终验：unit+integration 489 passed / 3 failed(历史) / 10 skipped；根目录存量 49 passed / 10 failed(历史，与 44101bd 持平)；pyflakes app/ 未定义名 0。 |
| 2026-09-05 | 批 10 dto 收编 schemas + schema 字段缺口修复（05 §2.3 V1 清单补漏） | 通过 | 用户复核发现 app/dto 与 app/schemas 双轨。合并：① app/dto/strategy_backtest_report.py（全库最后一条手写 dataclass+ValueError 校验路径）Pydantic 化为 schemas/backtest.py 的 StrategyBacktestReportSchema（APIModel + model_validator 跨字段校验，保持旧错误文案与校验顺序）；三种请求形态统一收口——RPT-S 顶层三选一来源、RPT-M products 形态（服务端构建载荷）、RPT-M group_key 形态（前端全局预览页直传，05 §2.3 V1 清单此前漏登记 /backtest-reports/word 端点）；② export_api 改 parse_body(StrategyBacktestReportSchema)，export_service.export_backtest_word 收敛为仅收 Schema 并在 RPT-M 分支重建载荷后二次 model_validate，generate_word 删除 dict|DTO 双轨入参；③ 删除 app/dto 目录，weighting_mode 归一化留在 portfolio_combiner（schemas 不 import service）。字段缺口修复（用户复核发现）：④ TasksBatchCreateSchema 由空 APIModel 改 RootModel[dict]——原写法被 .root 调用必 AttributeError，C31 /tasks/batch-create 端点 500；⑤ 同端点恢复旧路由丢失的 service ValueError→BadRequestError 翻译（"至少需要一组 sheets 配置" 等校验消息此前变 500）；⑥ CreateUserSchema 补 is_alert_oncall 字段并修复 create_user/create_role 在 pydantic 模型上混用 .get() 的 AttributeError（POST /api/admin/users、/api/admin/roles 均 500）。测试同批更新：test_xpl_v2_page 改 model_validate + pydantic ValidationError（ValueError 子类，match 断言保留）；test_backtest_multi_product generate_word 捕获断言改属性访问。偏差登记：非 list/dict 类型的结构错误消息由手写文案变为 pydantic 默认消息（400 语义不变）；update_user/update_role 保持 raw dict 键存在性语义未 schema 化（V4 余项）。终验：unit+integration 489 passed / 3 failed(历史) / 10 skipped；test_xpl_v2_page 12 passed；pyflakes 无未定义名。 |
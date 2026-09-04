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


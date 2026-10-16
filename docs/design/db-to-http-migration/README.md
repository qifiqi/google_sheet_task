# db-to-http 数据层迁移方案（2026-09）

分支：`dev_db_to_http`。参考实现：`dev_vue_http` 分支（已验证的 SDK 接入与单 Token 鉴权）。

## 1. 目标与边界

- 数据层（repositories）全量接入远程 DY.Stock.Api（`172.18.20.20:8081`，接口契约见 swagger 文档）；本地 DB 层暂时保留为回退（`DATA_ACCESS_MODE=db`），原 ORM 仓储代码零改动，仅新增 HTTP 孪生实现。
- 登录改为单 Token 子服务模式：前端在 header `Token` 字段携带主 Web 颁发的令牌；本服务经 `POST /api/SysUser/GetUserInfo` 校验、`POST /api/SysUser/GetUserRoleList` 读取路由表（菜单）。本地 JWT/RBAC/SSO 全部停用（代码注释保留）。
- 仪表盘与看门狗整体停用（注释保留）。
- 无法接入的数据层函数：就地 `TODO(db-to-http)` 标注 + 本文 §6 登记。

## 2. 架构

```
service / routes（零改动）
        │ from app.repositories import task_repository
        ▼
app/repositories/__init__.py        ← 唯一绑定点（模块级单例，启动期按 env 选择）
        │ DATA_ACCESS_MODE=http（默认）→ http_backend/<name>_repository.py（同签名孪生）
        │ DATA_ACCESS_MODE=db          → <name>_repository.py（本地 ORM，原样保留）
        ▼
app/remote_api/                     ← 唯一 HTTP 出口（2026-09-16 重构，替代原
        │                              sdk_client 端点注册表与 stock_sdk）
        │ client.py     统一调用器 StockApiClient：Token 头 + 信封解包 + 异常映射
        │               + 出站布尔 0/1 编码
        └ controllers/  按 URL 控制器拆分的具体接口函数（一端点一具名函数，
                        docstring 含 curl 示例）；仓储经 stock_api.<controller>.<op>() 调用
```

- **路由单位是表**：同一张表的读写永远落在同一个后端，不做"写远端读本地"分家。
- 绑定在 import 期读取 env，不做运行时热切换。
- HTTP 仓储基类 `http_backend/base.py`：`HttpRepositoryBase`（page/list_all/iter_pages/save/delete + 事务兼容空实现）+ `RemoteRecord`（dict 属性访问兼容旧实体消费代码）。
- 响应信封：`ret_code=200` 成功；分页 total 派生顺序＝分页对象内字段 > 信封 `ret_count` > 当页条数（dev_vue_http 已验证 + 防御性兼容，因本机无法直连远端实测）。

## 3. 配置（全部走环境变量，凭据不入源码）

| 变量 | 默认 | 说明 |
|---|---|---|
| `DATA_ACCESS_MODE` | `http` | `http`/`db` 数据访问后端 |
| `STOCK_BASE_URL` | 空（必填） | 远端服务地址，仅允许 http/https（remote_api 统一调用器构造传输时校验） |
| `STOCK_API_TOKEN` | 空 | 服务级凭据（Token 请求头） |
| `STOCK_API_TIMEOUT` | `10` | 请求超时（秒） |
| `REDIS_URL` | 空 | Redis 连接；承载裁决层互斥锁（§8.1）+ 任务运行期中间态（§8.1.1，方案 B）。未配置时裁决层直通、运行态降级进程内存（单 worker 部署语义完整） |
| `REDIS_NAMESPACE` | `arb:gstask` | 两类 Redis 键的命名空间前缀（裁决锁 `{ns}:*`；运行态 `{ns}:rt:{task_id}:*`） |
| `TASK_RUNTIME_LOG_MAX` | `1000` | 运行期日志流截断上限（结束快照回灌 TaskLog 的行数量级） |

## 4. 鉴权（单 Token 子服务模式）

- 登录：`POST /api/auth/login`（账号密码）→ 后端代理远程 `SysUser/Login` → 返回远程 Token（写 `access_token` Cookie 供页面导航）。
- 校验：全局网关（`app/__init__.py::require_gateway_jwt`）按 `Token` 头 → `access_token` Cookie → `?token=` 取令牌，经远程 `GetUserInfo` 校验，注入 `g.current_user`（`RemoteTokenUser`）。页面导航 302 到 `/login`，API 返回统一信封 401/503。
- 路由表：`GET /api/meta/nav` → `GetUserRoleList` 平铺模型行 → 服务端组装旧契约树 `{label, path, children}`（前端渲染零改动）；`page_permissions` 恒空（本地权限码停用）。
- 豁免路径：`/static/*`、`/login`、`/api/auth/login|refresh`、`/api/meta/versions|enums`。
- 退役（注释保留）：本地登录/refresh/改密、用户/角色/权限管理 API 与页面（`/admin/users|roles|navigation` 网关直接 404）、SSO 换票（`/api/auth/sso/exchange`）。
- 前端：`static/js/template-auth.js` 改为 `Token` 请求头；cookie 名对齐 `access_token`；本地 refresh 停用（401 → 清态回登录页）；SSO hash 分支停用。

## 5. 停用清单（注释保留，可恢复）

| 功能 | 位置 | 说明 |
|---|---|---|
| 看门狗 | `app/startup.py::_start_background_components` | 巡检/自动重启依赖本地任务 SQL |
| 仪表盘页 + 接口 | `app/routes/pages/admin.py`、`app/routes/admin_api.py` | 聚合统计依赖本地 SQL |
| 用户/角色管理页 | `app/routes/pages/admin.py` | 管理上收主 Web |
| SSO | `app/routes/__init__.py` | 随本地登录退役 |

## 6. 无法接入清单（远端能力缺口，均已就地 TODO 标注）

远端 15 张 Param* 表中 7 张已有过滤查询 DTO（tasks/logs/results/returns/summary_index/google_sheet/run_locks/stock_metadata），其余为无过滤分页（小表全量拉取可接受）。以下缺口按影响排序：

### 6.1 结构性缺口（等 Redis / 远端端点）

| 方法 | 缺口 | 当前退化策略 |
|---|---|---|
| `task_repository.mark_running_if_pending` / `mark_running_if_not_running` / `revert_running_to_pending` | 无条件更新端点（状态机 CAS） | 读-改-写，竞态窗口待 Redis 裁决层 |
| `google_sheet_repository.occupy` / `release_by_task` | 同上（占用互斥） | 读-改-写 + 复核 |
| `google_sheet_token_repository.apply_in_use_counts` | 计数回写竞态 | 逐行读-改-写 |
| `backtest_repository.acquire_lock` / `release_lock` | 锁原子性红线 | 读-改-写 + DuplicateKey 兜底 |
| `scheduled_task_repository.acquire_run_lock` / `release_run_lock` | 调度锁 CAS | 读-改-写（调度单线程，窗口可控） |
| `backtest_repository.insert_product_cache_if_absent` | 幂等插入 | exists 检查 + DuplicateKey 兜底 |
| 全部 `transaction()/commit=False` 组合（22 处） | 远端无事务 | 顺序独立提交，中途失败留部分写入 |
| `task_result_repository.create_with_return` | 跨表写入 + id 回链 | 先写 return 再查最新行回链（同任务串行写入前提） |

### 6.2 查询能力缺口（性能问题，非正确性）

| 方法 | 缺口 | 退化策略 |
|---|---|---|
| `task_repository.list_paginated_with_statistics`（完成时长聚合） | 无聚合端点 | 扫描全部 completed 任务，任务量上千需远端聚合端点 |
| `task_repository.list_by_name` / `list_distinct_task_types` / `clear_created_by` / `list_by_ids` | 无 name/created_by/ids 过滤 | 全量拉取本地处理（低频路径） |
| `task_repository.count_grouped_by_*` / `count_daily_*` | 无 group by | 按状态/类型逐查询 total；按日拉窗口内数据本地分组 |
| `task_repository.list_by_status_ordered` / `get_latest_task_id_by_type` 等双键排序 | 单一 order_field | 近似单字段排序 |
| `backtest_repository.dedupe_best_per_task` / `page_summary_index(best_per_stock)` | 无窗口函数 | 拉取后本地分组去重（O(索引行数)） |
| `backtest_repository.delete_legacy_performance_analysis_jobs` | xpl_jobs 无过滤 | 全量扫描本地筛选 |
| `*_repository.delete_by_task / delete_older_than / delete_by_ids` | 只有按 id Delete | 逐 id 删除（非原子）；logs 清理走 timestamp 升序扫描提前终止 |
| `task_result_repository.list_paginated`（无 task_id 分支） | 无 join/类型过滤 | 任务 id 分块过滤结果后本地分页 |
| `task_result_repository.list_by_task_fields`（fields 白名单投影，2026-09-28 dev_vue 新增） | **http 孪生缺失**：无字段投影端点 | **TODO(db-to-http)**：http 模式下 `/api/tasks/<id>/results?fields=` 报 AttributeError。补法：http 侧复用 `list_by_task` 取数通道后 Python 白名单投影，`return_date_range` 从 returns 控制器首末行取；长期按 §8 向远端要字段投影 DTO |
| `task_log_repository.create_logs`（快照回灌批量写，2026-10-16 方案 B 新增） | 远端无批量创建端点（E9 裁定不提供） | **best-effort**：逐行 ModifyOrAdd 慢写、单次 2 秒超时（管线按次 timeout 覆盖），仅抛弃失败行并继续写剩余、不重试——本地文件日志有全量留存 |
| `model_summary/jobs.py` 的 `task_repository.add_entity` / `task_log_repository.add_entity` | **http 孪生缺失**：实体流接口 | 重建任务在 http 模式不可用；该任务为本仓 **方案 B 例外**（批量粒度进度保持落库，不走 Redis 运行态），改造时一并补 http 孪生 |
| `google_sheet_repository.get_by_spreadsheet_id` / `get_duplicate_row` | 无对应过滤 | 全量拉取本地匹配（registry 表小） |
| `stock_metadata_repository.bulk_upsert` | 无批量端点 | 循环 upsert |

### 6.3 固定本地（远端无对应表）

- `navigation_repository`：导航菜单表远端不存在；本地保留（菜单展示已改走远端路由表，本地表仅存历史数据）。
- `auth_repository`：用户/角色/权限管理上收主 Web；本地实现仅服务 db 模式。
- ~~`utils/ding_talk_notifier.py` 的值班用户取数（`list_alert_oncall_active_entities`）读本地 User 表~~
  **已解决（2026-10-02）**：@ 手机号机制整体移除（值班开发者 + 任务创建人手机号），告警只发
  机器人 webhook 群消息；创建人显示在 http 后端退化为 `created_by_user_id`（db 后端保持用户名，
  `getattr` 默认值兼容 RemoteRecord 无 `created_by` 关系）。后续如需恢复 @ 人，从主 Web 接口取
  值班名单（并入 §8 路线）。

## 7. 测试

- `tests/conftest.py` 固定 `DATA_ACCESS_MODE=db`：全量回归跑本地后端，零网络依赖。
- HTTP 仓储可在单测中注入假 adapter（各孪生构造函数接受 `client` 参数）。
- 已验证：双模式 `create_app()` 启动；原 sdk_client 端点注册表 97 条路径全部移植为 `app/remote_api/controllers/` 的具体接口函数（2026-09-16 重构，见 `docs/model_update/2026-09-16-remote-api-refactor.md`）；分页 total 派生、config JSON 解析、404→False 映射（内联桩测试）。
- 退役特性的既有测试（本地 JWT/RBAC/SSO 共 5 个模块）标注 skip；`test_unified_envelope`/`test_rate_limiting` 等走 HTTP client 的用例改用 `AUTH_ENABLED=false` mock 用户验证契约。
- 已知与迁移无关的既有失败（改动前后一致，见基线核对）：`test_kline_service` 5 例、`test_c_series_services` 日期相关 1 例、`test_global_preview` excess_sharpe 1 例等共 16 例。

## 8. 后续工作

1. ~~**Redis 裁决层**：互斥锁（状态机/占用/锁）迁移到 Redis SETNX+TTL+续期，替换 §6.1 的读-改-写退化~~
   **已实施（2026-10-02）**：`app/adjudication.py`（SET NX EX + Lua 校验释放 + 启动命名空间清理）。
   落地形态与原设想的差异：**只串行化秒级读-改-写临界区**（持久状态仍在远端行，Redis 锁不承载
   业务语义，TTL 兜底防死锁），因此不需要长持锁与续期；已接入 §6.1 的状态机 CAS ×3、Sheet
   占用 ×2、token 计数回写 ×1、回测锁 ×3、调度锁 ×2（共 11 处，原 TODO 标注同步改写）。
   `REDIS_URL` 未配置时直通退化（等价单 worker 现状）；部署见 `dockers/docker-compose.yml`
   redis 服务与 `dockers/.env.example`。远端条件更新端点（E1）落地后，相关临界区可整体
   替换为 CAS，届时 Redis 仅剩跨副本兜底职责。
2. **远端增量端点建议**（按收益排序）：条件更新（CAS）、按 task_id 批量删除、聚合统计（count/sum/group by）、join 查询（task+result）、批量 ids 查询——**已整理为接口需求规格：[02-remote-incremental-endpoints.md](02-remote-incremental-endpoints.md)**（含请求/响应 DTO、消费方映射与实施顺序；E9 日志批量创建已于 2026-10-16 裁定不提供，日志回灌改 best-effort 逐行 + 超时抛弃）。
3. 迁移稳定后删除 `DATA_ACCESS_MODE=db` 回退与本地 ORM 仓储（含 models），完成"无兼容层"收口。

### 8.1.1 任务运行期中间态迁 Redis（方案 B，2026-10-16）

数据库在任务执行期只保留三个**瞬时里程碑**：创建 pending、启动 running（一次写）、
结束终态快照；**持续中间态**——每组合进度（current_step/total_steps）、业务日志、
取消标志、心跳——全部落 `app/services/task/runtime_state.py`（Redis 主存 +
进程内存降级），任务结束时由 `_finalize_task_execution → sync_snapshot` 一次性
回灌（进度字段合并终态更新 + 日志批量回灌 TaskLog）并清键。

- **取消链路**：`cancel_task` 写 Redis 取消标志（`request_cancel`）+ DB 终态行；
  执行链每组合取消检查改读运行态（`_runtime_task_status`），不再逐组合查库/查远端。
- **断点恢复**：`mark_running` 以任务行当前进度播种运行态（恢复窗口崩溃对账不回退）；
  重启/启动期先 `sync_snapshot` 对账遗留运行态再读 DB 步号；启动对账在
  `_recover_runtime_resources` 中先于裁决层 `namespace_reset` 执行（顺序不能反）。
- **查询面**：运行中任务的进度由查询服务叠加运行态（`query._overlay_runtime_progress`、
  `runtime_view`、`check_local_task_status` 心跳读运行态）；日志读取统一 store 优先
  （`TaskLogMixin`/`runtime_view.read_task_logs`）。
- **例外登记**：model_summary 索引重建任务保持落库进度（批量粒度、自带终态收尾、
  不走任务运行时）；看门狗仍停用，恢复时其"最新日志时间"心跳需改读运行态 `heartbeat_at`。
- 修改文档：`docs/model_update/2026-10-16-任务运行态迁Redis.md`。

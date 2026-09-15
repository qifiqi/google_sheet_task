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
| `google_sheet_repository.get_by_spreadsheet_id` / `get_duplicate_row` | 无对应过滤 | 全量拉取本地匹配（registry 表小） |
| `stock_metadata_repository.bulk_upsert` | 无批量端点 | 循环 upsert |

### 6.3 固定本地（远端无对应表）

- `navigation_repository`：导航菜单表远端不存在；本地保留（菜单展示已改走远端路由表，本地表仅存历史数据）。
- `auth_repository`：用户/角色/权限管理上收主 Web；本地实现仅服务 db 模式。
- ⚠️ `utils/ding_talk_notifier.py` 的值班用户取数（`list_alert_oncall_active_entities`）读本地 User 表：
  纯 http 部署下本地用户表不再维护，钉钉告警收件人会失效，需改从主 Web 接口取值班名单（待办）。

## 7. 测试

- `tests/conftest.py` 固定 `DATA_ACCESS_MODE=db`：全量回归跑本地后端，零网络依赖。
- HTTP 仓储可在单测中注入假 adapter（各孪生构造函数接受 `client` 参数）。
- 已验证：双模式 `create_app()` 启动；原 sdk_client 端点注册表 97 条路径全部移植为 `app/remote_api/controllers/` 的具体接口函数（2026-09-16 重构，见 `docs/model_update/2026-09-16-remote-api-refactor.md`）；分页 total 派生、config JSON 解析、404→False 映射（内联桩测试）。
- 退役特性的既有测试（本地 JWT/RBAC/SSO 共 5 个模块）标注 skip；`test_unified_envelope`/`test_rate_limiting` 等走 HTTP client 的用例改用 `AUTH_ENABLED=false` mock 用户验证契约。
- 已知与迁移无关的既有失败（改动前后一致，见基线核对）：`test_kline_service` 5 例、`test_c_series_services` 日期相关 1 例、`test_global_preview` excess_sharpe 1 例等共 16 例。

## 8. 后续工作

1. **Redis 裁决层**：互斥锁（状态机/占用/锁）迁移到 Redis SETNX+TTL+续期，替换 §6.1 的读-改-写退化；启动期清理本应用锁命名空间（替代 startup 占用重置语义）。
2. **远端增量端点建议**（按收益排序）：条件更新（CAS）、按 task_id 批量删除、聚合统计（count/sum/group by）、join 查询（task+result）、批量 ids 查询。
3. 迁移稳定后删除 `DATA_ACCESS_MODE=db` 回退与本地 ORM 仓储（含 models），完成"无兼容层"收口。

# 接口硬性规定与存量违规收敛

> 本文是**规范文件**：§1~§10 是全库接口必须遵守的规定（在 AGENTS.md 已有框架上补全执法细节）；§11 是 2026-09 审计出的存量违规清单；§12 是收敛批次。
> 唯一出口/异常体系/分层方向的顶层原则见 AGENTS.md"接口规范"章节，本文不重复顶层原则，只做可执行、可 grep 验证的规定。

---

## §1 响应信封

1. 所有 JSON 响应必须且只能经 `app/utils/api_response.py` 的 `success()` / `error()` / `paginated()` 产出；routes 与 services 均禁止手写 `{"status": ..., "message": ...}` 字典（违规点已从 routes 挪进 service 的，同样算违规）。
2. service 层**禁止返回信封形状的 dict**（`{"status", "code", "message", "data"}` 任一组合）。service 返回业务数据或抛异常；信封组装只发生在 routes 层。
3. routes 禁止 `return jsonify(...), status_code` 透传 service 返回的 dict；判断成功/失败只能通过"service 正常返回 / 抛 AppException"两态，不允许 route 窥探 `result["status"]` 分流。
4. 业务数据一律放 `data`，键名保持现状；顶层平铺禁止。
5. 调试信息、内部错误串、异常原文（`str(exc)`）禁止出现在响应中。例外白名单：`ValidationError` 的字段级 `errors` 列表（表单校验回显）；`BadRequestError` 携带**面向用户的**业务文案（如"任务状态已变化，无法启动"），判断标准是"该文案是否会被用户理解且不暴露实现"。
6. `code` 失败时默认等于 HTTP 状态码；需要业务码时显式覆盖，业务码表登记在本文件 §9。

## §2 分页

1. 分页响应唯一形状：`paginated()` 产出的 `{items, total, pages, current_page, per_page}`；`data` 内不再嵌套 `pagination` / `results` 等第二形状。
2. repository 层分页方法返回 `{items(或实体列表), total}`，`pages/current_page/per_page` 组装留给 `paginated()`；repository 不产出信封。
3. 存量四种分页形状（`result_api` results+total…、`backtest_api` results+pagination{has_prev…}、`task_api` tasks+pagination+statistics、repository 的 results 键）在 B2 批一次性统一，前端同步改造，**不留双形状兼容**。
4. 分页参数解析必须走 `parse_query(PageQuery)`，路由内手写 `int(request.args.get("page", 1))` + clamp 禁止。

## §3 请求校验

1. body 一律 `parse_body(XxxSchema)`，query 一律 `parse_query(XxxQuery)`；`request.get_json()` / `request.args.get` 手工取值在 routes 中禁止（schema 覆盖不到的字段先补 schema 再用）。
2. 同一资源族内不允许"一个端点用 schema、兄弟端点手拼 isinstance"（现存反例：`backtest_api.py` bmp_calculate_ratios 用 schema、bmp_update_ratios 手拼——B2 批统一）。
3. 校验失败统一转 `ValidationError` → 400 信封（`request_parsing.py` 已实现，勿在 route 再 catch）。
4. `app/schemas/` 只做边界校验（类型/长度/枚举），业务规则校验留 service。

## §4 鉴权

1. **全部路由（页面 + API）默认挂 `login_required`**；豁免清单（白名单）仅限：`/login`、`/api/auth/login`、`/api/auth/refresh`、健康检查类只读端点（如有）。豁免必须在本文件登记，不允许"忘了挂"。
2. 新增 `admin_required` 装饰器（实现只做"当前用户是否管理员角色"单一判断，不做细粒度权限），强制用于：`/api/admin/users|roles` CUD、`/admin/users`、`/admin/roles` 页面、`/api/database/vacuum`、`/admin/api/model-summary/rebuild`。其余管理读端点维持 `login_required`（RBAC 细粒度随主服务接入统一解决，见 `api-model-query-audit/07` §1）。
3. 限流端点必须考虑未登录场景：无 `login_required` 的限流路由 key 函数用 IP，不允许恒为 `user:anon`（现存反例：xpl analyze）。
4. 页面路由含 DB 查询的（`/google-sheet/create`、`/google-sheet/detail` 的 `_resolve_task_version`）在挂上鉴权前不得新增同类写法。

## §5 日志

1. 所有**写操作**路由（POST/PUT/DELETE/PATCH 及页面触发的状态变更）必须有 logger 调用：入口记操作者 + 目标 id，失败记原因。最小粒度：`logger.info("删除任务 %s by user %s", task_id, g.current_user.username)` 级别即可。
2. service 层写方法（rbac_service、navigation_service 当前整文件无 logger）在状态变更点补 logger；日志脱敏按 config_manager 既有约定（key 含 token/secret/password/credential/apikey 自动打码）。
3. `except Exception` 必须至少 `logger.exception(...)` 或 `logger.error(..., exc_info=True)`；**静默吞异常（except 后仅赋默认值/return 常量）禁止**。现存 4 处（logs_api:51/121、task_api:263、google_sheet_api:51）B1 批修复。
4. 统一经 `app.utils.logger.get_logger(__name__)`，直接 `logging.getLogger` 禁止（现存 8 处见 01 文档 CLN-11）。
5. 日志级别语义：ERROR=需要人处理；WARNING=自动恢复/降级；INFO=状态变更；DEBUG=诊断细节。禁止在 except 分支用 INFO 记错误（现存：C5/C7 service）。

## §6 异常处理

1. routes 原则上不写 try/except 业务包裹——异常交给 `app/errors.py` 全局处理器。现存反例：`xpl.py:65-71/102-108` 自行 `error('处理请求时出错', 500)` 重复兜底，删除。
2. 全局处理器兜底 500 下发固定文案"服务器内部错误"，绝不 `str(e)`；`IntegrityError` 兜底 409 保留。
3. **`str(exc)` 下发治理**：export_api 10 处、backtest_api 3 处、stock_api 2 处的 `BadRequestError(str(exc))` / `ServiceError(str(exc), 502)` 全部改为：service 抛带用户文案的领域异常（NotFoundError/ValidationError/ServiceError），route 不做异常翻译。上游（东财/Google）错误文本不得直发客户端。
4. service "不存在"语义统一抛 `NotFoundError`（404），禁止用 ValueError 表达（现存：google_sheet_token_service / google_sheet_service 的 get/update/delete，被路由翻译成 400——B2 批统一为 404）。
5. 裸 `except:`（E722）全库禁止，现存 backtest_training_service:230/474/503、C3/C4/C5/C7 各 3 处，随批次清除。
6. 重抛一律裸 `raise`（保链），`raise e` 禁止。

## §7 分层与路由职责

1. 分层方向与红线沿用 AGENTS.md（routes 零 ORM、零 repository import）。
2. routes 只做：鉴权装饰 → 参数解析（schema）→ 调 service → 组信封。以下内容禁止出现在 routes（存量清单 → B3 批下沉）：
   - 业务构建逻辑：`backtest_api.py` 的 `_build_global_preview_workbook`（~90 行 openpyxl）、`global_preview.py` 的 ZIP 流式导出编排（Queue+Thread）、`meta_api.py` 的权限过滤树、`task_api.py`/`logs_api.py` 的日志文件正则解析（三份拷贝合一下沉 log 服务）；
   - 基础设施：`google_sheet_api.py` 模块级 TTL 缓存（下沉 google_sheet_registry_service 或专用缓存组件）；
   - import service 私有符号（`_build_backtest_result_export_data` 等 5 处）：service 提供公开函数，路由只引公开名。
3. service 不伸入其他对象内部：`scheduler_api.py:99` 的 `scheduler_service.scheduler.get_jobs()` 改为 service 公开方法；admin_api/dashboard 直连 `task_manager.running_tasks / task_stop_events` 改走 runtime_view 公开快照。
4. 蓝图 url_prefix 只写一处（定义处或注册处，二选一）；现存 `scheduler_api.py` / `admin_api.py` 双重书写修正。

## §8 命名与语法

1. PEP8：类名 CapWords、模块/函数 snake_case。现存违规：`app/exceptions/checkForErrors.py`（随 CLN-04 改名 SheetCheckError）。
2. 函数名必须与行为一致：`xxx_or_none` 就返回 None 且调用方必须判空；抛异常的命名 `get_required_xxx` / `xxx_or_raise`（BUG-04 已修）。
3. 枚举/常量值大小写全库一致：task_type、version 类字面量一律小写（BUG-07 已修，新增端点禁再引入大写 value）。
4. 死代码（无引用函数/文件/常量）合入即删，不留"以后可能用"；历史实现交给 git，不保留注释尸体。
5. 服务模块禁止 `if __name__ == '__main__'` 调试块。

## §9 业务码表（code 覆盖时使用）

| code | 含义 | HTTP |
|---|---|---|
| 0 | 成功 | 200 |
| 400 | 请求参数/格式错误 | 400 |
| 401 | 未登录/令牌失效 | 401 |
| 403 | 已登录但无权限（admin_required 拒绝） | 403 |
| 404 | 资源不存在 | 404 |
| 409 | 冲突（唯一键/状态机冲突） | 409 |
| 429 | 限流 | 429 |
| 500 | 服务器内部错误 | 500 |
| 502 | 上游服务错误（Google/东财） | 502 |

> 新增业务码必须先登记本表再使用。

## §10 新增接口自查清单（PR 模板引用）

- [ ] 响应走 success()/error()/paginated()，无手拼字典
- [ ] body/query 走 parse_body/parse_query
- [ ] 挂 login_required（或登记 §4 豁免），管理面挂 admin_required
- [ ] 写操作有日志；无裸 except、无静默吞异常、无 str(exc) 下发
- [ ] 无 ORM/repository 直连、无 import service 私有符号
- [ ] 分页走 paginated() 单一形状
- [ ] 不存在值语义用 NotFoundError

---

## §11 存量违规清单（2026-09-06 实测）

### 信封旁路（5 端点）

| 端点 | 位置 | 形态 |
|---|---|---|
| POST /api/tasks（POST 分支） | task_api.py:73 | jsonify 透传 creation.py 手拼 dict（无 code/data 键） |
| POST /api/tasks/batch-create | task_api.py:91-92 | 同上 + debug_message 注入下发 |
| PUT /api/tasks/<id>/config | task_api.py:137-138 | 同上 + str(exc) 下发 |
| POST /api/tasks/<id>/restart | task_api.py:194-195 | 同上 + str(exc) 下发 |
| GET /admin/api/dashboard/overview | admin_api.py:69-73 | 裸 jsonify 透传 runtime_view 字典 |

service 层手拼源头：`task/creation.py:593`、`task/restart.py:64-188`、`model_summary/query.py:107,195,297`。

### 分页/校验规范零执法

- `paginated()` 全库 0 调用；`parse_query` 0 调用；`parse_body` 仅 8/25 路由文件使用。
- 分页四形状：result_api.py:29-37、backtest_api.py:126-139、task_api.py:58-62、task_result_repository（results 键）。

### str(exc) 下发（16 端点）

- export_api.py 10 处（:107,119,135,155,169,186,200,210,227,242）
- backtest_api.py 3 处（:102,434,546）
- stock_api.py 2 处（:28,31，其中 502 一处语义保留但改走 ServiceError 用户文案）
- xpl.py 2 处（:68,105）
- task_api.py:217-221（start_error 原文拼入 message）

### 鉴权缺口

- 无 `admin_required` 装饰器（全库不存在）。
- 页面无鉴权 25+ 端点：/admin/* 13、/backtest-training/* 6、/backtest/* 6（legacy）、/backtest-multi-product/* 5、/backtest-multi/* 5（legacy）、/global-preview 2、/xpl 3、/yule 2、/eastmoney-kline 1、/google-sheet 4。
- API 无鉴权：POST /xpl/analyze、POST /xpl/v1/analyze（且限流 key 恒 anon）；login/refresh 属合理豁免但缺限流。
- 管理 API 仅 login_required：/api/admin/users|roles 全部 CUD、/api/database/vacuum、/admin/api/model-summary/rebuild 等。

### 写操作零日志（13 端点）

- auth_api：logout、change_password、users CUD ×3、roles CUD ×3、permissions(GET 内含同步写)
- navigation_api：create/update/delete ×3
- database_api：vacuum（且实为空操作桩，见 01 文档）
- admin_api：rebuild、cleanup（路由层无 logger）
- scheduler_api：create/delete/run_now（service 层有日志，路由层无——以 service 层为准视为合规，本条仅登记）

### 路由层业务/基础设施逻辑（B3 下沉清单）

| 内容 | 位置 |
|---|---|
| openpyxl 全局预览工作簿构建 ~90 行 | backtest_api.py:296-381 |
| ZIP 流式导出编排（Queue+Thread+_ZipStreamWriter） | global_preview.py:57-134 |
| 日志文件解析（同正则三份拷贝） | logs_api.py:32-82,101-137、task_api.py:240-280 |
| 模块级 TTL 缓存 _worksheets_cache | google_sheet_api.py:28-57 |
| 权限过滤树递归 | meta_api.py:50-87 |
| payload 解析/模型名推断私有函数 | backtest_api.py:466 起 |

### 其他

- ValueError 表达"不存在"→400：google_sheet_api 的 sheet/token detail 与 import（应为 404）。
- 同语义双端点双形状：/admin/api/scheduler/status（admin_api.py:25）vs /api/admin/scheduler/status（scheduler_api.py:92-101）。
- GET 端点内写库：/api/google-sheet-tokens（reconcile ×2，见 01 文档 BUG-15）。
- 配置明文下发：/api/config/validate（见 01 文档 BUG-14）。
- 死代码端点：global_preview.py:export_preview 未注册。

---

## §12 收敛批次（B 系列）

| 批次 | 范围 | 要点 |
|---|---|---|
| **B1** | 异常与日志治理 | 静默吞异常 4 处补日志；裸 except 清零；xpl 路由 try/except 删除改全局兜底；8 处 logging.getLogger 统一；写操作路由/service 补日志；admin_required + 页面 login_required（BUG-17） |
| **B2** | 信封与分页统一 | task_api 4 端点 + admin_api 1 端点信封收编（service 手拼源头一并改抛异常/返数据）；分页四形状 → paginated() 单一形状（前端同步）；ValueError→NotFoundError；str(exc) 16 处治理 |
| **B3** | 校验与职责下沉 | parse_body/parse_query 全覆盖；B3 下沉清单逐项搬入 service（路由只留编排）；同语义双端点合并；GET 内写库治理（BUG-15）；配置脱敏（BUG-14） |
| **B4** | 复验 | §10 自查清单全量过一遍 + `04-endpoint-call-chains.md` 中问题标记列清零复查；grep 断言：routes 中 `"status"` 字面量（api_response 之外）= 0、`request.get_json(` = 0、`paginated(` > 0 |

> 每批验收：pytest 全绿 + README §5 门槛。前端配合改造的批次（B2 分页形状）需在同批完成模板/JS 适配，AGENTS.md"改模板必须同步 JS 回填"条款适用。

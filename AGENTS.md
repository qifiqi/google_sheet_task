# AGENTS.md

指导代码代理在本仓库工作。不解释 Flask 基础概念，只记录项目真实结构、风险点和约定。

## 项目定位

Flask 长时运行任务平台（前后端分离），核心能力：Google Sheet 参数批量校验（C3/C4/C5/C7 多模板）、C31 批量拆分为多个 C3 子任务、backtest_training / multi_product 回测、任务调度、Google Sheet token/sheet 占用管理、单 Token 子服务鉴权（本地 RBAC/JWT 已退役）。**看门狗与 pending 唤醒暂缓，见“当前暂缓”。**

目录速览：

- `app/` — Flask 应用主体（routes / services / repositories / remote_api / schemas / exceptions / utils）
- `app/services/task/` — 任务主控门面（facade/runtime/creation/restart/occupancy/query/results）
- `templates/` + `static/` — Jinja2 服务端渲染页面（Bootstrap 5 + 大量内联 JS） 
- ~~`frontend/`~~ — Vue 3 SPA 已于 2026-10 从仓库移除（源码存根目录 `frontend.7z`），当前唯一前端为 `templates/` + `static/` 静态页面
- `app/remote_api/` — DY.Stock.Api 远程接口客户端：`client.py` 统一调用器 + `controllers/` 按 URL 控制器拆分的具体接口函数（wire 字段 `stock_open/stock_max/...` 的翻译在 `KlineService.read/write_internal_kline_data`）
- `tests/`、`docs/`、`docs/design/`、`migrations/`、`scripts/`

任何修改优先考虑：线程生命周期、数据库与内存状态一致性、Token/Sheet 占用释放、失败后可恢复性、网络抖动重试重连。

## 常用命令

```bash
pip install -r requirements.txt          # 运行依赖（pytest 在 requirements-dev.txt）
python run.py                            # 启动 Flask，port 5000
# （2026-10 起 frontend/ Vue SPA 已移除，无前端构建步骤，直接访问 Flask 5000）
python -m pytest tests/unit tests/integration   # 全量回归（统一入口，见"测试"）
python -m pytest tests/unit/test_xxx.py::test_name   # 定向测试
flask db migrate -m "..." / flask db upgrade     # 标准迁移（启动期 schema 修补已停用，见下）
docker-compose up -d                     # Docker 部署
```

### Windows PowerShell 编码

仓库含大量中文模板与注释，PowerShell 默认编码会乱码。读文件显式 UTF-8：

```powershell
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
Get-Content .\run.py -Encoding UTF8
```

## 接口规范（2026-09 数据层重构确立）

设计文档（已收官，归档查阅）：`docs/archive/design/data-layer-refactor/`、`docs/archive/design/code-audit-2026-09/`。总原则：**不修改数据库 schema/迁移/数据**；**全库无兼容层**（单一响应格式、单一异常体系、单一执行路径，无灰度/回退/双轨开关）。

- **统一响应信封**（唯一格式 `{"status","code","message","data"}`）：唯一出口 `app/utils/api_response.py` 的 `success()/error()/paginated()`。routes 禁止手写响应字典；分页统一 `{items,total,pages,current_page,per_page}`。
- **统一异常体系**：`app/exceptions/base.py` 的 `AppException` 层级（BadRequest 400 … ServiceError 500）。repositories 只抛 `NotFoundError`/`ConflictError`；services 抛业务子类；routes 原则上不 catch，交给 `app/errors.py` 全局处理器（仅 `/api` 前缀返回 JSON 信封，兜底 500 绝不 `str(e)` 下发）。任务线程域异常（`C5*`、`RetryableNetworkTaskError`、`[NETWORK_RETRYABLE]`）不并入 HTTP 语义体系。
- **请求校验**：Pydantic v2。模型在 `app/schemas/`，解析经 `app/utils/request_parsing.py` 的 `parse_body/parse_query`。
- **鉴权边界**：本项目作为**子服务接入主服务**，采用**单 Token 子服务模式**：前端携带主服务 Token，本服务经远程 `GetUserInfo` 校验；本地 JWT/RBAC 及 SSO 换票均已退役（`app/routes/sso.py` 未注册，`sso_service.py` 为死代码，`permission_required` 为空装饰器）。保持两个迁移接缝单一：服务端只经 `login_required` 装饰器，前端只经 `template-auth.js`；新增路由/页面不得自写鉴权逻辑。**注意：接口授权已上收主 Web，本地 `permission_required` 不做拦截，不能把它当作后端授权。** 红线：任何外部令牌/凭据一律不写入源码、日志或测试，凭据仅来自环境变量或密钥服务。Token 只经 `Token` 头 / `access_token` Cookie / `?token=` 传入。
- **限流**：Flask-Limiter（`app/extensions.py::limiter`，内存存储，默认无全局限流），不自行实现限流算法。

## 数据层分层规则

- 方向：`routes`（HTTP 编排）→ `services`（业务编排）→ `repositories`（独占数据访问：本地 ORM 或 HTTP 孪生）→ `models`。
- **数据访问后端**：`DATA_ACCESS_MODE=http`（默认）走 `app/repositories/http_backend/*` → `app/remote_api` → DY.Stock.Api；`db` 仅本地开发回退，走本地 ORM。`.env` 由 `app/env_loader.py` 在 `app` 导入 routes/services 之前加载；非法模式启动失败。HTTP 仓储的 `transaction()/commit()/rollback()` 是兼容空实现，多步写为顺序独立提交，**不能依赖跨仓储原子性**。
- routes/services **禁止直接写 ORM 查询**（`db.session` / `Model.query`；import 枚举常量允许）；routes **禁止直接 import/call repository**，一律经 service。
- repository 命名前缀：`get_`/`get_required_`/`list_`/`count_`/`exists_`/`create_`/`update_`/`delete_`/`bulk_`，及领域动词 `upsert_/acquire_/release_/mark_/revert_/record_/dedupe_/sum_/apply_`。
- 写方法默认方法内 commit（签名带 `commit: bool = True`），异常 rollback 后裸 `raise`；跨 repository 原子流程用 `base.transaction()` 包裹、各步骤传 `commit=False`。
- `config_manager → repository` 方向固定，禁止反向 import。
- `app/startup.py`、`run.py`、`migrations/`、`tests/`、`scripts/` 不在分层收编范围。
- **业务事实常量**（被多个模块依赖的静态表，如 C 系模板单元格语义、参数行序、导出键序列）统一放 `app/constants/`（现仅 `c_template_layout.py`）：纯数据、零 IO、零 Flask 依赖，任何层可 import，禁止反向依赖业务模块；派生视图必须逐值等价于消费方语义，禁止顺手改名。单模块私有常量留在各自文件，不进包。审计与遗留登记见 `docs/archive/design/constants-audit-2026-09/`（design/ 原位留跳转存根）。

## 真实入口与启动流程

`run.py` 只创建应用并调用 `bootstrap_app(app)`，启动编排全部在 `app/startup.py`：目录准备/日志 → 重置 token/Sheet 占用与回测锁 → 回灌遗留 Redis 运行态 → 清理裁决锁命名空间 → 幂等播种 SystemConfig（RBAC/导航种子**不在启动期**）→ 清理死任务 → 启动调度器。**看门狗未启动**（见“当前暂缓”）。

注意：表结构不在启动期创建，新环境需先 `flask init_db` 或 `flask db upgrade`；`_initialize_database_schema()` 的运行时 ALTER TABLE 修补**已停用**，线上脏库请走迁移。启动期会无条件复位远端 Token/Sheet 占用，因此**只允许单 serving worker / 单副本**；任何影响任务状态、token 占用、Redis 运行态的修改，都要评估 `app/startup.py`。

## 当前暂缓（2026-10-21）

- **看门狗自动重启**：`app/services/task_watchdog.py` 代码保留但未启动；`[NETWORK_RETRYABLE]` 仍由执行链写入 `Task.error_message`，但**没有消费者**。失败任务需人工重启，不要假设后台会自动恢复。
- **pending 任务唤醒**：配额拒绝、C31 子任务启动失败等会停留在 `pending`，没有后台唤醒器；需人工启动或重启进程（重启只复位 running，不自动续跑 pending）。
- **多副本 / 独立 worker**：当前硬约束单 serving worker、单副本；启动期会复位远端占用，Redis 锁竞争超时/连接异常会直通。扩容前必须先把任务执行迁到独立 worker，并引入 leader/租约语义。

## 任务系统核心

- 生产入口是 `app/services/task/facade.py`（对外仍叫 `TaskManager`/`task_manager`）；`app/services/task_manager.py` 已不存在，旧引用均为历史残留。
- 关键文件：`runtime.py`（`start_task()`、`_execute_*_task()`）、`creation.py`（`create_task()`、`batch_create_and_start_task()`）、`restart.py`、`occupancy.py`。
- 运行态 dict（`running_tasks` 等）复合操作必须持 `_runtime_state_lock`；`start_task` 前置失败必须走 `_rollback_start_reservation()`。
- **C31** 不是独立执行器：前端批量创建页 → `batch_create_and_start_task()` 拆成多个 C3 子任务 → service 消费。新增字段要三层透传（前端 config → child_config 透传 → 执行 service 读取），只改一层不够。
- **C 系任务骨架**：`BaseGoogleSheetService` 唯一实现批量执行骨架；新增 C 系任务经钩子（`_prepare_batch/_expand_parameters/...`）接入，**禁止复制骨架**（见 `docs/archive/design/code-audit-2026-09/03-task-code-refactor.md` §3.3）。去重/断点在基类，子类不得本地覆盖。
- **C5/C7 自定义K线**（`config.kline_source=custom`）：只在 `get_bdl()` 预计算阶段读一次 Sheet 输入列，不进 `_get_all_parameters()` 的自动行情链路；不要把 custom 分支塞进 `_get_all_parameters()`。
- **K线字段命名**（全项目统一英文 schema）：内部行用 `open/high/low/close/volume/amount/vwap` + `stock_date/stock_code/stock_name`；推送远程的 wire 字段（`stock_open/stock_max/...`）保持不变，翻译在 `KlineService.read/write_internal_kline_data`。`price_mode → 价格字段` 唯一入口 `kline_service.get_kline_price_field()`；取价序列统一 `build_price_rows()`。C4 固定按市场取价（A股 open、美股 close）。
- **结果载荷**：C5/C7 指标/analyze 透传字段以 `app/services/result_payload.py` 规格表为准，新增指标只改规格表。注意历史键名升级：模型指标键以规格表为准（如索提诺/超额夏普曾被旧键名坑过）。
- **运行期中间态**：进度/日志/取消/心跳在 `app/services/task/runtime_state.py`（Redis 主存、内存降级），任务结束回灌 DB；`Task.status` 仍是里程碑事实源。
- **Token**：唯一来源是 `GoogleSheetToken` 表的 `token_context`；不读文件、不接受内联 JSON。解析顺序：任务 `token_id` → SystemConfig `default_token_id` → 最低占用可用 Token；默认 Token 满额/失效/类型不符时自动回退。外部 API 只返回脱敏预览，内部 `get_entity()` 取全量。
- **内部命令**：钉钉微服务不再持有 `TaskManager`；重启/取消经 `POST /api/internal/task-command` + `X-Internal-Secret` 转发给 Web 进程。`INTERNAL_COMMAND_SECRET` 留空时端点 404，钉钉侧返回明确错误。
- **看门狗** `task_watchdog.py`：代码保留但**未启动**；自动重启与 pending 唤醒暂缓（见“当前暂缓”）。不要把失败任务的可恢复性寄托在它身上。

## 网络链路

- Google Sheet IO 底层在 `app/services/google_sheet_client.py`（gspread，timeout/代理/重试/重连，可恢复错误抛 `RetryableNetworkTaskError`）。网络问题优先改这里，不要在上层散加 try/except。
- 东方财富/股票：`app/utils/dfcf_api.py`（搜索 codetable 优先、suggest 回退；K线拉取）、`app/utils/proxy_manager.py`；K线代理开关 `SystemConfig.dfcf_kline_proxy_enabled`；fake 搜索结果必须含 `code/market/status/shortName`（`StockSearchService._normalize_result` 契约）。
- DY.Stock.Api 远程数据服务唯一出口在 `app/remote_api/`：新增远程接口 = 在对应控制器文件加一个具体函数（docstring 带 curl 示例），方法体一行 `_make_request(method, path, payload)`；**禁止手写 `/api/*` URL、禁止 resurrect `(group, operation)` 字符串注册表**。Repository 与 KlineService 经单例 `stock_api.<controller>.<op>()` 调用，保证 IDE 可检索调用链。出站载荷布尔 → 0/1 编码只在统一调用器出口做一次。

## 配置系统

统一经 `app/services/config_manager.py`，不要散落地直接读环境变量。规则：

- `get_config` 对布尔返回真 `bool`（读侧做 json.loads + 历史 `"True"/"False"/"None"` 还原）；布尔解析统一 `coerce_bool(value, default)`，不要再造 `.lower() in (...)`。
- **负缓存**：绕过 `set_config` 直接 ORM 插入的配置行本进程可能读不到；写配置必须走 `set_config`/`update_configs` 或写后 `refresh_cache()`。
- `get_all_configs()` 读缓存（全量字典拷贝），不要在任务参数循环内反复调用；管理端强一致显式传 `force_refresh=True`。
- key 含 `token/secret/password/credential/apikey` 的值日志自动打码，新增敏感配置沿用命名约定。
- `default_token_id` 是任务未显式选择 Token 时的默认 Token；留空/满额/失效时回退最低占用可用 Token。
- 配置全量加载失败后有 5 秒退避，故障期间 `get_config` 返回默认值，不再逐次触发全量远端拉取。

## 双前端

1. **静态页面**（`templates/` 纯静态 HTML，2026-09 静态化完成，方案见 `docs/archive/design/frontend-refactor/`）：全部页面零 Jinja 语法，页面路由统一在 `app/routes/pages/` 包（JSON API 留在 `app/routes/` 平级 `*_api.py`，结构约定见 `docs/archive/design/routes-restructure-2026-09/`），经包内 `send_page`/`register_page_routes` 表驱动返回文件；同一产物支持 nginx 独立部署与 Flask 托管（`05-deployment.md`）。JS 分层：`static/js/common/{api,business,components,utils,admin-shell}.js`（接口唯一出口 api.js——页面禁手写 `/api/*` URL；跨页业务在 business/ 的 `Biz.*`；navbar.js 渲染 `data-navbar` 占位）+ `static/js/pages/<页>.js`（页面逻辑，普通 script 原位置，禁 defer/module）；CSS 在 `static/css/{common,pages}/`。改字段仍须同步检查：表单初始化、localStorage 恢复、模板回填、restart 回填、提交 payload，否则刷新后"变回旧字段"。google_sheet 版本分发走 `/google-sheet/{create,detail}` 的 dispatcher 页（缺 version 时前端查任务补参重定向）。**前后端契约镜像**：后端有对应事实、前端需同值的常量（如 C3 默认佣金、TaskStatus 文案/配色）统一放 `static/js/common/contract-constants.js`（`window.BizConstants`），页面禁再私拷一份；改契约两侧同批修改（后端源头见该文件各条注释，规约见 `docs/archive/design/constants-audit-2026-09/` §5.6/P5）。
2. ~~Vue 3 SPA~~（已移除）：`frontend/` 已于 2026-10 删除（源码存根目录 `frontend.7z`）；`docs/前端Vue工程.md` 归档至 `docs/archive/前端Vue工程.md` 仅作历史参考。

## 测试

- `tests/unit/`（服务/工具/模型层）+ `tests/integration/`（Flask test_client）；`tests/archive/` 已被 `norecursedirs` 排除，不要在里面新增正式测试。
- `tests/conftest.py` 固定 `DATA_ACCESS_MODE=db`，全量回归不覆盖 http 默认后端；HTTP 行为由 `test_http_*` / 孪生签名/假客户端用例覆盖。鉴权/SSO 相关用例随单 Token 模式整体 skip。
- 全量回归统一 `python -m pytest tests/unit tests/integration`：tests 根目录还有迁移/启动编排等独立测试文件，直接 `pytest` 会连带给收集进来。
- `pytest.ini` 的 `--basetemp=.pytest_tmp` 是为绕开本机 Temp 目录 ACL 损坏，不要删。
- 部分用例带 `@pytest.mark.skip` 对应未完成修复，修复后取消 skip（grep 可定位）。

## 数据模型要点

`app/models.py`：Task、TaskLog、TaskResult、TaskResultReturn、TaskTemplate、SystemConfig、GoogleSheetToken、GoogleSheet、ScheduledTask、User/Role/Permission。

- `Task.config` 是任务恢复、重启、前端回填的核心。
- `Task.error_message` 是用户可见错误摘要；执行链仍会写 `[NETWORK_RETRYABLE]` 前缀，但看门狗暂缓，当前没有自动消费者，不要覆盖成无结构长 traceback。
- `GoogleSheetToken.token_file` 本地列已删除（迁移 `20261021_drop_google_sheet_token_file`）；远端表仍保留兼容列，HTTP 仓储写入唯一 `legacy-token:*` 占位值。新 Token 只写 `token_context`，外部 DTO 不返回。

## 不要做的事

- 不要只改模板不改 JS 回填逻辑；不要只改 C31 前端不改 `batch_create_and_start_task()`。
- 不要在任务线程里吞异常不写 `Task.error_message`；看门狗暂缓，失败任务不会自动重启，必须保证错误摘要可人工定位。
- 不要用 `raise e`（丢失异常链），裸 `raise`；任务级错误摘要用 `app/utils/task_error_utils.py`。
- 不要把旧 `app/services/task_manager.py` 当生产入口（已不存在）。
- 不要在业务代码散读环境变量；不要硬编码代理账号/密码/token。
- 不要随意清除注释代码与文字细节，只改上下文需要的代码。

## 文档索引

`docs/README.md` 是全部文档唯一索引（2026-10-15 起，原 `docs/目录索引.md` 已退役归档）。结构：`docs/project-memory/`（实现实况权威源：架构总览 + 领域分册 + 技术决策 + 变更日志 + 已知问题 + 文档台账）、`docs/guides/`（操作指南）、`docs/design/`（仅 partial/pending 设计；已收官主题归档至 `docs/archive/design/`，design/ 原位留跳转存根）、`docs/archive/`（只读归档）、`docs/model_update/`（变更记录）、`docs/release-notes/`。

改敏感区域前先读对应文档：

- 执行链路：`docs/project-memory/GoogleSheet执行链路.md`、`docs/project-memory/任务系统与调度.md`
- 回测/指标：`docs/project-memory/回测系统与报告.md`、`docs/design/metrics-unify-2026-09/指标计算与单品多品统一方案.md`（partial，行号锚点已漂移，以代码为准）
- 接口/分层：`docs/archive/design/data-layer-refactor/`、`docs/archive/design/code-audit-2026-09/`、`docs/project-memory/接口总览.md`
- db→http 迁移/远端缺口：`docs/design/db-to-http-migration/`（含“无法接入清单”与远端缺陷登记）
- 鉴权：`docs/guides/登录与鉴权指南.md`；部署：`docs/guides/部署运维.md`；本地开发：`docs/guides/本地开发指南.md`

设计文档存放在 `docs/design/<主题目录>/` 下，每个主题独立建目录；已收官主题归档至 `docs/archive/design/`。
每次大规模修改后在 `docs/model_update/` 当月月度汇总（如 `2026-10-月度汇总.md`）文末追加小节（标题 + 要点 + 涉及文件），并在 `docs/project-memory/变更日志.md` 对应月份登记；变更记录按月归并维护，不再新增单篇文件。
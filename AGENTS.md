# AGENTS.md

指导代码代理在本仓库工作。不解释 Flask 基础概念，只记录项目真实结构、风险点和约定。

## 项目定位

Flask 长时运行任务平台（前后端分离），核心能力：Google Sheet 参数批量校验（C3/C4/C5/C7 多模板）、C31 批量拆分为多个 C3 子任务、backtest_training / multi_product 回测、任务调度与看门狗、Google Sheet token/sheet 占用管理、RBAC + JWT 鉴权。

目录速览：

- `app/` — Flask 应用主体（routes / services / repositories / schemas / exceptions / utils）
- `app/services/task/` — 任务主控门面（facade/runtime/creation/restart/occupancy/query/results）
- `templates/` + `static/` — Jinja2 服务端渲染页面（Bootstrap 5 + 大量内联 JS）
- `frontend/` — Vue 3 SPA（Vite + Element Plus/Naive UI，开发中）
- `ding_stream_service/` — 钉钉 Stream 独立微服务（不挂载到 run.py）
- `stock_sdk/` — 内置K线库读写客户端（wire 字段 `stock_open/stock_max/...`）
- `tests/`、`docs/`、`docs/design/`、`migrations/`、`scripts/`

任何修改优先考虑：线程生命周期、数据库与内存状态一致性、Token/Sheet 占用释放、失败后可恢复性、网络抖动重试重连。

## 常用命令

```bash
pip install -r requirements.txt          # 运行依赖（pytest 在 requirements-dev.txt）
python run.py                            # 启动 Flask，port 5000
cd frontend && npm run dev               # Vite dev server，代理 /api、/admin/api、/backtest-training/api 到 5000
cd frontend && npm run build
.venv\Scripts\python.exe run_ding.py     # 钉钉 Stream 微服务（不要用系统 python，缺 dingtalk-stream）
python -m pytest tests/unit tests/integration   # 全量回归（统一入口，见"测试"）
python -m pytest tests/unit/test_xxx.py::test_name   # 定向测试
flask db migrate -m "..." / flask db upgrade     # 标准迁移（启动期另有 schema 修补，见下）
docker-compose up -d                     # Docker 部署
```

### Windows PowerShell 编码

仓库含大量中文模板与注释，PowerShell 默认编码会乱码。读文件显式 UTF-8：

```powershell
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
Get-Content .\run.py -Encoding UTF8
```

## 接口规范（2026-09 数据层重构确立）

设计文档：`docs/design/data-layer-refactor/`、`docs/design/code-audit-2026-09/`。总原则：**不修改数据库 schema/迁移/数据**；**全库无兼容层**（单一响应格式、单一异常体系、单一执行路径，无灰度/回退/双轨开关）。

- **统一响应信封**（唯一格式 `{"status","code","message","data"}`）：唯一出口 `app/utils/api_response.py` 的 `success()/error()/paginated()`。routes 禁止手写响应字典；分页统一 `{items,total,pages,current_page,per_page}`。
- **统一异常体系**：`app/exceptions/base.py` 的 `AppException` 层级（BadRequest 400 … ServiceError 500）。repositories 只抛 `NotFoundError`/`ConflictError`；services 抛业务子类；routes 原则上不 catch，交给 `app/errors.py` 全局处理器（仅 `/api` 前缀返回 JSON 信封，兜底 500 绝不 `str(e)` 下发）。任务线程域异常（`C5*`、`RetryableNetworkTaskError`、`[NETWORK_RETRYABLE]`）不并入 HTTP 语义体系。
- **请求校验**：Pydantic v2。模型在 `app/schemas/`，解析经 `app/utils/request_parsing.py` 的 `parse_body/parse_query`。
- **鉴权边界**：本项目后续作为**子服务接入主服务**（路由网关/鉴权/权限整体迁移），当前 RBAC/JWT 是历史产物，**不再新增权限类建设**。保持两个迁移接缝单一：服务端只经 `login_required` 装饰器，前端只经 `template-auth.js`；新增路由/页面不得自写鉴权逻辑。已知缺口登记于 `docs/design/api-model-query-audit/07-public-deployment-and-subservice.md`。
- **限流**：Flask-Limiter（`app/extensions.py::limiter`，内存存储，默认无全局限流），不自行实现限流算法。

## 数据层分层规则

- 方向：`routes`（HTTP 编排）→ `services`（业务编排）→ `repositories`（独占 ORM）→ `models`。
- routes/services **禁止直接写 ORM 查询**（`db.session` / `Model.query`；import 枚举常量允许）；routes **禁止直接 import/call repository**，一律经 service。
- repository 命名前缀：`get_`/`get_required_`/`list_`/`count_`/`exists_`/`create_`/`update_`/`delete_`/`bulk_`，及领域动词 `upsert_/acquire_/release_/mark_/revert_/record_/dedupe_/sum_/apply_`。
- 写方法默认方法内 commit（签名带 `commit: bool = True`），异常 rollback 后裸 `raise`；跨 repository 原子流程用 `base.transaction()` 包裹、各步骤传 `commit=False`。
- `config_manager → repository` 方向固定，禁止反向 import。
- `app/startup.py`、`run.py`、`migrations/`、`tests/`、`scripts/` 不在分层收编范围。

## 真实入口与启动流程

`run.py` 只创建应用并调用 `bootstrap_app(app)`，启动编排全部在 `app/startup.py`：目录准备/日志 → 重置 token/Sheet 占用与回测锁 → 幂等播种 SystemConfig/RBAC/导航 → 清理死任务 → 启动调度器 + 看门狗。

注意：表结构不在启动期创建，新环境需先 `flask init_db` 或 `flask db upgrade`；运行时 ALTER TABLE 补列的 schema 修补逻辑只在 `app/startup.py`（`run.py` 仅是 27 行的干净入口，只 create_app + bootstrap），线上脏库问题直接看 `app/startup.py`。任何影响任务状态、token 占用、RBAC、看门狗的修改，都要评估 `app/startup.py`。

## 任务系统核心

- 生产入口是 `app/services/task/facade.py`（对外仍叫 `TaskManager`/`task_manager`）；`app/services/task_manager.py` 已不存在，旧引用均为历史残留。
- 关键文件：`runtime.py`（`start_task()`、`_execute_*_task()`）、`creation.py`（`create_task()`、`batch_create_and_start_task()`）、`restart.py`、`occupancy.py`。
- 运行态 dict（`running_tasks` 等）复合操作必须持 `_runtime_state_lock`；`start_task` 前置失败必须走 `_rollback_start_reservation()`。
- **C31** 不是独立执行器：前端批量创建页 → `batch_create_and_start_task()` 拆成多个 C3 子任务 → service 消费。新增字段要三层透传（前端 config → child_config 透传 → 执行 service 读取），只改一层不够。
- **C 系任务骨架**：`BaseGoogleSheetService` 唯一实现批量执行骨架；新增 C 系任务经钩子（`_prepare_batch/_expand_parameters/...`）接入，**禁止复制骨架**（见 `docs/design/code-audit-2026-09/03-task-code-refactor.md` §3.3）。去重/断点在基类，子类不得本地覆盖。
- **C5/C7 自定义K线**（`config.kline_source=custom`）：只在 `get_bdl()` 预计算阶段读一次 Sheet 输入列，不进 `_get_all_parameters()` 的自动行情链路；不要把 custom 分支塞进 `_get_all_parameters()`。
- **K线字段命名**（全项目统一英文 schema）：内部行用 `open/high/low/close/volume/amount/vwap` + `stock_date/stock_code/stock_name`；推送远程的 wire 字段（`stock_open/stock_max/...`）保持不变，翻译在 `KlineService.read/write_internal_kline_data`。`price_mode → 价格字段` 唯一入口 `kline_service.get_kline_price_field()`；取价序列统一 `build_price_rows()`。C4 固定按市场取价（A股 open、美股 close）。
- **结果载荷**：C5/C7 指标/analyze 透传字段以 `app/services/result_payload.py` 规格表为准，新增指标只改规格表。注意历史键名升级：模型指标键以规格表为准（如索提诺/超额夏普曾被旧键名坑过）。
- **看门狗** `task_watchdog.py`：查最近 5 天任务、running 长时间无日志、自动重启带 `[NETWORK_RETRYABLE]` 前缀的 error 任务。筛选压 SQL 层，避免无限重启循环。

## 网络链路

- Google Sheet IO 底层在 `app/services/google_sheet_client.py`（gspread，timeout/代理/重试/重连，可恢复错误抛 `RetryableNetworkTaskError`）。网络问题优先改这里，不要在上层散加 try/except。
- 东方财富/股票：`app/utils/dfcf_api.py`（搜索 codetable 优先、suggest 回退；K线拉取）、`app/utils/proxy_manager.py`；K线代理开关 `SystemConfig.dfcf_kline_proxy_enabled`；fake 搜索结果必须含 `code/market/status/shortName`（`StockSearchService._normalize_result` 契约）。

## 配置系统

统一经 `app/services/config_manager.py`，不要散落地直接读环境变量。规则：

- `get_config` 对布尔返回真 `bool`（读侧做 json.loads + 历史 `"True"/"False"/"None"` 还原）；布尔解析统一 `coerce_bool(value, default)`，不要再造 `.lower() in (...)`。
- **负缓存**：绕过 `set_config` 直接 ORM 插入的配置行本进程可能读不到；写配置必须走 `set_config`/`update_configs` 或写后 `refresh_cache()`。
- `get_all_configs()` 读缓存（全量字典拷贝），不要在任务参数循环内反复调用；管理端强一致显式传 `force_refresh=True`。
- key 含 `token/secret/password/credential/apikey` 的值日志自动打码，新增敏感配置沿用命名约定。

## 双前端

1. **静态页面**（`templates/` 纯静态 HTML，2026-09 静态化完成，方案见 `docs/design/frontend-refactor/`）：全部页面零 Jinja 语法，页面路由经 `app/routes/page_files.py::send_page` 返回文件；同一产物支持 nginx 独立部署与 Flask 托管（`05-deployment.md`）。JS 分层：`static/js/common/{api,business,components,utils,admin-shell}.js`（接口唯一出口 api.js——页面禁手写 `/api/*` URL；跨页业务在 business/ 的 `Biz.*`；navbar.js 渲染 `data-navbar` 占位）+ `static/js/pages/<页>.js`（页面逻辑，普通 script 原位置，禁 defer/module）；CSS 在 `static/css/{common,pages}/`。改字段仍须同步检查：表单初始化、localStorage 恢复、模板回填、restart 回填、提交 payload，否则刷新后"变回旧字段"。google_sheet 版本分发走 `/google-sheet/{create,detail}` 的 dispatcher 页（缺 version 时前端查任务补参重定向）。
2. **Vue 3 SPA**（`frontend/`，当前分支 dev_vue 主战场）：Vite dev proxy 到 Flask 5000；JWT 存 localStorage，401 自动 refresh 重试（`docs/前端Vue工程.md`）；其 `src/{api,composables,components}` 分层与静态版 common/ 对齐，迁移时是翻译不是重设计。

## 测试

- `tests/unit/`（服务/工具/模型层）+ `tests/integration/`（Flask test_client）；`tests/archive/` 已被 `norecursedirs` 排除，不要在里面新增正式测试。
- 全量回归统一 `python -m pytest tests/unit tests/integration`：tests 根目录还有迁移/启动编排等独立测试文件，直接 `pytest` 会连带给收集进来。
- `pytest.ini` 的 `--basetemp=.pytest_tmp` 是为绕开本机 Temp 目录 ACL 损坏，不要删。
- 部分用例带 `@pytest.mark.skip` 对应未完成修复，修复后取消 skip（grep 可定位）。

## 数据模型要点

`app/models.py`：Task、TaskLog、TaskResult、TaskResultReturn、TaskTemplate、SystemConfig、GoogleSheetToken、GoogleSheet、ScheduledTask、User/Role/Permission。

- `Task.config` 是任务恢复、重启、前端回填的核心。
- `Task.error_message` 同时承担"用户可见错误摘要"和"看门狗自动恢复信号"（`[NETWORK_RETRYABLE]` 前缀），不要覆盖成无结构长 traceback。

## 不要做的事

- 不要只改模板不改 JS 回填逻辑；不要只改 C31 前端不改 `batch_create_and_start_task()`。
- 不要在任务线程里吞异常不写 `Task.error_message`；不要把所有失败任务都交给看门狗自动重启。
- 不要用 `raise e`（丢失异常链），裸 `raise`；任务级错误摘要用 `app/utils/task_error_utils.py`。
- 不要把旧 `app/services/task_manager.py` 当生产入口（已不存在）。
- 不要在业务代码散读环境变量；不要硬编码代理账号/密码/token。
- 不要随意清除注释代码与文字细节，只改上下文需要的代码。

## 文档索引

`docs/目录索引.md` 是全部文档索引。改敏感区域前先读对应文档：

- 执行链路：`docs/GoogleSheet执行链路.md`、`docs/任务系统与调度.md`
- 回测/指标：`docs/回测系统与报告.md`、`docs/指标计算与单品多品统一方案.md`
- 接口/分层：`docs/design/data-layer-refactor/`、`docs/design/code-audit-2026-09/`、`docs/接口总览.md`
- 鉴权：`docs/登录与鉴权指南.md`；部署：`docs/部署运维.md`；本地开发：`docs/本地开发指南.md`

设计文档存放在 `docs/design/<主题目录>/` 下，每个主题独立建目录。

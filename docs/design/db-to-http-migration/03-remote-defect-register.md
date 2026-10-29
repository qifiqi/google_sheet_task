# 远端缺陷登记：ParamTasks/ModifyOrAdd 插入分支失败（2026-10-17）

> **2026-10-20 更新：开发实例已修复，线上未部署。**
> `http://172.18.20.20:7070`（开发实例，与线上共用同一数据库）已按新契约工作：
> 插入不携带 `id`，`ret_obj` 直接返回 32 位主键字符串（无连字符），
> `id: null` 也接受。`https://stockapi.jaspil.cn`（线上）仍为旧版本、插入仍失败，
> 待部署。消费方（本仓）已按新契约改造：任务创建不发送本地 uuid，以返回 id 为准。

## 现象

`POST https://stockapi.jaspil.cn/api/ParamTasks/ModifyOrAdd`：

- **更新**（id 为已存在任务）→ `ret_code=200` 成功；
- **插入**（id 为任意新 uuid，载荷为已验证合法的完整行）→ HTTP 200 但 `ret_code=500`、
  `ret_msg="操作失败"`；部分载荷变体返回 `ret_msg="内部请求出错"`（id 传 null 时）。

对照实验：`ParamTaskLogs/ModifyOrAdd` 对**新行插入成功**——通用插入管道与鉴权均正常，
缺陷定位在 `t_param_tasks` 这张表的插入路径（疑似表约束 / EF 实体配置 / 触发器）。

**影响**：子服务纯 http 数据层新建任务依赖该端点插入，当前无法建新任务（P0）。

## 复现步骤

```bash
# 1. 登录取 Token
curl -s -X POST 'https://stockapi.jaspil.cn/api/SysUser/Login' \
  -H 'Content-Type: application/json' \
  -d '{"user_name":"<账号>","user_password":"<密码>"}'
# → {"ret_code":200, "ret_obj":{"token":"<TOKEN>", ...}}

# 2. 对照 A：更新已存在任务（预期成功）
curl -s -X POST 'https://stockapi.jaspil.cn/api/ParamTasks/ModifyOrAdd' \
  -H 'Content-Type: application/json' -H 'Token: <TOKEN>' \
  -d '{"id":"<已存在任务id>","name":"t","task_type":"google_sheet_C7","status":"pending","config":"{}","created_by_user_id":280573}'
# → {"ret_code":200,...}

# 3. 复现 B：插入新任务（预期失败）
curl -s -X POST 'https://stockapi.jaspil.cn/api/ParamTasks/ModifyOrAdd' \
  -H 'Content-Type: application/json' -H 'Token: <TOKEN>' \
  -d '{"id":"<新uuid，例如 11111111-2222-4333-8444-555555555555>","name":"insert-probe","task_type":"google_sheet_C7","status":"pending","config":"{}","created_by_user_id":280573}'
# → {"ret_code":500,"ret_msg":"操作失败","ret_obj":null}

# 4. 对照 C：ParamTaskLogs 插入新行（预期成功，证明通用插入管道正常）
curl -s -X POST 'https://stockapi.jaspil.cn/api/ParamTaskLogs/ModifyOrAdd' \
  -H 'Content-Type: application/json' -H 'Token: <TOKEN>' \
  -d '{"task_id":"<已存在任务id>","level":"info","message":"insert probe","timestamp":"2026-10-17T16:30:00"}'
# → {"ret_code":200,...}
```

## 已排除的载荷侧原因（全部失败）

| 变体 | 结果 |
|---|---|
| 完整合法行（字段/类型与既有行逐一对齐，仅换新 id） | 操作失败 |
| 补齐 created_at/updated_at 非空时间戳 | 操作失败 |
| 补齐 start_time/end_time/error_message 显式 null | 操作失败 |
| created_by_user_id 置 null | 操作失败 |
| total_steps/current_step 显式 0 | 操作失败 |
| task_type 换其它已存在值（google_sheet_C5） | 操作失败 |
| id 传 null（由服务端生成） | 内部请求出错 |
| DTO 层面（Swagger）：所有字段均可空、无 required | — |

## 新插入契约（2026-10-20 起）

```
POST /api/ParamTasks/ModifyOrAdd
{"name":"...","task_type":"google_sheet_C7","status":"pending","config":"{}","created_by_user_id":1}
→ {"ret_code":200,"ret_msg":"请求(或处理)成功","ret_count":0,
   "ret_obj":"0f88d30c59ea4685948d8fd6b65af1f1"}
```

- 插入：不携带 `id`（或 `id:null`），`ret_obj` 为主键字符串；
- 更新：携带既有 `id`，`ret_obj` 为空（仅成功信封）；
- 本仓 `HttpRepositoryBase.save` 统一处理三种回执（None / 主键字符串 / 完整对象），
  字符串按仓储 `normalize_id` 规则定类型（数值表转 int，任务表保留字符串）。

## 需要远端回报

插入分支的服务端异常堆栈（EF/数据库层异常被 `"操作失败"` 吞掉了）：
重点排查 `t_param_tasks` 的约束/触发器、实体主键配置、以及 ModifyOrAdd 实现在
"id 不存在 → Add" 分支的数据库写入异常。

修复验证：执行上方步骤 3 返回 `ret_code=200` 即为修复完成。

---

# 缺陷 2：ParamTask 系 Delete/分页过滤契约与 Swagger 不符（2026-10-28）

> **线上（stockapi.jaspil.cn）实测**。Swagger 的 `ParamTaskIdRequestDto {task_id}`
> 与实际行为差距大，本仓消费侧已按实测契约改造（task_result/task_log http 仓储）。

## 实测契约（三表同款：ParamTaskResults / ParamTaskResultsReturn / ParamTaskLogs）

1. **Delete 按 task_id 整任务删除，id 字段被忽略**：
   - `{"id": 1}` → 400 `"task_id 不能为空"`（id 在 Dto 里根本不存在，缺 task_id 即校验失败）；
   - `{"id": 1, "task_id": "X"}` → 删除 **task_id=X 的全部行**（与 id 无关，
     ret_count=受影响行数；实测 2 行任务传 1 个 id 删了 2 行）；
   - `{"task_id": "X"}` 0 行匹配 → 400 `"操作失败"`（**删除零行是报错不是 200**，
     调用方必须先确认行存在再调 Delete）；
   - task_id 与行内存储形式**精确字符串匹配**：ModifyOrAdd 写入什么就存什么
     （连字符 uuid 原样存储，不做归一化），Delete/过滤必须用同一形式。
2. **ParamTaskResults/GetDataByPageList 只认 `task_ids[]` 数组**：
   单数 `task_id` 字段被静默忽略，返回不过滤的全表（ret_count 为全表行数）。
   `ParamTaskLogs` / `ParamTaskResultsReturn` 的分页过滤恰好相反，只认单数
   `task_id`——三表契约互不一致。
3. **ModifyOrAdd 数值主键表**（Results/ResultsReturn/Logs）：插入不携带 `id`
   （`id:null` 直接 400 类型错误），新行主键经 `ret_count` 回带（不是 `ret_obj`）。
4. 行级删除端点不存在（swagger 全部端点仅 Delete/GetDataByPageList/GetInfoById/
   ModifyOrAdd 四个）：单行删除无法表达，消费侧单结果删除仅当该结果是任务
   唯一结果时等价可删，否则报错（见 `task_result_repository.delete`）。

## 对本仓的影响与处置

- `task_result_repository` / `task_log_repository`（http 侧）：删除改为按 task_id
  整任务调用（先经过滤确认行存在）；Results 全部任务过滤改 `task_ids[]`；
  定期清理（scheduled_task_worker）语义由行级改为任务级（同任务未到期行会被
  一并删除，依赖清理相应覆盖任务全量结果行）。
- `t-1` / `task-id` / `bt-save-task` 等测试夹具行残留在共享 ParamTaskResults 表
  （来源疑为历史单测直连远端，未清）；已顺手核验契约时清理
  `insert-probe-20261028-e2e`、探针行与 'task-id' 夹具行，'t-1'×8、
  'bt-save-task'×2 仍在，可由远端择机清理。

## 需要远端回报/改进

- 三个 Delete 的真实行为与 Swagger Dto 注解对齐（或补按行删除端点）；
- ParamTaskResults 分页过滤补单数 `task_id`（或三表统一 `task_ids[]`）；
- Delete 0 行匹配建议返回 200+ret_count=0 而非 400，便于幂等删除。

## 缺陷 #4：ParamGoogleSheetTokens/ModifyOrAdd 插入分支 500（2026-10-29）

`POST /api/ParamGoogleSheetTokens/ModifyOrAdd`：**新行插入**一律 500"内部请求出错"
（与载荷无关，精简单字段同样 500）；**更新已有行正常 200**。读路径
（GetDataByPageList / GetInfoById）正常。影响：Token 导入/新建流程；占用计数更新
（update 分支）不受影响。**2026-10-29 复核：7070 已修复**——新行插入 200，
`ret_count` 回带新 id（实测 id=9）；探针行已清理。

## 缺陷 #5：ParamTaskResultSummaryIndex/ModifyOrAdd 插入分支 500（2026-10-29）

`POST /api/ParamTaskResultSummaryIndex/ModifyOrAdd`：**新行插入**一律 500（UUID
宿主任务 + DTO 全字段载荷同样 500）；分页/删除正常。影响：http 模式下回测汇总
重建（模型汇总 dedupe/重建链路写汇总索引）会失败。**2026-10-29 复核：7070 已修复**
——新行插入 200，`ret_count` 回带新 id（实测 id=7438）；探针行已清理。

## 缺陷 #6：StockParamResult/GetDataByPageList 的 task_id/task_index 过滤失效（2026-10-29）

`POST /api/StockParamResult/GetDataByPageList`：DTO 声明了 stock_code/task_id/task_index
三个过滤字段，实测 **task_id 与 task_index 均被忽略**（传不存在的真实 UUID、全 0 UUID
都返回全表最新行，ret_count=全表约 201.8 万），仅 stock_code 过滤生效（不存在的 code
返回 0）。影响：http 模式无法按任务查询参数校验结果（本项目执行链只写不查，暂不受
影响；若前端"按任务看结果"切 HTTP 会拿到全表数据）。已登记待主站修复。

## 附：2026-10-29 全控制器实测契约备忘（7070 测试环境）

- ParamTasks：不接受客户端自带 id（携带即 400"操作失败"）；不携带 id 插入，
  主键 UUID 经 ``ret_obj`` 字符串回带；Delete/Delete后读同既有登记。
- 数值主键表（Results/Return/Cache 等）新行主键经 ``ret_count`` 回带。
- ParamTaskLogs / Return Delete 按 task_id 整删（id 被忽略）。
- ParamScheduledTasks ModifyOrAdd 需 ``task_function``；ParamGoogleSheet 需
  ``registry_scope``/``sheet_name`` 等非空列齐全，否则 500。
- StockData/StockDataUs GetSummaryByPageList 过滤是 ``begin_date``+``end_time``
  （无 stock_code 过滤，空载荷 400）。

## 附：2026-10-29 补测契约备忘（57 个未测端点全覆盖，7070）

- ParamXplAnalysisJobs：**id 由客户端生成**（"id不能为空"；现有最大 id+1 可用），
  与其他数值表（主键远端生成）契约不同。
- StockParamResult/AddOrModify：插入正常（200，不带 id 由主站生成数值主键，按业务键
  task_id+task_index upsert）；**Delete 按 task_id+task_index 删单条**（DTO 仅这两个
  字段，task_index 缺省 0；无按 task_id 整批删除端点）——本项目执行链只写不删，
  不受影响。详见文末 2026-10-29 复核修正。
- StockData/GetListVolume：按应用真实调用形态（带后缀 stock_code + coefficient）
  200；DTO 里 stock_lelvel 等多个字段是严格 Int32（传字符串/空即 400 类型转换错）。
- StockData GetListHisPage/GetListPage/GetStockListByCodeOrDate 与 StockDataUs
  同名端点：带日期/分页参数后全部 200；GetDataAllList 空载荷超时（277 万行大表，
  生产代码须带过滤调用）。
- SysModel：列表行的主键字段是 ``model_id``（行内没有 id）；但 GetById 请求体是
  ``IdRequestDto {id}``——传 ``{"id": <row.model_id>}`` 200，传 ``{"model_id": ...}``
  会因 id 缺省 0 返回 400"数据不存在"。
- SheetTokens/Delete / ParamTaskLogs 等其余 Delete：不存在行 400（既有契约）。

## 附：StockParamResult 重跑语义与删除契约（2026-10-29 实测补记 / 同日复核修正）

以 swagger（`/swagger/v1/swagger.json` 的 `DeleteStockParamResultRequestDto`）为准并实测：

- **本项目策略：只写入、不移除。** 执行链仅调用 `AddOrModify`（每个成功参数组合
  写一行，按 task_id+task_index 覆盖）；全仓库没有任何 StockParamResult 的查询或
  Delete 调用，迁移侧不提供删除能力，历史行清理由主站负责。
- **重跑天然覆盖，无需删除**：AddOrModify 不带 id 时按业务键 **task_id + task_index**
  upsert（**不含 stock_code**）——同键二次写入更新同一行（实测 id 不变、
  return_rate 1.23→9.99，行数仍 1）。C 系重头重跑/重启不会堆行。
- **update 分支不更新 stock_code**：实测同一 (task_id, task_index) 先写 AAA.SH、
  再以 BBB.SH 写入，回查仍是 AAA.SH（仅指标字段被更新）。若重跑后同一 index 对应的
  股票发生变化，行内代码会保留旧值，需主站确认是否预期。
- **Delete 只按 task_id + task_index 删单条**：请求体只有这两个字段（task_index
  缺省为 0），删除命中行返回 200，未命中返回 400"操作失败"。实测同 task_id 的
  index 0/1/2 三行，`Delete({task_id})` 只删掉 index=0 一行，其余两行需逐个
  `Delete({task_id, task_index})`。**不存在按 task_id 批量删除的端点**；如需按任务
  清理，只能循环 task_index 0..N-1 并容忍 400。此前"需要整行字段才 200"是
  task_index 缺省 0 恰好命中探针行导致的误判，已修正。
- **ParamTaskResults/Delete 不级联**：`ParamTaskResults/Delete` 的 DTO 是
  `ParamTaskIdRequestDto {task_id}`，会整删该任务的全部 ``t_param_task_results`` 行
  （实测 3 行一次删净，重复删 400"操作失败"），但**不会删除同 task_id 的
  StockParamResult 行**（实测残留，需再按 task_id+task_index 逐条删）。两张表是
  两个独立端点，别混用。
- **列表接口的 task_id/task_index 过滤不生效**：见缺陷 #6；按任务查结果目前没有
  服务端手段，只能按 stock_code 过滤或全表翻页。

## 附：2026-10-29 主线业务语义复核（t_param + K线 + 代理）

复核范围：除 StockParamResult 外，双生项目实际使用的 17 个 t_param 控制器、
StockData/StockDataUs、StockDic 代理、Sys* 网关读。结论：读写主通路基本满足，
但存在 3 个硬缺口。

### 硬缺口 A：数值主键插入的新 id 只在 ret_count，仓储丢失（P0，2026-10-29 已修复）

实测 ParamTaskResults / ParamTaskResultsReturn / ParamGoogleSheetTokens /
ParamTaskResultSummaryIndex 等数值主键表新行插入时 ``ret_obj=null``，新 id 由
``ret_count`` 回带（Results=4611724、Token=9、SummaryIndex=7438）。
``HttpRepositoryBase.save()`` 只经 ``_make_request`` 取 ``ret_obj``，插入后返回的
记录没有 id。后果：

- ``create_with_return`` 用 ``saved["id"]`` 写 ParamTaskResultKlineLinks →
  ``result_id=null`` → 400（实测），任务保存失败且已插入的结果行残留（HTTP 无事务）；
- Token 导入 ``add_entity`` 无法回写 ``entity.id``，导入响应 id 为空。

修法：``save()`` 在“载荷无 id（插入）”分支改走 ``_make_request_with_count``，
把 ``ret_count`` 作为新 id 回填；更新分支忽略 ret_count。

### 硬缺口 B：生产 base 缺 E12 的 12 个端点（P0，2026-10-29 已加代码护栏；部署待主站）

应用 ``.env`` 指向 ``https://stockapi.jaspil.cn``；其 swagger 相比 7070 缺
ParamTaskKlineSources / ParamTaskRandomSeries / ParamTaskResultKlineLinks
全部 12 个端点（7070 有、生产无）。C5/C7 随机 K 线（persist_snapshots）在生产
环境会在建快照/写关联处 404。需主站部署 E12 或确认目标环境为 7070。

### 硬缺口 C：跨表无事务，失败留半写（P1，2026-10-29 已加补偿；完全原子性待 E4）

``transaction()`` 为空实现；``create_with_return`` 依次写 return → result →
kline link，任一步失败前序行保留（实测 link 400 后 result 行残留，需手工清理）。
本地 db 模式同事务，http 模式需补偿清理或远端事务端点（E4）。

### 契约差异（不阻塞当前执行，需知晓）

- ParamTaskResults/ModifyOrAdd **不按 (task_id, step_index) upsert**：同键写两次
  产生两行（实测 4611720/4611721）。正常每 step 只写一次且重启前 data_cleanup
  先删；超时重发/重复提交会堆行。
- Results/Return/Logs 的 Delete 按 task_id 整任务删；按“老行”触发的清理会连带
  删除同任务较新行（已在前文清理语义登记）。
- 逐任务循环删除，非原子；中途失败留部分数据。

### 并发残留（P2）

Redis 裁决层覆盖 11 处临界区（状态机/Sheet 占用/token 对账/回测锁/调度锁），
单 worker gthread=8 部署下有效。残留：``increment_usage`` / ``release_usage``
的读-改-写不在 Redis 互斥内，并发启动两个任务时 token 计数可能丢更新/瞬时
超额；``apply_in_use_counts`` 对账可纠正计数，容量校验窗口仍存在。建议套
``token:{id}:usage`` 锁。

### 已验证 OK（2026-10-29）

- 核心列表过滤全部生效（不存在的值返回 0，无第二个“过滤被忽略”）：tasks 的
  task_types/statuses/keyword/created_from、logs 的 task_id/level、results 的
  task_ids、returns 的 task_id/stock_code、GoogleSheet 的 task_id/table_type、
  run_locks 的 spreadsheet_id、summary_index 的 task_id/stock_keyword、
  kline_sources/random_series/kline_links 的 task_id/stock_code/result_id、
  stock_metadata 的 stock_code；分页 ret_count 与过滤一致。
- ParamGoogleSheet 的 task_id 过滤实测映射 current_task_id（探针行验证后清理），
  release_by_task 的“先过滤再校验 current_task_id”成立。
- StockData/StockDataUs GetDataAllList：stock_code+begin_date 过滤生效、字段
  （stock_open/max/min/close/volume/volume_price）与升序日期正确（沪市 37 行 /
  美股 41 行）。
- StockDic/GetProxyListByOne 返回 username/password/url/port 四字段，符合
  proxy_manager 拼装。
- 缺陷 #4/#5 已修复（见上文复核）。

### 修复（2026-10-29，代码侧）

- **A 已修复**：`HttpRepositoryBase.save()` 插入分支（载荷无 id）对开启
  ``capture_insert_id`` 的仓储改走 ``modify_or_add(with_count=True)``，把
  ``ret_count`` 回填为 id；``_with_generated_id`` 兼容数值回执。已开启：
  TaskResult / GoogleSheetToken / GoogleSheet；ResultsReturn 由
  ``create_with_return`` 直接取 ``ret_count``。7070 实测：结果 id=4611725、
  收益 id=7839、随机K线关联 result_id=4611725（一致），探针已清理。
- **B 已加代码护栏**：新增 `app/remote_api/capabilities.py::require_e12`
  （进程内缓存，探测失败只记 debug）；快照仓储 create_source/create_series/
  create_link 与 create_with_return 写前预检。生产 base 现在会在任务早期
  明确报“远端未部署随机K线接口(E12) + 缺失端点”，不再跑到一半 404；
  7070 预检通过。**端点部署仍需主站完成，代码无法替代。**
- **C 已加补偿**：create_with_return 失败时关联行按 id 删除；结果/收益行
  仅在确认本任务没有更早结果行（首步）时按 task_id 整删；存在更早结果行
  时记录“部分写入”warning 并保留数据（远端无行级删除，任务级整删会误删
  历史步骤）。完整原子性仍需远端事务端点（E4）。
- 测试：新增 `tests/unit/test_http_repository_insert_id.py` 7 例（插入 id /
  更新不走 count / 关联 result_id / 首步补偿 / 非首步不整删 / E12 预检 /
  Token 回写）；相关仓储、Token、C 系回归 170+ 例通过。


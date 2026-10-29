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
（update 分支）不受影响。已登记待主站修复。

## 缺陷 #5：ParamTaskResultSummaryIndex/ModifyOrAdd 插入分支 500（2026-10-29）

`POST /api/ParamTaskResultSummaryIndex/ModifyOrAdd`：**新行插入**一律 500（UUID
宿主任务 + DTO 全字段载荷同样 500）；分页/删除正常。影响：http 模式下回测汇总
重建（模型汇总 dedupe/重建链路写汇总索引）会失败。已登记待主站修复。

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
- StockParamResult/AddOrModify：插入正常（200，按 id upsert）；**Delete 需要
  id+task_id+stock_code 全字段才 200**（单 id / 单 task_id 都 400"操作失败"）——
  本项目执行链只写不删，不受影响。
- StockData/GetListVolume：按应用真实调用形态（带后缀 stock_code + coefficient）
  200；DTO 里 stock_lelvel 等多个字段是严格 Int32（传字符串/空即 400 类型转换错）。
- StockData GetListHisPage/GetListPage/GetStockListByCodeOrDate 与 StockDataUs
  同名端点：带日期/分页参数后全部 200；GetDataAllList 空载荷超时（277 万行大表，
  生产代码须带过滤调用）。
- SysModel：行主键是 ``model_id``（不是 id）；GetById 按 model_id 查 200 正常。
- SheetTokens/Delete / ParamTaskLogs 等其余 Delete：不存在行 400（既有契约）。


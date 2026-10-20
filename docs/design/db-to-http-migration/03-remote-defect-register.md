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

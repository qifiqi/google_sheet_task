# 远端缺陷登记：ParamTasks/ModifyOrAdd 插入分支失败（2026-10-17）

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

## 需要远端回报

插入分支的服务端异常堆栈（EF/数据库层异常被 `"操作失败"` 吞掉了）：
重点排查 `t_param_tasks` 的约束/触发器、实体主键配置、以及 ModifyOrAdd 实现在
"id 不存在 → Add" 分支的数据库写入异常。

修复验证：执行上方步骤 3 返回 `ret_code=200` 即为修复完成。

# 数据库监控与定时任务调度 API

> 涵盖 `database_api` 和 `scheduler_api` 两个蓝图

---

## 一、数据库监控（database_api 蓝图）

> 蓝图：`database_api_bp`，URL 前缀：`/api`
> 权限：`database:manage`

### 1. GET `/api/database/status`

获取数据库完整状态报告（表大小、索引、连接数等）。

**响应**：
```json
{
  "status": "success",
  "report": {
    "tables": [...],
    "total_size": "...",
    "connection_count": 10,
    ...
  }
}
```

### 2. POST `/api/database/vacuum`

执行数据库 VACUUM 压缩操作。

**响应**：
```json
{
  "status": "success",
  "result": { "success": true, "message": "VACUUM 完成" }
}
```

**错误**：`400` — VACUUM 执行失败

### 3. GET `/api/database/suggestions`

获取数据库优化建议（索引建议、慢查询分析等）。

**响应**：
```json
{
  "status": "success",
  "suggestions": [
    { "type": "index", "table": "tasks", "suggestion": "..." }
  ]
}
```

---

## 二、定时任务调度（scheduler_api 蓝图）

> 蓝图：`scheduler_api_bp`
> URL 前缀：`/api/admin/scheduler`
> 权限：`scheduler:view`（查询）/ `scheduler:manage`（操作）

### 4. GET `/api/admin/scheduler/stats`
**权限**：`scheduler:view`

获取调度器统计信息。

**响应**：
```json
{
  "success": true,
  "stats": {
    "total_tasks": 5,
    "active_tasks": 3,
    "inactive_tasks": 2,
    "scheduler_running": true
  }
}
```

### 5. GET `/api/admin/scheduler/tasks`
**权限**：`scheduler:view`

获取定时任务列表（分页）。

**参数**（query）：
| 参数 | 类型 | 默认 | 说明 |
|------|------|------|------|
| page | int | 1 | 页码 |
| per_page | int | 50 | 每页条数 |

**响应**：
```json
{
  "success": true,
  "tasks": [
    {
      "id": 1,
      "name": "每日清理",
      "description": "清理过期日志",
      "cron_expression": "0 2 * * *",
      "task_type": "cleanup",
      "task_function": "cleanup_old_logs",
      "task_params": { "days": 30 },
      "is_active": true,
      "last_run_time": "2024-01-01T02:00:00",
      "next_run_time": "2024-01-02T02:00:00",
      "run_count": 100,
      "created_at": "...",
      "updated_at": "..."
    }
  ],
  "pagination": { "page": 1, "per_page": 50, "total": 5, "pages": 1 }
}
```

### 6. POST `/api/admin/scheduler/tasks`
**权限**：`scheduler:manage`

创建定时任务。

**请求体**：
```json
{
  "name": "每日清理",
  "description": "清理过期日志",
  "cron_expression": "0 2 * * *",
  "task_type": "cleanup",
  "task_function": "cleanup_old_logs",
  "task_params": "{\"days\": 30}",
  "is_active": true
}
```

**必填字段**：`name`、`cron_expression`、`task_type`、`task_function`

**校验**：
- `cron_expression` 必须是有效 cron 表达式（使用 croniter 验证）
- `task_params` 必须是有效 JSON 字符串

### 7. PUT `/api/admin/scheduler/tasks/<int:task_id>`
**权限**：`scheduler:manage`

更新定时任务。可更新字段：`name`、`description`、`cron_expression`、`task_type`、`task_function`、`task_params`、`is_active`。

**调度器同步**：更新后自动从调度器移除旧任务，若 `is_active=true` 则重新添加。

### 8. DELETE `/api/admin/scheduler/tasks/<int:task_id>`
**权限**：`scheduler:manage`

删除定时任务（同时从调度器移除）。

### 9. POST `/api/admin/scheduler/tasks/<int:task_id>/toggle`
**权限**：`scheduler:manage`

切换定时任务启用/禁用状态。

**请求体**：
```json
{ "is_active": true }
```
> 不传 `is_active` 时自动取反。

### 10. POST `/api/admin/scheduler/tasks/<int:task_id>/run`
**权限**：`scheduler:manage`

立即执行定时任务（异步后台执行）。

**约束**：
- 调度器未运行时返回 `400`
- 任务正在执行中时返回 `400`

**响应**：
```json
{
  "success": true,
  "message": "任务已提交到后台异步执行",
  "task_id": 1
}
```

### 11. GET `/api/admin/scheduler/tasks/<int:task_id>/status`
**权限**：`scheduler:view`

获取定时任务的执行状态（含异步执行状态和调度器 job 状态）。

**响应**：
```json
{
  "success": true,
  "task": {
    "id": 1,
    "name": "每日清理",
    "is_active": true,
    "last_run_time": "...",
    "next_run_time": "...",
    "run_count": 100
  },
  "async_status": {
    "status": "completed",
    "start_time": "...",
    "end_time": "...",
    "error": null
  },
  "job_status": { ... }
}
```

### 12. GET `/api/admin/scheduler/status`
**权限**：`scheduler:view`

获取调度器运行状态。

**响应**：
```json
{
  "success": true,
  "status": {
    "running": true,
    "jobs_count": 3
  }
}
```

---

## 业务规则

1. **Cron 表达式**：使用 `croniter` 库验证，支持标准 5 段 cron 格式
2. **调度器同步**：创建/更新/删除/切换状态时，都会自动同步到 APScheduler（移除旧 job → 按 is_active 决定是否添加新 job）
3. **异步执行**：`run` 接口提交后任务在后台线程池执行，通过 `async_status` 查询进度
4. **VACUUM 限制**：PostgreSQL 中 VACUUM 不能在事务块内执行，`DatabaseMonitor` 内部处理了连接隔离

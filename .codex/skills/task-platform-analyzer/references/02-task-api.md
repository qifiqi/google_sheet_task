# 02 - 任务管理 API（核心）

## GET /api/tasks
获取任务列表 + 统计数据。支持分页、类型/状态筛选、关键词搜索。

**查询参数：**
| 参数 | 类型 | 默认 | 说明 |
|------|------|------|------|
| page | int | 1 | 页码 |
| per_page | int | 10 | 每页条数 |
| task_type | string | - | 筛选任务类型 |
| status | string | - | 筛选状态 |
| keyword | string | - | 搜索任务名称 |

**响应：**
```json
{
  "status": "success",
  "tasks": [
    {
      "id": "uuid-string",
      "name": "任务名称",
      "description": "...",
      "status": "running",
      "task_type": "google_sheet",
      "config": {},
      "created_by_user_id": 1,
      "start_time": "2025-01-01T10:00:00",
      "end_time": null,
      "current_step": 5,
      "total_steps": 20,
      "error_message": null,
      "created_at": "2025-01-01T09:00:00",
      "updated_at": "2025-01-01T10:05:00"
    }
  ],
  "pagination": {
    "page": 1, "per_page": 10, "total": 100,
    "pages": 10, "has_prev": false, "has_next": true,
    "prev_num": null, "next_num": 2
  },
  "statistics": {
    "total_tasks": 100,
    "completed_tasks": 80,
    "running_tasks": 5,
    "error_tasks": 3,
    "pending_tasks": 12,
    "today_new_tasks": 10,
    "success_rate": 80.0,
    "error_rate": 3.0,
    "avg_duration_minutes": 15.5
  }
}
```

---

## POST /api/tasks
创建任务并自动启动。

**请求体：**
```json
{
  "name": "AAPL参数回测 (必填)",
  "description": "描述 (可选)",
  "task_type": "google_sheet (默认)",
  "config": { /* 任务配置对象 (必填) */ }
}
```

**task_type 可选值：**
- `google_sheet` — C3 参数校验
- `google_sheet_C4` — C4 参数校验
- `google_sheet_C5` — C5 参数校验
- `backtest_training` — 单品回测训练
- `backtest_multi_product` — 多品回测

**C3 config 示例：**
```json
{
  "sheet": {"spreadsheet_id": "xxx", "worksheet_name": "Sheet1"},
  "token_file": "data/token.json",
  "token_id": 1,
  "parameters": [[0.001, 0.002], [1.0, 1.5, 2.0]],
  "market_type": "cn",
  "end_date": "2024-12-31"
}
```

**响应：** `{"status": "success", "task_id": "uuid", "message": "任务创建并启动成功"}`

---

## POST /api/tasks/batch-create
C31 批量创建接口。后端自动拆分为多个 C3 子任务。

**请求体：** C31 完整配置（包含 sheet、parameters 数组、market_type 等）。
**权限：** `task:create`

---

## GET /api/tasks/<task_id>
获取单个任务详情（含完整 config JSON）。

## DELETE /api/tasks/<task_id>
删除任务及其所有日志（TaskLog）和结果（TaskResult）。级联删除。

---

## PUT /api/tasks/<task_id>/config
更新任务配置。

**请求体：**
```json
{
  "config": { /* 新配置 (必填) */ },
  "name": "新名称 (可选)",
  "description": "新描述 (可选)",
  "status": "pending (可选，手动覆盖状态)"
}
```

---

## POST /api/tasks/<task_id>/cancel
取消运行中的任务。触发 `threading.Event` 停止信号。

---

## GET /api/tasks/<task_id>/logs
获取 TaskLog 表中该任务的执行日志。

**响应：**
```json
{
  "status": "success",
  "logs": [
    {"id": 1, "level": "info", "message": "开始执行...", "timestamp": "2025-01-01T10:00:00"}
  ]
}
```

---

## GET /api/tasks/<task_id>/results
获取任务结果列表，支持分页。

**查询参数：** `page`, `per_page`

**分页响应：**
```json
{
  "status": "success",
  "results": [{"id": 1, "step_index": 0, "result": {...}}],
  "total": 50, "pages": 5, "current_page": 1, "per_page": 10,
  "total_success": 45, "total_failed": 5
}
```

---

## GET /api/tasks/<task_id>/export
导出单个任务结果为 Excel 文件（`send_file` 二进制响应）。

---

## GET /api/tasks/<task_id>/status-check
检查任务在本地内存中的线程状态。返回任务是否仍在 `running_tasks` 字典中。

## GET /api/tasks/<task_id>/stop-confirmation
确认任务线程是否已完全停止（包括线程 join 状态、stop_event 是否 set 等）。

---

## POST /api/tasks/<task_id>/restart
重启任务。

**请求体：** `{"resume_from_checkpoint": true}`
- `true`（默认）：从最后成功的 step_index 继续
- `false`：从头开始

---

## POST /api/tasks/<task_id>/create-restart
基于原任务的 config 创建一个新的重启任务（不修改原任务）。自动启动新任务。

**特殊处理：** backtest_training / backtest_multi_product 如果已有任务运行中，会排队而非直接启动（返回 `queued: true`）。

---

## GET /api/tasks/<task_id>/system-logs
从系统日志文件（`app.log`）中提取与该任务相关的日志行。

**查询参数：**
| 参数 | 类型 | 默认 | 说明 |
|------|------|------|------|
| limit | int | 200 | 最大返回条数 |
| level | string | - | 过滤级别（info/warning/error） |

**匹配模式：** `[Task-<id前8位>]`、`任务 <id>`、完整 `task_id`

---

## POST /api/tasks/batch-export
批量合并导出多个 C3 任务结果为 CSV 文件。

**请求体：** `{"task_ids": ["id1", "id2", ...]}`
**限制：** 最多 10 个任务（`BATCH_EXPORT_MAX_TASKS = 10`）
**响应：** `text/csv` 文件下载，带 `Content-Length` 头
**性能：** 使用 SQL 列选择优化 + `SET LOCAL statement_timeout = '120s'`

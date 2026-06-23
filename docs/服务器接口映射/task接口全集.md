# task 接口全集

## 1. 文档说明

本文档整理当前系统 `task` 相关接口，便于外部服务联调。

包含内容：

- 创建任务
- 批量创建任务
- 查询任务列表
- 查询任务详情
- 删除任务
- 更新任务配置
- 取消任务
- 查询任务日志
- 查询任务结果
- 查询任务状态检查
- 查询任务停止确认
- 重启任务
- 创建重启副本任务
- 查询任务系统日志

统一说明：

- 基础路径示例：`http://127.0.0.1:5000`
- 鉴权方式：登录态 Cookie 或系统部署要求的认证头
- 请求头：

```http
Content-Type: application/json
Accept: application/json
```

---

## 2. 通用响应格式

### 成功

```json
{
  "status": "success",
  "message": "操作成功"
}
```

### 失败

```json
{
  "status": "error",
  "message": "错误说明"
}
```

---

## 3. 创建任务

### 接口

```http
POST /tasks
```

### 说明

创建并立即启动单个任务。

常见 `task_type`：

- `google_sheet`：C3
- `google_sheet_C4`：C4
- `google_sheet_C5`：C5

### 请求示例

```json
{
  "name": "AAPL",
  "description": "C3任务示例",
  "task_type": "google_sheet",
  "config": {
    "spreadsheet_id": "1AbCdEfGhIjKlMnOpQrStUvWxYz1234567890",
    "sheet_name": "Sheet1",
    "token_type": "file",
    "token_id": "__random__",
    "token_file": "",
    "token_json": "",
    "proxy_url": null,
    "parameters": [
      [1, 2, 3],
      [10, 20],
      [30, 40]
    ]
  }
}
```

### curl 示例

```bash
curl -X POST "http://127.0.0.1:5000/tasks" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json" \
  -b "session=你的登录态Cookie" \
  -d '{
    "name": "AAPL",
    "description": "C3任务示例",
    "task_type": "google_sheet",
    "config": {
      "spreadsheet_id": "1AbCdEfGhIjKlMnOpQrStUvWxYz1234567890",
      "sheet_name": "Sheet1",
      "token_type": "file",
      "token_id": "__random__",
      "token_file": "",
      "token_json": "",
      "proxy_url": null,
      "parameters": [[1,2,3],[10,20],[30,40]]
    }
  }'
```

### 成功响应

```json
{
  "status": "success",
  "task_id": "f3f6e6ae-0c74-4fa3-8b53-8a52dbf0baf8",
  "message": "任务创建并启动成功"
}
```

---

## 4. 批量创建任务

### 接口

```http
POST /tasks/batch-create
```

### 说明

用于 C31 批量创建子任务。

### curl 示例

```bash
curl -X POST "http://127.0.0.1:5000/tasks/batch-create" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json" \
  -b "session=你的登录态Cookie" \
  -d '{
    "name": "C31批量任务",
    "description": "批量创建示例",
    "config": {
      "base_task_name": "C31子任务",
      "stock_codes": ["600519"],
      "parameters": [[[1,2,3]], [[10,20]]],
      "sheets": [
        {
          "spreadsheet_id": "sheet_id_1",
          "sheet_name": "Sheet1",
          "title": "C31-[1y-1]"
        }
      ]
    }
  }'
```

### 成功响应字段

| 字段 | 说明 |
| --- | --- |
| `task_id` | 首个任务 ID |
| `task_ids` | 所有子任务 ID |
| `started_task_ids` | 成功启动的子任务 ID |
| `failed_to_start` | 启动失败明细 |
| `children` | 子任务摘要 |

---

## 5. 查询任务列表

### 接口

```http
GET /tasks
```

### 查询参数

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| `task_type` | string | 任务类型筛选 |
| `page` | int | 页码 |
| `per_page` | int | 每页数量 |
| `status` | string | 状态筛选 |
| `keyword` | string | 名称、描述、ID 模糊搜索 |

### curl 示例

```bash
curl "http://127.0.0.1:5000/tasks?page=1&per_page=10&task_type=google_sheet_C5" \
  -H "Accept: application/json" \
  -b "session=你的登录态Cookie"
```

### 响应示例

```json
{
  "status": "success",
  "tasks": [
    {
      "id": "任务ID",
      "name": "任务名称",
      "description": "任务描述",
      "status": "completed",
      "task_type": "google_sheet_C5",
      "config": {},
      "start_time": "2026-04-21T09:00:00",
      "end_time": "2026-04-21T09:30:00",
      "current_step": 10,
      "total_steps": 10,
      "error_message": null,
      "created_at": "2026-04-21T09:00:00",
      "updated_at": "2026-04-21T09:30:00"
    }
  ],
  "pagination": {
    "page": 1,
    "per_page": 10,
    "total": 1,
    "pages": 1,
    "has_prev": false,
    "has_next": false
  },
  "statistics": {
    "total_tasks": 1,
    "completed_tasks": 1,
    "running_tasks": 0,
    "error_tasks": 0,
    "pending_tasks": 0,
    "today_new_tasks": 1,
    "success_rate": 100.0,
    "error_rate": 0.0,
    "avg_duration_minutes": 30
  }
}
```

---

## 6. 查询任务详情

### 接口

```http
GET /tasks/{task_id}
```

### curl 示例

```bash
curl "http://127.0.0.1:5000/tasks/f3f6e6ae-0c74-4fa3-8b53-8a52dbf0baf8" \
  -H "Accept: application/json" \
  -b "session=你的登录态Cookie"
```

### 响应示例

```json
{
  "status": "success",
  "task": {
    "id": "任务ID",
    "name": "任务名称",
    "description": "任务描述",
    "status": "running",
    "task_type": "google_sheet",
    "config": {},
    "start_time": "2026-04-21T09:00:00",
    "end_time": null,
    "current_step": 3,
    "total_steps": 10,
    "error_message": null,
    "created_at": "2026-04-21T09:00:00",
    "updated_at": "2026-04-21T09:05:00"
  }
}
```

---

## 7. 删除任务

### 接口

```http
DELETE /tasks/{task_id}
```

### 说明

删除任务主记录，同时删除关联 `TaskResult`、`TaskLog`。

### curl 示例

```bash
curl -X DELETE "http://127.0.0.1:5000/tasks/f3f6e6ae-0c74-4fa3-8b53-8a52dbf0baf8" \
  -H "Accept: application/json" \
  -b "session=你的登录态Cookie"
```

### 成功响应

```json
{
  "status": "success",
  "message": "任务已删除"
}
```

---

## 8. 更新任务配置

### 接口

```http
PUT /tasks/{task_id}/config
```

### 请求示例

```json
{
  "name": "新任务名称",
  "description": "新描述",
  "config": {
    "spreadsheet_id": "new_sheet_id",
    "sheet_name": "Sheet1"
  }
}
```

### curl 示例

```bash
curl -X PUT "http://127.0.0.1:5000/tasks/f3f6e6ae-0c74-4fa3-8b53-8a52dbf0baf8/config" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json" \
  -b "session=你的登录态Cookie" \
  -d '{
    "name": "新任务名称",
    "description": "新描述",
    "config": {
      "spreadsheet_id": "new_sheet_id",
      "sheet_name": "Sheet1"
    }
  }'
```

---

## 9. 取消任务

### 接口

```http
POST /tasks/{task_id}/cancel
```

### curl 示例

```bash
curl -X POST "http://127.0.0.1:5000/tasks/f3f6e6ae-0c74-4fa3-8b53-8a52dbf0baf8/cancel" \
  -H "Accept: application/json" \
  -H "Content-Type: application/json" \
  -b "session=你的登录态Cookie" \
  -d '{}'
```

---

## 10. 查询任务日志

### 接口

```http
GET /tasks/{task_id}/logs
```

### curl 示例

```bash
curl "http://127.0.0.1:5000/tasks/f3f6e6ae-0c74-4fa3-8b53-8a52dbf0baf8/logs" \
  -H "Accept: application/json" \
  -b "session=你的登录态Cookie"
```

### 响应示例

```json
{
  "status": "success",
  "logs": [
    {
      "id": 1,
      "level": "info",
      "message": "开始执行任务",
      "timestamp": "2026-04-21T09:00:00"
    }
  ]
}
```

---

## 11. 查询任务结果

### 接口

```http
GET /tasks/{task_id}/results
```

### 查询参数

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| `page` | int | 页码，可选 |
| `per_page` | int | 每页数量，可选 |

### curl 示例

不分页：

```bash
curl "http://127.0.0.1:5000/tasks/f3f6e6ae-0c74-4fa3-8b53-8a52dbf0baf8/results" \
  -H "Accept: application/json" \
  -b "session=你的登录态Cookie"
```

分页：

```bash
curl "http://127.0.0.1:5000/tasks/f3f6e6ae-0c74-4fa3-8b53-8a52dbf0baf8/results?page=1&per_page=20" \
  -H "Accept: application/json" \
  -b "session=你的登录态Cookie"
```

### 响应示例

```json
{
  "status": "success",
  "results": [
    {
      "id": 1,
      "task_id": "任务ID",
      "step_index": 0,
      "parameters": {},
      "result": {},
      "success": true,
      "error_message": null,
      "timestamp": "2026-04-21T09:10:00"
    }
  ]
}
```

---

## 12. 查询任务状态检查

### 接口

```http
GET /tasks/{task_id}/status-check
```

### 说明

用于判断数据库状态、内存线程状态、是否可重启。

### curl 示例

```bash
curl "http://127.0.0.1:5000/tasks/f3f6e6ae-0c74-4fa3-8b53-8a52dbf0baf8/status-check" \
  -H "Accept: application/json" \
  -b "session=你的登录态Cookie"
```

---

## 13. 查询任务停止确认

### 接口

```http
GET /tasks/{task_id}/stop-confirmation
```

### curl 示例

```bash
curl "http://127.0.0.1:5000/tasks/f3f6e6ae-0c74-4fa3-8b53-8a52dbf0baf8/stop-confirmation" \
  -H "Accept: application/json" \
  -b "session=你的登录态Cookie"
```

---

## 14. 重启任务

### 接口

```http
POST /tasks/{task_id}/restart
```

### 请求示例

```json
{
  "resume_from_checkpoint": true
}
```

### curl 示例

```bash
curl -X POST "http://127.0.0.1:5000/tasks/f3f6e6ae-0c74-4fa3-8b53-8a52dbf0baf8/restart" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json" \
  -b "session=你的登录态Cookie" \
  -d '{
    "resume_from_checkpoint": true
  }'
```

---

## 15. 创建重启副本任务

### 接口

```http
POST /tasks/{task_id}/create-restart
```

### 说明

复制一个新的任务，再启动这个新任务，原任务保留。

### curl 示例

```bash
curl -X POST "http://127.0.0.1:5000/tasks/f3f6e6ae-0c74-4fa3-8b53-8a52dbf0baf8/create-restart" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json" \
  -b "session=你的登录态Cookie" \
  -d '{}'
```

### 响应示例

```json
{
  "status": "success",
  "new_task_id": "新任务ID",
  "message": "重启任务创建并启动成功"
}
```

---

## 16. 查询任务系统日志

### 接口

```http
GET /tasks/{task_id}/system-logs
```

### 查询参数

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| `limit` | int | 返回条数，默认 200 |
| `level` | string | 日志级别筛选，如 `info`、`warning`、`error` |

### curl 示例

```bash
curl "http://127.0.0.1:5000/tasks/f3f6e6ae-0c74-4fa3-8b53-8a52dbf0baf8/system-logs?limit=100&level=error" \
  -H "Accept: application/json" \
  -b "session=你的登录态Cookie"
```

### 响应示例

```json
{
  "status": "success",
  "logs": [
    {
      "timestamp": "2026-04-21T09:00:00",
      "level": "error",
      "message": "错误信息",
      "source": "app.services.task_manager",
      "task_id": "任务ID"
    }
  ],
  "task_id": "任务ID",
  "total_found": 1
}
```

---

## 17. 任务主对象字段

以下接口里大量复用 `task` 对象：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `id` | string | 任务 ID，UUID |
| `name` | string | 任务名称 |
| `description` | string | 任务描述 |
| `status` | string | 任务状态 |
| `task_type` | string | 任务类型 |
| `config` | object | 任务配置 JSON |
| `start_time` | string/null | 开始时间 |
| `end_time` | string/null | 结束时间 |
| `current_step` | int | 当前步骤 |
| `total_steps` | int | 总步骤数 |
| `error_message` | string/null | 错误信息 |
| `created_at` | string | 创建时间 |
| `updated_at` | string | 更新时间 |

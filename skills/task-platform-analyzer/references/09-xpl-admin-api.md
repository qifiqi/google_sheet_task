# XPL 数据分析与管理后台 API

> 涵盖 `xpl_bp`（XPL 分析工具）和 `admin_bp`（管理后台 API）

---

## 一、XPL 数据分析（xpl_bp 蓝图）

> 蓝图：`xpl_bp`，URL 前缀：`/xpl`
> **无需认证**（公开接口）

### 1. POST `/xpl/analyze`

分析 Excel 收益数据，计算各类统计指标。

**请求体**：
```json
{
  "data": "2023-01-01 0.01\n2023-01-02 0.02\n...",
  "time_format": "YYYY-MM-DD",
  "return_col": 2
}
```

| 字段 | 类型 | 默认 | 说明 |
|------|------|------|------|
| data | string | "" | 制表符/空格分隔的收益数据文本 |
| time_format | string | "auto" | 时间格式 |
| return_col | int | 2 | 收益率列序号（从 1 开始） |

**响应**：
```json
{
  "status": "success",
  "results": [
    { "date": "2023-01-01", "return": 0.01 }
  ],
  "metrics": {
    "total_return": 0.15,
    "annual_return": 0.12,
    "sharpe_ratio": 1.5,
    "max_drawdown": -0.08
  }
}
```

### 2. POST `/xpl/export`

导出分析结果为文件。

**请求体**：包含分析数据 + 文件名。
```json
{
  "filename": "analysis.xlsx",
  "data": "...",
  "format": "xlsx"
}
```

**响应**：文件下载（xlsx / csv 等）。

### 3. POST `/xpl/v1/analyze`

V1 版本：直接从 Google Sheet 读取数据并分析。

**请求体**：
```json
{
  "spreadsheet_id": "1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgVE2upms",
  "google_sheet_url": "https://docs.google.com/spreadsheets/d/...",
  "google_sheet_name": "Sheet1"
}
```

| 字段 | 说明 |
|------|------|
| spreadsheet_id | Google Sheet ID（优先级高于 url） |
| google_sheet_url | Google Sheet URL |
| google_sheet_name | 工作表名称，默认 "auto" |

---

## 二、管理后台 API（admin_bp 蓝图）

> 蓝图：`admin_bp`，URL 前缀：`/admin`
> 需要登录 + 对应权限

### 4. GET `/admin/api/dashboard/overview`
**权限**：`task:view`

管理后台仪表盘总览数据（任务统计、运行状态等）。

**响应**：由 `TaskRuntimeViewService.build_dashboard_overview()` 生成，按用户权限过滤。
```json
{
  "success": true,
  "total_tasks": 100,
  "running_tasks": 5,
  "error_tasks": 3,
  "completed_today": 10,
  "task_type_stats": { ... },
  "recent_tasks": [...]
}
```

### 5. GET `/admin/api/scheduler/status`
**权限**：`scheduler:view`

获取调度器异步任务执行状态（区别于 scheduler_api 的 `/api/admin/scheduler/status`）。

**响应**：
```json
{
  "success": true,
  "scheduler": {
    "is_running": true,
    "total_async_tasks": 3,
    "running_tasks": 1,
    "completed_tasks": 2,
    "failed_tasks": 0
  },
  "async_tasks": {
    "1": {
      "status": "running",
      "start_time": "2024-01-01T12:00:00",
      "end_time": null,
      "error": null,
      "duration": null
    },
    "2": {
      "status": "completed",
      "start_time": "...",
      "end_time": "...",
      "error": null,
      "duration": 120.5
    }
  }
}
```

### 6. POST `/admin/api/scheduler/cleanup`
**权限**：`scheduler:manage`

清理已完成的异步任务记录。

**请求体**：
```json
{ "max_age_hours": 24 }
```
> 默认 24 小时。

**响应**：
```json
{
  "success": true,
  "message": "已清理超过 24 小时的已完成任务记录"
}
```

### 7. GET `/admin/api/model-summary`
**权限**：`task:view`

查询单模型汇总数据（`TaskResultSummaryIndex` 表）。

**参数**（query）：由 `model_summary_service.query()` 解析，支持：
| 参数 | 说明 |
|------|------|
| task_type | 任务类型过滤 |
| stock_code | 股票代码过滤 |
| period_key | 年份/区间过滤 |
| is_best | 是否仅最优 |
| page / per_page | 分页 |

**响应**：汇总数据列表 + 分页信息。

### 8. GET `/admin/api/model-summary/export`
**权限**：`task:view`

按查询条件导出单模型汇总 CSV。

**参数**：同 model-summary 查询参数。

**响应**：CSV 文件下载（UTF-8 BOM），文件名 `model_summary.csv`。

### 9. POST `/admin/api/model-summary/rebuild`
**权限**：`database:model_summary` 或 `database:manage`

触发后台重建单模型汇总索引任务。

**请求体**：
```json
{
  "task_type": "backtest_training",
  "task_id": "uuid",
  "batch_size": 20,
  "reset": false
}
```

| 字段 | 类型 | 默认 | 说明 |
|------|------|------|------|
| task_type | string | null | 指定任务类型 |
| task_id | string | null | 指定任务 ID |
| batch_size | int | 20 | 批处理大小 |
| reset | bool | false | 是否清除已有索引 |

**响应**：
```json
{
  "status": "success",
  "job": { "job_id": "uuid", "status": "running", "progress": 0 }
}
```

### 10. GET `/admin/api/model-summary/rebuild/status`
**权限**：`database:model_summary` 或 `database:manage`

查询汇总索引重建状态。

**参数**（query）：
| 参数 | 类型 | 说明 |
|------|------|------|
| job_id | string | 可选，指定 job；不传则返回最新的 |

**响应**：
```json
{
  "status": "success",
  "job": {
    "job_id": "uuid",
    "status": "completed",
    "progress": 100,
    "total": 500,
    "processed": 500,
    "error": null
  }
}
```

### 11. GET `/admin/api/tasks/<task_id>/runtime-detail`
**权限**：`task:view`

获取任务运行时详细信息（含线程状态、token 占用、进度等管理视图）。

**权限逻辑**：通过 `authorize_task_type_action()` 按任务类型校验。

**响应**：
```json
{
  "success": true,
  "task": {
    "id": "uuid",
    "name": "...",
    "status": "running",
    "task_type": "google_sheet",
    "current_step": 50,
    "total_steps": 100,
    "is_running_in_thread": true,
    "token_info": { ... },
    ...
  }
}
```

---

## 业务规则

1. **XPL 接口无需认证**：`/xpl/analyze`、`/xpl/export`、`/xpl/v1/analyze` 为公开接口
2. **Dashboard 权限过滤**：`dashboard_overview` 根据当前用户权限返回其有权查看的任务类型统计
3. **Model Summary 重建**：后台异步执行，通过 `job_id` 轮询状态；`reset=true` 会先删除已有 `TaskResultSummaryIndex` 记录
4. **Scheduler 状态接口有两个**：
   - `/api/admin/scheduler/status`（scheduler_api）— 返回调度器基本状态
   - `/admin/api/scheduler/status`（admin_bp）— 返回异步任务执行详情
5. **Admin 蓝图页面路由**（仅页面渲染，非 API）：`/admin/`、`/admin/tasks`、`/admin/config`、`/admin/navigation`、`/admin/logs`、`/admin/templates`、`/admin/results`、`/admin/model-summary`、`/admin/google-sheets`、`/admin/scheduler`、`/admin/users`、`/admin/roles`

# 03 - Google Sheet 资源 API

## POST /api/google-sheet/worksheets
获取指定 Google 表格的所有工作表名称。带 5 天缓存。

**请求体：**
```json
{
  "spreadsheet_id": "Google表格ID (必填)",
  "proxy_url": "http://proxy:8080 (可选)"
}
```

**响应：**
```json
{
  "status": "success",
  "title": "表格标题",
  "worksheets": ["Sheet1", "Sheet2"],
  "cached": false
}
```

---

## GET /api/google-sheets
获取已注册的 Sheet 配置列表。

**查询参数：**
| 参数 | 类型 | 说明 |
|------|------|------|
| include_inactive | 0/1 | 包含已停用的配置 |
| only_available | 0/1 | 仅返回未被任务占用的 |
| task_id | string | 按关联任务筛选 |
| table_type | c3/c4/c5 | 按表类型筛选 |

---

## POST /api/google-sheets
注册新的 Sheet 配置。

**请求体：**
```json
{
  "spreadsheet_id": "xxx (必填)",
  "name": "配置名称 (可选)",
  "table_type": "c3 (必填)",
  "remark": "备注 (可选)",
  "is_active": true
}
```

---

## GET /api/google-sheets/<sheet_id>
获取单个 Sheet 配置详情。

## PUT /api/google-sheets/<sheet_id>
更新 Sheet 配置。
**可更新字段：** `spreadsheet_id`, `name`, `remark`, `table_type`, `is_active`

## DELETE /api/google-sheets/<sheet_id>
删除 Sheet 配置。

---

## GET /api/google-sheet-tokens
获取 Token 列表及使用摘要。

**查询参数：** `task_type`（google_sheet / backtest_training）

**响应：**
```json
{
  "status": "success",
  "random_value": "__random__",
  "tokens": [
    {
      "id": 1, "name": "Token 1",
      "token_file": "data/google_sheet_tokens/token_1.json",
      "is_active": true, "task_type": "google_sheet",
      "max_usage_count": 5, "current_usage_count": 2
    }
  ],
  "summary": {"total": 3, "active": 2, "occupied": 1}
}
```

---

## GET /api/google-sheet-tokens/<token_id>
获取 Token 详情。
**查询参数：** `include_context=1` 返回完整 token_context JSON

## PUT /api/google-sheet-tokens/<token_id>
更新 Token。
**可更新字段：** `name`, `token_context`, `is_active`, `task_type`, `max_usage_count`

---

## POST /api/google-sheet-tokens/import
导入新 Token（如已存在同 token_file 则更新）。

**请求体：**
```json
{
  "token_file": "data/google_sheet_tokens/token_1.json (必填)",
  "name": "Token名称 (可选)",
  "token_context": {},
  "task_type": "google_sheet (可选)",
  "max_usage_count": 5
}
```

---

## DELETE /api/google-sheet-tokens/<token_id>
物理删除 Token 记录。

---

## GET /api/<task_id>/export
兼容旧版导出路径，自动 302 重定向到 `/api/tasks/<task_id>/export`。

# 模板与任务结果 API（template_api 蓝图）

> 蓝图：`template_api_bp`，URL 前缀：`/api`
> 涵盖模板 CRUD 和跨任务结果查询

---

## 一、模板管理

### 1. GET `/api/templates`
**权限**：`template:view`

获取模板列表，可选按 `task_type` 过滤。

**参数**（query）：
| 参数 | 类型 | 说明 |
|------|------|------|
| task_type | string | 可选，按任务类型过滤 |

**响应**：
```json
{
  "status": "success",
  "templates": [
    {
      "id": 1,
      "name": "C3 标准模板",
      "description": "通用 C3 参数任务",
      "config": { "task_type": "google_sheet", "params": [...] },
      "created_at": "2024-01-01T00:00:00",
      "updated_at": "2024-01-01T00:00:00"
    }
  ]
}
```

### 2. POST `/api/templates`
**权限**：`template:manage`

创建新模板。

**请求体**：
```json
{
  "name": "新模板",
  "description": "描述",
  "config": { "task_type": "google_sheet", "params": [...] }
}
```

**校验**：
- `name` 必填
- `config` 必填，必须是有效 JSON

### 3. GET `/api/templates/<int:template_id>`
**权限**：`template:view`

获取模板详情。

### 4. PUT `/api/templates/<int:template_id>`
**权限**：`template:manage`

更新模板。请求体同创建。

### 5. DELETE `/api/templates/<int:template_id>`
**权限**：`template:manage`

删除模板。

---

## 二、跨任务结果查询

### 6. GET `/api/results`
**权限**：`task:view`

获取任务结果列表（跨任务），支持按 `task_id` 过滤。

**参数**（query）：
| 参数 | 类型 | 默认 | 说明 |
|------|------|------|------|
| page | int | 1 | 页码 |
| per_page | int | 20 | 每页条数，最大 100 |
| task_id | string | null | 按任务 ID 过滤 |

**权限逻辑**：
- 指定 `task_id` 时：校验当前用户对该任务类型的 `view` 权限
- 未指定 `task_id` 时：仅返回用户有权查看的任务类型的结果

**响应**：
```json
{
  "results": [
    {
      "id": 1,
      "task_id": "uuid",
      "step_index": 0,
      "success": true,
      "timestamp": "2024-01-01T00:00:00"
    }
  ],
  "total": 100,
  "pages": 5,
  "current_page": 1
}
```

### 7. GET `/api/results/<int:result_id>`
**权限**：`task:view`

获取任务结果详情（含完整 `result` JSON、`parameters` 等）。

**权限逻辑**：通过结果关联的 Task 的 `task_type` 进行 `authorize_task_type_action` 校验。

**响应**：完整 `TaskResult.to_dict()` 数据。

### 8. DELETE `/api/results/<int:result_id>`
**权限**：`task:delete`

删除任务结果。

**权限逻辑**：需要对应任务类型的 `delete` 权限。

---

## 业务规则

1. **任务类型权限隔离**：结果查询和删除都通过 `authorize_task_type_action()` 检查用户对任务类型的权限
2. **无权限时返回 403**：包含详细的 `required_permissions` 和 `missing_permissions` 信息
3. **跨类型过滤**：未指定 `task_id` 时，使用 `filter_task_types_by_action()` 获取用户有权查看的所有类型，仅返回这些类型的结果
4. **模板 config 格式**：存储为 JSON 字符串，API 返回时自动反序列化为对象

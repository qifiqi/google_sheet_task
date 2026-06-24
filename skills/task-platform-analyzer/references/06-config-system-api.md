# 配置与系统管理 API

> 涵盖 `config_api`、`meta_api`、`stock_api` 三个蓝图

---

## 一、系统配置（config_api 蓝图）

### 1. GET `/api/config`
**权限**：`config:view`

获取全部系统配置（从 ConfigManager 缓存刷新后返回）。

**响应**：
```json
{ "status": "success", "config": { "key1": "value1", ... } }
```

### 2. POST `/api/config`
**权限**：`config:manage`

批量更新系统配置。

**请求体**：JSON 键值对，每个 key 对应一条 `SystemConfig`。
```json
{ "proxy_enabled": "true", "max_concurrent_tasks": "5" }
```

**响应**：`{ "status": "success", "message": "配置更新成功，已立即生效" }`

### 3. GET `/api/config/validate`
**权限**：`config:view`

验证配置状态：返回数据库配置、缓存配置、Google Sheet 配置的对比信息。

**响应**：
```json
{
  "status": "success",
  "validation": {
    "database_configs": { "key": "value" },
    "cache_configs": { "key": "value" },
    "google_sheet_config": { ... },
    "cache_size": 10,
    "db_size": 10
  }
}
```

### 4. GET `/api/system-configs`
**权限**：`config:view`

获取 `system_configs` 表全量列表（按 key 升序）。

**响应**：
```json
{
  "status": "success",
  "configs": [
    { "key": "proxy_enabled", "value": "true", "description": "代理开关", "created_at": "...", "updated_at": "..." }
  ]
}
```

### 5. PUT `/api/system-configs/<key>`
**权限**：`config:manage`

更新单条 `SystemConfig`。

**请求体**：
```json
{ "value": "new_value", "description": "新描述" }
```
> `value` 和 `description` 至少传一个。

**错误**：`404` 配置不存在

---

## 二、导航菜单管理（config_api 蓝图）

### 6. GET `/api/navigation-menu-items`
**权限**：`navigation:view`

获取侧边栏路由表全量列表（按 parent_key → sort_order 排序）。

**响应**：
```json
{
  "status": "success",
  "items": [
    {
      "id": 1, "key": "admin.dashboard", "label": "仪表盘",
      "path": "/admin", "permission": "task:view",
      "parent_key": null, "sort_order": 0, "is_visible": true,
      "created_at": "...", "updated_at": "..."
    }
  ]
}
```

### 7. POST `/api/navigation-menu-items`
**权限**：`navigation:manage`

新增导航菜单项。

**请求体**：
```json
{
  "key": "admin.new_page",
  "label": "新页面",
  "path": "/admin/new",
  "permission": "task:view",
  "parent_key": "admin",
  "sort_order": 10,
  "is_visible": true
}
```

**校验规则**：
- `key` 必填且全局唯一
- `label` 必填
- `parent_key` 不能等于自身 `key`
- 父级菜单不能是可跳转路由（有 `path` 的）
- 显示状态的页面路由必须填写权限码

### 8. PUT `/api/navigation-menu-items/<int:item_id>`
**权限**：`navigation:manage`

更新导航菜单项，校验规则同新增。

### 9. DELETE `/api/navigation-menu-items/<int:item_id>`
**权限**：`navigation:manage`

删除导航菜单项。

**约束**：有子菜单时不允许删除，需先移动或删除子菜单。

---

## 三、系统日志（config_api 蓝图）

### 10. GET `/api/logs`
**权限**：`config:view`

读取应用日志文件，支持多维度过滤。

**参数**（query）：
| 参数 | 类型 | 默认 | 说明 |
|------|------|------|------|
| limit | int | 100 | 返回条数上限 |
| level | string | "" | 按级别过滤（info/warning/error） |
| search | string | "" | 关键字搜索 |
| date | string | "" | 日期过滤（如 2024-01-01） |
| task_id | string | "" | 按任务 ID 过滤 |

**响应**：
```json
{
  "status": "success",
  "logs": [
    {
      "timestamp": "2024-01-01T12:00:00",
      "level": "info",
      "message": "任务创建成功",
      "source": "task_api"
    }
  ]
}
```

### 11. GET `/api/logs/latest`
**权限**：`config:view`

获取最新日志，支持增量拉取。

**参数**（query）：
| 参数 | 类型 | 默认 | 说明 |
|------|------|------|------|
| since | string | "" | ISO 时间戳，仅返回此时间之后的日志 |
| limit | int | 50 | 返回条数上限 |

---

## 四、元数据（meta_api 蓝图）

### 12. GET `/api/meta/versions`
**无需认证**

返回可用任务版本列表。

**响应**：
```json
{
  "status": "success",
  "data": [
    { "value": "c3", "label": "C3", "create_url": "/google-sheet/create" },
    { "value": "c4", "label": "C4", "create_url": "/google-sheet/create?version=c4" },
    { "value": "c5", "label": "C5", "create_url": "/google-sheet/create?version=c5" },
    { "value": "c31", "label": "C31 批量", "create_url": "/google-sheet/create?version=c31" },
    { "value": "backtest_training", "label": "回测训练", "create_url": "/backtest-training/create" },
    { "value": "backtest_multi_product", "label": "多品数据回测", "create_url": "/backtest-multi-product/create" }
  ]
}
```

### 13. GET `/api/meta/enums`
**无需认证**

返回全部枚举值。

**响应**：
```json
{
  "status": "success",
  "data": {
    "google_sheet_table_types": [{ "value": "c3", "label": "C3" }, ...],
    "google_sheet_token_task_types": [...],
    "task_statuses": [{ "value": "pending", "label": "待执行" }, ...],
    "task_status_editable": [...],
    "task_types": [{ "value": "google_sheet", "label": "Google Sheet C3" }, ...]
  }
}
```

### 14. GET `/api/meta/nav`
**需要登录**

返回当前用户有权访问的导航菜单树（按权限自动过滤）。

**权限逻辑**：
- 读取 `NavigationMenuItem` 中 `is_visible=True` 的记录
- 检查用户是否持有菜单项的 `permission` 编码
- `资源:view` 权限可通过 `资源:manage` 继承
- 递归过滤子菜单

---

## 五、股票搜索（stock_api 蓝图）

### 15. GET `/api/search-stocks`
**权限**：`backtest:view`

全局股票搜索接口（与回测模块的搜索接口功能相同，但返回更详细的元数据字段）。

**参数**：同回测搜索（`q` + `page_size`）

**额外返回字段**：
- `inner_code`、`pinyin`、`security_type`、`small_type`、`flag`
- `ext_small_type`、`quote_id`、`market_type`、`unified_code`、`jys`、`classify`
- `is_exact_match`

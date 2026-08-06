# 01 - 认证与用户管理 API

## 认证接口

### POST /api/auth/login
登录获取 JWT 令牌。

**请求体：**
```json
{"username": "string", "password": "string"}
```

**成功响应（200）：**
```json
{
  "status": "success",
  "data": {
    "access_token": "eyJ...",
    "refresh_token": "eyJ...",
    "user": {
      "id": 1,
      "username": "admin",
      "mobile": "13800000000",
      "is_active": true,
      "is_alert_oncall": false,
      "permissions": ["task:view", "task:create", "config:manage", ...]
    }
  }
}
```

**错误响应：**
- 400：用户名和密码不能为空
- 400：用户名或密码错误
- 400：账号已被禁用

### POST /api/auth/refresh
刷新 access_token。

**请求体：** `{"refresh_token": "string"}`
**响应：** 返回新 `access_token` 和用户信息。
**错误：** 401（令牌过期/无效/版本不匹配）

### GET /api/auth/me
返回当前登录用户完整信息（含权限列表）。
**权限：** 已登录

### POST /api/auth/logout
退出登录，使当前 token 失效（通过递增 token_version）。

### PUT /api/auth/password
修改密码。
**请求体：** `{"old_password": "string", "new_password": "string"}`
**校验：** 新密码长度 ≥ 6 位

---

## 用户管理

### GET /api/admin/users
获取所有用户列表。
**权限：** `user:view` 或 `user:manage`

**响应：**
```json
{
  "status": "success",
  "data": [
    {"id": 1, "username": "admin", "mobile": "...", "is_active": true, "is_alert_oncall": false, "roles": [...]}
  ]
}
```

### POST /api/admin/users
创建新用户。
**权限：** `user:manage`

**请求体：**
```json
{
  "username": "string (必填)",
  "password": "string (必填)",
  "mobile": "string (可选)",
  "role_ids": [1, 2],
  "is_active": true,
  "is_alert_oncall": false
}
```

**说明：** `is_alert_oncall` 仅在用户关联了 developer 角色时才生效。

### PUT /api/admin/users/<user_id>
更新用户信息。
**可更新字段：** `mobile`, `is_active`, `password`, `role_ids`, `is_alert_oncall`

### DELETE /api/admin/users/<user_id>
删除用户（物理删除）。

---

## 角色管理

### GET /api/admin/roles
角色列表（含关联权限）。
**权限：** `user:view` 或 `user:manage`

### POST /api/admin/roles
创建角色。
**请求体：**
```json
{
  "name": "角色名称 (必填)",
  "code": "role_code (必填, 唯一)",
  "description": "描述",
  "permission_ids": [1, 2, 3]
}
```

### PUT /api/admin/roles/<role_id>
更新角色。可更新 `name`, `description`, `permission_ids`。

### DELETE /api/admin/roles/<role_id>
删除角色。系统内置角色（`is_system=true`）不可删除。

---

## 权限查询

### GET /api/admin/permissions
获取全部权限列表，按 `group` 分组返回。
**权限：** `user:view` 或 `user:manage`

**响应示例：**
```json
{
  "status": "success",
  "data": {
    "task": [
      {"id": 1, "code": "task:view", "name": "查看任务", "group": "task"}
    ],
    "config": [...],
    "admin": [...]
  }
}
```

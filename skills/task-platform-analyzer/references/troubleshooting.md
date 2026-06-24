# 故障排查与运维指南

---

## 一、任务系统故障

### 任务卡在 running 状态
**现象**：任务状态为 `running` 但长时间无新日志。

**排查步骤**：
1. 检查看门狗是否运行：`GET /admin/api/scheduler/status` 查看调度器状态
2. 查看任务日志：`GET /api/tasks/<task_id>/logs?limit=50`
3. 检查线程状态：`GET /admin/api/tasks/<task_id>/runtime-detail`
4. 看门狗会自动检测长时间无日志的 running 任务并标记

**手动处理**：
- 取消任务：`POST /api/tasks/<task_id>/cancel`
- 重启任务：`POST /api/tasks/<task_id>/restart`（支持 `resume_from_checkpoint`）

### 网络错误任务（[NETWORK_RETRYABLE]）
**现象**：任务 error_message 以 `[NETWORK_RETRYABLE]` 开头。

**机制**：
- `google_sheet_client.py` 识别网络超时/连接错误后标记
- 看门狗定期扫描带此标记的 error 任务并自动重启
- 重启间隔和次数由看门狗配置控制

**手动确认**：
```
GET /api/tasks?status=error&task_type=google_sheet
```
查看 `error_message` 是否包含 `[NETWORK_RETRYABLE]`。

### Token 占用未释放
**现象**：创建任务时报 "没有可用的 Token"。

**排查**：
1. `GET /api/google-sheet-tokens` 查看所有 token 的 `current_in_use_count`
2. `GET /api/google-sheet-tokens/<id>` 查看详情
3. 启动时 `run.py` 会调用 `reset_google_sheet_token_occupancy()` 自动清理

**手动释放**：更新 token 的 `current_in_use_count` 为 0。

### Google Sheet 占用未释放
**现象**：Sheet 显示 `is_in_use=true` 但关联任务已结束。

**排查**：
1. `GET /api/google-sheets` 查看 `is_in_use` 和 `current_task_id`
2. 启动时 `run.py` 调用 `reset_google_sheet_occupancy()` 自动清理

---

## 二、数据库问题

### 数据库连接数耗尽
**排查**：`GET /api/database/status` 查看连接数。

**处理**：
- `POST /api/database/vacuum` 清理死元组
- `GET /api/database/suggestions` 获取优化建议
- 检查是否有长时间空闲的连接

### 任务结果表过大
**处理**：
1. 使用批量导出功能归档：`POST /api/tasks/batch-export`（最多 10 个 C3 任务）
2. 删除旧结果：`DELETE /api/results/<result_id>`
3. 重建索引：`POST /admin/api/model-summary/rebuild`

### 查询超时
**机制**：批量导出使用 `SET LOCAL statement_timeout` 防止长查询阻塞。

**排查**：检查 `SystemConfig` 中的超时配置。

---

## 三、调度器问题

### 调度器未运行
**现象**：定时任务不执行，`scheduler_running: false`。

**排查**：
1. `GET /api/admin/scheduler/status` 确认状态
2. 检查 `run.py` 中 `init_scheduler()` 是否正常初始化
3. 查看系统日志：`GET /api/logs?search=scheduler`

### 定时任务执行失败
**排查**：
1. `GET /api/admin/scheduler/tasks/<id>/status` 查看异步状态
2. 检查 `async_status.error` 字段获取错误信息
3. `GET /admin/api/scheduler/status` 查看所有异步任务的运行状态

---

## 四、权限与认证问题

### JWT Token 过期
**处理**：`POST /api/auth/refresh` 刷新 token。

### 权限不足（403）
**排查**：
1. `GET /api/auth/me` 查看当前用户权限列表
2. 403 响应中包含 `required_permissions` 和 `missing_permissions`
3. 管理后台：`/admin/users` 和 `/admin/roles` 调整角色权限

### 任务类型权限
**机制**：不同任务类型有独立的权限编码。
- `task:view` / `task:create` / `task:delete` — 通用任务权限
- `backtest:view` / `backtest:create` — 回测任务权限
- 通过 `authorize_task_type_action()` 按任务类型动态校验

---

## 五、常用诊断 API 速查

| 场景 | API | 说明 |
|------|-----|------|
| 查看系统配置 | `GET /api/config/validate` | 对比数据库与缓存配置 |
| 查看数据库状态 | `GET /api/database/status` | 表大小、连接数 |
| 查看调度器 | `GET /admin/api/scheduler/status` | 异步任务状态 |
| 查看任务运行细节 | `GET /admin/api/tasks/<id>/runtime-detail` | 线程/Token 状态 |
| 查看系统日志 | `GET /api/logs?level=error` | 错误日志 |
| 查看任务日志 | `GET /api/tasks/<id>/logs` | 任务执行日志 |
| 检查 Token 占用 | `GET /api/google-sheet-tokens` | Token 使用计数 |
| 检查 Sheet 占用 | `GET /api/google-sheets` | Sheet 使用中状态 |
| 查看仪表盘 | `GET /admin/api/dashboard/overview` | 全局统计 |

---

## 六、启动与恢复

### 应用启动自动恢复（run.py）
启动时自动执行：
1. `db.create_all()` — 确保表结构存在
2. Schema 修补（`ensure_google_sheet_token_schema` 等）
3. `reset_google_sheet_token_occupancy()` — 重置 Token 占用
4. `reset_google_sheet_occupancy()` — 重置 Sheet 占用
5. `check_and_cleanup_dead_tasks()` — 清理死任务
6. `init_scheduler()` — 启动调度器
7. `init_task_watchdog()` — 启动看门狗

### 手动重启建议
1. 确认无正在运行的关键任务
2. 重启应用（`python run.py`）
3. 检查 `/admin/api/dashboard/overview` 确认状态恢复
4. 检查 `/admin/api/scheduler/status` 确认调度器正常

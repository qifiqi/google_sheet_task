# 权限模型与数据模型参考

---

## 一、RBAC 权限模型

### 三级结构
```
User → Role → Permission
```

- **User**：用户，可关联多个角色
- **Role**：角色，可关联多个权限；`is_system=true` 的为内置角色不可删除
- **Permission**：权限，编码格式 `资源:操作`

### 关联表
- `user_roles`：用户-角色多对多关联
- `role_permissions`：角色-权限多对多关联

### 权限编码完整列表

| 分组 | 权限编码 | 说明 |
|------|----------|------|
| **task** | `task:view` | 查看任务/日志/结果 |
| | `task:create` | 创建任务（含更新配置） |
| | `task:cancel` | 取消任务 |
| | `task:restart` | 重启任务 |
| | `task:delete` | 删除任务 |
| **backtest** | `backtest:view` | 查看回测任务/结果/搜索股票 |
| | `backtest:create` | 创建回测任务/导入 Excel/保存比例 |
| **config** | `config:view` | 查看系统配置/日志 |
| | `config:manage` | 修改系统配置 |
| **template** | `template:view` | 查看模板 |
| | `template:manage` | 管理模板（CRUD） |
| **navigation** | `navigation:view` | 查看导航菜单 |
| | `navigation:manage` | 管理导航菜单（CRUD） |
| **scheduler** | `scheduler:view` | 查看定时任务 |
| | `scheduler:manage` | 管理定时任务（CRUD/执行/切换） |
| **database** | `database:manage` | 数据库操作（VACUUM/状态/优化） |
| | `database:model_summary` | 模型汇总索引重建 |
| **google_sheet** | `google_sheet:view` | 查看 Google Sheet 配置/Token |
| | `google_sheet:manage` | 管理 Google Sheet 配置/Token |
| | `google_sheet:c3` | 访问 Google Sheet C3 |
| | `google_sheet:c4` | 访问 Google Sheet C4 |
| | `google_sheet:c5` | 访问 Google Sheet C5 |
| **user** | `user:view` | 查看用户列表 |
| | `user:manage` | 管理用户/角色/权限 |
| **page** | `page:admin:dashboard` | 访问仪表盘页面 |
| | `page:admin:tasks` | 访问任务管理页面 |
| | `page:admin:templates` | 访问任务模板页面 |
| | `page:admin:results` | 访问任务结果页面 |
| | `page:admin:model_summary` | 访问单模型汇总页面 |
| | `page:admin:scheduler` | 访问定时任务页面 |
| | `page:admin:config` | 访问系统配置页面 |
| | `page:admin:navigation` | 访问路由表页面 |
| | `page:admin:google_sheets` | 访问 Google Sheet 管理页面 |
| | `page:admin:logs` | 访问系统日志页面 |
| | `page:admin:users` | 访问用户管理页面 |
| | `page:admin:roles` | 访问角色管理页面 |

### 任务类型权限映射

`authorize_task_type_action()` 根据任务类型动态计算所需权限：

| 任务类型 | view | create | delete |
|----------|------|--------|--------|
| `google_sheet` (C3/C31) | `task:view` | `task:create` | `task:delete` |
| `google_sheet_C4` | `task:view` | `task:create` | `task:delete` |
| `google_sheet_C5` | `task:view` | `task:create` | `task:delete` |
| `backtest_training` | `backtest:view` | `backtest:create` | `task:delete` |
| `backtest_multi_product` | `backtest:view` | `backtest:create` | `task:delete` |
| `model_summary_rebuild` | `database:model_summary` | — | — |

### 权限继承规则
- `资源:manage` 自动包含 `资源:view`
- 导航菜单过滤时，`资源:view` 可通过 `资源:manage` 继承

---

## 二、核心数据模型

### Task（任务）
| 字段 | 类型 | 说明 |
|------|------|------|
| id | String(36) | UUID 主键 |
| name | String(255) | 任务名称 |
| status | String(20) | `pending`/`running`/`completed`/`cancelled`/`error` |
| task_type | String(50) | 见 TaskType 枚举 |
| config | Text | 任务配置 JSON（恢复/重启/回填的核心） |
| created_by_user_id | Integer | 创建人 FK → user.id |
| current_step / total_steps | Integer | 进度 |
| error_message | Text | 错误信息（`[NETWORK_RETRYABLE]` 前缀触发看门狗自动重启） |
| start_time / end_time | DateTime | 执行时间 |
| created_at / updated_at | DateTime | 创建/更新时间 |

### TaskLog（任务日志）
| 字段 | 类型 | 说明 |
|------|------|------|
| id | Integer | 自增主键 |
| task_id | String(36) | FK → tasks.id |
| level | String(20) | info/warning/error |
| message | Text | 日志内容 |
| timestamp | DateTime | 日志时间 |

### TaskResult（任务结果）
| 字段 | 类型 | 说明 |
|------|------|------|
| id | Integer | 自增主键 |
| task_id | String(36) | FK → tasks.id |
| step_index | Integer | 步骤序号 |
| parameters | Text | 参数 JSON |
| result | Text | 结果 JSON |
| return_series_id | Integer | FK → task_results_return.id |
| success | Boolean | 是否成功 |
| error_message | Text | 错误信息 |
| timestamp | DateTime | 结果时间 |

### TaskResultReturn（收益时间序列）
| 字段 | 类型 | 说明 |
|------|------|------|
| id | Integer | 自增主键 |
| task_id | String(36) | FK → tasks.id |
| stock_date | String(50) | 日期 |
| index_return | Float | 指数收益 |
| start_return | Float | 策略起始收益 |
| returns_json | Text | 按列存储 `{dates, index_returns, start_returns}` |

### TaskResultSummaryIndex（汇总索引）
| 字段 | 类型 | 说明 |
|------|------|------|
| id | Integer | 自增主键 |
| task_id / task_result_id | FK | 关联任务和结果 |
| task_type | String(50) | 任务类型 |
| stock_code / stock_name | String | 股票信息 |
| model_key / model_name | String | 模型标识 |
| year_label / period_key | String | 年份/区间标签 |
| best_metric_name / best_metric_value | String/Float | 最优指标 |
| metrics_json | Text | 汇总指标 JSON |
| is_best | Boolean | 是否分组最优 |

### GoogleSheetToken（Token 池）
| 字段 | 类型 | 说明 |
|------|------|------|
| id | Integer | 自增主键 |
| name | String(255) | 展示名称 |
| task_type | String(50) | `google_sheet` / `backtest_training` |
| token_file | String(500) | 落地文件路径 |
| token_context | Text | Token JSON 原文 |
| current_in_use_count | Integer | 当前占用次数 |
| max_usage_count | Integer | 最大同时占用（0=不限） |
| is_active | Boolean | 是否启用 |

### GoogleSheet（Sheet 注册表）
| 字段 | 类型 | 说明 |
|------|------|------|
| id | Integer | 自增主键 |
| name | String(255) | 显示名称 |
| spreadsheet_id | String(255) | Google Sheet ID |
| table_type | String(20) | `c3`/`c4`/`c5` |
| is_active | Boolean | 是否启用 |
| is_in_use | Boolean | 是否使用中 |
| current_task_id | String(36) | 当前占用任务 ID |

### ScheduledTask（定时任务）
| 字段 | 类型 | 说明 |
|------|------|------|
| id | Integer | 自增主键 |
| name | String(255) | 任务名称 |
| cron_expression | String(100) | Cron 表达式 |
| task_type | String(50) | 任务类型 |
| task_function | String(255) | 执行函数名 |
| task_params | Text | 参数 JSON |
| is_active | Boolean | 是否启用 |
| last_run_time / next_run_time | DateTime | 上次/下次执行时间 |
| run_count | Integer | 执行次数 |

### SystemConfig（系统配置）
| 字段 | 类型 | 说明 |
|------|------|------|
| key | String(100) | 配置键（唯一） |
| value | Text | 配置值 |
| description | Text | 配置说明 |

### NavigationMenuItem（导航菜单）
| 字段 | 类型 | 说明 |
|------|------|------|
| key | String(100) | 唯一键 |
| label | String(100) | 菜单名称 |
| path | String(255) | 前端路由路径 |
| permission | String(100) | 访问权限编码 |
| parent_key | String(100) | 父级菜单 key |
| sort_order | Integer | 排序值 |
| is_visible | Boolean | 是否显示 |

---

## 三、枚举类型

### TaskStatus
| 值 | 标签 | 说明 |
|-----|------|------|
| `pending` | 待执行 | |
| `running` | 运行中 | |
| `completed` | 已完成 | |
| `cancelled` | 已取消 | |
| `error` | 错误 | |

> 可编辑状态：`pending`、`completed`、`cancelled`、`error`（不含 `running`）

### TaskType
| 值 | 标签 | 说明 |
|-----|------|------|
| `google_sheet` | Google Sheet C3 | C3/C31 共用 |
| `google_sheet_C4` | Google Sheet C4 | |
| `google_sheet_C5` | Google Sheet C5 | |
| `backtest_training` | 单品回测 | |
| `backtest_multi_product` | 多品回测 | |
| `model_summary_rebuild` | 汇总索引重建 | 系统类型，默认不在列表中显示 |

> 别名映射：`google_sheet_c3` → `google_sheet`，`google_sheet_c31` → `google_sheet`，`backtest` → `backtest_training`

### GoogleSheetTableType
`c3` / `c4` / `c5`（C31 规范化为 `c3`）

### GoogleSheetTokenTaskType
`google_sheet` / `backtest_training`

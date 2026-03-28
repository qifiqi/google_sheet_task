# CLAUDE.md
本文件为 Claude Code (claude.ai/code) 在此代码仓库中工作时提供指导。

## 命令

### Windows 编码约定
在 Windows PowerShell 中读取包含中文的文件时，默认编码可能不是 UTF-8，容易导致 `Get-Content` 输出乱码。

- 读取文件时始终显式指定 `-Encoding UTF8`
- 在需要把中文输出到终端前，先设置：

```powershell
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$OutputEncoding = [System.Text.UTF8Encoding]::new($false)
```

- 推荐示例：

```powershell
Get-Content .\run.py -Encoding UTF8 -TotalCount 50
Get-Content .\run.py -Encoding UTF8 | Select-String "应用|乱码|编码"
```

### 运行开发服务器
```bash
python run.py
```

### 使用 gunicorn 运行（生产环境）
```bash
gunicorn -w 4 -b 0.0.0.0:5000 'app:create_app()'
```

### Windows 批处理启动
```bat
start.bat
```

### 安装依赖
```bash
pip install -r requirements.txt
```

### 数据库初始化和迁移
```bash
flask db init # 首次运行时执行
flask db migrate -m "描述信息"
flask db upgrade
```

### 运行测试
```bash
pytest
pytest tests/test_specific.py::test_name # 运行单个测试
```

## 环境配置

复制 `.env.example` 到 `.env` 并设置以下变量：
- `APP_ENV` — `development`（开发环境） / `production`（生产环境）
- `SECRET_KEY` — Flask 密钥
- `DATABASE_URL` — SQLite 或 PostgreSQL URI
- `MAX_CONCURRENT_TASKS` — 并行任务上限
- `TASK_TIMEOUT` — 看门狗终止任务前的超时时间（秒）
- `GOOGLE_CREDENTIALS_PATH` — 服务账号 JSON 文件路径

加载顺序：`.env` → `.env.{APP_ENV}`（后加载的文件会覆盖前面的配置）。

## 架构概览

### 应用工厂
`app/__init__.py` 导出 `create_app()`。它负责注册蓝图，通过 `app/extensions.py` 初始化 SQLAlchemy/Migrate，并作为 `run.py` 和 gunicorn 的入口点。

`run.py` 在 `create_app()` 之后执行启动钩子：架构补丁、令牌池重置、死任务清理、APScheduler 初始化、看门狗线程初始化。

### 路由蓝图
| 模块 | 前缀 | 用途 |
|------|------|------|
| `app/routes/api.py` | `/api` | REST API：任务 CRUD、SSE 流式传输、配置、模板、结果、日志、令牌/表格管理 |
| `app/routes/admin.py` | `/admin` | 管理界面页面 + 仪表盘/运行时详情/调度器的 JSON API |
| `app/routes/`（其他） | 各种 | 其他特定表格类型路由（`google_sheet_c4`、`google_sheet_c5`、`xpl`） |

### 任务执行引擎
`app/services/task_manager.py` — `TaskManager` 单例（`task_manager`）。
- 每个任务在其自己的守护线程中运行；`running_tasks` 字典映射 `task_id → 线程`。
- `task_stop_events` 字典映射 `task_id → threading.Event`，用于实现优雅取消。
- 在启动前获取一个令牌和/或一个 Google Sheet 资源，在完成、取消或出错时释放它们。
- 将进度写入 `TaskLog` 行，并更新 `Task.current_step` / `Task.total_steps`。
- `api.py` 中的 SSE 端点将日志行实时流式传输到浏览器。

### 资源池管理
- **令牌池** — `GoogleSheetToken` 模型；`TokenPoolService`（或 `task_manager` 中的内联逻辑）跟踪 `is_in_use` / `current_task_id`。
- **表格注册表** — `app/services/google_sheet_registry_service.py`；`GoogleSheetRegistryService` 通过 `acquire_for_task` / `release_for_task` 提供基于数据库乐观锁的获取与释放。

### 数据模型 (`app/models.py`)
| 模型 | 关键字段 |
|------|------|
| `Task` | `id`, `task_type`, `status`, `config` (JSON), `current_step`, `total_steps`, `start_time`, `end_time` |
| `TaskLog` | `task_id`, `level`, `message`, `timestamp` |
| `TaskResult` | `task_id`, `step_index`, `success`, `parameters` (JSON), `result` (JSON) |
| `TaskResultReturn` | `task_id`, `stock_date`, `index_return`, `start_return` |
| `TaskTemplate` | 可复用的任务配置预设 |
| `SystemConfig` | 存储在数据库中的键值对应用配置 |
| `GoogleSheetToken` | OAuth 令牌记录，包含 `is_in_use` 锁 |
| `GoogleSheet` | 已注册的电子表格 ID，包含 `is_in_use` / `current_task_id` 锁 |
| `ScheduledTask` | 持久化到数据库的 APScheduler 作业定义 |

### 配置服务
`app/services/config_manager.py` — `get_config_manager()` 合并 `SystemConfig` 数据库行与环境变量覆盖。整个服务的运行时配置值都通过它获取。

### XPL 分析服务
`app/services/xpl_service.py` — `XPLAnalyzer` 类。从 Google Sheets 读取收益率序列（支持 C3/C4/C5 列格式），计算：年化收益率、夏普比率、卡尔玛比率、索提诺比率、最大回撤、相对于指数的超额收益。结果以 `TaskResult` 行存储，键为 `I15`–`I17`。

### Google Sheet 客户端
使用 `gspread` + `google-auth` 服务账号凭据。每个任务使用从池中获取的令牌来实例化其自己的 sheet 客户端。

### 调度器
`app/services/scheduler_service.py` — 封装 APScheduler；将作业持久化到 `ScheduledTask` 表中；暴露异步任务状态跟踪功能，供管理员调度器界面使用。

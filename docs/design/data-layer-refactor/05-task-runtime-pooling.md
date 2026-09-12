# 05 - 任务执行池化与任务类型注册表（P1-2）

> 前置依赖：数据层 B3 完成（`task/runtime.py` 已迁移 repository），避免同一文件双重改造。

## 1. 现状问题（实测）

- `task/runtime.py:548-584`：`if/elif` × 6 硬编码分发 `task_type` → 每个任务一个裸 `threading.Thread`；
- `task/facade.py:32-33`：`running_tasks: dict[str, Thread]`、`task_stop_events: dict[str, Event]` 承载运行态；
- `scheduler_service.py:63,209`：调度延迟执行也是裸线程；
- **无任何并发上限**：任务创建即可启动，理论上可无限并发——直接风险是 Google Sheet token 配额挤兑、东方财富限流、DB 连接池耗尽；
- 新增任务类型需要改 `runtime.py` 的 if/elif 分发 + facade 状态 + 页面，无注册扩展点。

## 2. 目标

1. 线程池化：全局并发上限 + 分任务类型并发上限，全部走 `SystemConfig` 可配置；
2. 任务类型注册表化：新增任务类型只需注册一个 spec，不改分发代码；
3. 断点重启、看门狗活性检查、占用释放、`task_stop_events` 语义完全不变。

## 3. 设计

### 3.1 任务类型注册表（新文件 `app/services/task/registry.py`）

```python
@dataclass(frozen=True)
class TaskTypeSpec:
    type_key: str                      # "google_sheet" / "google_sheet_c4" / ...
    display_name: str
    runner: Callable[[Task], Callable[[], None]]   # 由 Task 生成线程目标函数
    max_concurrency_key: str | None    # 分类型上限的 SystemConfig key；None = 不单独限
    max_concurrency_default: int = 4

GLOBAL_MAX_KEY = "task_max_workers"        # 全局上限，默认 8
GLOBAL_MAX_DEFAULT = 8

TASK_TYPE_REGISTRY: dict[str, TaskTypeSpec] = {
    "google_sheet":          TaskTypeSpec("google_sheet", "C3", runner=_run_google_sheet, "task_concurrency_google_sheet", 4),
    "google_sheet_c4":       TaskTypeSpec(...),
    "google_sheet_c5":       TaskTypeSpec(...),
    "google_sheet_c7":       TaskTypeSpec(...),
    "backtest_training":     TaskTypeSpec(...),
    "backtest_multi_product":TaskTypeSpec(...),
}

def register_task_type(spec: TaskTypeSpec) -> None:  # 新任务类型扩展点
    ...
```

- `runtime.py` 的 if/elif 替换为 `spec = TASK_TYPE_REGISTRY.get(task_type)`；未注册类型 → 不启动，写 `error_message`（可被前端展示）；
- C31 批量拆分逻辑不变：子任务仍是 `google_sheet` 类型，自然获得注册表与上限约束。

### 3.2 池化与并发控制

- facade 持有 `ThreadPoolExecutor(max_workers=全局上限)`，`running_tasks` 值类型 `Thread → Future`；
- **并发上限采用"启动前配额检查"而非依赖线程池队列排队**：调度点先查 `全局运行数 < task_max_workers` 且 `该类型运行数 < 分类型上限`，不满足则任务保持 `pending` 不 submit。理由：排队进池会让任务状态与实际执行脱节，破坏看门狗"pending 不检查、running 无日志才告警"的现有语义；
- 超限不报错、不排队，任务安静等待下次调度/手动启动（现状行为的最小收紧）；
- `task_stop_events` 机制保留：取消走 event 置位；`future.cancel()` 仅对尚未启动的任务生效，作为补充。

### 3.3 兼容改造点（逐一清单化）

| 现有调用 | 改造 |
|---|---|
| `facade.is_task_running` / 线程活性判断 | `Thread.is_alive()` → `not future.done()` |
| `restart.py` 取消后判断线程退出 | 同上 |
| `task_watchdog.py` running 活性 | 不依赖线程对象，仅看日志时间（现状已如此，确认即可） |
| `scheduler_service.py` 裸线程 | 改走统一调度入口（配额检查 + submit） |
| `runtime.py:549-584` 六处 `threading.Thread(...)` | 删除，由 spec.runner + submit 取代 |

### 3.4 配置项

| SystemConfig key | 默认 | 说明 |
|---|---|---|
| `task_max_workers` | 8 | 全局并发上限 |
| `task_concurrency_google_sheet` | 4 | 分类型示例（C3/C4/C5/C7 各自独立 key） |

不设 `task_pool_enabled` 之类灰度/回退开关：池化为**单一路径**，不保留裸线程回退分支（无兼容层总原则）。

配置读取统一走 `config_manager.get_config`（bool 用 `coerce_bool`）；变更后下个调度周期生效，不做运行时热重建线程池。

## 4. 实施顺序（每步独立 commit + pytest + 冒烟）

1. 注册表化：if/elif → registry，行为完全不变；
2. 全局池 + `task_max_workers` 上限（单一路径，不保留裸线程回退分支）；
3. 分类型并发上限；
4. scheduler 调度入口统一 + 收尾。

## 5. 验收

- 并发压测：一次性创建 N>上限 的任务，确认只有上限内进入 running，其余保持 pending，随任务完成逐个启动；
- 取消/重启/看门狗三场景冒烟通过；
- 收尾检查：`task/runtime.py` 内 `threading.Thread` 分发残留为 0（单一路径，无回退分支）。

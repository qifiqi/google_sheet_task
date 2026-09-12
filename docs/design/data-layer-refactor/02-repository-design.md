# 02 - 数据层详细设计

> 异常体系不在本文件：统一异常收敛到 `app/exceptions/`（单一体系），见 `04-exception-response-design.md` §3。
> 方法契约以**现有调用点为基准**归纳；执行替换时若发现调用点有出入，以调用点为契约反向补齐 repository 方法，不得改调用点行为。

## 1. `base.py` 通用约定

```python
# app/repositories/base.py
from contextlib import contextmanager
from app.extensions import db


class BaseRepository:
    model = None  # 子类指定对应模型类

    @contextmanager
    def transaction(self):
        """多步原子流程：调用方在各写方法传 commit=False，由此上下文统一提交/回滚。"""
        try:
            yield
            db.session.commit()
        except Exception:
            db.session.rollback()
            raise

    def _commit(self): db.session.commit()
    def _rollback(self): db.session.rollback()

    def get_entity(self, pk):
        """返回 ORM 实例（不 commit）。任务执行域（runtime/runner 线程目标）的正式实体访问方法，长期保留；其余场景一律使用 dict 返回方法。"""
        return db.session.get(self.model, pk) if self.model else None
```

**通用规则：**

1. 所有写方法签名带 `commit: bool = True`；默认方法内提交（保持现状粒度），异常 `_rollback()` 后原样 `raise`；
2. 读方法一律不 commit；
3. 返回 JSON 兼容结构（`to_dict()` / `with_entities` 投影）；`get_*` 不存在返回 `None`，`get_required_*` 抛 `NotFoundError`；
4. repository 内禁止 import `app.services` / `app.routes` / Flask；
5. 跨 repository 原子流程在 service/route 层组合：`with repo_a.transaction(): repo_b.update_x(commit=False); repo_a.update_y(commit=False)`（唯一已知场景：`auth_api` 删用户同事务清 `user_roles` + `Task.created_by_user_id`）；
6. **无兼容入口**：不提供过渡别名、双入口或回退开关，每个能力只有一个方法入口（与 README"无兼容层"总原则一致）。

## 2. 各 repository 方法契约

### 2.1 `task_repository.py` — Task

| 方法 | 返回 | commit | 说明 |
|---|---|---|---|
| `get(task_id)` | `dict\|None` | 否 | |
| `get_required(task_id)` | `dict` | 否 | 不存在抛 `NotFoundError` |
| `get_entity(task_id)` | `Task\|None` | 否 | 任务执行域实体访问（B3 runtime/线程目标，正式契约长期保留）；admin.py `db.session.get` 视消费方式选 `get`（dict） |
| `list_all(task_type=None, task_types=None)` | `list[dict]` | 否 | 按 `created_at desc` |
| `list_paginated(page, per_page, task_type=None, status=None, keyword=None)` | `{items,total,pages,current_page,per_page}` | 否 | |
| `count()` / `count_by_status(status)` | `int` | 否 | admin 仪表盘 |
| `summary_counts()` | `{total,completed,running,error}` | 否 | admin.py:23-26 四连 count 合并 |
| `recent(limit=10)` | `list[dict]` | 否 | admin.py:29 |
| `distinct_task_types()` | `list[str]` | 否 | task_api.py:51 |
| `list_by_ids(ids)` | `list[dict]` | 否 | task_api.py:355 |
| `create(fields)` | `dict` | 是 | 替代 `safe_create` |
| `update_fields(task_id, **fields, commit=True)` | `dict\|None` | 参数 | 替代 `safe_update` |
| `clear_created_by(user_id, commit=False)` | `int` | 参数 | auth_api 删用户置空引用 |
| `delete(task_id, commit=True)` | `bool` | 参数 | |

### 2.2 `task_result_repository.py` — TaskResult / TaskResultReturn

| 方法 | 返回 | commit | 说明 |
|---|---|---|---|
| `get(result_id)` | `dict\|None` | 否 | |
| `get_with_task_type(result_id)` | `dict\|None`（含 `task_type` 键） | 否 | template_api get_result/delete_result |
| `list_by_task(task_id)` | `list[dict]` | 否 | |
| `list_by_task_paginated(task_id, page, per_page)` | 分页结构 + `{total_success,total_failed}` | 否 | task_api results 分页 |
| `list_paginated(task_id=None, page, per_page)` | `{results,total,pages,current_page}` | 否 | 迁移后 result_api `/api/results`（保持现有 load_only 精简键） |
| `count_by_task_success(task_id)` | `{success, failed}` | 否 | |
| `create(fields)` / `bulk_create(rows)` | `dict` / `int` | 是 | |
| `get_returns(result_id)` / `get_returns_by_task(task_id)` | `list[dict]` | 否 | TaskResultReturn |
| `create_return(fields)` / `bulk_create_returns(rows)` | `dict` / `int` | 是 | |
| `delete(result_id)` / `delete_by_task(task_id)` | `bool` / `int` | 是 | |
| `delete_returns_by_task(task_id)` / `delete_older_than(cutoff)` | `int` | 是 | data_cleanup，窗口条件压 SQL 层 |

### 2.3 `task_log_repository.py` — TaskLog

| 方法 | 返回 | commit | 说明 |
|---|---|---|---|
| `add(task_id, level, message, **fields)` | `dict` | 是 | **热路径**（执行链每步写日志） |
| `get_last(task_id)` | `dict\|None` | 否 | 看门狗活性检查 |
| `list_by_task_paginated(task_id, page, per_page, level=None)` | 分页结构 | 否 | |
| `count_by_task(task_id)` | `int` | 否 | |
| `delete_by_task(task_id)` / `delete_older_than(cutoff)` | `int` | 是 | data_cleanup |

### 2.4 `task_template_repository.py` — TaskTemplate

`list_all(task_type=None)`（保持现有"解析 config JSON 后按 `config.task_type` 过滤"的 Python 端语义）、`get` / `get_required` / `create(name, description, config_str)` / `update(template_id, fields)` / `delete(template_id)`。

### 2.5 `system_config_repository.py` — SystemConfig

| 方法 | 说明 |
|---|---|
| `get_row(key)` | 返回 `{key,value,description,...}`，**value 保持入库原样字符串**；JSON 解析/bool 还原逻辑留在 `config_manager`（负缓存语义不动） |
| `list_rows()` | 按 `key asc`（config_api 管理端） |
| `list_key_descriptions()` | `[{key, description}]`（config.py 启动期读取，暂保留原处） |
| `upsert(key, value, description=None, commit=True)` | 写入；**调用方负责走 `set_config`/`update_configs` 或刷新缓存** |
| `delete(key, commit=True)` | |

### 2.6 `navigation_repository.py` — NavigationMenuItem

`list_all()` / `get(item_id)` / `get_by_key(key)` / `exists_key(key)` / `count_children(key)` / `create(fields)`（保留 flush 取 id 语义）/ `update(item_id, fields)` / `delete(item_id)`。

### 2.7 `rbac_repository.py` — User / Role / Permission / 关联表

| 方法 | 说明 |
|---|---|
| `get_user(user_id)` / `get_user_by_username(username)` | dict 含 roles |
| `list_users()` / `list_roles()` / `list_permissions()` | permissions 按 `group, code` 排序（auth_api:276） |
| `create_user(username, password_hash, role_ids=None, **fields)` | 关联角色同一事务 |
| `update_user(user_id, fields, role_ids=None)` | |
| `delete_user(user_id, commit=True)` | 清 `user_roles` 关联；`Task.created_by_user_id` 由调用方用 `task_repository.clear_created_by` 组合进同一 `transaction()` |
| `role_code_exists(code)` | |
| `create_role(code, name, permission_ids=None)` / `update_role(role_id, fields, permission_ids=None)` / `delete_role(role_id, commit=True)` | delete 清 `role_permissions` + `user_roles`（auth_api:262-263 语义） |
| `list_permission_codes()` | `list[str]`，auth.py 热路径（缓存仍留在 auth 层） |

### 2.8 `google_sheet_repository.py` — GoogleSheet

`list_all(table_type=None, scope=None)` / `get` / `get_required` / `create` / `update` / `delete`；registry scope 过滤与占用查询方法在 B2/B3 按 `google_sheet_registry_service`、`task/occupancy.py` 调用点定形后补入本契约。

### 2.9 `google_sheet_token_repository.py` — GoogleSheetToken

`list_all(include_context=True)` / `get` / `get_required` / `create` / `update` / `delete` / `bulk_import(rows)`；可用性筛选、状态流转方法在 B2 按 `google_sheet_token_service` 调用点定形后补入。

### 2.10 `scheduled_task_repository.py` — ScheduledTask

| 方法 | 说明 |
|---|---|
| `count()` / `count_active()` | scheduler_api stats |
| `list_paginated(page, per_page)` / `list_all()` | `created_at desc` |
| `get(task_id)` / `get_required(task_id)` | **替代 `get_or_404`**（HTTP 语义不进数据层） |
| `create(fields)` / `update(task_id, fields)` / `delete(task_id)` | |
| `find_due(now)` | scheduler_service 到期扫描 |
| `stats()` | 聚合 |

### 2.11 `stock_metadata_repository.py` — StockMetadata

`get(stock_code)` / `upsert(stock_code, **fields)`（替代 `safe_create`）/ `bulk_upsert(rows)` / `count()`。

### 2.12 `backtest_repository.py` — TaskResultSummaryIndex / BacktestProductResultCache / BacktestSheetRunLock

| 方法 | 说明 |
|---|---|
| `get_summary_index(task_id)` / `upsert_summary_index(task_id, **fields)` / `delete_summary_index(task_id)` | model_summary / restart / cleanup |
| `get_product_cache(...)` / `upsert_product_cache(...)` / `delete_product_cache_by_task(task_id)` | backtest_multi_product_service |
| `get_lock(sheet_id)` / `acquire_lock(sheet_id, task_id)` / `release_lock(sheet_id, task_id)` | **acquire/release 原子性红线**（B3 按 runtime.py/occupancy.py 现有语义定形） |

## 3. `__init__.py` 导出

模块级单例：`task_repository = TaskRepository()` 等全部导出，调用方 `from app.repositories import task_repository`。

## 4. 测试约定

- 新增 `tests/unit/test_repositories.py`：内存 SQLite + app context，覆盖各 repository 基础读写与异常路径；
- 每个批次替换完成后，该批次相关既有测试（unit/integration）必须全绿；
- repository 层测试允许直接断言 ORM 行为（测试代码不受"禁止 ORM"约束）。

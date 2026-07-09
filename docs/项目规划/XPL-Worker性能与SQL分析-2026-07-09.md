# XPL Worker 性能与 SQL 分析

日期：2026-07-09

## 结论

当前异步 XPL 的主要优化方向不是继续把 Flask 任务线程变复杂，而是把 XPL 后处理从 C 系列任务主链路中拆出去，让主任务只负责：

1. 获取 Google Sheet 参数结果。
2. 读取并保存收益序列快照。
3. 创建 XPL 分析 job。
4. 继续执行下一个参数组合。

Worker 负责异步 claim job、读取收益序列、执行 XPL、写回结果、刷新汇总索引、推送外部结果。

但是当前 worker 仍然依赖 Flask `create_app()`、`app.app_context()`、`db.session`、ORM Model 和 C3 `GoogleSheetService`。这让它更像“另一个 Flask 后台线程入口”，还不是独立小服务。后续应把 worker 改成独立服务，通过统一接口访问任务平台。

## 是否改成调用任务平台接口

建议改成调用任务平台接口，但要分清控制面和数据面。

控制面建议走接口：

- claim 一批待处理 job。
- 标记 job running / completed / retrying / error。
- 写任务日志。
- 查询任务、任务结果、配置摘要。
- 触发汇总索引刷新。
- 触发 StockParamResult 外部推送，或由平台内部完成推送。

数据面可以有两种选择：

- 收益序列数据量不大时，接口直接返回压缩后的收益序列或解压后的 rows。
- 收益序列数据量变大时，接口只返回数据指针，worker 读取本地归档文件或对象存储文件。

推荐方案是“接口优先，数据指针可选”。这样 worker 不需要知道 Flask ORM、数据库 schema 细节，也不用导入 `app.models`。任务平台保留数据一致性和权限边界，worker 只做计算。

不建议让 worker 继续直接复用 app 的 SQLAlchemy 对象。原因：

- worker 不是 Flask 请求或 Flask 任务线程，不应该依赖 app context 生命周期。
- 独立窗口启动时，错误边界、日志和配置加载都应独立。
- ORM Model 变化会直接影响 worker 发布，耦合太深。
- worker 内部直接调用 C3 `GoogleSheetService` 会阻塞 C4/C5 统一异步。

## 当前链路问题

当前 worker 入口：

- `scripts/run_xpl_analysis_worker.py` 导入 `create_app()`。
- 启动后进入 `app.app_context()`。
- 配置读取依赖 `get_config_manager()`。

当前 worker 执行：

- `app/services/xpl_analysis_worker.py` 直接使用 `db.session.get(...)`。
- 直接导入 `Task`、`TaskLog`、`TaskResult`、`TaskResultReturn`、`XplAnalysisJob`。
- `_push_stock_param_result()` 直接导入 C3 `GoogleSheetService`。
- 当前 executor 使用 `ThreadPoolExecutor`，虽然文件里也导入了 `ProcessPoolExecutor`。

这些问题导致：

- worker 难以独立部署、独立测试。
- C4/C5 结果推送容易走错 C3 payload 构造逻辑。
- CPU 型 XPL 计算用线程池可能被 GIL 限制。
- 数据库事务边界分散在多个 service 和 ORM session 中，不利于做原子 claim。

## 性能空间

### 1. 主任务链路收益

异步后，C 系列任务主链路可以从：

```text
写入参数 -> 固定等待 -> 读取结果 -> 读取收益序列 -> XPL计算 -> 保存结果 -> 推送 -> 下一个参数
```

变成：

```text
写入参数 -> 固定等待 -> 读取结果 -> 读取收益序列 -> 保存基础结果+创建job -> 下一个参数
```

固定等待 20 秒不处理的前提下，优化收益主要来自移除每个参数组合中的 XPL 计算时间、外部推送时间和一部分结果写入压力。

从生产日志看，阶段一后：

- 收益序列读取通常约 `0.35s - 0.57s`。
- XPL 计算常见约 `0.27s - 1.60s`，曾出现 `3.9s`，历史还有 `7s - 8s`。
- 保存和推送约 `0.04s - 0.06s`。

如果同步执行，每个参数组合仍会被 XPL 计算串行拖慢。异步后主任务吞吐更接近 Google Sheet 固定等待和读取速度。

### 2. Worker 计算吞吐

如果 XPL 是 CPU 密集型，Python 多线程不能稳定提升吞吐，应该使用多进程。

推荐：

- `XPL_EXECUTOR=process` 作为生产默认。
- `XPL_WORKER_PROCESSES` 不超过 CPU 核心数或核心数减一。
- `XPL_CLAIM_BATCH_SIZE` 约等于进程数的 `2 - 4` 倍。
- IO 阶段可以用线程，XPL 计算阶段用进程。

如果 XPL 内部主要调用 NumPy/Pandas 且释放 GIL，线程可能有收益，但需要用基准测试确认。不能只看单次日志判断。

### 3. 收益序列读取

当前收益序列存储在 `TaskResultReturn.returns_json`。后续如果按任务完成后统一压缩到本地文件，并让数据库只存路径，会减少数据库体积和备份压力。

建议存储策略：

- 任务执行中：数据库保存 `data/index/start` 三列 list JSON，或保存结构化 `returns_json`。
- 任务完成后：统一归档压缩为 `.json.gz`。
- 数据库保留 `archive_path`、`archive_format`、`row_count`、`checksum`。
- Worker 读取时优先通过平台接口获取 rows 或获取归档路径。

注意：如果 worker 独立部署到另一台机器，本地路径必须是共享路径或对象存储路径，否则 worker 无法读取。

## SQL 处理分析

### 当前 claim 方式

当前 `XplAnalysisJobService.claim_jobs()` 大致流程是：

1. `recover_stale_running()` 先把超时 running 改成 retrying。
2. 查询 pending/retrying 候选 job。
3. 对每个候选 job 单独 update 成 running。
4. 再按 id 读取 claimed job。

这个方式可以工作，但有几个问题：

- SQL 往返次数较多。
- 多 worker 并发时依赖逐条 update 抢锁，效率一般。
- `recover_stale_running()` 需要 `(status, locked_at)` 索引，否则 running job 多时会慢。
- claim 和读取 job 不是一个紧凑的数据库原子操作。

### 推荐原子 claim SQL

PostgreSQL 推荐用 `FOR UPDATE SKIP LOCKED`：

```sql
WITH picked AS (
    SELECT id
    FROM xpl_analysis_jobs
    WHERE status IN ('pending', 'retrying')
    ORDER BY created_at ASC, id ASC
    FOR UPDATE SKIP LOCKED
    LIMIT :limit
)
UPDATE xpl_analysis_jobs AS j
SET
    status = 'running',
    attempts = attempts + 1,
    locked_by = :worker_id,
    locked_at = NOW(),
    started_at = COALESCE(started_at, NOW()),
    updated_at = NOW(),
    error_message = NULL
FROM picked
WHERE j.id = picked.id
RETURNING
    j.id,
    j.task_id,
    j.task_result_id,
    j.return_series_id,
    j.attempts,
    j.max_attempts;
```

优点：

- 一条 SQL 完成选取、加锁、状态更新、返回 job。
- 多 worker 并发时天然跳过已锁记录。
- 避免 Python 层逐条抢占。

### 推荐 stale 恢复 SQL

```sql
UPDATE xpl_analysis_jobs
SET
    status = 'retrying',
    locked_by = NULL,
    locked_at = NULL,
    error_message = 'running job stale, recovered for retry',
    updated_at = NOW()
WHERE status = 'running'
  AND locked_at < NOW() - (:stale_after_seconds * INTERVAL '1 second')
  AND attempts < max_attempts;
```

超过最大次数的 running job 应进入 `error`，避免无限重试：

```sql
UPDATE xpl_analysis_jobs
SET
    status = 'error',
    locked_by = NULL,
    locked_at = NULL,
    finished_at = NOW(),
    error_message = 'running job stale and max attempts reached',
    updated_at = NOW()
WHERE status = 'running'
  AND locked_at < NOW() - (:stale_after_seconds * INTERVAL '1 second')
  AND attempts >= max_attempts;
```

### 推荐索引

现有 SQL 已有：

- `idx_xpl_jobs_status_created(status, created_at)`
- `idx_xpl_jobs_task_status(task_id, status)`
- `ix_xpl_analysis_jobs_return_series_id(return_series_id)`

建议补充：

```sql
CREATE INDEX IF NOT EXISTS idx_xpl_jobs_status_locked_at
    ON xpl_analysis_jobs (status, locked_at);

CREATE INDEX IF NOT EXISTS idx_xpl_jobs_status_created_id
    ON xpl_analysis_jobs (status, created_at, id);
```

如果 PostgreSQL 版本和数据量允许，可以使用 partial index：

```sql
CREATE INDEX IF NOT EXISTS idx_xpl_jobs_claimable_created_id
    ON xpl_analysis_jobs (created_at, id)
    WHERE status IN ('pending', 'retrying');

CREATE INDEX IF NOT EXISTS idx_xpl_jobs_running_locked_at
    ON xpl_analysis_jobs (locked_at)
    WHERE status = 'running';
```

### 批量读取

claim 返回一批 job 后，不建议每个 job 单独查询 `task_results_return`。可以批量读取：

```sql
SELECT id, returns_json
FROM task_results_return
WHERE id = ANY(:return_series_ids);
```

如果平台接口返回 claim job 时直接带 `returns_payload` 或 `archive_path`，worker 甚至不需要再查收益表。

### 完成写回

完成写回应保持幂等：

- 只有 `running` 且 `locked_by = worker_id` 的 job 才能 completed。
- 写回 `task_results.result` 时保留原基础结果，只合并 XPL 字段。
- `analysis_status` 从 `pending/running` 改为 `completed`。
- 汇总索引刷新可以放在平台接口内部，worker 只调用 `complete_job`。

示例约束：

```sql
UPDATE xpl_analysis_jobs
SET status = 'completed',
    finished_at = NOW(),
    locked_by = NULL,
    locked_at = NULL,
    updated_at = NOW()
WHERE id = :job_id
  AND status = 'running'
  AND locked_by = :worker_id;
```

## 推荐性能指标

Worker 每个批次应输出结构化指标：

- `claim_count`
- `claim_elapsed`
- `load_return_elapsed`
- `compute_elapsed`
- `save_elapsed`
- `push_elapsed`
- `completed_count`
- `failed_count`
- `retry_count`

Job 表可以统计：

- pending 数量。
- running 数量。
- error 数量。
- 最老 pending 等待时间。
- 平均 XPL 计算耗时。
- p95 XPL 计算耗时。

## 风险点

1. 只用线程池可能无法解决 CPU 瓶颈。
2. worker 直接读本地压缩文件时，必须保证路径对 worker 可见。
3. worker 直接推送外部接口会扩大失败面，建议平台接口内部统一处理推送或提供单独 push API。
4. C4/C5 不能继续复用 C3 `GoogleSheetService` 的 payload 构造。
5. 数据库 JSON 过大时，会影响查询、备份和 VACUUM，任务完成后归档是正确方向。


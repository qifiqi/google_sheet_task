# XPL Worker 小服务化变更说明

日期：2026-07-09

## 目标

把 XPL worker 从 Flask 应用内部实现中拆出来，作为独立小服务运行。

目标边界：

- worker 不导入 `app.create_app`。
- worker 不使用 `app.app_context()`。
- worker 不使用 Flask-SQLAlchemy 的 `db.session`。
- worker 不直接导入 `app.models`。
- worker 不直接调用 C3/C4/C5 service。
- worker 通过统一接口类访问任务平台。

任务平台继续负责任务创建、任务结果保存、job 状态机、汇总索引、权限和外部推送。worker 只负责 XPL 计算编排。

## 推荐目录

新增独立目录：

```text
xpl_worker/
  __init__.py
  main.py
  config.py
  interfaces.py
  platform_client.py
  processor.py
  runner.py
  models.py
  logging_config.py
```

职责：

- `main.py`：命令行入口，解析参数，启动 worker。
- `config.py`：读取环境变量和 `.env.worker`。
- `interfaces.py`：定义统一接口类和 DTO。
- `platform_client.py`：任务平台 HTTP API 客户端实现。
- `processor.py`：单个 job 的处理流程。
- `runner.py`：循环 claim、并发调度、退出控制。
- `models.py`：worker 内部 DTO，不是数据库 ORM Model。
- `logging_config.py`：独立日志配置。

`scripts/run_xpl_analysis_worker.py` 可以保留为兼容薄壳，但最终只调用：

```python
from xpl_worker.main import main

if __name__ == "__main__":
    main()
```

`run_worker.bat` 改为：

```bat
.venv\Scripts\python.exe -m xpl_worker.main
```

## 统一接口类

worker 内部只依赖接口，不关心底层是 HTTP、SQLAlchemy Core 还是测试 fake。

```python
class XplWorkerPlatformPort:
    def claim_jobs(self, worker_id: str, limit: int, stale_after_seconds: int) -> list[XplJobDTO]:
        ...

    def get_return_series(self, return_series_id: int) -> ReturnSeriesDTO:
        ...

    def complete_job(
        self,
        job_id: int,
        worker_id: str,
        flat_result: dict,
        analyze_result: dict,
        elapsed_seconds: float,
    ) -> None:
        ...

    def fail_job(self, job_id: int, worker_id: str, error_message: str, retryable: bool = True) -> None:
        ...

    def append_task_log(self, task_id: str, level: str, message: str) -> None:
        ...
```

如果外部推送仍由 worker 触发，单独放接口：

```python
class XplWorkerPushPort:
    def push_result(self, job_id: int, worker_id: str) -> None:
        ...
```

更推荐平台在 `complete_job` 内部完成汇总索引刷新和外部推送，worker 不直接理解 C3/C4/C5 的 payload。

## 平台接口建议

新增内部 API，建议只允许本机或内网访问，并使用 worker token。

### claim job

```text
POST /api/internal/xpl-worker/jobs/claim
```

请求：

```json
{
  "worker_id": "host-1234",
  "limit": 8,
  "stale_after_seconds": 300
}
```

响应：

```json
{
  "jobs": [
    {
      "id": 1,
      "task_id": "uuid",
      "task_result_id": 100,
      "return_series_id": 200,
      "attempts": 1,
      "max_attempts": 3
    }
  ]
}
```

### 获取收益序列

```text
GET /api/internal/xpl-worker/return-series/{return_series_id}
```

响应可以是 rows：

```json
{
  "id": 200,
  "row_count": 725,
  "format": "rows",
  "rows": []
}
```

也可以是归档指针：

```json
{
  "id": 200,
  "row_count": 725,
  "format": "archive",
  "archive_path": "data/return_archives/task_xxx.json.gz",
  "checksum": "sha256:..."
}
```

### 完成 job

```text
POST /api/internal/xpl-worker/jobs/{job_id}/complete
```

请求：

```json
{
  "worker_id": "host-1234",
  "elapsed_seconds": 0.812,
  "flat_result": {},
  "analyze_result": {}
}
```

平台内部处理：

- 校验 job 是否 running 且 locked_by 匹配。
- 合并写入 `TaskResult.result`。
- 更新 `xpl_analysis_jobs`。
- 刷新汇总索引。
- 写任务日志。
- 按任务类型执行外部推送。

### 失败 job

```text
POST /api/internal/xpl-worker/jobs/{job_id}/fail
```

请求：

```json
{
  "worker_id": "host-1234",
  "error_message": "return series is empty",
  "retryable": true
}
```

平台内部根据 attempts / max_attempts 决定 `retrying` 或 `error`。

## 为什么接口模式更适合

接口模式的优点：

- worker 与 Flask 内部实现解耦。
- C3/C4/C5 差异由平台内部处理，worker 不需要知道任务类型细节。
- SQL 事务集中在任务平台，避免 worker 和 app 同时写同一批表产生隐藏不一致。
- 后续 worker 可以独立发版、独立日志、独立窗口运行。
- 测试可以用 fake platform client，不需要启动 Flask app context。

接口模式的代价：

- 多一次 HTTP 调用开销。
- 平台需要新增内部 API 和 worker token。
- 大收益序列直接走 HTTP 会增加序列化成本。

综合看，XPL 单次计算通常是百毫秒到数秒，HTTP 内网开销相对可接受。收益序列如果只有几百到几千行，也可以先通过接口传输。等数据变大后，再切到归档指针。

## 不推荐的方案

不推荐 worker 直接使用 app 的 `db.session` 和 ORM。

不推荐 worker 直接复用 `GoogleSheetService`、`GoogleSheetServiceC4`、`GoogleSheetServiceC5`。

不推荐 worker 自己拼接 C 系列 payload 并推送外部接口。

不推荐 worker 启动时自动执行 schema 修补。数据库变更应通过 SQL 文件或迁移脚本显式执行。

## 阶段计划

### 阶段一：补齐平台内部接口

修改范围：

- 新增内部 worker API 蓝图。
- 把 `XplAnalysisJobService` 中的 claim、complete、fail 封装成接口调用入口。
- complete 接口内部统一刷新汇总索引和外部推送。
- 增加 worker token 校验。

验证方式：

- 用 curl 调 claim/complete/fail。
- 构造一个 pending job，确认能变为 running/completed。
- 确认非 worker token 不能访问内部接口。

### 阶段二：新增 `xpl_worker/` 小服务

修改范围：

- 新建 `xpl_worker` 目录。
- 实现 `XplWorkerPlatformPort`。
- 实现 HTTP client。
- 实现 runner 和 processor。
- 默认使用 `ProcessPoolExecutor` 执行 XPL。

验证方式：

- `python -m xpl_worker.main --once` 可以处理一批 job。
- 搜索 `xpl_worker/`，确认没有 `create_app`、`app_context`、`db.session`、`app.models`。
- worker 失败时 job 进入 retrying 或 error。

### 阶段三：替换旧 worker 入口

修改范围：

- `run_worker.bat` 指向 `python -m xpl_worker.main`。
- `scripts/run_xpl_analysis_worker.py` 改成兼容薄壳。
- 旧 `app/services/xpl_analysis_worker.py` 标记为废弃或删除，避免双入口混用。

验证方式：

- 主 `run.bat` 只启动 Flask。
- `run_worker.bat` 独立窗口启动 worker，能看到日志。
- 关闭 `XPL_WORKER_ENABLED` 时，C 系列任务仍按同步逻辑实时计算 XPL。

### 阶段四：C 系列统一接入

修改范围：

- C3/C4/C5 使用同一套“保存收益序列 + 创建 job + 标记 analysis_status”的逻辑。
- C4/C5 不复用 C3 payload 构造。
- 任务完成时，如果存在未完成 XPL job，汇总索引刷新延后或增量刷新。

验证方式：

- C3/C4/C5 各跑一个小任务。
- 每个 `TaskResult` 有唯一 `XplAnalysisJob`。
- `Task : XplAnalysisJob = 1:N`。
- `TaskResult : XplAnalysisJob = 1:1`。
- 汇总页最终能查到完整 XPL 指标。

### 阶段五：收益数据归档

修改范围：

- 任务执行中保留收益序列在数据库。
- 任务完成后统一压缩归档到本地或对象存储。
- 数据库只保留路径、格式、行数、checksum。
- 平台接口按需返回 rows 或 archive pointer。

验证方式：

- 压缩前后 XPL 结果一致。
- 归档文件缺失时接口返回明确错误。
- 删除任务时能清理对应归档文件或标记孤儿文件。

## 验收标准

1. worker 可独立启动，不依赖 Flask app context。
2. `xpl_worker/` 下没有 Flask ORM 依赖。
3. worker 和任务平台之间通过统一接口类通信。
4. job claim 使用数据库原子 claim，支持多 worker 并发。
5. XPL CPU 瓶颈时可使用多进程。
6. C3/C4/C5 后处理入口一致。
7. 数据库 schema 变更只通过 SQL/迁移文件执行。
8. 任务结果、任务日志、汇总索引、外部推送与原同步逻辑保持一致。


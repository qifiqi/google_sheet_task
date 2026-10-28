# 远端增量端点需求清单（DY.Stock.Api）

> 2026-10-02。依据：[README](README.md) §6.1/§6.2（能力缺口）与 §8.2（端点建议）。
> 本文是给远端（DY.Stock.Api）的接口需求规格：命名对齐现有控制器约定
> （`POST /api/<Controller>/<Action>`，统一信封 `ret_code/ret_obj/ret_count`，布尔 0/1 编码）。
> 本仓库侧消费方均为 `app/repositories/http_backend/` 孪生仓储（落地时同步替换退化策略并消除对应
> `TODO(db-to-http)` 标记）。

## 与 Redis 裁决层的分工

- **Redis 裁决层**（本仓库自建，见 §8.1）：解决"进程间互斥与竞态窗口"——同一部署内多 worker
  抢锁/状态机/占用的串行化；不依赖远端改造，先行落地。
- **远端 CAS 端点**（本文 E1）：解决"数据层原子性"——条件更新在存储侧一步完成，跨副本/跨部署
  都成立。E1 落地后 Redis 只保留长周期互斥（回测锁 + 续期）与启动期锁命名空间清理，两者互补。

## P0：正确性（消除读-改-写竞态与逐行退化）

### E1 条件更新（CAS）

```
POST /api/ParamTasks/UpdateIfMatch        # 建议每表同构：/api/ParamGoogleSheets/UpdateIfMatch 等
```

- 请求：`{"id": "...", "expect": {"status": 2}, "patch": {"status": 3, "start_time": "..."}}`
  （`expect` 为条件字段当前值，`patch` 为满足条件时要写入的字段）
- 响应：`ret_obj = {"updated": 1}`（0=条件不满足，**不是错误**，ret_code 仍 200）
- 消费方（替换现行"读-改-写+复核"退化）：

| 本仓库方法 | expect | patch |
|---|---|---|
| `task_repository.mark_running_if_pending` | `status=pending` | `status=running` |
| `task_repository.mark_running_if_not_running` | `status!=running`（需支持 expect_not 或拆两次调用） | `status=running` |
| `task_repository.revert_running_to_pending` | `status=running` | `status=pending` |
| `google_sheet_repository.occupy` | `occupied_by=null` | `occupied_by=<task_id>` |
| `google_sheet_repository.release_by_task` | `occupied_by=<task_id>` | `occupied_by=null` |
| `scheduled_task_repository.acquire_run_lock` | 锁字段空闲 | 写锁持有者+时间戳 |
| `backtest_repository.acquire_lock`（Redis 兜底外的落库态） | 空闲 | 持有者 |

### E2 按任务批量删除

```
POST /api/ParamTaskResults/DeleteByTaskIds    # ParamTaskLogs / ParamTaskResultsReturn 同构
```

- 请求：`{"task_ids": ["t1", "t2"]}`；响应：`ret_obj = {"deleted": 57}`
- 消费方：`*_repository.delete_by_task`（现状逐 id N 次调用 → 1 次）、
  `delete_older_than`（配合 E7 时间窗删除）、任务删除级联清理（results+returns+logs 三连）
- 附：`/DeleteByTimeWindow`（`{"before": "2026-01-01T00:00:00", "limit": 5000}`）替代
  logs 清理的"timestamp 升序扫描提前终止"退化。

### E3 批量 ids 查询

```
POST /api/ParamTasks/GetByIds
```

- 请求：`{"ids": ["t1", "t2", "t3"]}`（**单页全量**，不走分页）；响应：`ret_obj = [记录数组]`
- 消费方：`task_repository.list_by_ids`、`task_result_repository.list_return_entities(ids)`、
  `delete_by_ids` 的前置读取、C31 批量子任务创建后的批量回查

### E4 跨表原子写入 + 主键回链

```
POST /api/ParamTaskResults/CreateWithReturn
```

- 请求：`{"result": {结果行字段}, "return": {收益序列行字段, 可空}}`
- 响应：`ret_obj = {"result_id": 123, "return_id": 456}`
- 消费方：`task_result_repository.create_with_return`（现状"先写 return 再查最新行回链"，
  依赖同任务串行写入前提；E4 后该前提不再必要）
- 语义：两行同事务，任一失败整体回滚（ret_code != 200）

## P1：性能（消除全量扫描本地处理）

### E5 聚合统计

```
POST /api/ParamTasks/Aggregate
```

- 请求：
  ```json
  {
    "filters": {"statuses": [2], "created_from": "2026-09-01T00:00:00"},
    "group_by": ["status", "task_type", "date:created_at"],
    "aggregates": [{"op": "count"}, {"op": "avg", "field": "duration_seconds"}]
  }
  ```
- 响应：`ret_obj = [{"status": 2, "task_type": "c3", "count": 120, "avg_duration_seconds": 84.2}, ...]`
- 消费方：`count_grouped_by_status/type`、`count_daily_created_*`（逐状态逐日 N 次查询 → 1 次）、
  `list_paginated_with_statistics`（扫描全部 completed 任务算时长 → avg 聚合）

### E6 join 查询（task × result）

```
POST /api/ParamTaskResults/QueryWithTask
```

- 请求：任务侧过滤（`task_type`/`created_from`/`task_name` 模糊）+ 结果侧分页与排序
- 响应：`ret_obj = [结果行（可带 fields 投影）]`，`ret_count = 总数`
- 消费方：`task_result_repository.list_paginated`（无 task_id 分支：任务 id 分块过滤后本地分页 →
  一次查询）、model_summary 候选对查询

### E7 GetDataByPageList 增强（改现有 DTO，不新增端点）

| 控制器 | 增强项 | 消费方 |
|---|---|---|
| ParamTasks | `name` 模糊、`created_by`、`ids`、`order_fields: [["created_at","desc"],["id","desc"]]`（多键排序） | `list_by_name`、`clear_created_by`、`get_latest_task_id_by_type` 等双键排序 |
| ParamTaskResults | `fields: ["id","task_id","parameters",...]` 白名单投影（`result` 大 JSON 不下发）；`success_only` | `list_by_task_fields`（**当前 P0 缺口** http 孪生的长期解）、`get_export_entity` |
| ParamGoogleSheets | `spreadsheet_id` 精确过滤 | `get_by_spreadsheet_id`/`get_duplicate_row`（registry 表小，低优先） |
| ParamTaskResultSummaryIndex | `best_per_task` 分组取首（`PARTITION BY task_id ORDER BY metric DESC`） | `dedupe_best_per_task`、`page_summary_index(best_per_stock)`（拉全量本地去重 → 服务端窗口） |
| ParamTasks | `distinct: "task_type"`（或复用 E5） | `list_distinct_task_types` |

### E8 批量 upsert

```
POST /api/StockMetadata/BulkUpsert
```

- 请求：`{"rows": [元数据行数组]}`；响应：`ret_obj = {"upserted": n}`
- 消费方：`stock_metadata_repository.bulk_upsert`（循环单行 upsert → 批量；
  搜索结果落库路径每任务一次调用）

### ~~E9 任务日志批量创建~~（已裁定不提供，2026-10-16）

~~`POST /api/ParamTaskLogs/BulkCreate`~~ —— 主站无此端点且不再补充。替代策略：
任务结束快照回灌保持逐行 `ModifyOrAdd` 慢写，**单次请求 2 秒超时**（管线新增按次
`timeout` 覆盖：transport → client → ControllerApi → ParamTaskLogs.modify_or_add），
**仅抛弃失败的一条并继续写剩余**（不重试）——日志为低价值数据，本地文件日志有
全量留存。落地位置：`TaskLogHttpRepository.create_logs`（`LOG_WRITE_TIMEOUT_SECONDS = 2.0`）。

## 实施顺序建议

1. **E7-fields 投影**（ParamTaskResults 加 `fields` 参数）——最小改动，直接消掉本仓库当前唯一
   P0 缺口 `list_by_task_fields`；
2. **E1 CAS + E2 批量删除**——正确性核心；E1 落地后 Redis 裁决层仅剩回测锁/启动清理职责；
3. E3/E4 → E5/E6 → E7 其余 → E8。

## P2：随机K线三表（2026-10-28 新增，dev_vue 合入后的本地固定表上收）

> 本地三表 `t_param_task_kline_sources` / `t_param_task_random_series` / `t_param_task_result_kline_links`
> 当前固定本地 DB（http 模式下孪生仓储走本地混合读写）。远端补齐下列控制器后即可上收。
> 命名对齐现有约定：`POST /api/<Controller>/<Action>`，统一信封 `ret_code/ret_msg/ret_count/ret_obj`，
> 布尔 0/1 编码；四动作同构（GetDataByPageList / GetInfoById / ModifyOrAdd / Delete）。

### E10 源快照：/api/ParamTaskKlineSources

```bash
# 分页查询（唯一键过滤：task_id + stock_code + kline_key + data_source + adjust_type）
curl -X 'POST' 'http://stockapi.jaspil.cn/api/ParamTaskKlineSources/GetDataByPageList'   -H 'accept: application/json' -H 'Content-Type: application/json' -H 'Token: <token>'   -d '{"task_id": "t1", "stock_code": "600000", "kline_key": "2026-2025",
       "data_source": "dfcf", "adjust_type": "forward", "page_index": 1, "page_size": 20}'

# 按主键读快照详情（含 dates_json/open_json/... 大字段，单页全量不分页）
curl -X 'POST' 'http://stockapi.jaspil.cn/api/ParamTaskKlineSources/GetInfoById'   -H 'accept: application/json' -H 'Content-Type: application/json' -H 'Token: <token>'   -d '{"id": 1}'

# 新增/更新（get-or-create 语义：唯一键命中即更新，否则插入；ret_obj 回显行含 id）
curl -X 'POST' 'http://stockapi.jaspil.cn/api/ParamTaskKlineSources/ModifyOrAdd'   -H 'accept: application/json' -H 'Content-Type: application/json' -H 'Token: <token>'   -d '{"task_id": "t1", "stock_code": "600000", "stock_name": "浦发银行", "market_type": "cn",
       "kline_key": "2026-2025", "data_source": "dfcf", "adjust_type": "forward",
       "start_date": "2025-01-02", "end_date": "2026-01-23", "row_count": 260,
       "dates_json": "[\"2025-01-02\", ...]", "open_json": "[...]", "high_json": "[...]",
       "low_json": "[...]", "close_json": "[...]", "vwap_json": "[...]"}'

# 按主键删除
curl -X 'POST' 'http://stockapi.jaspil.cn/api/ParamTaskKlineSources/Delete'   -H 'accept: application/json' -H 'Content-Type: application/json' -H 'Token: <token>'   -d '{"id": 1}'
```

### E11 随机序列：/api/ParamTaskRandomSeries

```bash
# 分页查询（按 owner 任务 + source_id 或 stock_code+kline_key 过滤）
curl -X 'POST' 'http://stockapi.jaspil.cn/api/ParamTaskRandomSeries/GetDataByPageList'   -H 'accept: application/json' -H 'Content-Type: application/json' -H 'Token: <token>'   -d '{"task_id": "t1", "source_id": 1, "page_index": 1, "page_size": 50}'

# 按主键读序列（values_json 随机价格数组）
curl -X 'POST' 'http://stockapi.jaspil.cn/api/ParamTaskRandomSeries/GetInfoById'   -H 'accept: application/json' -H 'Content-Type: application/json' -H 'Token: <token>'   -d '{"id": 1}'

# 新增/更新（执行链每随机组合一条；ret_obj 回显行含 id，供结果关联外键）
curl -X 'POST' 'http://stockapi.jaspil.cn/api/ParamTaskRandomSeries/ModifyOrAdd'   -H 'accept: application/json' -H 'Content-Type: application/json' -H 'Token: <token>'   -d '{"source_id": 1, "task_id": "t1", "stock_code": "600000", "kline_key": "2026-2025",
       "dataset_key": "600000|2026-2025|g1", "random_group": 1, "price_mode": "random_price",
       "random_price_range": "high_low", "seed": "<seed>", "row_count": 260,
       "values_json": "[...]"}'

# 按主键删除（任务清理时按 task_id 级联删除需配合 E2 语义或逐 id）
curl -X 'POST' 'http://stockapi.jaspil.cn/api/ParamTaskRandomSeries/Delete'   -H 'accept: application/json' -H 'Content-Type: application/json' -H 'Token: <token>'   -d '{"id": 1}'
```

### E12 结果关联：/api/ParamTaskResultKlineLinks

```bash
# 写关联（结果落库时同步写；result_id+series_id 幂等）
curl -X 'POST' 'http://stockapi.jaspil.cn/api/ParamTaskResultKlineLinks/ModifyOrAdd'   -H 'accept: application/json' -H 'Content-Type: application/json' -H 'Token: <token>'   -d '{"result_id": 123, "task_id": "t1", "series_id": 1}'

# 分页查询（审计反查：task_id + series_id 过滤；ret_count 即 count_by_kline_series 总数）
curl -X 'POST' 'http://stockapi.jaspil.cn/api/ParamTaskResultKlineLinks/GetDataByPageList'   -H 'accept: application/json' -H 'Content-Type: application/json' -H 'Token: <token>'   -d '{"task_id": "t1", "series_id": 1, "page_index": 1, "page_size": 100}'

# 按主键删除
curl -X 'POST' 'http://stockapi.jaspil.cn/api/ParamTaskResultKlineLinks/Delete'   -H 'accept: application/json' -H 'Content-Type: application/json' -H 'Token: <token>'   -d '{"id": 1}'
```

### 端点增强核对补充（并入 E7 表）

| 控制器 | 增强项 | 消费方 |
|---|---|---|
| ParamTaskResults | `result_ids` 数组过滤、`return_series_id` 精确过滤 | `list_by_kline_series`（省"task_id 全量拉取本地过滤"）、`get_entity_by_return_series_id`（省逐行扫描） |
| ParamTaskLogs | `after_id` 游标过滤（id asc 增量） | `list_by_task_after`（日志增量轮询省重复传输） |
| ParamTasks | `error_message_prefix` 前缀过滤（LIKE 转义） | `list_pending_queued_entities`（[SHEET_QUEUED] 排队补跑扫描） |

> 执行锁不在此清单：2026-10-28 已裁定统一 Sheet 执行锁改走 Redis（TTL+续租），
> Sheet 表仅保留占用展示镜像，远端无需新增锁端点。


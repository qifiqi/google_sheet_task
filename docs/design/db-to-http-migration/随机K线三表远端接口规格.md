# 随机K线三表远端接口规格（DY.Stock.Api）

> 2026-10-28。给主站（DY.Stock.Api）的建控制器需求规格，对应本仓库迁移文档
> [02-remote-incremental-endpoints.md](02-remote-incremental-endpoints.md) 的 E10–E12。
> 命名对齐现有约定：`POST /api/<Controller>/<Action>`，统一信封
> `{"ret_code", "ret_msg", "ret_count", "ret_obj"}`，布尔 0/1 编码，`Token` 请求头鉴权。
> 本仓库侧消费方：`app/repositories/http_backend/` 孪生仓储（当前临时走本地 DB，端点就绪后切换）。

## 涉及表

| 表 | 控制器 | 说明 |
|---|---|---|
| `t_param_task_kline_sources` | `/api/ParamTaskKlineSources` | 源K线快照（执行前 get-or-create 一次） |
| `t_param_task_random_series` | `/api/ParamTaskRandomSeries` | 随机价格序列（每随机组合一条） |
| `t_param_task_result_kline_links` | `/api/ParamTaskResultKlineLinks` | 结果 ↔ 序列关联（结果落库同步写） |

唯一键约束（主站建库时需一并建好）：

- sources：`task_id + stock_code + kline_key + data_source + adjust_type`
- links：`result_id + series_id`

三个控制器动作同构：`GetDataByPageList` / `GetInfoById` / `ModifyOrAdd` / `Delete`。

---

## E10 源快照 /api/ParamTaskKlineSources

字段：`id, task_id, stock_code, stock_name, market_type, kline_key, data_source, adjust_type, start_date, end_date, row_count, dates_json, open_json, high_json, low_json, close_json, vwap_json, created_at`（六个 `*_json` 为数组 JSON 串，mediumtext 级容量）。

### 分页查询（唯一键过滤）

```bash
curl -X 'POST' 'http://stockapi.jaspil.cn/api/ParamTaskKlineSources/GetDataByPageList' \
  -H 'accept: application/json' \
  -H 'Content-Type: application/json' \
  -H 'Token: <token>' \
  -d '{
    "task_id": "t1",
    "stock_code": "600000",
    "kline_key": "2026-2025",
    "data_source": "dfcf",
    "adjust_type": "forward",
    "page_index": 1,
    "page_size": 20
  }'
```

### 按主键读详情（含大字段，单行全量）

```bash
curl -X 'POST' 'http://stockapi.jaspil.cn/api/ParamTaskKlineSources/GetInfoById' \
  -H 'accept: application/json' \
  -H 'Content-Type: application/json' \
  -H 'Token: <token>' \
  -d '{"id": 1}'
```

### 新增/更新（get-or-create：唯一键命中即更新，否则插入；`ret_obj` 回显整行含自增 id）

```bash
curl -X 'POST' 'http://stockapi.jaspil.cn/api/ParamTaskKlineSources/ModifyOrAdd' \
  -H 'accept: application/json' \
  -H 'Content-Type: application/json' \
  -H 'Token: <token>' \
  -d '{
    "task_id": "t1",
    "stock_code": "600000",
    "stock_name": "浦发银行",
    "market_type": "cn",
    "kline_key": "2026-2025",
    "data_source": "dfcf",
    "adjust_type": "forward",
    "start_date": "2025-01-02",
    "end_date": "2026-01-23",
    "row_count": 260,
    "dates_json": "[\"2025-01-02\",\"2025-01-03\"]",
    "open_json": "[10.5,10.8]",
    "high_json": "[11.0,11.2]",
    "low_json": "[10.2,10.6]",
    "close_json": "[10.9,11.1]",
    "vwap_json": "[10.7,10.9]"
  }'
```

### 删除

```bash
curl -X 'POST' 'http://stockapi.jaspil.cn/api/ParamTaskKlineSources/Delete' \
  -H 'accept: application/json' \
  -H 'Content-Type: application/json' \
  -H 'Token: <token>' \
  -d '{"id": 1}'
```

---

## E11 随机序列 /api/ParamTaskRandomSeries

字段：`id, source_id, task_id, stock_code, kline_key, dataset_key, random_group, price_mode, random_price_range, seed, row_count, values_json, created_at`。

### 分页查询（owner 任务 + source_id 过滤）

```bash
curl -X 'POST' 'http://stockapi.jaspil.cn/api/ParamTaskRandomSeries/GetDataByPageList' \
  -H 'accept: application/json' \
  -H 'Content-Type: application/json' \
  -H 'Token: <token>' \
  -d '{
    "task_id": "t1",
    "source_id": 1,
    "page_index": 1,
    "page_size": 50
  }'
```

### 按主键读序列

```bash
curl -X 'POST' 'http://stockapi.jaspil.cn/api/ParamTaskRandomSeries/GetInfoById' \
  -H 'accept: application/json' \
  -H 'Content-Type: application/json' \
  -H 'Token: <token>' \
  -d '{"id": 1}'
```

### 新增/更新（`ret_obj` 回显整行含自增 id，供结果关联外键）

```bash
curl -X 'POST' 'http://stockapi.jaspil.cn/api/ParamTaskRandomSeries/ModifyOrAdd' \
  -H 'accept: application/json' \
  -H 'Content-Type: application/json' \
  -H 'Token: <token>' \
  -d '{
    "source_id": 1,
    "task_id": "t1",
    "stock_code": "600000",
    "kline_key": "2026-2025",
    "dataset_key": "600000|2026-2025|g1",
    "random_group": 1,
    "price_mode": "random_price",
    "random_price_range": "high_low",
    "seed": "<seed>",
    "row_count": 260,
    "values_json": "[10.9,11.05]"
  }'
```

### 删除

```bash
curl -X 'POST' 'http://stockapi.jaspil.cn/api/ParamTaskRandomSeries/Delete' \
  -H 'accept: application/json' \
  -H 'Content-Type: application/json' \
  -H 'Token: <token>' \
  -d '{"id": 1}'
```

---

## E12 结果关联 /api/ParamTaskResultKlineLinks

字段：`id, result_id, task_id, series_id, created_at`。

### 写关联（结果落库同步写；`result_id + series_id` 幂等）

```bash
curl -X 'POST' 'http://stockapi.jaspil.cn/api/ParamTaskResultKlineLinks/ModifyOrAdd' \
  -H 'accept: application/json' \
  -H 'Content-Type: application/json' \
  -H 'Token: <token>' \
  -d '{"result_id": 123, "task_id": "t1", "series_id": 1}'
```

### 分页反查（审计用：task_id + series_id 过滤；`ret_count` 即关联总数）

```bash
curl -X 'POST' 'http://stockapi.jaspil.cn/api/ParamTaskResultKlineLinks/GetDataByPageList' \
  -H 'accept: application/json' \
  -H 'Content-Type: application/json' \
  -H 'Token: <token>' \
  -d '{
    "task_id": "t1",
    "series_id": 1,
    "page_index": 1,
    "page_size": 100
  }'
```

### 删除

```bash
curl -X 'POST' 'http://stockapi.jaspil.cn/api/ParamTaskResultKlineLinks/Delete' \
  -H 'accept: application/json' \
  -H 'Content-Type: application/json' \
  -H 'Token: <token>' \
  -d '{"id": 1}'
```

---

## 可选增强（并入 E7，非必需）

| 控制器 | 增强项 | 用途 |
|---|---|---|
| ParamTaskResults | `result_ids[]` / `return_series_id` 过滤 | 快照反查省"task_id 全量拉取本地过滤" |
| ParamTaskLogs | `after_id` 游标过滤 | 日志增量轮询省重复传输 |
| ParamGoogleSheets | `spreadsheet_id` 精确过滤（E7 已登记） | registry 查重 |

> 统一 Sheet 执行锁不在本规格内：已裁定改走 Redis（TTL+续租），Sheet 表仅保留占用展示镜像。

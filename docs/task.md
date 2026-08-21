# task

需要添加这些查询

  "task_types": ["backtest_training", "backtest_multi_product"],
  "statuses": ["pending", "running", "error", "cancelled"],

  "keyword": "任务名、描述或任务ID",

  "created_from": "2026-08-16T00:00:00",

  "sort": [
    { "field": "created_at", "direction": "asc" },
  

# task_log
## 查询
  "task_id": "任务UUID",
    { "field": "timestamp", "direction": "desc" },

## 删除
  "task_id": "任务UUID",


# TaskResult

## 查询
  "success": true,
  "task_ids": ["任务UUID-1", "任务UUID-2"],
{ "field": "timestamp", "direction": "desc" },

## 删除
  "task_id": "任务UUID",


# TaskResultReturn
## 查询
  "task_id": "uuid",


## 删除
  "task_id": "任务UUID",

# BacktestSheetRunLock

## 查询
    spreadsheet_id，task_id


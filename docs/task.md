# task_log
## 查询
  "task_id": "任务UUID",
    "level" "日志级别查询"
    "timestamp"：时间查询
        { "field": "timestamp", "direction": "desc" },

## 删除
  "task_id": "任务UUID",


# ParamStockMetadata

## 查询
    stock_code
    market_type

## 添加
    stock_code + market_type 做约束，两个同时存在不插入


# 修改 t_param_task_results_return
CREATE TABLE `t_param_task_results_return` (
  `id` int NOT NULL AUTO_INCREMENT COMMENT '主键ID',
  `task_id` varchar(36) NOT NULL COMMENT '关联任务ID',
  `stock_code` varchar(20) NOT NULL,
  `stock_name` varchar(20) NOT NULL,
  `start_return_date` date NOT NULL COMMENT '起始日期',
  `end_return_date` date NOT NULL COMMENT '结束日期',
  `return_length` int NOT NULL COMMENT '收益列长度',
  `stock_date` text COMMENT '日期',
  `index_return` text COMMENT '指数收益',
  `start_return` text COMMENT '策略收益',
  PRIMARY KEY (`id`),
  KEY `ix_t_param_task_results_return_stock_code` (`stock_code`),
  KEY `ix_t_param_task_results_return_task_id` (`task_id`),
  KEY `ix_t_param_task_results_return_stock_name` (`stock_name`)
) ENGINE=InnoDB AUTO_INCREMENT=2 DEFAULT CHARSET=utf8mb3 COMMENT='任务收益时间序列表';


# ParamTaskResultSummaryIndex

## 查询
  "task_id": "任务ID",
  "task_result_id": 123,
  "task_type": "google_sheet_C5",
  "market_type": "cn",
  "stock_keyword": "600519",
  "period_key": "2024",
  "is_best": true,
  "best_metric_value_gt": 0.2,
  "result_timestamp_from": "2024-01-01T00:00:00",
  "result_timestamp_to": "2024-12-31T23:59:59"


## 返回添加
  "summary": {
    "stock_count": 196,
    "cn_stock_count": 104,
    "us_stock_count": 92,
    "task_count": 1049,
    "return_beats_gt_0": 1150,
    "return_beats_gt_20": 897,
    "return_beats_gt_50": 635,
    "return_beats_gt_100": 394
  }
  return_beats_gt_* 是returnbetas大于多少return再metrics_json内
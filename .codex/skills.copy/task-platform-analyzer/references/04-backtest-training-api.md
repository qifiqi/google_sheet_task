# 04 - 单品回测训练 API

> 前缀：`/backtest-training`，旧版兼容前缀：`/backtest`

## GET /backtest-training/api/search-stocks
股票搜索（东方财富数据源）。搜索结果会自动缓存到 stock_metadata 表。

**查询参数：**
| 参数 | 类型 | 默认 | 说明 |
|------|------|------|------|
| q | string | - | 搜索关键词（股票代码/名称） |
| page_size | int | 10 | 返回条数（最大20） |

**响应：**
```json
{
  "status": "success",
  "keyword": "600519",
  "results": [
    {
      "source": "codetable",
      "code": "600519",
      "name": "贵州茅台",
      "security_type_name": "沪A",
      "market": "SH",
      "is_exact_match": true,
      "label": "600519 · 贵州茅台 · 沪A",
      "market_type": "cn",
      "inner_code": "...",
      "pinyin": "GZMT",
      "unified_code": "..."
    }
  ]
}
```

---

## POST /backtest-training/api/import-excel
上传 Excel 文件解析回测参数。

**请求格式：** `multipart/form-data`，字段名 `file`
**响应：** 解析后的参数配置 JSON（含 stock_code, parameters 等）

---

## GET /backtest-training/api/task-results/<task_id>
获取回测任务结果列表（分页）。仅支持 `backtest_training` 类型任务。

**查询参数：** `page`（默认1）、`per_page`（默认10，最大100）

**响应：**
```json
{
  "status": "success",
  "task_id": "uuid",
  "results": [
    {
      "id": 1,
      "task_id": "uuid",
      "step_index": 0,
      "parameters": {"parameter": [0.001, 1.0], "year": "2020-2024"},
      "success": true,
      "error_message": null,
      "timestamp": "2025-01-01T10:00:00"
    }
  ],
  "pagination": {
    "page": 1, "per_page": 10, "pages": 5, "total": 50,
    "has_prev": false, "has_next": true
  }
}
```

---

## GET /backtest-training/api/task-result/<task_result_id>
获取单条回测结果详情（含完整 calculate_metrics 和 sheet_result）。

**响应：**
```json
{
  "status": "success",
  "result": {
    "excess_returns": [...],
    "start_sharpe_ratios": {...},
    "index_sharpe_ratios": {...},
    "start_maximum_drawdown": {...},
    "index_maximum_drawdown": {...},
    "outperform_year": "60%",
    "sheet_result": {"I15": "12.5%", "I18": "8.3%", ...}
  }
}
```

---

## GET /backtest-training/api/task-summary/<task_id>
C3 回测任务汇总分析。将每个参数组合 × 年份的结果展平为表格。

**响应：**
```json
{
  "status": "success",
  "task": {"id": "uuid", "name": "任务名", "model_version": "c3"},
  "parameter_fields": [
    {"key": "commission", "label": "Commission"},
    {"key": "xm", "label": "X Multiplier"},
    ...
  ],
  "summary": {"row_count": 24, "parameter_group_count": 4},
  "rows": [
    {
      "commission": 0.001, "xm": 1.0, "dbbh1": 0.5, "dbbh2": 0.3,
      "zlxc": 1.0, "zsgz": 0.8, "ywf1": 0.5, "ywf2": 0.3,
      "year": "2024",
      "strategy_return": 0.125,
      "index_return": 0.083,
      "beats_index": 0.042,
      "strategy_max_drawdown": -0.05,
      "index_max_drawdown": -0.08,
      "drawdown_beats": 0.03,
      "strategy_monthly_sharpe": 1.5,
      "excess_annualized_return": 0.04,
      "outperform_year": 0.6,
      ...
    }
  ]
}
```

**说明：** 仅支持 C3 模型。rows 按参数组合分组，同组内按年份倒序排列。

---

## GET /backtest-training/api/global-preview/<task_id>
全局预览数据。按年份分组，展示所有参数组合的指标对比矩阵。

**响应结构：**
```json
{
  "status": "success",
  "task": {"id": "uuid", "name": "...", "status": "completed", "stock_code": "600519"},
  "summary": {
    "total_results": 24, "success_results": 20,
    "failed_results": 4, "group_count": 5
  },
  "groups": [
    {
      "group_key": "2020-2024",
      "group_label": "2020-2024 年",
      "year": "2020-2024",
      "period": "2020/1/2 - 2024/12/31",
      "columns": [
        {"column_key": "result_1", "result_id": 1, "step_index": 0, "header": "0.001 / 1.0", "model_name": "C3", "success": true}
      ],
      "rows": [
        {
          "category": "绝对收益", "metric": "年化收益",
          "index_value": "8.30%", "values": {"result_1": "12.50%"}
        },
        {"category": "回撤", "metric": "年最大回撤", "index_value": "", "values": {"result_1": "-5.20%"}}
      ],
      "column_count": 4, "failed_results": 1
    }
  ]
}
```

---

## GET /backtest-training/api/global-preview/<task_id>/export
导出全局预览为 Excel 文件（openpyxl 格式）。包含：
- 汇总 Sheet（所有年份的回报/回撤对比）
- 每个年份一个独立 Sheet（完整指标矩阵）

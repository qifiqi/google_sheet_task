# 多品数据回测 API（backtest_multi_product）

> 蓝图：`backtest_multi_product_bp`，URL 前缀：`/backtest-multi-product`
> 另有 legacy 蓝图 `backtest_multi_product_legacy_bp` 前缀 `/backtest-multi`（功能完全相同）
> 权限前缀：`backtest:view` / `backtest:create`
> 仅支持 `task_type = backtest_multi_product` 的任务

---

## 1. Excel 导入

### POST `/backtest-multi-product/api/import-excel`
**权限**：`backtest:create`

上传 Excel 文件，解析为多品回测配置数据。

**请求**：`multipart/form-data`
| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| file | file | 是 | Excel 文件 |

**响应**：
```json
{
  "status": "success",
  "products": [...],
  "date_range": {...}
}
```

**错误**：
- `400` — 未上传文件 / Excel 解析失败
- `500` — 服务器内部错误

---

## 2. 股票搜索

### GET `/backtest-multi-product/api/search-stocks`
**权限**：`backtest:view`

通过东方财富接口搜索股票，同时写入 `stock_metadata` 表缓存。

**参数**（query）：
| 参数 | 类型 | 默认 | 说明 |
|------|------|------|------|
| q | string | "" | 搜索关键词（股票代码/名称/拼音） |
| page_size | int | 10 | 每页条数，1-20 |

**响应**：
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
      "label": "600519 · 贵州茅台 · 沪A",
      "status": 10
    }
  ]
}
```

---

## 3. 任务结果列表

### GET `/backtest-multi-product/api/task-results/<task_id>`
**权限**：`backtest:view`

分页获取指定多品回测任务的结果列表。

**参数**（query）：
| 参数 | 类型 | 默认 | 说明 |
|------|------|------|------|
| page | int | 1 | 页码 |
| per_page | int | 10 | 每页条数，最大 100 |

**响应**：
```json
{
  "status": "success",
  "task_id": "uuid",
  "results": [
    {
      "id": 1,
      "task_id": "uuid",
      "step_index": 0,
      "parameters": {},
      "success": true,
      "error_message": null,
      "timestamp": "2024-01-01T00:00:00"
    }
  ],
  "pagination": {
    "page": 1, "per_page": 10, "pages": 1, "total": 1,
    "has_prev": false, "has_next": false,
    "prev_num": null, "next_num": null
  }
}
```

---

## 4. 任务结果详情

### GET `/backtest-multi-product/api/task-result/<int:task_result_id>`
**权限**：`backtest:view`

获取单条结果的详细数据，含 `calculate_metrics`、`sheet_result`、`daily_returns`。

**响应**：
```json
{
  "status": "success",
  "result": {
    "total_return": 0.15,
    "sharpe_ratio": 1.2,
    "max_drawdown": -0.1,
    "sheet_result": { ... },
    "daily_returns": {
      "dates": ["2024-01-01", "..."],
      "index_returns": [0.01, "..."],
      "start_returns": [0.02, "..."]
    }
  }
}
```

---

## 5. 全局预览

### GET `/backtest-multi-product/api/global-preview/<task_id>`
**权限**：`backtest:view`

获取多品全局预览数据（按指标分组、各产品 × 加权比例）。

**响应**：
```json
{
  "status": "success",
  "task": { "name": "...", "id": "uuid" },
  "products": [
    { "product_name": "茅台", "stock_code": "600519", "ratio": "50" }
  ],
  "groups": [
    {
      "rows": [
        {
          "category": "收益指标",
          "metric": "年化收益率",
          "product_values": [
            { "index_value": "10%", "result_value": "15%", "weighted_result_value": "7.5%" }
          ],
          "weighted_index_value": "...",
          "weighted_result_value": "..."
        }
      ]
    }
  ]
}
```

---

## 6. 计算比例预览

### POST `/backtest-multi-product/api/global-preview/<task_id>/calculate-ratios`
**权限**：`backtest:view`

传入自定义比例，实时计算加权预览（不保存到数据库）。

**请求体**：
```json
{
  "ratios": [
    { "ratio": "60" },
    { "ratio": "40" }
  ]
}
```

**响应**：同全局预览格式。

**错误**：
- `400` — ratios 必须是数组 / 比例数量不匹配 / ValueError

---

## 7. 保存比例

### PUT `/backtest-multi-product/api/global-preview/<task_id>/ratios`
**权限**：`backtest:create`

将比例写入任务的 `config.products[].ratio`，持久化到数据库。

**请求体**：
```json
{
  "ratios": [
    { "ratio": "60" },
    { "ratio": "40" }
  ]
}
```

**响应**：
```json
{
  "status": "success",
  "message": "比例已保存",
  "products": [...],
  "groups": [...]
}
```

**错误**：
- `400` — ratios 数量与产品数量不一致

---

## 8. 导出全局预览 Excel

### GET `/backtest-multi-product/api/global-preview/<task_id>/export`
**权限**：`backtest:view`

下载全局预览的 Excel 文件。

**参数**（query）：
| 参数 | 类型 | 说明 |
|------|------|------|
| ratios | string(JSON) | 可选，自定义比例 JSON |

**响应**：Excel 文件下载（`.xlsx`）

**错误**：
- `400` — ratios 参数不是有效 JSON / ValueError
- `404` — 任务不存在

---

## 业务规则

1. **任务类型校验**：所有接口通过 `_load_multi_product_task_or_response()` 验证 `task_type` 必须为 `backtest_multi_product`
2. **权限分级**：查看类接口需 `backtest:view`，写入比例需 `backtest:create`
3. **NaN/Inf 清理**：所有响应数值经过 `_sanitize_json_value()` 过滤，NaN/Inf 替换为 null
4. **比例约束**：`PUT ratios` 时数量必须与 `products` 数组长度一致
5. **收益曲线**：`TaskResultReturn` 通过 `return_series_id` 关联，按列存储 `dates/index_returns/start_returns`

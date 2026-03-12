# 统一 Config Schema 草案

## 1. 目标

这份草案用于 B 方案阶段 1，定义后续统一配置契约。

设计原则：

- 以 `C5` 为主结构
- `C4` 通过归一化映射到该结构
- 默认版 `google_sheet` 可逐步接入，但短期不强制全量替换

## 2. 统一结构

```json
{
  "task_type": "google_sheet_C5",
  "token_type": "file",
  "token_file": "data/token.json",
  "token_json": "",
  "proxy_url": null,
  "count_mode": "n_plus_1",
  "price_mode": "kp_price",
  "market_type": "cn",
  "date_range_mode": ["full"],
  "start_date": null,
  "end_date": null,
  "parameters": [],
  "sheets": [
    {
      "spreadsheet_id": "",
      "sheet_name": "",
      "title": ""
    }
  ]
}
```

## 3. 字段定义

### 顶层字段

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---|---|---|
| `task_type` | `string` | 否 | `google_sheet_C5` | 当前任务类型 |
| `token_type` | `string` | 是 | `file` | `file` 或 `json` |
| `token_file` | `string` | 条件必填 | `data/token.json` | `token_type=file` 时使用 |
| `token_json` | `string` | 条件必填 | `""` | `token_type=json` 时使用 |
| `proxy_url` | `string \| null` | 否 | `null` | HTTP/HTTPS 代理 |
| `count_mode` | `string \| null` | 否 | `n_plus_1` | 统计方式 |
| `price_mode` | `string \| null` | 否 | `kp_price` | 当前主要给 C5 使用 |
| `market_type` | `string \| null` | 否 | `cn` | 市场类型 |
| `date_range_mode` | `string[]` | 否 | `["full"]` | 时间范围模式 |
| `start_date` | `string \| null` | 否 | `null` | `YYYY-MM-DD` |
| `end_date` | `string \| null` | 否 | `null` | `YYYY-MM-DD` |
| `parameters` | `array[]` | 是 | `[]` | 参数组数组 |
| `sheets` | `object[]` | 是 | `[]` | 工作表配置列表 |

### `sheets[]`

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---|---|---|
| `spreadsheet_id` | `string` | 是 | `""` | Google Sheet ID |
| `sheet_name` | `string` | 是 | `""` | 工作表名称 |
| `title` | `string` | 否 | `""` | 展示或标记用途 |

## 4. 归一化规则

### 4.1 C5 -> Unified

规则：

- 原样保留
- 缺失字段按默认值补齐

### 4.2 C4 -> Unified

规则：

- `task_type` 保持为 `google_sheet_C4`，但结构按 C5 兼容
- 若存在顶层 `spreadsheet_id` / `sheet_name`，转为 `sheets[0]`
- `price_mode` 若缺失，补默认值 `kp_price`
- `date_range_mode` 若是字符串，转为数组

### 4.3 默认版 -> Unified

规则：

- `spreadsheet_id` / `sheet_name` 转为 `sheets[0]`
- 保留默认版专有字段作为“扩展字段”
- `count_mode` / `price_mode` / `market_type` 可为空

## 5. 校验规则

### 最低校验

必须满足：

1. `token_type` 只能是 `file` 或 `json`
2. `token_type=file` 时 `token_file` 不能为空
3. `token_type=json` 时 `token_json` 不能为空
4. `parameters` 必须是数组
5. `sheets` 必须是数组
6. `sheets.length >= 1`
7. 每个 sheet 都必须有 `spreadsheet_id`
8. 每个 sheet 都必须有 `sheet_name`

### 建议校验

建议增加：

1. `date_range_mode` 只允许 `full` / `recent`
2. `start_date` / `end_date` 应满足日期格式
3. `count_mode` 应限制在允许值内
4. `price_mode` 应限制在允许值内

## 6. 代码落地建议

### 后端

建议新增模块：

- `app/services/config_schema.py`
- `app/services/config_normalizer.py`
- `app/services/config_validator.py`

### 前端

建议统一抽出：

- `normalizeTaskConfig(rawConfig, taskType)`
- `validateTaskConfig(config)`
- `buildTaskConfigFromForm(formState)`

## 7. 近期执行顺序

建议下一步这样落地：

1. 先做后端 `normalize` 与 `validate` 草实现
2. 再让 C5 前端优先使用统一结构
3. 然后把 C4 的 `normalizeC4Config` 改成“映射到统一 schema”
4. 最后决定是否让默认版也接入统一前端编辑逻辑

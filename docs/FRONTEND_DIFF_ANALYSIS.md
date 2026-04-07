# 新旧前端配置差异深度分析

> 基于代码逐行对比，聚焦字段差异、行为差异、缺失功能。
> 生成日期：2026-04-07

---

## 一、C3 创建页差异（`templates/google_sheet/create.html` vs `frontend/src/views/task/CreateC3.vue`）

### 1.1 字段差异

| 字段 | 老前端 | 新前端 | 说明 |
|------|--------|--------|------|
| `task_description` | ✅ 有 | ✅ 有 | 对齐 |
| `token_file`（直接文本输入） | ✅ 有（旧版遗留，已被 token_id 替代） | ❌ 无 | 老前端有 `token_file` 隐藏字段，新前端只用 `token_id`；提交时老前端会带 `token_file`，新前端提交 `token_file: ''` |
| `spreadsheet` 选择方式 | 下拉 select（从 `/api/google-sheets` 加载） | 下拉 select（同） | 对齐 |
| 工作表名称 | `readonly` 文本框（自动带出） | `el-input` 可编辑 | **差异**：老前端 readonly，新前端可手动改 |
| 刷新 Google Sheet 列表按钮 | ✅ 有（`refresh-google-sheets` 按钮） | ❌ 无 | 新前端无刷新按钮，只在选择时触发加载 |
| 参数数量 | 固定 6 个（param1~param6），可动态增删 | 初始 6 个，可动态增删 | 对齐 |
| 参数组合预览 | ✅ 有（模态框） | ✅ 有（el-dialog） | 对齐 |
| 第一次执行确认模态框 | ✅ 有（`confirmModal`，但功能已移除） | ❌ 无 | 老前端保留了 HTML 但 JS 已注释，新前端直接删除 |
| 任务执行状态模态框 | ✅ 有（`taskStatusModal`，但功能已移除） | ❌ 无 | 同上，老前端保留 HTML 壳 |

### 1.2 行为差异

| 行为 | 老前端 | 新前端 | 风险 |
|------|--------|--------|------|
| localStorage key | `google_sheet_form_data` | `google_sheet_form_data` | ✅ 一致 |
| 提交后跳转路径 | `/google-sheet/detail?task_id=xxx` | `/task/{id}` | 正常，路径已迁移 |
| 模板加载时 spreadsheet_id 处理 | 调用 `loadGoogleSheets(config.spreadsheet_id)` 重新拉取列表 | 直接 `form.spreadsheet_id = config.spreadsheet_id` 再调 `onSheetChange()` | **差异**：老前端会把 spreadsheet_id 加入下拉列表（即使不在可用列表中），新前端只调 `onSheetChange` 不会补充选项 |
| 重启任务时任务名 | `restartConfig.name + ' (重启)'` | `task.name + ' (重启)'` | ✅ 一致 |
| 清除数据 | 重置表单 + 隐藏组合信息 + 清 localStorage | 重置 form + params + 清 localStorage | 对齐 |
| 参数 JSON 格式校验 | `parseJsonArray` 返回 null 时阻止提交 | 同 | 对齐 |

### 1.3 缺失功能

- **刷新 Google Sheet 列表按钮**：老前端有独立刷新按钮，新前端无。用户无法在不重新选择的情况下刷新列表。
- **模板加载时 spreadsheet_id 不在列表中的兼容**：老前端会把历史 spreadsheet_id 追加到下拉选项，新前端不会，可能导致模板回填后下拉框显示空白。

---

## 二、C4 创建页差异（`templates/google_sheet_c4/create.html` vs `frontend/src/views/task/CreateC4.vue`）

### 2.1 字段差异

| 字段 | 老前端 | 新前端 | 说明 |
|------|--------|--------|------|
| Spreadsheet ID 输入方式 | 文本框（手动输入 ID 或 URL） | 文本框（同） | 对齐 |
| 工作表名称 | 下拉 select + "自定义" 选项 | 下拉 select + `__custom__` 选项 | 对齐 |
| 自定义工作表名称 | `custom_sheet_name` 文本框 | `sheet.custom_sheet_name` | 对齐 |
| 表标题 `spreadsheet_title` | ✅ 有 | ✅ 有 | 对齐 |
| 统计方式 `count_mode` | radio（总数/N+1） | radio-button（同） | 对齐 |
| 市场类型 `market_type` | radio（美股/A股，值 `us`/`cn`） | radio-button（同） | 对齐 |
| 时间范围类型 `date_range_mode` | checkbox（整年/近年），仅 N+1 时启用 | checkbox（同），仅 N+1 时启用 | 对齐 |
| 开始/结束日期 | `start_date`/`end_date` date input | `el-date-picker`（同） | 对齐 |
| 产品代码 chips | ✅ 有（基于隐藏 param1） | ✅ 有（`productCodes` 数组） | 对齐 |
| 多 Sheet 配置（增删） | ✅ 有（`addVisualSheetConfigItem`） | ✅ 有（`sheetConfigs` 数组） | 对齐 |
| 模板选择 | ✅ 有（仅加载 `task_type=google_sheet_C4`） | ✅ 有（同） | 对齐 |
| 保存为模板 | ✅ 有 | ✅ 有 | 对齐 |

### 2.2 行为差异

| 行为 | 老前端 | 新前端 | 风险 |
|------|--------|--------|------|
| localStorage key | `google_sheet_c4_form_data` | `google_sheet_c4_form_data` | ✅ 一致 |
| 日期默认值初始化 | `initDefaultDatesIfEmpty()`：结束=昨天，开始=5年前 | `initDefaultDates()`：同逻辑 | ✅ 对齐 |
| count_mode 与 date_range_mode 联动 | N+1 时才启用 checkbox | 同 | ✅ 对齐 |
| 多 Sheet 提交结构 | `sheets: [{spreadsheet_id, sheet_name, title}]` | 同 | ✅ 对齐 |
| 旧结构兼容（`normalizeC4Config`） | ✅ 有（兼容旧版 `spreadsheet_id` 顶层字段） | ❌ 无 | **差异**：新前端 `applyTemplate` 里有兼容逻辑，但 `loadRestartTask` 里直接 `Object.assign` 不做 normalize，旧任务重启可能丢失 sheets |
| 重启任务时 `applyTemplate(null)` | 无此调用 | ✅ 有（先 reset 再 assign） | 新前端多了一步 reset，逻辑更清晰 |

### 2.3 缺失功能

- **旧结构重启兼容**：老前端有 `normalizeC4Config()` 专门处理旧任务（顶层 `spreadsheet_id`），新前端 `loadRestartTask` 里没有等价处理，旧任务重启时 `sheetConfigs` 可能为空。

---

## 三、C5 创建页差异（`templates/google_sheet_c5/create.html` vs `frontend/src/views/task/CreateC5.vue`）

### 3.1 字段差异（C5 相比 C4 新增字段）

| 字段 | 老前端 | 新前端 | 说明 |
|------|--------|--------|------|
| `price_mode`（开盘价/收盘价） | ✅ 有 | ✅ 有 | 对齐 |
| `exclude_years`（排除年份，近年模式） | ✅ 有 | ✅ 有 | 对齐 |
| 参数2 `param2` | ✅ 有 | ✅ 有 | 对齐 |
| 参数3 `param3` | ✅ 有 | ✅ 有 | 对齐 |
| 模板选择 | ✅ 有（`task_type=google_sheet_C5`） | ✅ 有（同） | 对齐 |
| 保存为模板 | ✅ 有 | ✅ 有 | 对齐 |

### 3.2 行为差异

| 行为 | 老前端 | 新前端 | 风险 |
|------|--------|--------|------|
| localStorage key | `google_sheet_c5_form_data` | `google_sheet_c5_form_data` | ✅ 一致 |
| `exclude_years` 联动 | 仅近年模式时显示 | 同（`v-if="dateRangeRecent"`） | ✅ 对齐 |
| 参数2/3 提交逻辑 | `parameters = [param1, param2, param3]`（过滤空） | 同 | ✅ 对齐 |

C5 整体对齐较好，无明显缺失。

---

## 四、C31 批量创建页差异（`templates/google_sheet_c31/create.html` vs `frontend/src/views/task/CreateC31.vue`）

### 4.1 字段差异

| 字段 | 老前端 | 新前端 | 说明 |
|------|--------|--------|------|
| 模板选择 | ✅ 有 | ❌ 无 | **缺失**：新前端 C31 没有模板选择功能 |
| 任务描述 `task_description` | ✅ 有 | ❌ 无 | **缺失**：新前端无任务描述字段 |
| 股票代码输入 | 单个输入框（每次一个） | 批量输入（逗号/空格分隔） | **差异**：新前端支持批量输入，功能更强 |
| 市场类型值 | `cn`/`en`（美股用 `en`） | `cn`/`en`（同） | ✅ 对齐（CLAUDE.md 已记录） |
| 参数配置 | 6 个参数，支持一维/二维数组 | 6 个参数，同 | 对齐 |
| 参数格式提示 | 有提示文字 | ✅ 有（"每个参数支持一维或二维数组"） | 对齐 |
| 组合预览 | 显示"N 个子任务" | 显示"股票数 × 参数组合 × 表格数 = 子任务数" | **新前端更详细** |
| 保存为模板 | ✅ 有 | ❌ 无 | **缺失** |
| 提交 API | `POST /api/tasks`（`task_type: 'google_sheet'`，批量由后端拆分） | `POST /api/tasks/batch` | **差异**：API 路径不同，需确认后端 `/api/tasks/batch` 是否存在 |

### 4.2 行为差异

| 行为 | 老前端 | 新前端 | 风险 |
|------|--------|--------|------|
| localStorage key | `google_sheet_c31_form_data` | `google_sheet_c31_form_data` | ✅ 一致 |
| 提交后跳转 | `/google-sheet/?version=c31`（任务列表） | `/task/list?version=c31` | 路径已迁移，正常 |
| 提交 payload 结构 | `task_type: 'google_sheet'`，config 含 `stock_codes`/`base_task_name` | 同结构，但走 `/api/tasks/batch` | **需确认** `/api/tasks/batch` 接口是否存在 |

### 4.3 缺失功能（高优先级）

1. **模板选择**：老前端有，新前端无
2. **保存为模板**：老前端有，新前端无
3. **任务描述字段**：老前端有，新前端无
4. **`/api/tasks/batch` 接口确认**：新前端调用此接口，需确认后端是否实现

---

## 五、任务详情页差异（`templates/google_sheet/detail.html` vs `frontend/src/views/task/Detail.vue`）

### 5.1 字段/功能差异

| 功能 | 老前端 | 新前端 | 说明 |
|------|--------|--------|------|
| 任务信息卡片 | ✅ 有 | ✅ 有 | 对齐 |
| 时间信息卡片 | ✅ 有 | ✅ 有 | 对齐 |
| 执行统计（成功/失败/成功率） | ✅ 有 | ✅ 有 | 对齐 |
| 配置信息展示 | ✅ 有（分 Google Sheet 配置 + 参数配置两列） | ✅ 有（Tab "任务配置"，JSON 格式展示） | **差异**：老前端分字段展示，新前端直接 JSON dump |
| **编辑配置弹窗** | ✅ 有（`editConfigModal`，含参数位置配置） | ❌ 无 | **缺失**：老前端支持在详情页直接编辑任务配置（包括 param_positions/check_positions/result_positions），新前端无此功能 |
| 日志查看器 | ✅ 有 | ✅ 有 | 对齐 |
| 结果表格 | ✅ 有（含参数组合列、执行结果列、耗时列） | ✅ 有（含参数列、状态、时间） | **差异**：老前端有"执行结果"列和"耗时"列，新前端无 |
| 结果筛选（全部/成功/失败） | ✅ 有（下拉筛选） | ❌ 无 | **缺失** |
| 结果分页 | ✅ 有 | ✅ 有 | 对齐 |
| 结果详情抽屉 | ❌ 无（模态框展示） | ✅ 有（el-drawer） | 新前端更好 |
| 结果折线图 | ✅ 有（步骤 vs 成功/失败） | ❌ 无 | **缺失**（已在旧 PLAN 中记录） |
| 重启任务下拉 | ✅ 有（从断点/从头/跳转创建） | ✅ 有（同） | 对齐 |
| 检查状态按钮 | ✅ 有 | ✅ 有 | 对齐 |
| 自动刷新（运行中） | ✅ 有（SSE + 轮询） | ✅ 有（5s 轮询） | 对齐 |

### 5.2 重要缺失

1. **编辑配置弹窗**：老前端支持在详情页直接修改 spreadsheet_id、sheet_name、token、参数位置（param_positions/check_positions/result_positions）。新前端完全没有此功能。
2. **结果筛选**：老前端可按成功/失败筛选结果，新前端无。
3. **结果表格"执行结果"列**：老前端结果表格有 `result` 字段展示，新前端只有参数和状态。

---

## 六、系统日志页差异（`templates/admin/logs.html` vs `frontend/src/views/admin/Logs.vue`）

| 功能 | 老前端 | 新前端 | 说明 |
|------|--------|--------|------|
| 刷新按钮 | ✅ 有 | ✅ 有 | 对齐 |
| 清空日志按钮 | ✅ 有 | ✅ 有 | 对齐 |
| 下载日志按钮 | ✅ 有 | ✅ 有 | 对齐 |
| 级别筛选 | ✅ 有 | ✅ 有 | 对齐 |
| 关键词搜索 | ✅ 有 | ✅ 有 | 对齐 |
| 日期筛选 | ✅ 有 | ✅ 有 | 对齐 |
| 日志颜色区分 | ✅ 有（info/warning/error） | ✅ 有（同） | 对齐 |

日志页已完全对齐，旧 PLAN 中标记的"缺失"已实现。

---

## 七、C3 详情页 vs C4/C5 详情页

老前端 C4/C5 有独立的 `detail.html`（`templates/google_sheet_c4/detail.html`、`templates/google_sheet_c5/detail.html`），新前端统一用 `task/Detail.vue`。

需确认 C4/C5 详情页是否有 C3 没有的特殊字段展示（如 `sheets` 数组、`count_mode`、`market_type` 等）。新前端用 JSON dump 展示配置，理论上不会丢失，但可读性差。

---

## 八、汇总：需要修复的差异（按优先级）

### 高优先级（影响功能完整性）

| 编号 | 页面 | 问题 | 建议 |
|------|------|------|------|
| H1 | `CreateC31.vue` | 缺少模板选择和保存为模板功能 | 参考 C3/C4 补充 |
| H2 | `CreateC31.vue` | 缺少任务描述字段 | 补充 `form.description` 字段 |
| H3 | `CreateC31.vue` | ~~提交走 `/api/tasks/batch`，需确认后端接口存在~~ | ✅ 已修复：后端路由为 `/tasks/batch-create`，前端已更正 |
| H4 | `task/Detail.vue` | 缺少结果筛选（成功/失败） | 在结果 Tab 加筛选按钮 |
| H5 | `task/Detail.vue` | 结果表格缺少"执行结果"列 | 补充 `result` 字段展示 |

### 中优先级（影响使用体验）

| 编号 | 页面 | 问题 | 建议 |
|------|------|------|------|
| M1 | `CreateC3.vue` | 无刷新 Google Sheet 列表按钮 | 在 Sheet 选择旁加刷新按钮 |
| M2 | `CreateC3.vue` | 模板回填时 spreadsheet_id 不在列表中不会补充选项 | 参考老前端 `loadGoogleSheets(config.spreadsheet_id)` 逻辑 |
| M3 | `CreateC4.vue` | 旧任务重启时缺少 `normalizeC4Config` 兼容处理 | 在 `loadRestartTask` 中补充旧结构兼容 |
| M4 | `task/Detail.vue` | 配置展示为 JSON dump，可读性差 | 可选：分字段展示关键配置（spreadsheet_id、sheet_name、token 等） |
| M5 | `task/Detail.vue` | 缺少结果折线图 | 已在旧 PLAN 中记录，补充 Chart.js 折线图 |

### 低优先级（细节完善）

| 编号 | 页面 | 问题 | 建议 |
|------|------|------|------|
| L1 | `CreateC3.vue` | 工作表名称老前端 readonly，新前端可编辑 | 可保留新前端行为（更灵活） |
| L2 | `task/Detail.vue` | 缺少编辑配置弹窗（含 param_positions 等） | 低频功能，可暂不补充 |
| L3 | `task/Detail.vue` | 结果表格缺少"耗时"列 | 补充 `duration` 字段 |

---

## 九、C31 提交 API 路径确认（已修复）

后端实际路由为 `POST /api/tasks/batch-create`（`app/routes/task_api.py:62`），
新前端原来调用的是 `/tasks/batch`，已修复为 `/tasks/batch-create`。

老前端 C31 提交走 `POST /api/tasks`（`task_type: 'google_sheet'`），由后端 `TaskManager.batch_create_and_start_task()` 处理。
新前端走专用接口 `/api/tasks/batch-create`，后端同样调用 `batch_create_and_start_task()`，逻辑一致。

---

## 十、localStorage key 对照表

| 页面 | 老前端 key | 新前端 key | 是否一致 |
|------|-----------|-----------|---------|
| C3 创建 | `google_sheet_form_data` | `google_sheet_form_data` | ✅ |
| C4 创建 | `google_sheet_c4_form_data` | `google_sheet_c4_form_data` | ✅ |
| C5 创建 | `google_sheet_c5_form_data` | `google_sheet_c5_form_data` | ✅ |
| C31 创建 | `google_sheet_c31_form_data` | `google_sheet_c31_form_data` | ✅ |

localStorage key 全部一致，用户切换前端后历史数据可恢复。

---

*本文档基于代码逐行对比生成，请结合实际运行效果进行人工复核。*

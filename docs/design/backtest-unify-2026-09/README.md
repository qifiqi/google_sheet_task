# 回测域统一与体验优化分析（2026-09-16）

> 状态：**分析稿，未实施**。覆盖四项议题（全局预览统一、Word 导出透出数据、单/多品前后端统一与多品 Sheet/K 线优化、Google Token 去文件化），附上轮已分析、仍待确认的"无风险利率"方案摘要。所有结论基于 dev_vue 分支当前工作区，行号可直达代码。
>
> 第二轮分析（2026-09-17，回应四个追问：组件化共用不跳转 / preview 数据直驱 Word + v3 页 / config·result 统一格式与全层级 Pydantic / Sheet 高效处理）：[02-第二轮分析.md](02-第二轮分析.md)。
> 第三轮分析（2026-09-17，Word 上传云端硬盘指定文件夹 + 上传后回写登记 Sheet）：[03-云端硬盘导出与Sheet登记分析.md](03-云端硬盘导出与Sheet登记分析.md)。
>
> 实施前需逐条确认文末"决策清单"。无风险利率部分已于 2026-09-16 实施并推送（de22047 / c830b9b / cd5f870）。

---

## 议题一：全局预览统一到一个页面

### 现状：三个预览入口并存

| # | 入口 | 前端文件（行数） | 数据 API | 能力 |
|---|---|---|---|---|
| 1 | `/backtest-training/global-preview/<task_id>`（任务详情页内入口） | `templates/backtest_training/global_preview.html`(110) + `static/js/pages/backtest_training_global_preview.js`(211) | `GET /backtest-training/api/global-preview/<task_id>` → `backtest_report_query_service.build_global_preview_payload`（`app/routes/backtest_api.py:425`） | 只读指标表 + xlsx 导出 + 收益序列导出 |
| 2 | `/backtest-multi-product/global-preview/<task_id>` | `templates/backtest_multi_product/global_preview.html`(269) + `backtest_multi_product_global_preview.js`(727) | `GET /backtest-multi-product/api/global-preview/<task_id>` → `backtest_multi_product_preview.build_multi_product_global_preview_payload`；另有 `calculate-ratios` / `ratios`(PUT) / `return-series` 三个 API（`app/routes/backtest_api.py:285-321`） | 比例编辑 + Word 导出 + 收益序列导出 |
| 3 | `/global-preview` 与 `/global-preview/single_product`（独立"全局预览中心"） | `templates/global_preview/index.html`(79) + `static/js/pages/global_preview_index.js`(152) | `GET /global-preview/api/tasks/<task_id>` + `POST .../preview-group`（`app/routes/global_preview_api.py:36-71`）→ `build_global_preview_initial_payload` / `build_global_preview_group_payload` | 仅支持 C 系单品（`backtest_training` + `google_sheet` C 系）；多品显式"预留未适配"（`global_preview_api.py:31-32`） |

### 关键事实

- **#3 本来就是一次"统一预览中心"的尝试**：数据层与 #1 同源（都在 `backtest_report_query_service`），缺口只剩多品。
- #1 与 #3 功能高度重叠（同数据源、同为只读分组表）；#2 独有比例编辑与 Word 出口。
- 前端两两 JS 相似度很低（#1 vs #2 约 12% 相同），重复在数据语义与"分组指标表渲染"，不在代码复制。

### 结论与建议

**推荐方向 A：以 #3 预览中心为唯一预览 UI，多品能力并入。**

- 后端（小）：`global_preview_api._preview_status` 放开 `backtest_multi_product`；preview-group 协议扩展接收 `group_key + ratios`，内部适配 `build_multi_product_global_preview_payload`。多品三个 ratio/return-series API 原样保留。
- 前端（中）：hub 页增加比例编辑面板与 Word 导出按钮（从 #2 移植）；任务详情页"全局预览"链接改跳 hub。
- 下线 #1、#2 页面路由，旧 URL 重定向到 hub（防书签失效）。

**方向 B（保守）：** 保留 #2（功能最全）为唯一任务侧预览页，#1 下线改跳 #2，#3 维持只读中心。改动最小，但"两个预览页"长期共存。

风险提示：#3 的 preview-group 协议按 `result_ids` 拉分组，多品按 `group_key + ratios` 组织，协议需要统一抽象；导航注册 `app/navigation.py` 与详情页入口需同步。

---

## 议题二：Word 导出接口透出 V1 数据与绘图数据（Web 直接看结果）

### 现状

- **Word 与 Web 指标同引擎同源**：`generate_word` → `_build_benchmark_runs`（`app/services/strategy_backtest_report_service.py:174`）→ `performance_analyzer.get_calculate_metrics_v1_with_dataframes`（:220/:240）→ `calculate_v1_metrics`——与页面 `/performance_analysis/analyze`、`/v1/analyze` 是同一套 V1 引擎与指标函数。结果载体 `MetricsV1Result{schema_version, metrics, canonical_metrics, index_df, start_df, excess_df}`（`app/services/performance_analysis/response_dto.py:12-20`）。
- **Word 版面** = 通用 blocks JSON（`app/services/word_export_template.py`：heading/metadata/table/paragraph/bullet_list/image）+ 服务端 matplotlib PNG（`generate_report_charts`：净值/回撤/日收益面板/累计超额/月度超额分布/年度收益对比 + 相关系数热力图，注入见 `strategy_backtest_report_service.py:81-97`）+ 结论。
- **图表数据中间层已是纯 dict**：`_build_chart_data`（:1280）产出 `{dates, benchmarks[{label,nav,drawdown,daily_returns}], strategy_nav, strategy_drawdown, excess_series, monthly_excess, benchmark_annuals, ...}`——天然可 JSON 化。
- 当前接口只回 docx 文件流；没有任何 JSON 预览出口；结果经磁盘缓存 `get_or_build_word_export`（`app/utils/ttl_cache.py:143`）。
- **Web 端图集与 Word 图集不同**：绩效分析 V2 页 Chart.js 画 9 张图（年度收益/年超额/最大回撤/Kama/Sortino/月波动率/月超额/夏普对比/盈利月占比，`static/js/pages/performance_analysis_v2.js:1457-1797`），数据来自 analyze 接口的 metrics JSON；Word 是另一组 matplotlib 图。指标同源，图不重合，且页面展示与报告之间隔着重算（runtime_params 可能不同）。

### 结论：可行，成本低，建议加"报告预览"端点

**推荐**：新增只读预览端点 `POST /api/exports/backtest-reports/word/preview`（复用 `StrategyBacktestReportSchema` 校验），内部复用 `_build_benchmark_runs` + `_build_report_data` + `_build_chart_data`，返回：

```json
{ "metadata": {...}, "blocks": [...], "chart_data": {...}, "benchmark_labels": [...] }
```

不生成 docx、不进 docx 缓存。前端做一个"报告预览"视图（弹窗或独立页）：`blocks` 直渲染表格/段落，`chart_data` 用 Chart.js 重画（与 Word 图一一对应）。**Web 所见即 Word 所得**——同一次计算、同一份指标。

不推荐的两个替代：
- 把 JSON 混进 docx 文件流响应——文件流无扩展点，前端解析别扭；
- 前端拿页面 analyze 结果自己拼报告——会退回"页面指标 ≠ 报告指标"的老问题（两次计算、runtime_params 不同源）。

注意点：预览与导出必须同参同payload；预览端点同挂 `_export_limit` 限流（`app/routes/export_api.py:36-39`）；预览每次重算无缓存，如需缓存另走轻量 TTL，不复用 docx 磁盘缓存。

与无风险利率改造天然联动：预览端点让 rf 调参"改一次看一次"，不必反复下载 docx 验证。

---

## 议题三：单/多品前端统一 + 多品后端 Sheet/K 线优化

### 3.1 前端统一可行性：detail/result/list 可统一，create 不强并

实测重复度（`git diff --no-index --numstat`，相同行占比相对 training 侧）：

| 页面对 | 相似度 | 判断 |
|---|---|---|
| detail.js（1250 vs 1356 行） | ≈91%（约 55 个函数逐字相同，C3 指标汇总整块一致） | **可统一** |
| result.js（897 vs 946 行） | ≈94%（图表函数成对复制：buildLineChart/buildBarChart/renderCharts/renderSharpeCompare 等） | **可统一** |
| list.js（528 vs 508 行） | ≈84% | **可统一** |
| create.js（1308 vs 997 行） | ≈23%（单品=单 Sheet+年份勾选；多品=产品卡片+比例，表单本质不同） | 不强并，只抽公共小件 |

本质差异点（统一时以配置注入）：结果读取端点（`/backtest-training/api/task-result/<id>` vs `/backtest-multi-product/api/task-result/<id>`，`static/js/common/api.js:152/:176`）、config 字段结构（单品 `sheet{}/stock_code/recent_years`，多品 `products[]/start_date/weighting_mode`，归一化在 `app/services/backtest_multi_product_service.py:169-234`）、多品多出比例编辑与 global-preview API。

**建议**：新增 `static/js/common/backtest/` 公共层（result-core / detail-core / list-core），差异以初始化配置传入（API 端点、字段映射、额外面板开关）；**页面 URL 与路由不动**（`app/routes/pages/backtest_training.py`、`backtest_multi_product.py` 的 PAGES 表保持，书签不破）。渐进顺序 result → detail → list；剪贴板四件套、股票搜索、Sheet 选择器等小件可先上移 `common/`。

风险：静态页面无构建系统（普通 script），要控制全局命名与加载顺序；公共层每次改动需回归两套页面。

### 3.2 多品后端循环：用户三点判断逐一核实

**(1) 同一 Sheet 反复重连 —— 属实。**
主循环每步调 `_init_google_sheet`（`app/services/backtest_multi_product_service.py:859`）→ 每次新建 `GoogleSheet` 实例（`app/services/google_sheet_tasks/base.py:1217`）→ `_connect_and_select_worksheet` 每次都 `Credentials.from_authorized_user_file` + `gspread.authorize` + `open_by_key`（网络请求，`app/services/google_sheet_client.py:54-68`）。**client 层零缓存**（全文件无任何 client/spreadsheet 缓存；`_reconnect` :493-536 同样全量重来）。N 个产品共用同一 spreadsheet = N 次完整重连。对照组：单品任务整个生命周期只连一次。

修复方向（两层可选）：
- **最小改法**：多品循环内 spreadsheet 未变化时不重建连接（把 :859 提升为"变化才建"），影响面最小；
- **通用改法**：`google_sheet_client` 按 `(token 身份, spreadsheet_id, worksheet)` 做进程级对象缓存。注意 gspread 6.x 基于 requests Session（非线程安全），任务线程模型下需按任务隔离实例或加锁；缓存生命周期要和任务取消、看门狗重启、Sheet 占用锁（`app/services/task/runtime.py:84-110` 按 spreadsheet 上锁）对齐。

**(2) 同 Sheet 换产品强制滞空 —— 属实。**
`sheet_kline_cache` 按 `spreadsheet_id::sheet_name` 只记"上一次组合身份"（`_build_sheet_cache_key` :760-765）；命中但 `product_index` 不同 → 强制 `rewrite_kline=True` 并清空缓存组合（:868-872）→ 清空输入列 + 等 20 秒 + 整段重写 K 线（:876-881；同款逻辑训练侧 `backtest_training_service.py:383-394`、:557-611）。**"滞空"= 清空输入列后固定等待**，不是补行/日期对齐。跨产品不存在"同源跳过"：`_is_same_kline_source`（:1022-1029，比较 Kline_key/stock_code/kline_signature）只对同产品相邻参数组生效。

**(3) 用户提议方案评估：**

- **"多产品 K 线长度正常一致"——成立**：全任务共享 `start_date/end_date`（`normalize_multi_product_config` :173-180），按各自交易日截取，下限 100 条（:1101-1102）。
- **"本地缓存直接比较，不够再滞空"——可行且低成本**：现有 `sheet_kline_cache` 条目加 K 线摘要（stock_code + kline_signature + 长度 + 日期首尾），跨产品同表先本地比较，一致则跳过清空/等待/重写（把 `_is_same_kline_source` 的思路扩展到跨产品）。**摘要必须含日期首尾**，否则有读到脏输入列的风险。
- **"不够再滞空"的按需清理**：现在滞空上界 = 历史最大 K 线长 `column_A_length + 2`（:867），本意是清残留尾行。可改为：仅当新 K 线比上次长时才 `clear_range` 尾部区间，否则整段覆盖写即可——再省一次 clear + 20 秒等待。
- **"Sheet 函数取一列最新单元格"**：gspread 无"最后非空单元格"原生读取；现有 `get_last_row(col)` 就是 `col_values` 整列拉取（`google_sheet_client.py:200-209`），一次整列网络读，没有更省的现成能力。若本地摘要可信可完全不读；若要兜底校验远端状态，一次整列读也远好于"20 秒等待 + 全量重写"。
- **会话级 K 线缓存**：现只有任务内 `kline_cache`（按 product_index，:816/:860-863）；`KlineService` 本身无任何缓存。跨任务长 TTL 缓存有行情新鲜度风险，建议维持任务级；"同批固定产品"的复用已由 DB 级固定产品缓存覆盖（:607-689）。

---

## 议题四：Google Token 去文件路径化

### 现状事实链

- Admin 管理页**已经是纯 JSON 粘贴**（`templates/admin/config.html:133-134`，无文件路径框），`POST /api/google-sheet-tokens/import` 接收 `token_context / token_file` 双字段（`app/routes/google_sheet_api.py:136-157`）。
- DB 双字段（`app/models.py:775-776`）：`token_context` = JSON 原文；`token_file` = **后端生成**的运行时落地路径 `data/google_sheet_tokens/token_<id>.json`（`google_sheet_token_service.py:113`、`ensure_token_file` :286-300 把 JSON 写盘后回写路径）。
- **消费侧只认文件**：`google_sheet_client.py:55`（及重连 :503）`Credentials.from_authorized_user_file(路径)`——从不读 DB 里的 JSON 原文。这就是"文件地址注入"的实质。
- 旧建单页仍有"输入文件路径导入"入口 4 处（`google_sheet_c4/create.html:157-160`、`google_sheet_create.js:433-452`、`google_sheet_c31_create.js:611`、`google_sheet_c7_create.js:942`），走 import 的 `token_file` 分支（仅当 `token_context` 为空时后端按路径读本地文件，`google_sheet_token_service.py:266-284`）。
- **隐患**：C4/C5 页面暴露的 `token_type=json` 提交的 `token_json` 字段后端 0 处处理（全仓 grep 无结果），json 模式任务运行时会静默回退默认文件 `data/token.json`（`base.py:1165`）。

### 结论：可改为 DB JSON 直读，且应该改

**技术可行性已验证**：当前凭据是 OAuth 用户凭据（`google.oauth2.credentials.Credentials`），其 `from_authorized_user_info(info, scopes)` 在本机 google-auth 环境实测存在（gspread 6.2.1）。即 `gspread.authorize(Credentials.from_authorized_user_info(json.loads(token_context), SCOPES))`，凭据不落盘。

收益：少一处凭据磁盘明文（符合 AGENTS 红线精神）；消除 `token_file` 唯一约束与多 worker 写盘竞争；旧"文件路径导入"入口可名正言顺下线；顺带清理 `token_json` 假字段。

改动面：`google_sheet_client` 授权两处（:55、:503）、`ensure_token_file` 退役、任务执行侧 token 解析（`base.py:1165` 改为按 `token_id` 从 DB 取 `token_context`）、`performance_analysis/sheet_reader.py:50-54`、`google_sheet_registry_service.py:138-153`（签名从 token_file 改 token_context）、4 个旧页面入口与 C5 详情弹窗文案清理。

需裁决的兼容点：存量任务 `config` 里已注入 `token_file` 路径、SystemConfig 默认 `token_file=data/token.json`（`app/config.py:197-200`）。按"全库无兼容层"原则建议**单路径切换**：执行时 `config.token_id → DB token_context` 直读，`token_file` 字段退役不再消费；正在运行中的旧任务重启后自然走新路径（config 里有 token_id 即可）。`data/token.json` 默认值仅保留给未选 token 的历史任务。

---

## 附 A：无风险利率改造（上轮结论摘录，仍待确认）

- 现状：展示层 `strategy_backtest_report_service.py:430` 读 `metadata.risk_free_rate`（无人传，恒显 "0.00%"）；计算层 `performance_analysis/metrics.py:192-195` 夏普公式 rf=0 硬编码。
- 改动清单：弹窗（`templates/performance_analysis/v2.html:733-766` 重设计 + 加输入框）→ `confirmWordExport()` 双通道写入（`metadata.risk_free_rate` 展示 + `runtime_params.risk_free_rate` 计算）→ `MetricsRuntimeParamsDTO` 加字段（`request_dto.py:15`）→ `calculate_sharpe_for_period` 公式改 `(月均收益 − rf/12) × 12 / 年化波动` 并逐层透传（metrics.py:304/953/957、text_analysis.py:242）→ fixture 与单测同步。
- 缓存无需动：Word 导出缓存键是整个 payload 的规范化 JSON 哈希（`ttl_cache.py:172-175`），rf 变化自动 miss。
- 待确认三口径：① 生效范围（仅 Word 导出重算，还是页面 analyze 同用）；② 输入单位（建议百分比输入、小数存储，与现有阈值一致）；③ 其他三个无弹窗的 Word 导出入口维持 rf=0 默认。

---

## 决策清单（请逐条确认后开工）

1. **全局预览**：方向 A（hub 扩多品、收编 #1/#2）还是方向 B（只合并 #1/#2）？
2. **Word 预览**：新增 `word/preview` JSON 端点 + 前端预览视图，是否接受？预览图集按 Word 版面（6-7 图）还是 Web 图集（9 图）？
3. **前端统一**：抽 `common/backtest/` 公共层、按 result → detail → list 三步走、create 不强并——是否接受？
4. **多品后端**：以下做哪些？ a) 连接复用（最小改法：循环内变化才重建 / 通用改法：client 层缓存）； b) K 线摘要跨产品比较、同源跳过滞空； c) 按需清理（只在变长时清尾部）； d) 维持任务级 K 线缓存不做跨任务缓存。
5. **Token**：DB JSON 直读单路径切换（token_id → token_context，token_file 退役）是否接受？旧页面"文件路径导入"入口直接删除还是保留只读提示？
6. **无风险利率**：三口径按附 A 建议执行？

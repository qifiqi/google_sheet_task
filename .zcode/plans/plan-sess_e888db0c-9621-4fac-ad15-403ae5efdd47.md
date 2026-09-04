## 结论与目标

可以中断当前全库回填。你截图里的 C7 历史 `calculate_metrics` 确实已经有超额相关的历史字段：`excess_sharp`、`excess_of_promissory_note`、`index_sotino_ratio`、`start_sotino_ratio`，以及现有的收益/回撤/卡玛字段；当前代码已有 alias 映射把它们转换为 `excess_sharpe`、`excess_sortino`、`index_sortino_ratio`、`start_sortino_ratio`。

缺的关键是年度最大修复天数这两个新字段（历史 27/28 键摘要没有它们），所以仅靠 alias 不能补齐这行。对有 `TaskResultReturn` 的单品/C7/回测训练结果，兼容层应在**读取预览时按需从收益序列重算**；无收益序列时保留历史已存指标并让真正不可恢复的新字段显示 `-`。这样无需全库写回，也不会影响原始任务结果。

多产品已走“读取收益序列 → 组合 → 当前口径重算”的路径并有 LRU 缓存，因此主要需要确认并补足它的旧字段 alias 读取；不改其组合算法。

## 事实核实

- 线上 `result_id=2855596/2855597/2855598` 当前仍为旧结构：顶层 Sheet 键下有 `calculate_metrics`，没有 `metrics_payload`。
- 旧 `calculate_metrics` 含 27 键，实际含：
  - `index_sotino_ratio` / `start_sotino_ratio`
  - `excess_sharp` / `excess_of_promissory_note`
  - `excess_returns`、`monthly_excess_returns`、`index_kama_ratio` 等。
- 当前运行时的历史 alias 已定义在 `app/services/performance_analysis/historical_metrics.py:12-22`，但 `extract_core_metrics()` 回退 legacy 结构时没有统一调用它，是全局预览中 alias 可能不生效的缺口。
- 年度最大修复天数历史没有等价字段，但这三条有 `TaskResultReturn`（251/752/1255 行），按当前 V1 公式重算后得到完整指标；线上 dry-run 已验证对应值可得。

## 实施计划

### 1. 建立集中运行时兼容模块
新增/扩展 `app/services/performance_analysis/historical_metrics.py`：

- 让 `extract_core_metrics()` 对 `metrics_payload.metrics`、legacy `calculate_metrics`、legacy `analyze_result` 三条路径都统一调用 `upgrade_historical_metrics()`，确保所有消费者都看到标准键名。
- 新增一个只读的“完整预览指标解析”工具：
  1. 先返回升级后的已存指标；
  2. 只有当预览必需的新增键（年度修复天数及其关联 V1 字段）缺失、且关联 `TaskResultReturn` 或旧 result 内嵌收益序列可用时，调用 `parse_return_series_fields()` / `extract_return_rows()` 和 `calculate_v1_metrics()` 按当前口径重算；
  3. 将重算 metrics 仅用于当前请求，不写 `TaskResult.result`；
  4. 无序列时回退升级后的历史指标，不以重算失败覆盖原有历史显示。
- 回填脚本保留为可选离线迁移工具，但不再是页面正常展示的依赖。

### 2. 单品全局预览接入按需兼容
修改 `app/services/backtest_training_api_service.py`：

- `_query_global_preview_results()` 的 `load_only` 补入 `TaskResult.return_series_id`。
- 对当前分组的 result IDs 批量查询 `TaskResultReturn`，构建 `return_series_id -> series` 映射，避免循环中的 N+1 查询。
- `_build_global_preview_payload_from_results()` 通过集中兼容工具取 metrics；只有历史缺键的当前分组结果才重算。
- C7 原始 Sheet 单元格/版本归一化（C7.0.2/0.3）保持不变；仅替换固定 20 项摘要行的指标来源。
- 为避免重复计算，在该请求内按 result ID 复用结果；不引入跨请求的大型单品缓存，保持现有按分组懒加载的性能策略。

### 3. 单品结果预览与导出接入同一兼容层
修改 `app/services/backtest_training_api_service.py` 的 `_extract_task_result_payload()` / `_build_backtest_result_export_data()`：

- 已存标准/legacy metrics 先经统一 alias 升级；
- 当单个结果的预览必需指标缺失且有收益序列时，按需重算补全再交给现有结果页、Excel 导出预览和 Word 相关数据构造；
- 路由 `app/routes/backtest_training.py` 在调用前提供关联收益序列或由 service 批量/单条载入，保持路由层不出现公式逻辑。

### 4. 多产品与 C 系列边界

- **多产品**：保留当前 `backtest_multi_product_service` 的“序列优先、组合后重算、64 项 LRU”机制；只确认其历史 alias 也走统一兼容函数。不会把单品公式/比例线性加权混进去。
- **C7 / backtest_training**：有序列的历史任务可完整按需恢复。
- **C3/C4/C5**：新结果有 `TaskResultReturn` 时同样适用；老结果若没有独立序列，运行时只能升级旧字段名，无法凭 Sheet 单元格可靠恢复年度修复天数等新指标，保持 `-` 而不伪造数值。

### 5. 修复天数返回格式
保留刚完成的改动：

- `maximum_number_of_backtest_repair_days()` 始终返回 Python `int`；
- `yearly_max_repair_days()` 始终返回 `{int 年份: int 天数}`。

这避免 numpy `int64` 作为 JSON 字典键导致 `metrics_payload` 持久化失败，也使全局预览的“年度最大回测修复天数”可以稳定取 yearly 字典中的最大值。

### 6. 测试与验证

新增/更新测试覆盖：

1. 历史 `calculate_metrics` 的 `sotino` / `excess_sharp` / `excess_of_promissory_note` alias 在全局预览和结果预览都能显示；
2. 缺年度修复天数 + 有 `TaskResultReturn` 的历史结果：按需重算后全局预览展示完整值；
3. 缺序列的历史 C3/C5：保留已有旧指标、只让不可恢复的新行为空；
4. 批量全局预览读取中收益序列是批量加载，避免 N+1；
5. 多产品历史展示不回归，现有组合/缓存测试通过；
6. 以线上任务 `ffcffe40-...` 三条结果的真实结构构造 fixture，验证截图中的 4 行在运行时补齐，不执行数据库写入。

## 当前后台脚本为什么一直没结束

刚才的 `--all --apply` 设计有缺陷：它先把匹配到的所有结果 ID 物化到内存，再对大表结果分块扫描；同时逐条 V1 重算、逐条远程 PostgreSQL 提交、并输出日志。线上 `t_param_task_results` 超过 170 万条，这会导致扫描和网络提交极慢。且线上查询看到目前 `metrics_payload` 计数仍为 0，说明尚未成功写入任何一条；可以安全中断，随后改用上面的运行时兼容层。
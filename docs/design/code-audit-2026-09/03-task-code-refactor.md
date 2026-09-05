# 任务执行代码重构方案（公共层提取 + 拆包）

> 回答两个问题：① C3~C7 各任务独立实现 K线/时间/参数/GoogleSheet/结果保存是否合理？——**不合理，其中两类（IO、结果保存）已下沉且工作良好，四类（主流程、K线、时间、参数展开）是复制-改参式重复，约 60~70% 可下沉**。② 能否拆到独立目录？——**能，且应先提公共层、后拆目录**（拆目录只是搬家，去重才是收益）。

## 1. 现状证据

### 1.1 类结构

| 文件 | 行数 | 类名 | 继承 | 说明 |
|---|---|---|---|---|
| google_sheet_service_base.py | 615 | BaseGoogleSheetService | object | 只下沉了日志/落库/通知/Sheet 初始化 |
| google_sheet_service.py (C3) | 1041 | GoogleSheetService | Base | 四个类**同名**，靠 runtime.py import 别名区分 |
| google_sheet_service_C4.py | 680 | GoogleSheetService | Base | 同上 |
| google_sheet_service_C5.py | 1052 | GoogleSheetService | Base | 同上 |
| google_sheet_service_C7.py | 1329 | GoogleSheetService | Base | 同上 |

四个同名类是坏味道：grep/IDE 跳转无法区分。全部改名为 `C3Service/C4Service/C5Service/C7Service`（C5 批）。

### 1.2 重复度矩阵（实测）

| 逻辑 | C3 | C4 | C5 | C7 | 结论 |
|---|---|---|---|---|---|
| execute_task 主流程 | ~70% 同源（125 行） | **=C5=C7 逐字 97 行**（diff=0 实测） | **=C4=C7 逐字** | **=C4=C5 逐字** | 下沉为模板方法 |
| K线五步流水线（取数→校验→投影→日期校验→年度拆分） | 独立实现 | 相似（price_field 硬编码 ×4 绕过统一映射） | 相似 | 相似（超集） | 下沉 KlinePreparation |
| 时间/日期处理（end_date/exclude_recent_years 回退） | 独立（year_n 语义） | 相似 | 相似 | 与 C5 逐字同段 | 下沉工具函数 |
| 参数展开 _get_all_parameters | 异构（按索引展开） | 8 参 static | 11 参 | 13 参（与 C5 diff ~15%） | 下沉骨架+策略 |
| Google Sheet IO | 共用 base/client | 共用 | 共用 | 共用 | ✅ 已下沉 |
| 结果保存 | 共用 _save_task_result | 共用 | 共用 | 共用 | ✅ 已下沉 |
| 引导序列（滞空→写K线→写参数→读初始结果） | _write_parameter_cells | 自写 | set_googl_val | set_googl_val | 下沉 SheetSession |

**超长方法（>100 行，12 个）**：C7 `_execute_parameter_combination` 307 行、C7 `_get_all_parameters` 243 行、C5 同名 249/240 行、C5/C7 `get_bdl` 218/191 行、C4 `get_bdl`/`_execute_parameter_combination` 各 163 行、C3 `get_bdl` 163 / `cell_kline_data` 141 / `execute_task` 125 行、C4 `_get_all_parameters` 114 行。

**逐字/近逐字重复块**：`_build_stock_param_result_payload` 的 analyze_result 40 行字段块 ×4；`_to_decimal_ratio` ×2（逐字）；`_get_resume_start_index` ×2（逐字）；`_deduplicate_parameter_combinations` ×2（差 4 行）；`check_result`/`_validate_check_values` 闭包 ×4 变体；"滞空+等待20秒"段 ×4；check_task_status + safe_db_operation 闭包 ×4；K线→cell_updates 写入循环 ×5。

**魔法参数漂移**（同一语义不同值，无出处注释）：K线 limit 系数 C4=250 vs C5=300；min_rows C3=100 vs C4/C5/C7=30；轮询 `range(60)`；刷新点 `[3,5,8]` vs `[5,15,25,35]`；固定睡 20/30 秒；`len(all_kline)+20`。

**模板几何坐标无集中定义**：C3 B6/B7/B9…I15-I23、C4 D2-D20、C5/C7 output_range/column_j/column_l、C7 默认布局 "D2:D20"/"D8:D26"/"D22:F25"、CC-CG 列、row_offset=6——散落全文件。

### 1.3 异常处理现状

- C5 专属异常 `c5_exceptions.py`（149 行 7 个类）**全库零 raise**，死代码（删除，见 01 文档 CLN-01）；
- 四文件共同依赖空壳 `checkForErrors`，靠中文消息字符串区分错误（CLN-04 改名 `SheetCheckError` 并加 error_code）；
- `_raise_retryable_network_error` 只在 C7（1 处）和 backtest 系有，**C3/C4/C5 的 get_bdl/execute_task 未包装**——底层 client 抛 `RetryableNetworkTaskError` 时 watchdog 能看到信号，但 service 层自产异常（如 KlineService 拉数失败）不打网络标记，四类任务可重启信号不一致 → 提为基类方法后 C3/C4/C5 补齐。

### 1.4 回测家族重复

- backtest_training_service（执行侧 941 行）与 backtest_multi_product_service（执行+预览混装 1484 行）：后者继承前者复用 `_execute_parameter_combination`/`_save_task_result`，方向正确；
- backtest_training_api_service（1462 行）实为**纯读侧导出服务**，名字名不副实（改 `backtest_report_query_service`，C6 批）；
- 三件套内部复制 ~15%（400-500 行）：年最大超额回撤推导两份同构、20 项汇总指标契约两种格式各实现一遍（SUMMARY_ROW_DEFS vs 硬编码 rows）、K线获取两份、`_sanitize_json_value` 在已有共享实现下又复制；
- `backtest_multi_product_service.py` 前半执行后半预览/Word 报告——执行与展示混装，预览部分（~260 行 + 模块级 700 行预览辅助）应拆出。

## 2. 目标结构

```
app/services/google_sheet_tasks/          # 新包：C 系任务（C5 批落地）
├── __init__.py                           # 对外暴露 C3Service/C4Service/C5Service/C7Service
├── base.py                               # run_task() 模板方法 + SheetSession 引导 + 公共异常
├── kline_prep.py                         # K线五步流水线（KlinePreparation，配置对象收敛魔法参数）
├── param_expand.py                       # 参数展开骨架（recent/full 拆分、年份窗口）+ C3 索引展开器
├── result_payload.py                     # StockParamResultPayloadBuilder（analyze_result 4 份合一、
│                                         #   _to_decimal_ratio、百分比解析）
├── check_policy.py                       # 结果就绪判定策略（C3 检查位 / C4 D2D3 变化 / C5、C7 回显校验）
├── layouts.py 不设——布局常量放各任务文件顶部
├── c3.py / c4.py / c5.py / c7.py         # 各任务钩子实现 + 布局常量 + 真正的领域逻辑
└── backtest/                             # 回测执行侧（C6 批）
    ├── training.py                       # 原 backtest_training_service.py
    ├── multi_product_exec.py             # 多品执行（继承 training）
    └── summary_contract.py               # 20 项指标契约单一来源（SUMMARY_ROW_DEFS 迁入）
```

读侧不动：`backtest_training_api_service.py` 改名 `backtest_report_query_service.py`（C6 批，纯改名 + import 收敛）；预览/Word 构建从 multi_product 拆到既有 export 域服务。

旧文件 `google_sheet_service*.py` 在 C5 批完成后**删除**（无兼容层，`runtime.py` 的 import 与 `google_sheet_api.py:16` 一次性切换）。

## 3. 公共层设计

### 3.1 模板方法 run_task()（C1 批，收益最大风险最低）

```python
# base.py
class BaseGoogleSheetService:
    task_kind: str                      # "c3"/"c4"/"c5"/"c7"，用于日志与通知
    def _resolve_sheets(self, config): ...      # 钩子1：单表/多表解析（现 _init_google_sheet 参数化）
    def _run_batch(self, task, config): ...     # 钩子2：原 get_bdl 主循环
    def _finalize_success(self, task, result): ...  # 钩子3：完成通知差异
    def run_task(self, task):           # 原 execute_task 97 行骨架，唯一实现
```

C4/C5/C7 的 `execute_task` 直接删除（97 行 ×3 → 1 份）；C3 的 125 行版本对比骨架补齐差异点（额外取消检查、multiplier final_status——先确认 L545-557 `stock_param is None` 死分支删除后差异是否归零）。

### 3.2 KlinePreparation（C2 批）

五步流水线参数化为配置对象，消除魔法参数漂移：

```python
@dataclass
class KlinePrepPolicy:
    limit_factor: int            # C4=250 / C5=300（记录出处后统一或显式保留差异）
    min_rows: int                # C3=100 / C4~C7=30
    price_field: str | None      # None=走 get_kline_price_field() 统一映射（修 C4 硬编码）
    include_ohlc: bool = False   # C7
    date_window: ...             # C3 year_n 语义 / C4~C7 start_end 语义，策略注入
```

顺带修复：C4 四处 `'open' if market_type == 'cn' else 'close'` 改走 `get_kline_price_field()`（kline_service.py:51 注释声明的唯一映射入口）。

### 3.3 get_bdl 公共批量执行器（C3 批）

下沉：total_steps 计算、断点恢复 `_get_resume_start_index`、cancel 双检、单组合 try/except、`_save_task_result` + `send_stock_param_result_data` 编排、`check_task_status + safe_db_operation` 闭包。C5/C7（85% 相同度）先行合并验证，C4（60%）跟随。任务差异以策略对象/钩子注入，**去重键（A1/B1/K线区间）等业务规则留在各任务文件**。

### 3.4 其余公共件

- `result_payload.py`：analyze_result 40 行字段块 ×4 合一；
- `check_policy.py`：`check_result` 四变体改为策略接口（检查位校验 / 变化检测 / 参数回显校验）；
- Sheet 引导序列（滞空→等待→写K线→写参数→读 initial_results）：公共 `SheetSession`，C3 的卡死检测/滞空重写作为可选策略保留；
- 异常：`SheetCheckError(error_code)` 替代 checkForErrors；`_raise_retryable_network_error` 提为基类方法，C3/C4/C5 的 get_bdl 补齐调用，使 `[NETWORK_RETRYABLE]` 覆盖一致。

## 4. 必须保留的任务特异性（不要强行抽象）

| 任务 | 保留内容 | 理由 |
|---|---|---|
| C3 | `_write_parameter_cells` 卡死检测/滞空重写；`_attach_return_analysis`（xpl 收益附加）；`year_n` 语义 | C3 独有产品行为 |
| C4 | 市场取价规则（经统一映射后） | 产品差异 |
| C5 | custom kline 来源切换（任务级开关）；`_deduplicate_parameter_combinations` 去重键定义 | 业务规则 |
| C7 | `_get_c7_layout`/`_get_c7_model_version` 双版本布局；OHLC 校验与 `_calculate_c7_0_3_index_returns`；random_price 分组（`_expand_random_price_groups`，种子按任务+股票+分组固定） | C7 真领域逻辑 |
| 全部 | 模板单元格坐标常量（B6/I15、D2:D20、CC-CG…）集中在各任务文件顶部 | 布局属模板，不沉公共层 |

## 5. 批次计划

| 批次 | 内容 | 验收 |
|---|---|---|
| **C1** | `run_task()` 模板方法 + 四类改名 `C3Service~C7Service` + 删 C3 stock_param 死分支 | pytest 全绿；C4/C5/C7 execute_task 不复存在（grep `_execute_google_sheet` 仅剩 runtime 4 个薄包装）；diff 工具确认无行为变化 |
| **C2** | KlinePreparation + 修 C4 硬编码 + 魔法参数配置对象化（漂移值先按文件原值记录） | K线相关单测（构造 fake 行情）覆盖 4 任务；limit/min_rows 全部来自 policy |
| **C3** | get_bdl 公共批量执行器（C5/C7 先合，C4 跟随，C3 视差异合入） | 断点恢复/取消/保存路径各有单测；`_execute_parameter_combination` 超长方法拆到 <150 行/个 |
| **C4** | result_payload + check_policy + SheetSession + 异常统一（SheetCheckError、retryable 补齐） | `checkForErrors` 引用清零；C3/C4/C5 网络失败带 `[NETWORK_RETRYABLE]`（单测断言 error_message 前缀） |
| **C5** | 拆包落地 `app/services/google_sheet_tasks/`，旧文件删除，runtime/api import 切换 | 旧 `google_sheet_service*.py` 文件不存在；grep import 无残留；全量回归 |
| **C6** | 回测家族：`backtest/` 子包 + summary_contract 单一来源 + api_service 改名 + multi_product 预览拆出 | 指标契约单点维护（新增指标只改一处）；backtest_training_api_service 文件名不存在 |

## 6. 全程约束

1. **不改数据库 schema/迁移/数据**；不改 Google Sheet 模板布局（坐标常量只是搬家集中）；
2. **无兼容层**：旧类名/旧文件/旧函数删除，不留 re-export 转发；`tests/archive/` 不改（已排除收集）；
3. 每批一次合入：`python -m pytest tests/unit tests/integration` 全绿 + `git grep` 断言（各批验收列）；
4. 执行链行为（取消、断点、watchdog、通知）在本方案内**只搬不改**；行为变更（如 limit 250/300 统一）必须单独立项列出漂移值与选择理由，不得夹带；
5. 前端零感知：任务类型标识、API 路径、信封字段不变。

> 执行提示词见 `EXECUTION_PROMPT.md` 第 2 节。

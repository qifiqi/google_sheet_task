# 执行提示词（EXECUTION PROMPT）

> 用法：按批次向代理/开发者下达。每批独立合入、独立验收。通用约束见本目录 `README.md` §5，执行时先读 `README.md` + 当批引用的文档章节。

## 第 0 步（任何批次开始前）

```text
阅读 docs/design/code-audit-2026-09/README.md 全文与 AGENTS.md 的"接口规范"章节。
本批只做 <批次号> 范围内的修改，不夹带其他重构。完成后运行：
python -m pytest tests/unit tests/integration
并执行当批"验收"小节的 grep/断言，全部通过后才允许提交。
提交信息格式：fix(audit)/refactor(audit)/docs(audit): <批次号> <一句话>
```

## 1. A 系列批次（Bug 止血）——依据 `01-bugs-and-fixes.md`

### 批次 A1（P0 功能性 bug）

```text
修复 docs/design/code-audit-2026-09/01-bugs-and-fixes.md 中的 BUG-01 ~ BUG-07。
每条严格按该文档"修复需求"执行，逐条给出"验收标准"对应的验证证据（新增测试或 grep 输出）。
特别注意：
- BUG-01 修复时同步统一 create_restart_task 内的取值风格，不留属性/下标混用；
- BUG-03 的回滚逻辑抽成 _rollback_start_reservation 供五条失败路径共用；
- BUG-05 只改代码默认值，不做数据迁移；
- BUG-06 修改 db_retry 时保持裸 raise 保异常链。
```

### 批次 A2（P1 并发与资源）

```text
按 01 文档修复 BUG-08（运行态锁 + 代际误删 + 提交窗口）、BUG-09（调度子进程 PIPE 与锁超时）、
BUG-12（repository 写方法 commit 参数统一），并复验 BUG-03 的验收断言仍然成立。
BUG-08 的并发压测脚本放入 tests/unit/test_runtime_concurrency.py（不依赖真实 DB 网络）。
```

### 批次 A3（P1 数据与安全 + P2 清理）

```text
按 01 文档修复 BUG-10 ~ BUG-17，并完成 CLN-01 ~ CLN-13 全部清理项。
- BUG-10 执行前先 grep 现有 SystemConfig 行，列出受类型收窄影响的 key 清单附在 PR 描述；
- BUG-17 的 admin_required 实现放 app/utils/auth.py，同时在
  docs/design/api-model-query-audit/07-public-deployment-and-subservice.md §1 登记缺口；
- CLN 删除类条目每删一项跑一次 pytest（防误删活引用）。
```

## 2. B 系列批次（接口收敛）——依据 `02-api-spec.md`

### 批次 B1（异常与日志）

```text
执行 02 文档 §12 B1：静默吞异常 4 处补日志；裸 except 清零（含 backtest_training_service 3 处、
C3/C4/C5/C7 各 3 处）；删除 xpl.py 路由内 try/except 改走全局兜底；
8 处 logging.getLogger 统一为 get_logger（CLN-11 清单）；写操作路由/service 补日志（§11 清单）；
实现 admin_required 并为页面路由挂 login_required（BUG-17 联动，若 A3 未完成则在本批完成）。
```

### 批次 B2（信封与分页统一）

```text
执行 02 文档 §12 B2：
1. 信封旁路 5 端点收编：task_api 4 端点对应的 service 手拼源头（task/creation.py、task/restart.py）
   改为"返回数据或抛 AppException"，路由统一 success()/error()；admin_api dashboard_overview 同理；
2. 分页四形状统一为 paginated()（{items,total,pages,current_page,per_page}），
   涉及 result_api / backtest_api / task_api / scheduler_api tasks 与对应前端模板/JS 适配
   （遵守 AGENTS.md：改模板必须同步 JS 回填/取数逻辑）；
3. google_sheet_token_service / google_sheet_service 的 ValueError"不存在"改 NotFoundError（404）；
4. str(exc) 下发 16 处治理：service 抛带用户文案的领域异常，路由删除异常翻译。
前端改造完成后用 04-endpoint-call-chains.md 的问题标记列复查清零。
```

### 批次 B3（校验与职责下沉）

```text
执行 02 文档 §12 B3：parse_body/parse_query 全覆盖（含 PageQuery 分页）；
§11"路由层业务/基础设施逻辑"6 项下沉对应 service
（openpyxl 构建入 export_service、ZIP 编排入 global_preview 导出服务、日志解析合并为一个
log_query 服务、TTL 缓存入 google_sheet_registry_service、权限树入 navigation_service、
payload 推断入 backtest_report_query_service）；
路由 import service 私有符号 5 处改公开函数；同语义双端点（scheduler/status 两处）合并；
GET 内写库治理（BUG-15）与配置脱敏（BUG-14，若 A3 未完成）。
```

### 批次 B4（复验）

```text
全量复验 02 文档 §10 自查清单；grep 断言：
- grep -rn '"status"' app/routes 除 api_response import 外为 0
- grep -rn 'request.get_json(' app/routes 为 0
- grep -rn 'paginated(' app/routes 大于 0
- grep -rn 'str(exc)\|str(e)' app/routes 为 0（白名单：无）
- 04-endpoint-call-chains.md 各表问题标记列逐行复查，标注"已修/移交主服务接入"
输出复验报告到 docs/design/code-audit-2026-09/B4-verification.md。
```

## 3. C 系列批次（任务代码重构）——依据 `03-task-code-refactor.md`

> 每批只做搬家/去重，不改执行链行为；漂移值（limit 250/300、min_rows 100/30）先按原值记录进
> 配置对象，统一与否单独立项，不得夹带。

### 批次 C1

```text
按 03 文档 §5 C1：提取 run_task() 模板方法（C4/C5/C7 execute_task 97 行逐字重复收敛为 1 份，
C3 对比骨架处理差异、删除 stock_param 死分支 L545-557）；四个同名 GoogleSheetService 改名
C3Service/C4Service/C5Service/C7Service，runtime.py import 与别名同步。
验收：grep 确认 execute_task 骨架仅存在于 base；pytest 全绿。
```

### 批次 C2

```text
按 03 文档 §3.2：落地 kline_prep.py（KlinePreparation + KlinePrepPolicy），
四任务 K线五步流水线收敛；C4 四处 price_field 硬编码改走 get_kline_price_field()；
limit/min_rows 等魔法参数进 policy（先保持各文件原值并注释出处）。
```

### 批次 C3

```text
按 03 文档 §3.3：get_bdl 公共批量执行器（先 C5/C7 合并验证，再 C4，最后评估 C3）；
_execute_parameter_combination 拆分到单方法 <150 行。
断点恢复/取消/保存路径新增单测。
```

### 批次 C4

```text
按 03 文档 §3.4：result_payload.py、check_policy.py、SheetSession；
SheetCheckError(error_code) 替代 checkForErrors（6 个 service 引用同步）；
_raise_retryable_network_error 提为基类方法，C3/C4/C5 get_bdl 补齐网络标记，
单测断言 error_message 带 [NETWORK_RETRYABLE] 前缀。
```

### 批次 C5

```text
按 03 文档 §2：拆包落地 app/services/google_sheet_tasks/（c3/c4/c5/c7.py + 公共件），
旧 google_sheet_service*.py 删除，runtime.py / google_sheet_api.py import 一次性切换。
验收：旧文件不存在；grep "google_sheet_service" 全库无残留 import；pytest 全绿。
```

### 批次 C6

```text
按 03 文档 §2/§1.4：回测家族收尾——backtest/ 子包、summary_contract 单一指标契约、
backtest_training_api_service 改名 backtest_report_query_service、multi_product 预览拆出执行文件。
验收：20 项汇总指标契约仅一处定义；旧文件名不存在。
```

## 4. 完成定义（Definition of Done）

- A/B/C 全部批次合入且 `B4-verification.md` 产出；
- `04-endpoint-call-chains.md` 中所有"问题标记"要么已修、要么明确登记到主服务接入缺口清单；
- README §4 的关键数字复查更新（作为整改前后对比留档）；
- AGENTS.md 补记：本次新增的硬性规定以 `docs/design/code-audit-2026-09/02-api-spec.md` 为执法细则。

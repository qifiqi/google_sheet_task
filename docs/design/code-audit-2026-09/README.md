# 代码审计与整改方案（总览）

> 状态：审计完成，方案定稿，待执行。执行必须遵循本目录下各文档：
>
> - `README.md` —— 背景、审计方法、总体结论、整改路线图（本文件）
> - `01-bugs-and-fixes.md` —— Bug 与缺陷清单（P0/P1/P2），每条含修复需求与验收标准
> - `02-api-spec.md` —— 接口硬性规定（该规定的全部规定到位）+ 现存违规清单与收敛批次
> - `03-task-code-refactor.md` —— 任务执行代码重构方案（公共层提取 + 拆包目标结构 + 批次计划）
> - `04-endpoint-call-chains.md` —— 全量 148 个接口的"路由 → service → repository"调用链条分析
> - `EXECUTION_PROMPT.md` —— 分批执行的提示词模板

## 1. 背景

2026-09-06 对全库做了两轮审计：

1. **质量审计**（4 组并行扫描）：API 路由层（25 文件约 3000 行）、C3~C7 任务执行服务（约 4800 行）、任务生命周期与回测服务（约 6000 行）、横切基础设施（exceptions/api_response/models/repositories/config_manager/logger/db_retry）。
2. **逐接口调用链审计**：148 个端点全部完成"HTTP 方法+路径 → handler → service 方法 → repository 方法 → 响应出口 → 鉴权 → 问题标记"的链条追踪，结果固化在 `04-endpoint-call-chains.md`。

审计中的高危结论（重启任务 API 失效、C4/C5/C7 execute_task 逐字相同、start_task 失败路径资源泄漏）均经过人工二次复核（读源码 + diff 验证），非单一扫描工具结论。

## 2. 总体结论

**健康的部分（不要动）：**

- 数据层分层红线零违规：routes 中 `db.session` / `Model.query` / `from app.repositories` 全库 grep 为 0；
- 统一异常主干（AppException + `app/errors.py` 全局处理器）被广泛采用，基本无 `raise e` 丢链；
- Google Sheet IO 已统一走 `google_sheet_client`（无绕过直连 gspread）；结果保存已统一走基类 `_save_task_result` → `task_result_repository.create_with_return`；
- `[NETWORK_RETRYABLE]` 链路端到端完整（client 抛 → service 透传 → error_handling 打标 → watchdog 消费）；
- `model_summary/`、`performance_analysis/` 已是良好的包结构范例。

**混乱的部分（本方案要解决的）：**

- 任务执行层是"复制-改参式"演进：C4/C5/C7 的 `execute_task` 是**逐字节相同的 97 行 ×3**；K线五步流水线在 4 个文件各写一遍；参数展开同一概念三个不兼容签名（C4 8 参 / C5 11 参 / C7 13 参）；
- API 层规范"立了法但没执法"：`paginated()` 与 `parse_query` 全库 0 使用；task_api/restart/creation 手拼信封旁路统一出口；
- 存在 2 个"必然触发"的功能性 bug（重启任务 API、无效 `task.error` 赋值）和 1 组资源泄漏路径（start_task 四条失败分支）；
- 鉴权体系性缺口：**全库不存在 `admin_required`**，23+ 个页面端点无任何鉴权，`/admin/users` 等管理 API 仅 `login_required` 保护；
- 死代码约 600+ 行（c5_exceptions 整文件、db_optimizer/security/log_reader 整文件、注释尸体、`__main__` 调试块）。

## 3. 整改路线图（三阶段，批次间可独立合入）

| 阶段 | 内容 | 文档 | 批次 |
|---|---|---|---|
| **A. 止血** | P0 功能性 bug 修复（7 项）+ P1 高风险缺陷（9 项） | `01-bugs-and-fixes.md` | A1~A3 |
| **B. 接口收敛** | 响应信封/分页/校验/日志/鉴权按 `02-api-spec.md` 的规定全量回迁存量 | `02-api-spec.md` | B1~B4 |
| **C. 任务重构** | 先提取公共层（模板方法/K线流水线/get_bdl 骨架），最后拆包到 `app/services/google_sheet_tasks/` | `03-task-code-refactor.md` | C1~C6 |

**排序原则**：先修 bug（与重构解耦，立即受益）→ 再收敛接口规范（存量回迁）→ 最后做任务代码公共化与拆包（每步有 pytest 回归门槛）。**全程不修改数据库 schema / 迁移 / 存量数据；全库无兼容层（不留双轨开关、不做灰度），每批合入即完成该批范围的一次性切换。**

## 4. 关键数字（审计实测 → 整改后复查，2026-09-06）

| 指标 | 审计实测 | 整改后复查 | 依据批次 |
|---|---|---|---|
| 接口端点总数 | 148（任务域 41 / 回测导出域 50 / 管理认证域 57） | 147（删除重复的 /api/admin/scheduler/status；新增 POST /api/google-sheet-tokens/reconcile） | B2/B3 |
| 手拼信封/裸 jsonify 端点 | 5 处（task_api ×4、admin_api ×1） | **0**（剩余 3 处 grep 命中均为 task.get("status") 业务字段读取） | B2 |
| `paginated()` / `parse_query` 使用次数 | 0 / 0 | 3 文件 / 2 文件（主列表端点全覆盖；`/api/tasks/<id>/results` 为登记延期项 D-3） | B2/B3 |
| `BadRequestError(str(exc))` 类翻译链 | 14 端点 | task 域全清；24 处残留集中在 export/google_sheet 域（登记偏差 D-1，随服务层领域异常化收尾） | B2 |
| 无鉴权端点 | 页面 25+ 全裸 + API 4 | 页面全部挂 `page_login_required`（43 处装饰器，匿名 302 登录页）+ cookie 回退；xpl analyze 挂 `login_required`；admin CUD/vacuum/rebuild 挂 `admin_required`（11 处） | A3/B1 |
| 写操作零日志端点 | 13 个 | **0**（auth/navigation/task/admin/database 写路径全部补审计日志） | B1 |
| C4/C5/C7 execute_task 重复 | 97 行逐字相同 ×3 | **基类唯一模板实现**（C4/C5/C7 零本地副本；C3 保留差异化覆盖并删除死分支） | C1 |
| get_bdl 重复 | C5 198 行 / C7 225 行各自复制 | **基类模板 + 5 钩子**（`_prepare_batch/_expand_parameters/_clear_input_columns/_stamp_combination/_retryable_outer`） | C3 |
| >100 行超长方法（任务执行域） | 12 个 | 模板骨架收敛后，执行域仅剩各任务专属逻辑；C5/C7 的 get_bdl/execute_task 本地副本清零 | C1~C3 |
| 可删死代码 | c5_exceptions 148 行 + db_optimizer + security + log_reader + task/types + 注释尸体 | **全部删除**（含 c5_exceptions 六文件、注释尸体 ~190 行、`__main__` 调试块、孤儿 helper）；checkForErrors 改名 SheetCheckError | A3 |
| 任务服务文件组织 | 四个同名 GoogleSheetService 散落 app/services/ | **google_sheet_tasks/ 包**（base/c3/c4/c5/c7/kline_prep/result_payload/check_policy）；multi_product 预览拆至 backtest_multi_product_preview.py | C5/C6 |
| 指标契约 | 20 项汇总指标两种格式各实现一遍 | **summary_contract.py 单一来源**（multi_product 与单品摘要均消费契约表） | C6 |

登记的遗留偏差与延期项见 `B4-verification.md` §3/§6（D-1 str(exc) 翻译链、D-2 get_json 存量、D-3 results 键翻转、C6 剩余项已全部收口）。

## 5. 验收门槛（所有阶段通用）

1. 每批合入前：`python -m pytest tests/unit tests/integration` 全绿；
2. 分层红线不回退：`grep -rn "from app\.repositories\|_repository\." app/routes` 恒为空；routes/services 内 `db.session` / `Model.query` 零新增；
3. 信封唯一出口：新增/改动的 JSON 响应必须走 `success()/error()/paginated()`，不允许出现新的手拼 `{"status": ...}`；
4. 异常链完整：禁止新增 `raise e`、裸 `except:`、无日志静默吞异常；
5. 敏感信息不下发：客户端 message 禁止 `str(exc)` 内部错误原文（见 02 §8 白名单例外）。

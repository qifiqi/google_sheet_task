# 多 AI Agent 并行开发协作方案

更新时间：2026-05-15

---

## 1. 文档目标

这份文档不是写“产品内 Agent 怎么运行”，而是写“当我们要开发当前平台时，如何把一个复杂需求拆成多个 AI agent 并行执行”，仿照一个完整开发团队来协作。

它适用于这类场景：

- 需求跨前端、后端、任务执行链路、调度器、测试
- 单个 Agent 全包会很慢，而且容易遗漏
- 希望像真实团队一样并行推进，再由主控 Agent 统一集成

---

## 2. 总体协作模型

建议采用“主控 Agent + 专项 Agent”的组织方式。

### 2.1 主控 Agent

职责：

- 读取用户需求
- 判断是否需要并行拆分
- 先建立总体方案和边界
- 拆出可并行的子任务
- 给每个子 Agent 明确文件责任范围
- 统一集成结果
- 统一做风险复核和最终交付

主控 Agent 不应把自己下一步立刻依赖的阻塞任务也直接外包出去，否则会卡住主线。

### 2.2 专项 Agent

专项 Agent 只做边界明确的工作。  
在当前仓库里，推荐优先按“职责域”拆，而不是按“感觉”拆。

---

## 3. 适合当前仓库的 Agent 角色划分

### 3.1 产品/架构 Agent

职责：

- 梳理需求与影响面
- 确认涉及哪些任务类型
- 判断是否会影响 C31、watchdog、scheduler、资源占用
- 给出任务拆分建议

适合处理：

- 新能力设计
- 改造方案评审
- 技术方案初稿

### 3.2 后端编排 Agent

职责：

- 负责 `app/services/task/*`
- 负责任务创建、启动、重启、取消、批量拆分
- 负责运行态状态变更

重点文件范围：

- `app/services/task/facade.py`
- `app/services/task/creation.py`
- `app/services/task/runtime.py`
- `app/services/task/restart.py`
- `app/services/task/occupancy.py`

### 3.3 调度恢复 Agent

职责：

- 负责调度器、watchdog、worker、启动补偿逻辑
- 关注长任务恢复、死任务识别、自动重启

重点文件范围：

- `app/startup.py`
- `app/services/scheduler_service.py`
- `app/services/scheduled_task_worker.py`
- `app/services/task_watchdog.py`

### 3.4 业务执行器 Agent

职责：

- 负责具体任务执行服务
- 负责 Google Sheet / backtest 等业务逻辑消费

重点文件范围：

- `app/services/google_sheet_service.py`
- `app/services/google_sheet_service_C4.py`
- `app/services/google_sheet_service_C5.py`
- `app/services/backtest_training_service.py`
- `app/services/google_sheet_client.py`

### 3.5 前端表单 Agent

职责：

- 负责模板页面字段、回填、localStorage、内联 JS 重建逻辑
- 负责用户输入和提交 payload

重点文件范围：

- `templates/google_sheet/create.html`
- `templates/google_sheet_c4/create.html`
- `templates/google_sheet_c5/create.html`
- `templates/google_sheet_c31/create.html`
- `templates/backtest_training/create.html`

### 3.6 接口契约 Agent

职责：

- 负责 API 请求体、响应体、权限校验、前后端字段对齐
- 适合在“字段改动多”的需求中单独存在

重点文件范围：

- `app/routes/task_api.py`
- `app/routes/backtest_training.py`
- `app/routes/scheduler_api.py`
- 对应文档目录

### 3.7 测试与验收 Agent

职责：

- 找到受影响测试
- 补充最小回归验证路径
- 汇总未覆盖风险

重点文件范围：

- `tests/test/test_p0_p1_refactor.py`
- 与本次需求直接相关的测试文件

### 3.8 评审 Agent

职责：

- 不负责写大块代码
- 负责找遗漏、竞争状态、前后端脱节、资源释放问题

这是最适合最后并行加入的一类 Agent。

---

## 4. 适合并行拆分的任务类型

在当前仓库里，以下任务最适合多个 AI agent 并行推进。

### 4.1 字段新增类需求

例如：

- C31 新增字段
- backtest 新增参数
- C3/C4/C5 表单字段调整

推荐拆法：

- 前端表单 Agent
- 后端编排 Agent
- 业务执行器 Agent
- 测试与评审 Agent

### 4.2 执行链路改造类需求

例如：

- 调整任务启动方式
- 修改断点恢复逻辑
- 统一资源占用释放时机

推荐拆法：

- 后端编排 Agent
- 调度恢复 Agent
- 业务执行器 Agent
- 评审 Agent

### 4.3 平台方案/重构类需求

例如：

- 队列化
- worker 化
- scheduler / watchdog 收敛

推荐拆法：

- 产品/架构 Agent
- 后端编排 Agent
- 调度恢复 Agent
- 测试与评审 Agent

---

## 5. 不适合并行硬拆的任务

以下任务虽然看起来很大，但如果强行并行，很容易互相覆盖：

- 同一个文件内的大规模重构
- 同一个核心状态机的同时改写
- 当前步骤强依赖上一步结果才能继续的任务
- 还没搞清需求边界就开始多 Agent 分工

对于这类任务，建议：

- 先由主控 Agent 做方案和边界收敛
- 再只把可独立落地的部分并行拆出去

---

## 6. 多 Agent 并行开发的标准流程

### 6.1 第一步：主控 Agent 先建立任务地图

主控 Agent 必须先回答：

- 这次改动触达哪些模块
- 哪些模块之间存在严格依赖
- 哪些工作可以并行
- 哪些文件绝不能让两个 Agent 同时写

在当前仓库里，最常见的高风险联动有：

- 模板页面字段和回填 JS
- C31 前端与 `batch_create_and_start_task()`
- 执行服务字段消费与任务 config 透传
- watchdog / runtime / restart 的状态联动

### 6.2 第二步：按写入边界拆 Agent

推荐原则：

- 一个 Agent 一块写入责任区
- 多个 Agent 尽量不要同时修改同一个文件
- 如果必须涉及同一文件，先让其中一个 Agent 只做探索，不做写入

### 6.3 第三步：给每个 Agent 明确输出格式

建议每个 Agent 至少返回：

- 负责范围
- 改动摘要
- 修改文件列表
- 风险说明
- 需要主控 Agent 集成的点

### 6.4 第四步：主控 Agent 集成并做二次校验

主控 Agent 要重点检查：

- 前后端字段是否对齐
- 状态流转是否一致
- 占用是否申请与释放成对
- 重启和取消路径是否仍成立
- 是否影响 watchdog 判断

### 6.5 第五步：评审 Agent 做最终找错

评审 Agent 最适合做的不是重复造方案，而是专项找问题：

- 并发风险
- 漏改链路
- 回填遗漏
- 测试缺口

---

## 7. 推荐的团队式 Agent 模板

下面是最适合当前仓库的“完整开发团队”模板。

### 7.1 角色模板

1. `Coordinator`
   - 主控全局
   - 负责任务拆分和结果集成

2. `Architect`
   - 负责需求边界、影响面、状态机、数据流判断

3. `Backend-Orchestrator`
   - 负责 `app/services/task/*`

4. `Scheduler-Watchdog`
   - 负责 `startup.py` / `scheduler_service.py` / `task_watchdog.py`

5. `Business-Executor`
   - 负责 `google_sheet_service*` / `backtest_training_service.py`

6. `Frontend-Form`
   - 负责模板页、回填、提交 payload

7. `API-Contract`
   - 负责 route 和前后端契约

8. `QA-Reviewer`
   - 负责回归验证和最终 review

### 7.2 最常用的精简版

如果任务不是特别大，建议只开 4 个角色：

1. `Coordinator`
2. `Backend-Orchestrator`
3. `Frontend-Form`
4. `QA-Reviewer`

---

## 8. 针对这次 `app/platform/` 大改的推荐 Agent 编组

这次重构不适合只靠两个 Agent 硬拆。  
更合适的是 6 角色并行，主控统一集成。

### 8.1 推荐编组

1. `Coordinator`
   - 负责总体计划、目录边界、阶段集成

2. `Platform-Model`
   - 负责 `tasks` / `task_executions` / `resource_leases` / `task_packages` 数据模型
   - 负责状态机、重启模式、契约定义

3. `Platform-Worker`
   - 负责 `worker/`、claim、heartbeat、drain、失败恢复

4. `Platform-Executors`
   - 负责 `google_sheet`、`backtest`、`batch_orchestration`
   - 后续再接 `python_script` / `strategy_package`

5. `Platform-Web`
   - 负责新 API、列表查询、详情查询、取消、重启接口

6. `QA-Reviewer`
   - 负责切换风险、资源释放、状态回写、前后端契约查漏

### 8.2 写入边界建议

建议明确写入边界，避免互相覆盖：

- `Platform-Model` 不写执行器具体业务
- `Platform-Worker` 不改前端和路由
- `Platform-Executors` 不改核心状态机
- `Platform-Web` 不改 worker 主循环
- `QA-Reviewer` 默认只读检查，除非主控明确授权修复

---

## 9. 当前仓库下的典型拆分示例

### 8.1 示例一：C31 新增一个执行参数

推荐拆分：

1. `Frontend-Form`
   - 改 `templates/google_sheet_c31/create.html`
   - 同步改字段初始化、回填、localStorage、提交 payload

2. `Backend-Orchestrator`
   - 改 `app/services/task/creation.py`
   - 确保 `batch_create_and_start_task()` 透传到每个 child config

3. `Business-Executor`
   - 改 `app/services/google_sheet_service.py`
   - 真正消费该字段

4. `QA-Reviewer`
   - 检查前后端字段链路是否闭环

### 8.2 示例二：把主任务改成入队执行

推荐拆分：

1. `Architect`
   - 定义状态变化和迁移顺序

2. `Backend-Orchestrator`
   - 改任务门面和运行时入口

3. `Scheduler-Watchdog`
   - 改调度器和恢复逻辑

4. `QA-Reviewer`
   - 检查取消、重启、占用、日志是否仍闭环

### 8.3 示例三：新增上传脚本任务

推荐拆分：

1. `Architect`
   - 定义任务包格式和执行边界

2. `API-Contract`
   - 设计上传接口和状态查询接口

3. `Backend-Orchestrator`
   - 接入平台任务创建与调度

4. `Business-Executor`
   - 实现脚本执行器 / 沙箱 worker

5. `QA-Reviewer`
   - 验证隔离、错误回传、产物保存

---

## 10. Agent 之间的交接契约

为了避免多个 Agent 各写各的，建议强制执行交接契约。

### 9.1 输入契约

主控 Agent 给子 Agent 的输入应至少包括：

- 本次目标
- 负责范围
- 禁止修改范围
- 依赖的上游结论
- 预期输出

### 9.2 输出契约

子 Agent 返回时应至少包括：

- 改了什么
- 为什么这样改
- 改了哪些文件
- 还有哪些风险没解决
- 哪些地方需要主控 Agent 继续集成

### 9.3 冲突处理规则

如果两个 Agent 潜在会改同一个文件：

- 只能有一个拥有写权限
- 另一个只做探索或建议
- 最终由主控 Agent 决定合并方式

---

## 11. Agent 输入模板建议

主控 Agent 给子 Agent 下任务时，建议统一模板：

```text
目标：
负责范围：
禁止修改范围：
关键上下文：
相关文件：
预期输出：
风险提醒：
```

对这次大改，关键上下文至少应包含：

- `tasks` 保留为任务定义主表
- 新内核放在 `app/platform/`
- PostgreSQL 为主数据库
- 一次切换，旧入口只读
- token / sheet 占用控制必须保留
- C31 升级为通用批量编排框架
- checkpoint 第一版只强制支持 Google Sheet / backtest

---

## 12. 风险控制规则

多 AI agent 并行开发最容易出现的几个问题，在当前仓库里尤其明显。

### 10.1 漏改链路

典型表现：

- 只改模板没改回填 JS
- 只改 C31 前端没改 `batch_create_and_start_task()`
- 只改 service 没改 route 或 config 透传

控制方式：

- 主控 Agent 在拆任务前先列完整链路
- QA Agent 最后按链路验收，而不是只看文件 diff

### 10.2 状态竞争

典型表现：

- runtime、restart、watchdog 同时改时语义漂移

控制方式：

- 状态机类改动优先由一个 Agent 负责写
- 其他 Agent 只做 review 或辅助分析

### 10.3 资源释放遗漏

典型表现：

- token 占用释放不完整
- sheet 占用释放漏一条路径

控制方式：

- 专门让评审 Agent 检查 acquire / release 是否成对

### 10.4 上下文不一致

典型表现：

- 某个 Agent 还以为旧 `task_manager.py` 是生产入口
- 某个 Agent 不知道 C31 只是前端批量入口

控制方式：

- 主控 Agent 每次任务开始都要发一份“当前上下文摘要”

---

## 13. 推荐的执行节奏

### 小需求

适合：

- 单文件或单链路小改动

建议：

- 主控 Agent 自己做
- 最多加一个评审 Agent

### 中需求

适合：

- 前后端联动
- 任务参数新增
- 局部执行链路调整

建议：

- 3 到 4 个 Agent 并行

### 大需求

适合：

- worker 化
- 队列化
- scheduler / watchdog 收敛
- 上传脚本平台

建议：

- 5 到 8 个角色
- 先方案后实现
- 最后必须有独立评审 Agent

---

## 14. 结论

对于当前这个仓库，多 AI agent 的最佳使用方式不是让它们随意自治，而是像一个完整开发团队一样按角色分工：

- 主控 Agent 负责拆分与集成
- 架构 Agent 负责边界和方案
- 后端、调度、业务、前端各自守住写入边界
- QA / Review Agent 负责最后查漏补缺

一句话总结：

把多个 AI agent 当成一个可并行协作的开发团队来用，而不是一群同时改代码的自由个体。

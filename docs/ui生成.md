# UI 生成功能说明

## 产品范围

这是一个以任务为中心的管理系统，核心包含 3 类业务：

- Google Sheet 参数批量任务
- 数据回测训练任务
- 管理后台

另有 2 个辅助分析工具页：

- `xpl`
- `xpl/v1`

另有娱乐页 `yule`，与核心业务无强关联，可忽略。

## 全局布局要求

- 顶层需要统一导航，能进入：仪表盘、任务管理、模板管理、结果管理、定时任务、系统配置、Google Sheet 管理、日志、Google Sheet 业务页、回测训练页、分析工具页
- 所有列表页需要支持刷新
- 所有涉及任务的页面都需要展示任务状态
- 所有详情页都需要支持返回上一级
- 所有长耗时操作都需要加载中、失败提示、成功提示
- 所有 JSON 输入区域都需要基本校验
- 所有表格列表都需要空状态
- 时间字段统一显示创建时间、开始时间、结束时间
- 状态统一包含：`pending`、`running`、`completed`、`cancelled`、`error/failed`

## 统一数据对象

- 任务对象：`id`、`name`、`description`、`task_type`、`status`、`config`、`current_step`、`total_steps`、`error_message`、`created_at`、`start_time`、`end_time`
- 任务结果对象：`id`、`task_id`、`step_index`、`parameters`、`result`、`success`、`error_message`、`timestamp`
- 模板对象：`id`、`name`、`description`、`config`、`created_at`
- Google Sheet 对象：`id`、`name`、`spreadsheet_id`、`table_type`、`remark`、`is_active`、`is_in_use`、`current_task_id`
- Token 对象：`id`、`name`、`task_type`、`token_context`、`current_in_use_count`、`task_usage_count`、`max_usage_count`、`is_active`、`last_used_at`

## 一、管理后台

### 1. 仪表盘 `/admin/`

- 展示任务总数、已完成、运行中、错误、已取消、待执行数量
- 展示最近 7 天任务趋势图
- 展示任务状态分布图
- 展示任务类型分布图
- 展示当前运行中的任务卡片
- 展示最近任务列表
- 支持手动刷新
- 运行中任务需要能跳转到详情页

### 2. 任务管理 `/admin/tasks`

- 支持任务列表分页
- 支持按状态筛选
- 支持按任务类型筛选
- 支持按任务名称或任务 ID 搜索
- 支持每页条数切换
- 支持创建任务
- 创建任务时需要填写：名称、类型、描述、JSON 配置
- 支持查看任务详情弹窗
- 详情弹窗需展示：
- 基本信息
- 配置内容
- 参数摘要
- 结果摘要
- 运行说明
- 最近日志
- 指标图
- 收益曲线图
- 对运行中的任务支持取消
- 对异常/已结束任务支持重启
- 支持从断点重启、从头重启、创建重启任务
- 支持删除任务
- 支持跳转到独立详情页

### 3. 模板管理 `/admin/templates`

- 展示模板卡片列表
- 固定展示 3 个快捷入口：
- 新建普通模板
- 新建 C4 模板
- 新建 C5 模板
- 支持创建模板
- 支持编辑模板
- 支持删除模板
- 支持复制模板
- 支持直接使用模板创建任务
- 模板卡片需要显示名称、描述、创建时间、模板类型、配置摘要

### 4. 结果管理 `/admin/results`

- 展示结果列表分页
- 支持按任务 ID 过滤
- 列表字段只需：结果 ID、任务 ID、步骤序号、成功/失败、时间
- 支持查看单条结果详情
- 详情需展示：
- 参数 JSON
- 结果 JSON
- 错误信息
- 支持删除结果

### 5. 系统配置 `/admin/config`

- 展示系统配置列表
- 支持编辑配置项
- 支持配置校验
- 展示 Token 使用汇总：
- 当前占用总数
- 累计使用总数
- 全局占用上限
- 可用 Token 数
- 展示 Google Sheet Token 列表
- 支持新增 Token
- 新增/编辑 Token 需要字段：
- 名称
- `task_type`
- 最大占用数
- 是否启用
- token JSON 内容
- 支持编辑 Token
- 支持删除 Token

### 6. Google Sheet 管理 `/admin/google-sheets`

- 展示 Google Sheet 资源表
- 支持按关键字搜索名称或 Spreadsheet ID
- 支持按启用状态筛选
- 支持按表类型筛选
- 支持按占用状态筛选
- 支持新增 Google Sheet
- 新增/编辑字段：
- 名称
- Spreadsheet ID 或 URL
- 表类型 `c3/c4/c5`
- 备注
- 是否启用
- 支持编辑
- 支持删除
- 删除时如果正在占用应禁用删除

### 7. 定时任务管理 `/admin/scheduler`

- 展示定时任务统计：总数、启用数、停用数、调度器状态
- 展示定时任务列表
- 列表字段：
- ID
- 名称
- 描述
- Cron 表达式
- 任务类型
- 状态
- 执行次数
- 上次执行时间
- 下次执行时间
- 支持新增定时任务
- 新增字段：
- 名称
- 类型
- 描述
- cron
- 执行函数
- JSON 参数
- 是否启用
- 支持编辑定时任务
- 支持启停
- 支持删除

### 8. 系统日志 `/admin/logs`

- 展示日志流
- 支持刷新
- 支持清空日志
- 支持下载日志
- 支持按级别筛选
- 支持按关键词搜索
- 支持按日期筛选
- 支持自动轮询刷新

## 二、Google Sheet 任务模块

### 1. 任务首页 `/google-sheet/`

- 按版本展示对应任务列表，版本来源于 `version` 参数
- 支持版本：`c3`、`c31`、`c4`、`c5`
- 页面需要展示统计信息：
- 总任务数
- 已完成数
- 运行中数
- 错误数
- 今日新增
- 成功率
- 平均时长
- 支持任务状态筛选
- 支持分页
- 支持切换每页数量
- 支持跳页
- 支持刷新
- C3 版本需要提供“批量任务创建”入口
- 所有版本都需要提供“创建新任务”入口

### 2. 任务创建页 `/google-sheet/create`

- 支持从模板载入配置
- 基础信息：
- 任务名称
- 任务描述
- Google Sheet 配置：
- 选择 Google Sheet 资源
- 刷新 Google Sheet 列表
- 自动读取并展示标题
- 自动读取工作表名称
- token 认证方式切换：文件路径 / JSON 文本
- token 信息输入
- 可选代理 URL
- 参数配置：
- 支持多个参数组
- 每个参数组是 JSON 数组输入
- 支持新增参数组
- 支持删除参数组
- 支持清空全部参数
- 支持保存为模板
- 支持启动任务
- 启动前需要校验参数合法性
- 不同版本页面字段会有差异，但本质都是“配置 Sheet + 配置参数 + 创建任务”

### 3. C31 批量创建页 `/google-sheet/create?version=c31`

- 在普通创建能力基础上，增加批量任务创建能力
- 支持选择股票市场类型，前端显示中文，传后端传英文值
- `cn`
- `en`
- 支持设置结束时间
- 如果未选择，不传后端
- 支持批量配置股票或参数集合
- 支持批量创建多个 C3 任务

### 4. 任务详情页 `/google-sheet/detail`

- 展示任务概览：
- 名称
- ID
- 状态
- 进度
- 开始/结束时间
- 执行时长
- 错误信息
- 成功数/失败数
- 成功率
- 展示任务配置
- 展示参数配置
- 展示任务日志
- 展示执行结果列表
- 结果列表支持：
- 刷新
- 成功/失败筛选
- 分页
- 支持取消任务
- 支持状态检查
- 支持重启任务
- 从断点继续
- 从头重启
- 跳转创建重启任务
- 如果任务允许，需要支持配置编辑

## 三、回测训练模块

### 1. 回测任务列表 `/backtest-training/list`

- 展示回测任务统计：
- 总数
- 运行中
- 已完成
- 失败
- 展示任务列表
- 列表字段：
- 名称和短 ID
- 模型版本
- 状态
- 创建时间
- 开始时间
- 结束时间
- 支持刷新
- 支持删除任务
- 支持进入任务详情
- 支持进入创建任务

### 2. 回测任务创建 `/backtest-training/create`

- 输入 Google Sheet URL，自动识别模型版本
- 输入股票代码
- 支持股票搜索联想
- 支持智能识别按钮
- 支持任务名称
- 支持折叠/展开任务配置区域
- 支持选择 Google Sheet Token
- 支持读取工作表
- 支持 Excel 导入参数
- 支持年份范围与年份开关配置
- 支持开始/结束时间相关配置
- 支持参数表格编辑
- 支持生成回测任务
- 成功后跳转回任务列表

### 3. 回测任务详情 `/backtest-training/detail/<task_id>`

- 展示基础执行信息：
- 名称
- ID
- 状态
- 创建时间
- 开始时间
- 结束时间
- 展示任务输入参数
- 展示结果区域
- 对 C5 等普通模式：
- 展示子结果列表
- 支持分页
- 每条可进入结果详情
- 对 C3 汇总模式：
- 展示汇总表
- 包含参数列、年份列、收益指标列、回撤指标列、Sharpe 等
- 顶部操作：
- 全局预览页
- 创建重启任务
- 断点重启
- 从头开始
- 需要能展示任务日志

### 4. 单结果详情 `/backtest-training/result/<result_id>`

- 展示某一条回测结果的完整分析内容
- 内容包含：
- 指标摘要
- 结构化指标表
- 导出能力
- 需要从结果接口拉取完整 `result` 数据

### 5. 全局预览页 `/backtest-training/global-preview/<task_id>`

- 作用：把同一任务下的多个结果，按年份分组后，合并成一张横向比较表
- 页面同时只展示一个分组
- 支持切换分组
- 页面顶部展示汇总：
- 任务 ID
- 总结果数
- 成功结果数
- 分组数
- 每个分组需要显示：
- 分组名
- 区间
- 参数列数
- 失败结果数
- 表格结构：
- 左侧前三列固定
- 第一列为分类
- 第二列为指标名
- 第三列为股票/指数基准值
- 从第四列开始，每列对应一组参数结果
- 每个参数列头需要展示：
- 参数标题
- 结果 ID
- 模型类型 C3/C5
- 股票 code
- 支持导出 XLSX
- 导出规则：
- 每个分组对应一个 sheet
- sheet 内容与当前预览表结构一致
- 第一列背景为黄色
- 参数列头上移一行
- 需要写入股票 code
- 需要标明当前列属于 C3 还是 C5

## 四、辅助分析工具

### 1. `xpl` 数据分析工具 `/xpl/`

- 支持粘贴 Excel 数据
- 支持从剪贴板导入
- 支持加载示例数据
- 支持清空输入
- 支持选择时间格式
- 支持选择收益率列
- 支持执行分析
- 支持导出结果

### 2. `xpl/v1`

- 输入 Google Sheet URL
- 拉取工作表列表
- 选择工作表
- 执行分析
- 展示一组指标摘要卡片
- 展示分析明细
- 支持导出结果

## 五、生成 UI 时建议保留的关键交互

- 所有任务列表页要统一支持：
- 刷新
- 状态标签
- 空态
- 错误提示
- 详情跳转
- 所有创建页要统一支持：
- 模板回填
- 输入校验
- 提交中状态
- 提交成功后跳转
- 所有详情页要统一支持：
- 基础信息
- 配置区
- 日志区
- 结果区
- 任务操作区
- 所有导出功能要明确文件类型和导出范围
- 所有 JSON 配置输入都建议支持格式化和校验提示

## 六、核心接口映射

- 任务通用：`/api/tasks`
- 单任务详情/删除：`/api/tasks/<task_id>`
- 任务取消：`/api/tasks/<task_id>/cancel`
- 任务重启：`/api/tasks/<task_id>/restart`
- 任务结果：`/api/tasks/<task_id>/results`
- 任务日志：`/api/tasks/<task_id>/logs`
- 模板：`/api/templates`
- 结果管理：`/api/results`
- Google Sheet 列表：`/api/google-sheets`
- Google Sheet Token：`/api/google-sheet-tokens`
- 工作表读取：`/api/google-sheet/worksheets`
- 回测股票搜索：`/backtest-training/api/search-stocks`
- 回测 Excel 导入：`/backtest-training/api/import-excel`
- 回测任务结果列表：`/backtest-training/api/task-results/<task_id>`
- 回测单结果：`/backtest-training/api/task-result/<id>`
- 回测全局预览：`/backtest-training/api/global-preview/<task_id>`
- 回测全局预览导出：`/backtest-training/api/global-preview/<task_id>/export`

## 七、页面树 + 组件树

本节用于直接指导 UI 生成。重点描述页面层级、页面目标、组件组成、交互动作、状态变化、数据依赖。

---

## 1. 顶层页面树

### 1.1 系统级页面

- `/admin/` 仪表盘
- `/admin/tasks` 任务管理
- `/admin/templates` 模板管理
- `/admin/results` 结果管理
- `/admin/config` 系统配置
- `/admin/google-sheets` Google Sheet 资源管理
- `/admin/scheduler` 定时任务管理
- `/admin/logs` 系统日志

### 1.2 Google Sheet 业务页面

- `/google-sheet/?version=c3`
- `/google-sheet/?version=c31`
- `/google-sheet/?version=c4`
- `/google-sheet/?version=c5`
- `/google-sheet/create`
- `/google-sheet/create?version=c31`
- `/google-sheet/create?version=c4`
- `/google-sheet/create?version=c5`
- `/google-sheet/detail?task_id=xxx`

### 1.3 回测训练页面

- `/backtest-training/list`
- `/backtest-training/create`
- `/backtest-training/detail/<task_id>`
- `/backtest-training/result/<result_id>`
- `/backtest-training/global-preview/<task_id>`

### 1.4 辅助工具页面

- `/xpl/`
- `/xpl/v1`

---

## 2. 全局框架组件树

### 2.1 AppShell

- `TopHeader`
- `SideNavigation`
- `MainContent`
- `GlobalToastContainer`
- `GlobalModalHost`
- `GlobalLoadingMask`

### 2.2 TopHeader

- Logo / 系统名称
- 当前一级模块标题
- 全局刷新入口
- 可选全局状态提示区

### 2.3 SideNavigation

- 分组 1：后台管理
- 仪表盘
- 任务管理
- 模板管理
- 结果管理
- 定时任务
- 系统配置
- Google Sheet 管理
- 日志
- 分组 2：业务
- Google Sheet C3
- Google Sheet C4
- Google Sheet C5
- 回测训练
- 分组 3：工具
- XPL
- XPL V1

### 2.4 GlobalToastContainer

- 成功提示
- 失败提示
- 警告提示
- 信息提示

### 2.5 GlobalModalHost

- 通用确认弹窗
- JSON 编辑弹窗
- 详情弹窗
- 表单弹窗

### 2.6 通用页面骨架

- `PageHeader`
- `PageToolbar`
- `PageFilters`
- `PageSummaryCards`
- `PageContentSection`
- `PageFooterPagination`

---

## 3. 通用基础组件树

### 3.1 PageHeader

- 页面标题
- 页面副标题
- 返回按钮
- 主操作按钮
- 次操作按钮组

### 3.2 SummaryCardGroup

- `SummaryCard`
- 标题
- 数值
- 辅助说明
- 趋势/状态标识

### 3.3 FilterBar

- 搜索输入框
- 下拉筛选器
- 日期筛选器
- 状态筛选器
- 重置按钮
- 提交/刷新按钮

### 3.4 DataTable

- `TableHeader`
- `TableBody`
- `TableRow`
- `TableCell`
- `RowActions`
- 空状态
- 加载状态
- 错误状态

### 3.5 PaginationBar

- 总数说明
- 每页数量选择器
- 页码切换
- 上一页/下一页
- 快速跳页输入

### 3.6 StatusBadge

- pending
- running
- completed
- cancelled
- error
- failed

### 3.7 JsonEditorField

- 文本域
- 格式化按钮
- 校验按钮
- 错误提示区

### 3.8 LogViewer

- 日志容器
- 自动刷新开关
- 级别筛选
- 搜索框
- 日期筛选
- 滚动到底部按钮

### 3.9 EmptyState

- 图标
- 标题
- 说明文字
- 主操作按钮

### 3.10 ConfirmDialog

- 标题
- 说明文案
- 二次确认按钮
- 取消按钮

---

## 4. 仪表盘页面树 + 组件树

### 4.1 页面目标

- 让用户总览系统运行状态
- 快速发现异常任务
- 快速跳转到具体任务

### 4.2 组件树

- `DashboardPage`
- `PageHeader`
- 页面标题
- 刷新按钮
- `SummaryCardGroup`
- 总任务数
- 已完成数
- 运行中数
- 错误数
- 已取消数
- 待执行数
- `ChartSection`
- 最近 7 天任务趋势图
- 状态分布图
- 类型分布图
- `ActiveTaskPanel`
- 当前运行任务卡片列表
- 单卡片操作：查看详情
- `RecentTaskTable`
- 最近任务表格
- 行内操作：查看详情

### 4.3 关键交互

- 刷新页面数据
- 点击运行中任务进入详情
- 图表只读，不承担编辑行为

---

## 5. 任务管理页面树 + 组件树

### 5.1 页面目标

- 管理所有任务
- 创建任务
- 过滤、搜索、查看、取消、重启、删除任务

### 5.2 组件树

- `TaskManagementPage`
- `PageHeader`
- 标题
- 刷新按钮
- 创建任务按钮
- `FilterBar`
- 状态筛选
- 类型筛选
- 关键词搜索
- 清空筛选
- `TaskTable`
- 任务列
- 类型列
- 状态列
- 停止确认列
- 参数摘要列
- 进度列
- 创建时间列
- 开始时间列
- 结束时间列
- 操作列
- 查看
- 删除
- 可选取消
- 可选重启
- `PaginationBar`
- `CreateTaskModal`
- 名称输入
- 类型选择
- 描述输入
- JSON 配置输入
- 提交按钮
- `TaskDetailModal`
- 基本信息区
- 配置区
- 参数摘要区
- 结果摘要区
- 运行说明区
- 指标图
- 收益曲线图
- 日志区
- 页脚操作区
- 页面详情按钮
- 取消任务按钮
- 重启任务按钮组
- 删除任务按钮

### 5.3 子组件详细结构

#### 5.3.1 TaskTableRow

- 任务名称
- 任务 ID
- 任务类型标签
- 状态标签
- 进度条
- 参数组数量
- 创建时间
- 开始时间
- 结束时间
- 操作按钮组

#### 5.3.2 TaskDetailModal

- `BasicInfoPanel`
- id
- name
- type
- status
- progress
- duration
- stop confirmation
- created/start/end
- `ConfigPanel`
- 原始 config JSON
- `ParameterSummaryPanel`
- 参数组数量
- 参数预览
- `ResultSummaryPanel`
- 总结果数
- 成功数
- 失败数
- 成功率
- 最近指标点
- 收益曲线数据
- `RecentLogsPanel`
- 最新日志流

---

## 6. 模板管理页面树 + 组件树

### 6.1 页面目标

- 管理任务模板
- 快速基于模板创建任务

### 6.2 组件树

- `TemplateManagementPage`
- `PageHeader`
- 标题
- 新建模板按钮
- `TemplateQuickEntryGrid`
- 新建普通模板入口卡片
- 新建 C4 模板入口卡片
- 新建 C5 模板入口卡片
- `TemplateCardGrid`
- `TemplateCard`
- 模板名称
- 模板类型标签
- 描述
- 配置摘要
- 创建时间
- 操作菜单
- 编辑
- 复制
- 删除
- 使用模板
- `CreateTemplateModal`
- 名称
- 描述
- JSON 配置
- `EditTemplateModal`
- 名称
- 描述
- JSON 配置

### 6.3 模板卡片最小信息

- 模板名
- 模板类型
- 描述
- 工作表信息
- 参数信息摘要
- 创建时间
- 使用按钮

---

## 7. 结果管理页面树 + 组件树

### 7.1 页面目标

- 查询所有任务结果
- 查看单条结果详情
- 删除异常或无用结果

### 7.2 组件树

- `ResultManagementPage`
- `PageHeader`
- 标题
- `FilterBar`
- 任务 ID 输入
- 查询按钮
- `ResultTable`
- 结果 ID
- 任务 ID
- 步骤序号
- 成功/失败
- 时间
- 操作列
- 查看
- 删除
- `PaginationBar`
- `ResultDetailModal`
- 参数 JSON
- 结果 JSON
- 错误信息

---

## 8. 系统配置页面树 + 组件树

### 8.1 页面目标

- 编辑系统配置
- 管理 Google Sheet Token

### 8.2 组件树

- `SystemConfigPage`
- `PageHeader`
- 标题
- 刷新按钮
- 配置校验按钮
- `SummaryCardGroup`
- 当前占用总数
- 累计使用总数
- 全局占用上限
- 可用 Token 数
- `ConfigTableSection`
- 配置表格
- Key
- Value
- Description
- 操作
- 编辑
- `TokenManagementSection`
- 新增 Token 表单
- 名称
- 最大占用数
- task_type
- token JSON
- 新增按钮
- Token 表格
- id
- 名称
- task_type
- JSON 大小
- 当前占用
- 累计使用
- 最大占用
- 状态
- 最后使用时间
- 操作
- 编辑
- 删除
- `EditConfigModal`
- key
- value
- description
- `EditTokenModal`
- 名称
- task_type
- 最大占用
- 启用状态
- token JSON
- 保存
- 删除

---

## 9. Google Sheet 资源管理页面树 + 组件树

### 9.1 页面目标

- 维护 Google Sheet 资源池

### 9.2 组件树

- `GoogleSheetRegistryPage`
- `PageHeader`
- 标题
- 新增资源按钮
- `FilterBar`
- 关键词
- 启用状态
- 表类型
- 占用状态
- 刷新按钮
- `GoogleSheetTable`
- 名称
- Spreadsheet ID
- 表类型
- 备注
- 是否启用
- 是否占用中
- 当前任务 ID
- 操作列
- 编辑
- 删除
- `SheetFormModal`
- 名称
- Spreadsheet ID 或 URL
- 表类型
- 备注
- 启用开关
- 保存按钮

---

## 10. 定时任务管理页面树 + 组件树

### 10.1 页面目标

- 管理定时执行任务

### 10.2 组件树

- `SchedulerPage`
- `PageHeader`
- 标题
- 添加定时任务按钮
- `SummaryCardGroup`
- 总任务数
- 活跃任务数
- 暂停任务数
- 调度器状态
- `SchedulerTable`
- ID
- 名称
- 描述
- Cron
- 任务类型
- 状态
- 执行次数
- 上次执行
- 下次执行
- 操作
- 编辑
- 启停
- 删除
- `CreateSchedulerTaskModal`
- 名称
- 类型
- 描述
- cron 表达式
- 执行函数
- JSON 参数
- 启用开关
- `EditSchedulerTaskModal`
- 同创建表单

---

## 11. 系统日志页面树 + 组件树

### 11.1 页面目标

- 查看系统日志
- 快速按条件过滤

### 11.2 组件树

- `SystemLogPage`
- `PageHeader`
- 标题
- 刷新按钮
- 清空按钮
- 下载按钮
- `FilterBar`
- 级别筛选
- 关键词搜索
- 日期筛选
- 清空筛选
- `LogViewer`
- 日志计数
- 日志滚动区域
- 自动刷新

---

## 12. Google Sheet 业务首页页面树 + 组件树

### 12.1 页面目标

- 按版本查看业务任务
- 快速创建任务

### 12.2 组件树

- `GoogleSheetTaskHomePage`
- `PageHeader`
- 当前版本标题
- 页面说明
- 创建新任务按钮
- C3 批量创建按钮
- `SummaryCardGroup`
- 总任务数
- 已完成
- 运行中
- 错误
- 今日新增
- 成功率
- 平均时长
- `PendingTaskAlert`
- 有待重启任务时展示提醒
- 查看详情按钮
- `TaskFilterToolbar`
- 状态筛选
- 刷新按钮
- `TaskTable`
- 任务名称
- 状态
- 进度
- 开始时间
- 结束时间
- 操作
- 查看详情
- `PaginationBar`

---

## 13. Google Sheet 创建页页面树 + 组件树

### 13.1 页面目标

- 创建 Google Sheet 类任务
- 支持模板回填
- 支持参数编辑

### 13.2 组件树

- `GoogleSheetCreatePage`
- `PageHeader`
- 标题
- 返回按钮
- `TaskBaseInfoSection`
- 模板选择
- 任务名称
- 任务描述
- `GoogleSheetConfigSection`
- Google Sheet 选择器
- 刷新列表按钮
- 标题输入框
- 工作表名称输入框
- token 类型选择器
- token 文件输入
- token JSON 输入
- 代理 URL
- `ParameterConfigSection`
- 参数组列表
- 单参数卡片
- 参数组标题
- JSON 输入区
- 删除按钮
- 新增参数按钮
- 清空全部按钮
- `ActionBar`
- 保存模板按钮
- 创建任务按钮

### 13.3 ParameterGroupCard

- 参数组名称
- 参数组序号
- JSON 文本输入
- 校验提示
- 删除按钮

### 13.4 版本扩展要求

- C4、C5 可以在字段数、参数结构上不同，但仍沿用同一个页面骨架
- UI 生成时应支持通过配置切换字段组合

---

## 14. C31 批量创建页页面树 + 组件树

### 14.1 页面目标

- 一次生成多个 C3 批量任务

### 14.2 组件树

- `GoogleSheetBatchCreatePage`
- `PageHeader`
- 标题
- 返回按钮
- `BatchTaskBaseSection`
- 模板选择
- 任务名称规则说明
- 任务描述
- `ModelSourceSection`
- Google Sheet URL
- 解析按钮
- 工作表信息
- `StockBatchSection`
- 股票输入区域
- 市场类型单选
- A股
- 美股
- 批量股票列表
- `DateConfigSection`
- 结束时间选择器
- 未选择时不传后端
- `BatchParameterSection`
- 参数集合输入
- 批量预览
- `BatchActionBar`
- 批量创建按钮
- 创建结果反馈

---

## 15. Google Sheet 任务详情页页面树 + 组件树

### 15.1 页面目标

- 展示单任务运行情况
- 提供取消、重启、编辑配置等动作

### 15.2 组件树

- `GoogleSheetTaskDetailPage`
- `PageHeader`
- 任务概览标题
- 返回首页按钮
- 检查状态按钮
- 取消任务按钮
- 重启任务下拉按钮
- `TaskOverviewSection`
- 任务信息卡
- 时间信息卡
- 执行统计卡
- `TaskConfigSection`
- Google Sheet 配置
- 参数配置
- 编辑配置按钮
- `TaskLogSection`
- 日志查看器
- `TaskResultSection`
- 结果表格
- 刷新按钮
- 筛选按钮
- 成功
- 失败
- 全部
- 分页器
- `EditTaskConfigModal`
- 完整 JSON 配置

### 15.3 ResultTableRow

- 序号
- 参数组合摘要
- 执行结果摘要
- 状态
- 执行时间
- 耗时

---

## 16. 回测任务列表页页面树 + 组件树

### 16.1 页面目标

- 查看所有回测任务
- 进入详情
- 删除任务

### 16.2 组件树

- `BacktestTaskListPage`
- `PageHeader`
- 标题
- 创建任务按钮
- 最后更新时间
- `SummaryCardGroup`
- 总数
- 运行中
- 已完成
- 失败
- `BacktestTaskTable`
- 任务名称与短 ID
- 模型版本
- 状态
- 创建时间
- 开始时间
- 结束时间
- 操作
- 详情
- 删除

---

## 17. 回测任务创建页页面树 + 组件树

### 17.1 页面目标

- 从 Google Sheet URL 自动分析并创建回测任务

### 17.2 组件树

- `BacktestCreatePage`
- `PageHeader`
- 标题
- 返回任务列表按钮
- `ModelIdentifySection`
- Google Sheet URL 输入
- 股票代码输入
- 股票搜索下拉列表
- 智能识别按钮
- `TaskConfigCollapseSection`
- 任务名称
- token 选择
- 工作表读取
- 年份配置
- 开始/结束时间配置
- 识别结果展示
- `ExcelImportSection`
- Excel 上传
- 导入状态提示
- 导入结果回填
- `ParameterGridSection`
- 参数表格
- 单元格编辑
- 增删行能力
- `ActionBar`
- 创建任务按钮

### 17.3 年份配置组件

- `YearSwitchGrid`
- 年份启用开关列表
- 年份摘要
- 自定义范围配置

### 17.4 股票搜索组件

- 输入框
- 搜索结果浮层
- 单条结果项
- code
- name
- security type

---

## 18. 回测任务详情页页面树 + 组件树

### 18.1 页面目标

- 以任务维度查看回测执行情况
- 根据模型类型展示不同结果视图

### 18.2 组件树

- `BacktestDetailPage`
- `PageHeader`
- 任务标题
- task id
- 返回列表按钮
- 全局预览按钮
- 创建重启任务按钮
- 断点重启按钮
- 从头开始按钮
- `TaskMetaSection`
- 状态
- 创建时间
- 开始时间
- 结束时间
- `TaskParamSection`
- 参数表格
- 折叠/展开
- `TaskResultSection`
- C5 结果列表视图
- 结果 ID
- 参数摘要
- 状态
- 时间
- 操作
- 进入单结果详情
- 分页器
- C3 汇总表视图
- 参数列
- 年份列
- 收益列
- 回撤列
- Sharpe 列
- 其他指标列
- `TaskLogSection`
- 日志查看

### 18.3 视图切换规则

- 如果任务为 C3 汇总型，展示汇总表视图
- 如果任务为普通结果型，展示结果列表视图

---

## 19. 回测单结果详情页页面树 + 组件树

### 19.1 页面目标

- 展示单个回测结果的完整分析明细

### 19.2 组件树

- `BacktestResultPage`
- `PageHeader`
- 返回任务详情按钮
- 导出按钮
- `ResultSummaryCards`
- 核心指标卡片组
- `MetricTableSection`
- 指标名称
- 指标值
- `AnalysisSection`
- 结构化分块展示
- `ExportSection`
- 导出操作按钮

---

## 20. 全局预览页页面树 + 组件树

### 20.1 页面目标

- 把同一任务下的多个结果按年份分组横向对比

### 20.2 组件树

- `GlobalPreviewPage`
- `PageHeader`
- 页面标题
- 返回详情按钮
- 导出 XLSX 按钮
- `SummaryCardGroup`
- 任务 ID
- 总结果数
- 成功结果数
- 分组数
- `GroupSwitcherSection`
- 年份分组下拉框
- 分组元信息标签
- 区间
- 参数列数
- 失败结果数
- `PreviewTableSection`
- 横向对比表
- 左侧固定列 1：分类
- 左侧固定列 2：指标名称
- 左侧固定列 3：股票/指数基准值
- 动态列区：参数结果列

### 20.3 PreviewTable 详细列树

- `PreviewTable`
- `TableHeader`
- 固定列头 1：分类
- 固定列头 2：指标
- 固定列头 3：股票/指数值
- 动态参数列头
- 参数标题
- 结果 ID
- 模型类型 C3/C5
- 股票 code
- `TableBody`
- 行对象
- category
- metric
- index_value
- values[column_key]

### 20.4 导出 XLSX 结构要求

- 一个年份分组对应一个 sheet
- 每个 sheet 的表头与页面对比表一致
- 第一列为黄色背景
- 参数列头上移一行
- 参数列头要额外包含股票 code
- 参数列头要标注 C3 还是 C5

---

## 21. XPL 页面树 + 组件树

### 21.1 `xpl`

- `XplPage`
- 页面标题
- 刷新按钮
- 导出按钮
- 数据输入区
- 剪贴板导入
- 示例数据
- 清空
- 分析设置区
- 时间格式
- 收益率列
- 开始分析按钮
- 结果区

### 21.2 `xpl/v1`

- `XplV1Page`
- 页面标题
- 返回按钮
- Google Sheet URL 输入
- 获取工作表按钮
- 工作表选择器
- 分析按钮
- 指标摘要卡片组
- 详细结果区域
- 导出按钮

---

## 22. 推荐的 UI 生成策略

### 22.1 先生成框架

- 先生成 `AppShell`
- 再生成后台页面通用骨架
- 再生成业务页面

### 22.2 组件复用优先级

- 最高复用：
- `PageHeader`
- `SummaryCardGroup`
- `FilterBar`
- `DataTable`
- `PaginationBar`
- `StatusBadge`
- `LogViewer`
- 次级复用：
- 表单弹窗
- JSON 编辑器
- 详情布局

### 22.3 动态页面能力

- Google Sheet 创建页应支持通过配置切换字段
- 回测详情页应支持按任务类型切换结果视图
- 全局预览页应支持动态列数

### 22.4 状态覆盖要求

- loading
- empty
- success
- error
- no permission 或 unavailable

# B方案执行文档

## 1. 目标

这份文档用于按“B 方案”推进当前项目的结构化优化，原则是：

- 先修复已知前后端联调问题，再做架构调整
- 每一步都要有可验证结果
- 优先做低风险、高收益、可回滚的改造
- 文档和代码同步推进，避免后续失控

补充决策：

- `C5` 作为后续唯一主演进版本
- `C4` 视为过渡版本，只保留兼容运行能力
- 后续 schema、前端配置结构、服务抽象均以 `C5` 为基准
- `C4` 不再新增复杂特性，只做必要映射与兜底

## 2. 当前已完成

### 2.1 C5 详情页联调修复

已完成以下修复：

- 修复 C5 详情页创建重启任务后错误跳转到 `version=c4` 的问题
- 修复 C5 详情页编辑弹窗未正确回填 `price_mode`
- 修复 C5 详情页编辑弹窗未正确回填 `parameters[1]`、`parameters[2]`
- 修复 C5 编辑保存时只提交 `parameters[0]`、导致其余参数丢失的问题
- 修复 C5 编辑保存时 `price_mode` 丢失的问题
- 修复 C5 编辑保存时未保留原配置中其他字段的问题
- 增加 Sheet 配置保存前校验，避免保存出空的 `spreadsheet_id` / `sheet_name`
- 修复 C5 新建页载入重启/模板配置时未同步 `price_mode` 的问题
- 修复 C5 新建页多次套用配置时 `param1/2/3` 旧值残留的问题

### 2.2 本轮验证

已完成静态验证：

- `templates/google_sheet_c5/detail.html` 提取脚本后通过 `node --check`
- `templates/google_sheet_c5/create.html` 去除模板标签后通过 `node --check`

说明：

- 这里是模板脚本的静态语法验证，不等同于完整业务回归
- 浏览器联调和接口行为验证仍建议继续补一轮

## 3. B方案总路线

### 阶段 0：先稳住线上行为

目标：

- 保证 C5 页面创建、详情、编辑、重启链路可用
- 找出前端页面与后端接口字段不一致的点
- 明确默认版 / C4 / C5 三套配置结构与收敛方向

操作：

1. 检查 `google_sheet`、`google_sheet_c4`、`google_sheet_c5` 三套页面的创建页与详情页字段映射
2. 检查以下接口的入参与出参结构是否一致：
   - `GET /api/tasks/<task_id>`
   - `PUT /api/tasks/<task_id>/config`
   - `POST /api/tasks`
   - `POST /api/tasks/<task_id>/create-restart`
3. 对“字段名一致但含义不同”的配置做归一化登记
4. 将 `C4` 标记为“向 C5 对齐”的兼容版本，而不是独立长期结构

验收：

- 创建任务、查看详情、编辑配置、重启任务都能闭环

### 阶段 1：拆出配置契约

目标：

- 让前端和后端对 `config` 的理解统一
- 让默认版 / C4 都能映射到 C5 基准结构

操作：

1. 新建统一配置文档，定义三类任务的 `config schema`
2. 抽出配置归一化函数
3. 抽出配置校验函数
4. 让前端只消费归一化后的结构
5. 对 `C4` 只保留 `normalize_to_c5_like_config` 之类的兼容入口

建议落点：

- `app/services/` 下新增配置归一化模块
- 前端把 `normalizeC4Config` / `normalizeC5Config` 这类函数统一收敛

验收：

- 同一种配置在创建页、详情页、模板加载、重启加载中表现一致

### 阶段 2：拆 TaskManager

目标：

- 把当前“任务调度 + 状态迁移 + 结果管理 + 线程管理”拆开

操作：

1. 拆出 `TaskRepository`
2. 拆出 `TaskRuntimeRegistry`
3. 拆出 `TaskStatusService`
4. 让 `TaskManager` 只做编排层

验收：

- `TaskManager` 文件明显瘦身
- 取消、重启、状态检查逻辑可单独测试

### 阶段 3：合并 Google Sheet 三套实现

目标：

- 去掉 `google_sheet_service.py`、`google_sheet_service_C4.py`、`google_sheet_service_C5.py` 之间的重复逻辑

操作：

1. 抽出 `BaseGoogleSheetService`
2. 抽出共用日志、结果保存、Sheet 初始化逻辑
3. 将 C4/C5 差异降到参数策略或结果提取策略

验收：

- 公共日志与结果保存逻辑只保留一份
- 新增一个版本时不再复制整份服务

### 阶段 4：拆 API 和前端模板

目标：

- 降低单文件体积和修改冲突

操作：

1. 拆分 `app/routes/api.py`
2. 把超大模板里的脚本抽到独立 JS
3. 将 C4/C5/默认版共享逻辑抽成共用函数

验收：

- `api.py` 不再承载所有资源类型
- `create.html` / `detail.html` 中的内联 JS 明显减少

### 阶段 5：补测试

目标：

- 为后续重构提供安全网

操作：

1. 建立标准 `pytest` 结构
2. 补任务状态迁移测试
3. 补配置编辑和重启场景测试
4. 对 Google Sheet 依赖做 mock

验收：

- 关键接口和关键状态流转具备自动化回归

## 4. 下一步建议执行顺序

建议严格按下面顺序推进：

1. 完成阶段 0 的页面与接口字段对齐清单
2. 进入阶段 1，先收敛 `config schema`
3. 在 schema 稳定后再拆 `TaskManager`
4. 最后再合并三套 Google Sheet 服务

原因：

- 当前系统最大风险不是“功能少”，而是“配置结构和职责边界不稳定”
- 如果先大拆服务，再回头修配置契约，会出现重复返工

## 5. 本轮之后的直接待办

下一轮建议我继续做这三件事：

1. 产出 C4/C5/默认版的配置字段映射表
2. 新增统一的 `config schema` 文档
3. 开始拆 `TaskManager` 的只读能力，先把查询和状态检查抽出去
4. 标记并整理后续可删除的 `C4` 专属分支

## 6. 风险提示

- 当前 `test/` 目录还不是标准化测试结构，重构前要控制改动面
- `app/config.py` 里仍有敏感配置治理问题，后续需要单独处理
- `TaskManager` 与三套 Google Sheet Service 耦合较深，拆分时要先补最小回归验证

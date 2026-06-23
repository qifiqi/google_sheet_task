# 定时任务管理功能总结

## 功能概述

已成功为管理页面添加了完整的定时任务管理功能，包括：

- ✅ 定时任务数据库模型
- ✅ 定时任务调度服务（基于APScheduler）
- ✅ 定时任务管理页面
- ✅ 完整的API接口
- ✅ 默认清理任务
- ✅ 启动时延时加载

## 主要特性

### 1. 数据库模型 (`ScheduledTask`)
- 支持cron表达式定义执行时间
- 任务类型分类（cleanup、backup、maintenance、custom）
- 任务参数JSON格式存储
- 执行统计（次数、上次执行时间、下次执行时间）
- 启用/禁用状态控制

### 2. 调度服务 (`SchedulerService`)
- 基于APScheduler的后台调度器
- 支持延时启动（默认30秒后启动）
- 自动从数据库加载活跃任务
- 内置清理函数：
  - `cleanup_old_logs`: 清理旧日志
  - `cleanup_old_results`: 清理旧结果
  - `cleanup_old_data`: 清理旧数据（日志+结果）

### 3. 管理页面功能
- 任务列表展示（状态、执行次数、下次执行时间等）
- 添加新任务（支持cron表达式、任务参数配置）
- 编辑现有任务
- 启用/禁用任务
- 立即执行任务
- 删除任务
- 实时统计信息

### 4. API接口
- `GET /api/admin/scheduler/stats` - 获取统计信息
- `GET /api/admin/scheduler/tasks` - 获取任务列表
- `POST /api/admin/scheduler/tasks` - 创建任务
- `PUT /api/admin/scheduler/tasks/<id>` - 更新任务
- `DELETE /api/admin/scheduler/tasks/<id>` - 删除任务
- `POST /api/admin/scheduler/tasks/<id>/toggle` - 切换任务状态
- `POST /api/admin/scheduler/tasks/<id>/run` - 立即执行任务

## 默认任务

系统会自动创建一个默认的清理任务：
- **任务名称**: 每日数据清理
- **执行时间**: 每天0点 (`0 0 * * *`)
- **功能**: 清理超过10天的任务日志和任务结果
- **任务信息**: 不会被删除，只清理日志和结果数据

## 技术实现

### 依赖包
- `APScheduler`: 任务调度框架
- `croniter`: cron表达式解析

### 核心文件
- `app/models.py` - 添加了ScheduledTask模型
- `app/services/scheduler_service.py` - 调度服务实现
- `app/routes/scheduler_api.py` - API接口
- `templates/admin/scheduler.html` - 管理页面
- `run.py` - 启动时初始化调度器

### 启动流程
1. 应用启动时创建数据库表
2. 延时30秒启动调度器（避免启动冲突）
3. 从数据库加载活跃任务到调度器
4. 创建默认清理任务（如果不存在）

## 使用说明

### 访问管理页面
1. 启动应用：`python run.py`
2. 访问：`http://127.0.0.1:5000/admin/scheduler`
3. 在侧边栏点击"定时任务"进入管理页面

### 添加新任务
1. 点击"添加定时任务"按钮
2. 填写任务信息：
   - 任务名称（必填）
   - 任务类型（必填）
   - Cron表达式（必填，如：`0 0 * * *` 表示每天0点）
   - 执行函数（必填）
   - 任务参数（JSON格式，如：`{"days": 10}`）
3. 点击"添加任务"

### Cron表达式示例
- `0 0 * * *` - 每天0点
- `0 */6 * * *` - 每6小时
- `0 0 */7 * *` - 每7天
- `30 2 * * 1` - 每周一凌晨2:30

## 监控和维护

- 调度器状态会在管理页面实时显示
- 任务执行情况会记录到系统日志
- 支持手动立即执行任务进行测试
- 可以随时启用/禁用任务

## 扩展说明

如需添加新的任务类型，需要：
1. 在`scheduler_service.py`的`_run_task_function`方法中添加新的函数处理
2. 实现具体的任务执行逻辑
3. 在管理页面的任务函数选项中添加新选项

# SDK 第二阶段接口缺口与迁移边界

## 已确认的 SDK 能力

`ParamStockMetadata`、`ParamGoogleSheetTokens`、`ParamScheduledTasks` 均提供：

- `GetDataByPageList`
- `GetInfoById`
- `ModifyOrAdd`
- `Delete`

应用侧已通过 `app/repositories` 统一解包 `ret_obj`、校验 `ret_code`，并转换布尔值和 JSON 字段。

## 本阶段已接入

- StockMetadata：新增按 ID 读取和单条远程保存函数；业务键查找仍未切换。
- GoogleSheetToken：无筛选的普通列表、详情读取、普通详情更新、删除走 SDK；带 `task_type` 筛选时明确返回未实现提示，不做本地全量过滤。
- ScheduledTask：分页列表和执行状态接口中的任务详情读取走 SDK。

## 明确保留本地 ORM 的入口

- StockMetadata 按 `stock_code + market_type` 查询和批量 upsert。
- GoogleSheetToken 按 `task_type` 筛选列表（当前返回 501，等待远程筛选接口）。
- GoogleSheetToken 导入、重复检测、运行时 token 文件落地。
- Token 当前占用重算、随机选择、使用次数递增/释放、全局上限统计。
- ScheduledTask 创建、修改、删除、启停、立即执行。
- ScheduledTask 统计聚合和 `scheduler_service`/worker 生命周期联动。

这些路径包含业务键筛选、事务、并发占用或调度状态，不在第二阶段改写。

## 需要服务端补充或确认的接口

1. `ParamStockMetadata/GetByCodeAndMarket`
   - 请求：`stock_code`、`market_type`
   - 返回：单个 `t_param_stock_metadata` 或明确的空结果
2. `ParamGoogleSheetTokens/GetDataByPageList`
   - 分页请求需要正式支持 `task_type` 筛选
   - 需明确排序字段和总数结构
3. `ParamScheduledTasks/GetDataByPageList`
   - 需明确 `ret_obj.items/list/records` 的分页结构
4. `ParamScheduledTasks/GetInfoById`
   - 需明确详情不存在时的 `ret_code` 和 `ret_obj` 约定
5. 后续并发迁移需要原子接口：
   - Token 占用/释放
   - Google Sheet 占用/释放
   - Token 使用次数递增
   - ScheduledTask 状态与运行实例更新

在上述接口正式进入 Swagger 并重新生成 `stock_sdk` 前，不应通过客户端拉取全量数据后再做业务键过滤。

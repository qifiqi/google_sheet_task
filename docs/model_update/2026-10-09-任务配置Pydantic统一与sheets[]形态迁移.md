# 2026-10-09 任务配置 Pydantic 统一与 sheets[] 形态迁移

## 背景与目标

任务配置（`Task.config`）此前无字段级 schema：创建入参是裸 dict 全量落库，校验散在
`creation.py` 的 `_normalize_task_config_for_type` 与各业务 normalize 函数里；同一
"Google Sheet 引用"存在三种形态——C3 顶层平铺 `spreadsheet_id/sheet_name/title`、
C4/C5/C7 `sheets[]`、单品回测嵌套 `sheet{}`——执行层 `_init_google_sheet` 以
"三形态兼容读取"消化。结构化编辑表单因此各自为政，且详情页编辑保存是全量替换，
会静默丢掉表单未覆盖的键（C31 子任务的 `stock_code/year_n`、C7 的
`kline_source/c7_model_version` 等）。

本次统一（用户裁定：允许脚本重构历史 JSON）：

1. **逐类型 Pydantic 配置模型**（`app/schemas/task_configs.py`）：C3/C4/C5/C7/
   backtest_training/backtest_multi_product 每类一个模型，公共段（token、K线取数）
   mixin 复用，`extra="allow"` 保留执行期布局键。
2. **Sheet 引用唯一形态**：`sheets: [{spreadsheet_id, sheet_name, title}]`。
   C3/C31 子任务/单品回测恰好 1 个元素（`_SingleSheetMixin` 强约束）；
   多品回测因每产品一张表，保留 `products[].sheet` 但复用同一 `SheetRef` 定义。
3. **编辑语义改 merge**：`PUT /api/tasks/<id>/config` 默认 `merge=true`（payload
   顶层键覆盖、未列出的键保留，修复丢键）；管理端 JSON 编辑器传 `merge=false`
   （整体替换，支持删键）。`TaskConfigUpdateSchema` 新增 `merge: bool = True`。
4. **历史数据一次性迁移**：`scripts/migrate_task_config_schema.py`。

## 统一后的 config 形态（各任务类型）

| 任务类型 | 模型 | Sheet 引用 | 关键段 |
|---|---|---|---|
| google_sheet（C3/C31 子任务） | `C3TaskConfig` | `sheets[1]` | stock_code/year_n/end_date/parameters + 公共段 |
| google_sheet_C4 | `C4TaskConfig` | `sheets[n]` | count_mode/date_range_mode/起止日期/parameters |
| google_sheet_C5 | `C5TaskConfig` | `sheets[n]` | C4 段 + kline_source/exclude_recent_years/random_* |
| google_sheet_C7 | `C7TaskConfig` | `sheets[n]` | C5 段；版本在 `sheets[].c7_model_version` |
| backtest_training | `BacktestTrainingConfig` | `sheets[1]` | recent_years/full_years/excel_import + 公共段 |
| backtest_multi_product | `MultiProductConfig` | `products[].sheet` | start/end_date/weighting_mode/products |

canonical 形态即模型 `model_dump(mode="json")` 产物：声明字段全键落库（缺省为
null），`SheetRef` 恒带 `google_sheet_id/c7_model_version` 两个 null 默认键。
`token_id/google_sheet_id` 等占用键声明为 `str | int`（占用表主键可能 int 直传）。

## 后端改动清单

- `app/schemas/task_configs.py`（新增）：模型层唯一出口 `validate_task_config_shape`。
- `app/services/task/creation.py`：normalize 尾部接模型（pydantic 错误转
  `ValidationError` 单行消息）；删除 C4/C5/C7 顶层平铺键 pop（无兼容层，旧形状在
  模型层直接拒绝）；`update_task_config` 增加 `merge_config` 参数与 merge 分支；
  C31 子任务构建改产 `sheets[1]`。
- `app/routes/task_api.py`：透传 `data.merge`。
- `app/schemas/task.py`：`TaskConfigUpdateSchema.merge`。
- `app/services/google_sheet_tasks/base.py`：`_init_google_sheet` 三形态分支收敛为
  唯一 `sheets[]` 路径；单元素时同时填充 `google_sheet`（C3/training 消费）与
  `google_sheets`。
- `app/services/backtest_training_service.py`：`_c3_to_c5_get_config` 与执行期
  `config['sheet']` 读取改 `sheets[0]`。
- `app/services/backtest_multi_product_service.py`：`_build_product_config` 改产
  `sheets[1]`；C7.0.3 判定包装改 `{"sheets": [sheet]}`。注意
  `TaskResult.parameters` 中的 `sheet` 键是**结果载荷既有契约，未动**。
- `app/services/task/occupancy.py`：删除 `config["sheet"]` 引用收集；
  `validate_backtest_training_sheet` 改读 `sheets[0]`。
- `app/services/task/runtime.py`：`_extract_backtest_spreadsheet_id` 改 `sheets[0]`，
  删顶层平铺回退。
- `app/services/task/runtime_view.py`：`config_summary` 的 sheet_name/spreadsheet_id
  改读 `sheets[0]`（管理页抽屉消费）。
- `app/services/backtest_report_query_service.py`：新增 `_first_sheet`，三处
  （模型版本推断/导出模型名/RPT-S 元数据）改读 `sheets[0]`，删顶层 title 回退。
- `app/utils/backtest_report_metadata.py`：`is_c7_0_3_config` 收敛为纯 `sheets[]`
  遍历（版本或标题命中）。
- `app/utils/backtest_parameter_utils.py`：`_is_c3_config` 改读 `sheets[0]`。
- `app/utils/auth.py`：顺手修复今日安全提交引入的 CLN-11 违例（启动告警改用
  `get_logger`，不用裸 `logging.getLogger`）。

## 前端同步（双前端，读侧带未迁移数据回退，写侧只产新形态）

| 文件 | 改动 |
|---|---|
| `static/js/pages/google_sheet_create.js` | 提交/存模板产 `sheets[1]`；模板回填与 restart 回填读 `sheets[0]` |
| `static/js/pages/google_sheet_detail.js` | 摘要/编辑弹窗读 `sheets[0]`；保存改部分提交（merge 语义）+ `sheets[1]` |
| `static/js/pages/backtest_training_create.js` | 提交 `sheet:{}` → `sheets:[1]` |
| `static/js/pages/backtest_training_detail.js` / `_list.js` | 展示/版本推断读 `sheets[0]`（公共 `firstSheetRef`，回退 `sheet{}`） |
| `static/js/pages/admin_tasks.js` | JSON 编辑器提交带 `merge: false` |
| `frontend/src/views/task/CreateC3.vue` | 提交/存模板产 `sheets[1]`；applyTemplate 与 loadRestartTask 读 `sheets[0]` |
| `frontend/src/views/task/Detail.vue` | C3 编辑弹窗读 `sheets[0]`；保存改部分提交 + `sheets[1]` |
| `frontend/src/views/admin/Tasks.vue` | JSON 编辑器提交带 `merge: false` |
| `frontend/src/views/backtest/Create.vue` | 提交 `sheets:[1]` |
| `frontend/src/views/backtest/Detail.vue` / `List.vue` | 展示/版本推断读 `sheets[0]` |

确认不改：C31 两版创建页（父 payload 本就是 sheets[]，子任务回填经
normalizeC4Config 透传）、ConfigEditDialog / Biz.configEdit（C4/C5/C7 本就是
sheets[]）、backtest-multi 全部（products[].sheet 未变）、api/ 与 composables/。

localStorage 草稿键（`spreadsheet/title/sheet_name`）是草稿自有格式，与任务
config 无关，未改。

## 历史数据迁移（线上为 docker 容器内 MySQL）

脚本：`scripts/migrate_task_config_schema.py`（默认 dry-run，`--apply` 落库，
幂等可重复执行；逐行模型校验，校验失败/缺 spreadsheet_id 的行跳过并登记，
不阻断整批）。

迁移内容：C3 顶层平铺 → `sheets[1]`（`title` 缺失时回退 `spreadsheet_title`）；
training 嵌套 `sheet{}`（含 `google_sheet_id/c7_model_version`）→ `sheets[1]`；
其余已知类型直接过模型结构收口。旧形态键从顶层移除。

执行方式（二选一）：

```bash
# 方式 A：宿主机直连容器映射端口（需要 DATABASE_URL 指向该 MySQL）
set DATABASE_URL=mysql+pymysql://user:pass@127.0.0.1:3306/dbname
.venv\Scripts\python scripts\migrate_task_config_schema.py --include-templates          # dry-run 看报告
.venv\Scripts\python scripts\migrate_task_config_schema.py --apply --include-templates  # 确认后落库

# 方式 B：容器内执行（镜像内含代码与依赖时）
docker compose exec <app服务名> python scripts/migrate_task_config_schema.py --apply --include-templates
```

说明：
- `--include-templates` 连同 `t_param_task_templates` 迁移（模板行无 task_type，
  按"顶层平铺 spreadsheet_id → C3 形态 / 嵌套 sheet{} → training 形态"启发式推断；
  training 创建页无模板功能，实际只会命中 C3）。模板迁移务必执行，否则创建页
  "从模板启动"回填拿到旧形态。
- 脚本走应用 SQLAlchemy 连接配置，与 `run.py` 同源；先 dry-run 核对
  `tasks/templates` 的 migrated/unchanged/skipped 计数再 `--apply`。
- **上线顺序**：停写（或低峰）→ 跑迁移 `--apply` → 发布新后端与新前端。若新前端
  先于迁移上线，读侧的旧形态回退可保证展示不空白，但编辑保存请以迁移完成为准。

## 测试

- 新增 `tests/unit/test_task_config_schema.py`（17 用例）：各类型模型校验/类型
  收口/extra 保留/单 sheet 约束/未知类型透传；`migrate_config` 的 C3 平铺、training
  嵌套、幂等、坏数据跳过；`update_task_config` 的 merge（保留未列键）与全量替换
  （删键）双语义。
- 既有测试中的旧形态 fixture（C3 平铺/training `sheet{}`）已同步更新为 sheets[] 形态。
- 全量回归 `python -m pytest tests/unit tests/integration` 结果见提交说明（网络类
  既有失败与本次改动无关，基线对照确认）。

## 已知边界

- normalize 后落库的 config 为模型 dump 全键形态（声明字段补 null 默认值），存储
  体积略增，换取编辑器可见的键全集与稳定 schema。
- 列表页 `stock_code` 筛选是对 config 文本的 LIKE 匹配，迁移脚本沿用
  `json.dumps` 默认序列化，匹配行为不变。
- 重启链路（restart_task 原地重启/看门狗）不重跑 normalize，直接消费迁移后的
  config，形态一致。

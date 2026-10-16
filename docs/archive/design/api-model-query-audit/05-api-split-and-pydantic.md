# 05 — API 文件级拆分蓝图 与 Pydantic 请求校验设计

> 承接 `01` §5 职能位置问题清单的落地设计。两条硬约束贯穿全文：
>
> 1. **URL 一律不变**——前端 101 处 fetch 调用点、`template-auth.js` 豁免清单零改动；
> 2. **单一校验体系（无兼容层）**——Pydantic 落地后移除 `app/utils/request_validation.py`，不双轨。

## 一、API 文件级拆分蓝图

### 1.1 目标结构（文件级归位，URL 保持现状）

```
app/routes/
  task_api.py            # 瘦身：保留任务 CRUD/生命周期 10 个端点；
                         #   /tasks/<id>/results（读取+CSV）迁出
  result_api.py          # 扩容：承接 /api/tasks/<task_id>/results（结果域读取，
                         #   result_api_bp 与 task_api_bp 同为 /api 前缀，路由规则不冲突）
  export_api.py          # 不变：文件流导出（如 /tasks/<id>/results 的 CSV 分支按实际形态就近归并）
  backtest_api.py        # 新建：bt 6 端点 + bmp 6 端点。一个文件两个蓝图
                         #   （bt_api_bp url_prefix=/backtest-training、bmp_api_bp /backtest-multi-product），
                         #   URL 不变；import-excel / task-result 等同构逻辑下沉共享 service
  global_preview_api.py  # 新建：2 端点（gp_api_bp url_prefix=/global-preview）
  admin_api.py           # 新建：admin.py 的 7 个 /admin/api/* 端点
                         #   （admin_api_bp url_prefix=/admin，原路由从 admin.py 删除，无规则冲突）
  dashboard 相关         # 随 admin_api.py 内聚成模块（dashboard/overview、model-summary ×3）
  logs_api.py            # 新建：/api/logs、/api/logs/latest ← config_api
  navigation_api.py      # 新建：/api/navigation-menu-items CRUD ×4 ← config_api
  config_api.py          # 瘦身：仅剩 /config、/config/validate、/system-configs ×2
  scheduler_api.py       # 注册统一：url_prefix='/api'，路由改写短路径
                         #   '/admin/scheduler/...'（最终 URL 与现状逐字节一致）
  auth_api.py / meta / stock / database / template / google_sheet_api  # 不变
  xpl.py                 # 不拆：2 个 analyze 端点留在 xpl 域（URL /xpl/analyze 不变），
                         #   但补 login_required + 信封 + 计算逻辑抽 xpl_analysis_service
```

### 1.2 拆分规则

1. **一个资源域一个文件**；文件内蓝图数可以 >1（bt/bmp 共存是刻意为之，避免为 URL 兼容制造三个单路由文件）；
2. 页面蓝图（admin_bp、bt 页面 bp 等）拆分后**只含页面路由**；`admin.py` 从 227 行回落到 ~100 行纯页面；
3. `register_blueprints`（`app/routes/__init__.py`）同步调整：scheduler_api_bp 补 `url_prefix='/api'`，新增蓝图全部显式前缀；
4. 同前缀多蓝图（/api 下 task/result/logs/navigation/…）是 Flask 支持的常规形态，只要 `route` 规则字符串不重复即可——迁移时逐条对照原路径表（`01` §1）；
5. 每文件一次 commit + `pytest tests/integration` 回归；可按文件粒度回滚。

### 1.3 显式不做

- 不改任何 URL / HTTP 方法 / 请求响应结构（前端零配合）；
- 不在本批合并 bt/bmp 的**响应结构差异**（仅代码归位；行为合并另行立项）；
- auth_api 的用户/角色 CRUD 维持在 auth 域（`01` §5.6 倾向已记录）。

---

## 二、Pydantic 请求校验设计

### 2.1 决策与依赖

- 采用 **Pydantic v2**（≥2.12，Python 3.14 官方支持；v2 Rust core，解析开销可忽略）；
- **推翻** `request_validation.py` docstring"不引入 pydantic 等重依赖"的旧决策（记录：用户决策 2026-09-04；收益是声明式 schema、字段级错误明细、类型安全的 payload，代价一个依赖）；
- 无兼容层：`validate_body` 的 5 个调用点（auth_api ×3：change_password/create_user/create_role；template_api ×2：create/update；require_query 现无调用点——校准 2026-09-05，B1-2 重写 auth_api 后计数变化）随基建批迁移改写，最终删除该文件。

### 2.2 基建（约 60 行）

```
app/schemas/
  __init__.py
  common.py        # APIModel 基类 + PageQuery 分页模型 + 非空约束复刻
  task.py backtest.py auth.py config.py scheduler.py google_sheet.py meta.py
```

```python
# app/schemas/common.py
from pydantic import BaseModel, ConfigDict, Field

class APIModel(BaseModel):
    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

class PageQuery(APIModel):
    page: int = Field(default=1, ge=1)
    per_page: int = Field(default=20, ge=1, le=100)   # 对齐现有 clamp 语义
```

```python
# app/utils/request_parsing.py（替代 request_validation.py）
from flask import request, g
from pydantic import ValidationError as PydValidationError
from app.exceptions import ValidationError

def parse_body(schema):
    try:
        payload = schema.model_validate(request.get_json(silent=True) or {})
    except PydValidationError as exc:
        raise ValidationError(_format(exc))       # 进现有 400 信封链
    g.validated = payload
    return payload

def parse_query(schema):
    try:
        return schema.model_validate(request.args.to_dict())
    except PydValidationError as exc:
        raise ValidationError(_format(exc))
```

要点：

- **不新增全局 errorhandler**：pydantic.ValidationError 在解析入口就地转 `app.exceptions.ValidationError`，复用现有 400 信封链路（`errors.py` 零改动）；
- `_format(exc)` 产出首条错误的中文消息 + `errors=[{loc, msg, type}]` 明细（放入信封 `data` 或 message，实施时定稿）；
- 兼容旧语义差异点：`validate_body` 把"缺失"与"null/空串"都视为缺失——schema 侧对必填字符串统一 `Field(min_length=1)`、可选字段显式 `| None`，迁移时逐端点对齐（差异表列在实施 PR 描述里）；
- 路由写法：`payload = parse_body(TaskCreateSchema)` 后全程 `payload.xxx` 类型安全，替代散落 `data.get()`。

### 2.3 Schema 建模范围（按收益排序）

| 批次 | 端点 | 现状校验 |
|---|---|---|
| V1 | `/api/tasks` POST、`/tasks/batch-create`、bt/bmp `/api/import-excel`、`/calculate-ratios`、`/google-sheet-tokens/import`、`/auth/login`、`/auth/password` | 手写 if 分支散落（重构收益最大）|
| V2 | scheduler 任务 POST/PUT、system-configs PUT、navigation-menu-items POST/PUT、config POST | 手写分支 |
| V3 | 5 处 `validate_body` 调用点替换 + 全部列表端点接 `PageQuery` | 旧工具 |
| V4 | 删除 `request_validation.py`；`templates_api` 等剩余端点补齐 schema | — |

### 2.4 红线与测试

- schema 只做**请求边界校验**，不携带业务规则（业务判断留在 service），不碰 ORM；
- 外部输入经 pydantic 解析后仍全部走 ORM 参数绑定（天然满足安全约束，禁止 schema 校验后改用拼接 SQL）；
- 新增 `tests/unit/test_schemas_*.py`（每域一批：合法/缺字段/类型错/越界四类用例）；`tests/integration` 全量回归信封不变；
- `extra="ignore"` 为全局默认，涉及幂等写或导入类端点（tokens/import、import-excel）可单独 `extra="forbid"` 防误传。

## 三、实施顺序建议

1. 基建批：`app/schemas/` + `request_parsing.py` + V3 的 7 处替换（不动路由归属，风险最低先行）；
2. V1/V2 schema 批：按端点逐个迁移，每端点一 commit；
3. 文件拆分批（`一、`蓝图）：与 schema 批可并行，按文件粒度提交；
4. 收尾批：删 `request_validation.py`（V4）、`errors.py` 的 `_wants_json` 注释更新（`/admin/api/*` 已成正式 API 前缀）、AGENTS.md 路由章节更新。

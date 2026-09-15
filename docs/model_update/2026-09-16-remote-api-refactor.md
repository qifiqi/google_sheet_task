# remote_api 重构：移除 stock_sdk，按控制器拆分具体接口函数（2026-09-16）

分支：`dev_db_to_http`。本次修改文档对应提交「refactor(remote-api): 移除 stock_sdk 依赖，按 URL 控制器拆分具体接口函数」。

## 1. 背景与目标

db-to-http 迁移落地上存在两套远程访问实现，本次统一为一套：

- `stock_sdk/`：Swagger 生成的 SDK 包（`StockClient` + `ApiGroup` + DTO 模型），仅
  `KlineService` 在用；
- `app/repositories/sdk_client.py`：手写适配器，用 `_REMOTE_ENDPOINTS` 注册表把
  `(group, operation)` 字符串映射到 HTTP 方法 + 路径（即"原子信息表"）。

两者的问题：字符串分发无法被 IDE 跳转/检索调用链；同一远程服务两套传输、两套异常
语义；`stock_sdk` 全量生成代码（含大量未用端点与 DTO）维护成本高。

目标：

1. 彻底移除 `stock_sdk` 依赖；
2. 移除 `_REMOTE_ENDPOINTS` 原子注册表；
3. 按 URL 中段（Swagger 控制器，如 `StockData` / `ParamTasks`）拆分文件，每个具体
   端点一个具体函数（docstring 含等价 curl 示例）；
4. 一个通用调用器承担全部传输细节；db 层（repositories）经统一出口调用；
5. IDE 可正常跳转与检索调用链。

## 2. 新结构

```
app/remote_api/
├── __init__.py       # 导出 StockApiClient / stock_api 单例 / 异常体系
├── exceptions.py     # RemoteApiError 体系（原 Sdk*Error 改名，语义不变）
├── client.py         # StockApiClient 统一调用器 + RemoteTransport + encode_remote_body
├── base.py           # ControllerApi 基类：_make_request / _make_request_with_count
└── controllers/      # 19 个控制器文件，一控制器一文件一类，共 97 个具体接口函数
    ├── param_tasks.py          # class ParamTasksApi
    ├── stock_data.py           # class StockDataApi
    ├── sys_user.py             # class SysUserApi
    └── ...
```

具体接口函数统一形如：

```python
def get_data_all_list(self, payload: Mapping[str, Any] | None = None) -> Any:
    """
    按条件查询K线全量数据（无分页）

        curl -X 'POST' \
          'http://stockapi.stplan.cn/api/StockData/GetDataAllList' \
          -H 'accept: application/json' \
          -H 'Content-Type: application/json' \
          -d '{"begin_date": "2024-01-01", "stock_code": "600000.SH"}'
    """
    return self._make_request('POST', '/api/StockData/GetDataAllList', payload)
```

约定：

- 普通端点返回解包后的 `ret_obj`；分页端点（`GetDataByPageList` / `GetListPage` /
  `GetListHisPage`）返回 `(ret_obj, ret_count)`；
- 身份端点（`SysUser/Get`、`GetUserInfo`、`GetUserRoleList`）签名显式收
  `token: str`，请求体恒为 `{}`，凭据只走 `Token` 请求头；
- 新增远程接口 = 在对应控制器文件加一个函数，不碰任何注册表。

## 3. 调用方改造

| 调用方 | 改造 |
|---|---|
| `app/repositories/http_backend/*` | `self.client.call(group, op, payload)` → `self.api.<controller>.<op>(payload)`；`HttpRepositoryBase` 持 `StockApiClient`，`_controller(name)` 供泛化 CRUD 按 group 取控制器实例 |
| `app/repositories/sys_user_repository.py` | 同上；`GetUserInfo` / `GetUserRoleList` 经 `sys_user.get_user_info(token=...)` 等具体函数 |
| `app/services/kline_service.py` | 删除 `StockClient`，改持 `stock_api`（可注入）；`ret_obj` 已由调用器解包，删除 `.ret_obj` 访问 |
| `app/services/token_identity_service.py`、`app/routes/meta_api.py`、`app/routes/auth_api.py` | 异常随体系改名：`SdkDataAccessError→RemoteApiError`、`SdkOperationError→RemoteApiOperationError` 等，捕获语义不变 |
| 已删除 | `stock_sdk/`、`app/repositories/sdk_client.py`、`SdkFilterUnavailableError`（无使用方） |

异常对照（旧 → 新，基类均为 `RemoteApiError`）：
`SdkDataAccessError→RemoteApiError`、`SdkConfigurationError→RemoteApiConfigError`、
`SdkProtocolError→RemoteApiProtocolError`、`SdkOperationError→RemoteApiOperationError`、
`SdkDuplicateKeyError→RemoteApiDuplicateKeyError`、`SdkNotFoundError→RemoteApiNotFoundError`。

## 4. 行为修复（顺带）

- **出站布尔编码回归**：远端布尔字段以 0/1 整型承载（JSON `true`/`false` 会被远端
  模型绑定拒绝）。该编码在旧 `sdk_client.py` 中缺失（`tests/test_sdk_client_bool_encoding.py`
  的前两个用例因 Python `True == 1` 碰巧通过）。现编码统一在
  `StockApiClient.request_with_count` 唯一出站出口递归完成，并由新测试
  `tests/test_remote_api_client.py` 锁定（含 `isinstance(x, bool)` 反断言）。
- **测试进程直连远程服务的护栏**：`app/__init__` 在模块导入期即连锁导入
  repositories（按 `DATA_ACCESS_MODE` 一次性绑定），早于 fixture 设置环境变量；
  随后 `create_app` 载入 `.env` 的 `STOCK_BASE_URL`，导致测试会话可能以 http 后端
  直连真实远程服务。`tests/conftest.py` 顶部新增会话级护栏：任何导入前固定
  `DATA_ACCESS_MODE=db`、清空 `STOCK_BASE_URL` / `STOCK_API_TOKEN`，确保测试永不
  触达远程（键已存在时 `.env` 不覆盖）。

## 5. 测试

- `tests/test_remote_api_client.py`（新）：布尔编码（唯一出口、递归、非布尔保形）、
  具体接口函数方法/路径分发、身份接口按 Token 路由独立传输；
- `tests/unit/test_kline_service.py`：`stock_client` 属性更名 `stock_api`；为 5 个
  存量失败用例补内部K线桩（这些用例此前依赖内网远程可达，属迁移遗留，非本次行为
  变更）；
- 全量回归（`python -m pytest tests/unit tests/integration`）：本分支失败 11 个、
  通过 638 个；同一 conftest 护栏下基线（1e9f07a）失败 24 个，本分支失败集合为
  基线的严格子集（0 个新增失败，净修复 13 个）。剩余 11 个为该分支遗留的用例与
  现行为不一致问题（C 系K线区间/数量语义、报告图表、值解析等），与本次重构无关，
  待后续单独处理。

## 6. 风险与后续

- `STOCK_BASE_URL` 未配置时远程访问快速抛 `RemoteApiConfigError`（原 kline 链路会
  回退 SDK 内置默认地址 `172.18.20.20:8081`，该兜底随 stock_sdk 一并移除；部署须
  显式配置）；
- 控制器文件由人工按 Swagger 维护；如后续端点数量显著增长，可再引入生成器，但
  产物必须保持"一端点一具名函数 + curl docstring"的形态。

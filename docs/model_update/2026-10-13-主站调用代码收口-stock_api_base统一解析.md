# 主站调用代码收口——stock_api_base 统一解析

日期：2026-10-13　分支：dev_vue_to_http（自 dev_vue 合并后）

## 背景

调用股票主站服务（部署环境由 `STOCK_BASE_URL` 指定，如 `https://stockapi.jaspil.cn/`）的代码此前分散在三处，基地址解析逻辑不统一：

| 调用方 | 文件 | 收口前的问题 |
| --- | --- | --- |
| 参数回推 `StockAPIClient` | `app/utils/db_stock_api.py` | 本地硬编码历史默认地址 `http://stockapi.stplan.cn` |
| 代理池 `SmartProxyManager` | `app/utils/proxy_manager.py` | 同上，字面量重复出现 |
| K线 SDK `KlineService` → `create_stock_client` | `app/services/kline_service.py` | 自带一份本地 `_resolve_stock_base_url()`，与 `stock_api_base.resolve_stock_base_url` 逻辑重复 |

## 改动内容

1. **`app/utils/stock_api_base.py`** 升级为调用主站的唯一收口点：
   - 新增常量 `DEFAULT_STOCK_BASE_URL = 'http://stockapi.stplan.cn'`，全库主站历史默认地址只在此定义；
   - `resolve_stock_base_url(explicit, fallback=DEFAULT_STOCK_BASE_URL)` 的 `fallback` 参数默认值即历史默认地址，调用方不再各自传字面量。
2. **`db_stock_api.py` / `proxy_manager.py`**：删除硬编码兜底字面量，改为一行 `resolve_stock_base_url(base_url)`。
3. **`kline_service.py`**：删除本地 `_resolve_stock_base_url()`，改用共享解析器；保留原语义——未配置（或纯空白）时传 `None`，由 `StockClient` 使用 SDK 自身默认地址（`stock_sdk/http_client.py` 的内网默认），业务层不硬编码兜底。
4. **`tests/unit/test_stock_api_base_url.py`**：新增 `test_default_fallback_is_module_constant`，锁定常量唯一来源契约。

## 行为不变说明

- 配置了 `STOCK_BASE_URL`：三个调用方全部使用配置值（不变）。
- 未配置：`StockAPIClient` / `SmartProxyManager` 兜底 `http://stockapi.stplan.cn`（不变）；`KlineService` 传 `None` 走 SDK 内网默认地址（不变）。
- 显式 `base_url` 参数优先级最高（不变）。

## 不在本次范围

- `app/config.py` 的 `SSO_MAIN_VERIFY_URL`（`stockapi.stplan.cn/api/SysUser/GetUserInfo`）是主服务 SSO 换票验签地址，属 `docs/design/sso-integration-2026-09/` 体系，与股票主站基地址是两个独立关注点，未收口。
- `stock_sdk/`（内置K线库读写客户端）保持独立可用，其 `DEFAULT_BASE_URL` 仅在调用方未传基地址时生效；未引入对 app 配置的反向依赖。

## 验证

`tests/unit/test_stock_api_base_url.py`、`test_proxy_manager.py`、`test_kline_service.py`、`test_kline_adjustment.py` 共 39 用例通过。全量 `tests/unit`：650 通过 / 6 跳过 / 7 失败，7 个失败（`test_kline_sheet_guardrails.py` 5 个 + `test_c_series_services.py` 2 个，均为 `ApiTimeoutError`）经 stash 基线对比确认为存量环境依赖问题——用例未桩化内置K线库，真实请求打到 SDK 默认内网地址 `172.18.20.20:8081`（本机不可达）超时所致，与本次收口无关、失败集合与改动前完全一致。

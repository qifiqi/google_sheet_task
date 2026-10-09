# 外部API基地址收敛到 STOCK_BASE_URL

日期：2026-10-09
分支：dev_vue
范围：配置系统 / 外部 API 客户端

## 背景

全库审计发现 `stockapi.stplan.cn`（股票主服务）在同一代码库中有三条独立来源：

| 消费方 | 原基地址来源 | 位置 |
|---|---|---|
| K线 SDK（StockClient/KlineService） | 环境变量 `STOCK_BASE_URL`（已配置化） | `app/config.py` → `kline_service._resolve_stock_base_url()` |
| 参数回推（StockAPIClient） | 硬编码构造参数默认值 | `app/utils/db_stock_api.py` |
| DFCF 代理池（SmartProxyManager） | 硬编码构造参数默认值 | `app/utils/proxy_manager.py` |

主服务换域名时，只改 `STOCK_BASE_URL` 会让参数回推和代理池仍指向旧地址（只能改源码）。

## 改动内容

1. **新增 `app/utils/stock_api_base.py::resolve_stock_base_url(explicit, fallback)`**
   统一解析顺序：显式参数 > 应用配置 `STOCK_BASE_URL` > 调用方历史默认地址。
   无应用上下文（独立脚本）时跳过配置读取，直接回退。

2. **`app/utils/db_stock_api.py::StockAPIClient.__init__`**
   `base_url` 默认值改为空串，经统一解析器解析；未配置时回退历史默认
   `http://stockapi.stplan.cn`。唯一调用点 `google_sheet_tasks/base.py` 的
   `StockAPIClient()` 无需改动。

3. **`app/utils/proxy_manager.py::SmartProxyManager.__init__`**
   同上；代理池端点 `/api/StockDic/GetProxyListByOne` 跟随解析结果构建。
   单例 `get_smart_proxy_manager()` 首次创建发生在任务线程 app context 内，
   配置可正常读取。

4. **`app/config.py`**：`STOCK_BASE_URL` 注释更新为三消费方共用语义（键名与
   环境变量不变）。

5. **`.env.example`**：补充 `STOCK_BASE_URL` 条目及说明。

6. **测试**：新增 `tests/unit/test_stock_api_base_url.py`（7 例：显式参数优先、
   配置读取、无上下文回退、两个客户端集成解析、代理端点拼装）。

## 行为影响

- **生产**（`.env`: `STOCK_BASE_URL=http://stockapi.stplan.cn`）：三个消费方解析结果
  与原硬编码值一致，**零行为变化**。
- **开发**（`.env.development`: `STOCK_BASE_URL=http://172.18.20.20:7070`）：参数回推
  与代理池从 `stockapi.stplan.cn` 跟随到 `172.18.20.20:7070`。若开发实例未部署
  `/api/StockParamResult/*`、`/api/StockDic/*`，在 `.env.development` 中调整该值即可。
- **未配置 `STOCK_BASE_URL` 的环境**（如 `.env.testing`）：回退历史默认地址，行为不变。

## 未收敛项（有意保留）

- 东方财富（`dfcf_api.py`）、腾讯财经（`qq_api.py`）：公开固定行情端点，硬编码维持。
- SSO 校验地址 `SSO_MAIN_VERIFY_URL`：已独立配置化（默认 https 主服务校验接口），不动。
- 钉钉 webhook `oapi.dingtalk.com`：官方固定端点。
- `stock_sdk/http_client.py::DEFAULT_BASE_URL`：SDK 内部兜底，被 `STOCK_BASE_URL` 覆盖时无效。

## 验证

- `python -m pytest tests/unit/test_stock_api_base_url.py tests/unit/test_proxy_manager.py`：8 通过。
- 全量回归 `tests/unit tests/integration`：778 通过 / 25 失败；经 git stash 基线复跑确认
  25 个失败均为存量问题（日期解析、golden 投影、图表图例等），与本改动无关。

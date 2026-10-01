# 2026-10-01 dev_vue 并入 dev_db_to_http（合并记录）

## 背景

`dev_vue`（31 个提交：K线自有接口与页面重写、V3 回测分析页图表化、URL 全库收敛入 /api 单命名空间、
暗色主题、全局预览 Word 导出、移动端适配、docs 清理等）整体并入 `dev_db_to_http`
（db→http 数据层迁移分支：单 Token 子服务鉴权 + `app/remote_api` 远端数据访问 + `DATA_ACCESS_MODE` 双后端）。

合并提交：`ba61604`（merge commit，含冲突解决与测试适配）。

## 合并原则

保留 dev_db_to_http 的迁移决策，采纳 dev_vue 的全部新功能：

- 单 Token 子服务鉴权不变：本地 JWT/RBAC/SSO/仪表盘/看门狗保持停用（注释保留）；
- URL 采用 dev_vue 收敛后的 `/api` 单命名空间（`/api/admin/*`、`/api/backtest-training/*` 等），
  停用端点的注释同步对齐新前缀；
- dev_vue 新功能（K线 `/api/klines`、绩效分析 V3、analyze `include_series`、权重组合分析等）
  数据面全部经 repositories 绑定点，http 模式自动走远端。

## 冲突解决（11 文件）

| 文件 | 解法 |
|---|---|
| `app/routes/auth_api.py` | 保留单 Token 版（远程登录代理 + 本地 RBAC 注释保留），弃 dev_vue 的 Pydantic 本地鉴权版 |
| `app/routes/admin_api.py` | 仪表盘接口保持停用，注释内 URL 对齐 `/api/admin/dashboard/overview` |
| `app/routes/pages/admin.py` | 仪表盘/用户/角色/菜单页保持停用；`/admin/` 根重定向由 dashboard 改指 `.tasks` |
| `app/services/kline_service.py` | 保留 remote_api 控制器调用与 `RemoteApiConfigError` 降级；吸收 dev_vue 的 `rows[min(7, len-1)]` 越界防护；弃 stock_sdk 时代 `_resolve_stock_base_url`（无调用方） |
| `app/services/google_sheet_token_service.py` | 保留 dict 兼容 `_token_is_available`（http 后端 RemoteRecord 无模型方法）与 HTTP 后端本地排序 |
| `static/js/template-auth.js` | 保留 SSO 停用分支（ssoToken=null） |
| `tests/conftest.py` | 防直连远程护栏（db_to_http）+ word 导出缓存隔离 fixture（dev_vue）合并保留 |
| `docs/目录索引.md` | 双侧条目合并（db-to-http-migration 条目 + 2026-10-01 docs 清理条目） |
| 其余测试 3 文件 | 见下 |

## dev_vue 新测试适配单 Token 模式（17 例合并引入失败 → 0）

本地 JWT 退役后，dev_vue 新增测试的登录方式全部改为 `AUTH_ENABLED=false` mock 用户
（与分支内 `test_rate_limiting` 既有口径一致）：

- `test_stock_kline_api` / `test_performance_analysis_series` / `test_xpl_v3_page` /
  `test_weight_combination_products_api`：`create_access_token`/本地登录改 mock 用户 + 空鉴权头；
- `test_xpl_v2_page` 4 例补 `_auth_disabled(monkeypatch)`；
- `test_rate_limiting::test_word_report_endpoint_rate_limit_raised`：本地登录改 mock（限流键回落 anon）；
- `test_c6_preview_validation`：URL 用收敛后的 `/api/backtest-multi-product/...`，弃 Bearer 头；
- `test_global_preview`：URL 用收敛后连字符路径 + 保留网关 302 断言的 `Accept: text/html`；
- `test_static_pages`：仪表盘页停用不纳入断言；
- `test_stock_metadata_service`：`FakeDfcfApi.get_stock_kline_data` 补 `kline_type` 形参
  （dev_vue 侧存量问题，fake 与真实签名 `dfcf_api.py:114` 脱节）。

## 回归结论

全量 `python -m pytest tests/unit tests/integration`：**10 failed / 740 passed / 57 skipped**。

10 个失败为 dev_db_to_http 既有基线（合并前 11 例）的**严格子集**——基线中的
`test_performance_analysis_weight_combination::test_weight_combination_yields_requested_metrics`
合并后转绿；零新增失败。基线失败清单见 `docs/design/db-to-http-migration/README.md` §7。

## 遗留与建议（本次登记，未实施）

1. **P0** `task_result_repository.list_by_task_fields` 无 http 孪生（dev_vue 新增的 fields 投影，
   http 模式下 `/api/tasks/<id>/results?fields=` 会 AttributeError）——已登记迁移文档 §6.2，补法见该表。
2. **P2** 前端残留：`navbar.js` 内置菜单仍有 `/admin/dashboard` 链接（该页停用）；
   `static/js/pages/admin_{dashboard,users,roles,navigation}.js` 为孤儿页面 JS，可删。
3. **P1** 钉钉告警值班名单仍读本地 User 表（迁移文档 §6.3 既有待办），纯 http 部署值班收件人失效。
4. §6.1/§6.2 既有 33 处 `TODO(db-to-http)` 退化策略不变，按文档 §8（Redis 裁决层/远端增量端点）推进。

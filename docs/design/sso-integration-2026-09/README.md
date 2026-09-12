# 主服务 SSO 接入设计（2026-09）

子服务作为主服务的子模块接入：主服务侧边栏携带 Token 跳入本服务，两套登录
并存（主服务 Token 换票 + 本地账号密码），共用同一套本地 JWT/RBAC 会话。

## 1. 方案选型：入口换票（非每请求透传）

| 维度 | 透传校验（每请求带 Token） | 入口换票（已采用） |
| --- | --- | --- |
| 页面导航 | 浏览器导航带不了自定义 header，需把主服务 Token 写 cookie，与 `gsc_access_token` 回退链路冲突 | 不受影响，导航走现有 cookie |
| 主服务可用性 | 每请求多一跳，主服务宕机子服务全瘫 | 只影响新进入，已登录会话不受影响 |
| 对既有接缝 | `login_required` 语义要改 | **零改动**：仅新增免登端点 + 登录页入口钩子 |
| 会话实时性 | 主服务禁用实时生效 | 不实时（本地 JWT 最长 2h，refresh 7d） |

## 2. 端到端时序

```
主服务侧边栏 [class 绑定点击]
  → window.open("https://<子服务>/login?next=<落地页>#sso_token=<主服务Token>")
子服务 /login（template-auth.js）
  → consumeSsoTokenFromHash()：读 fragment 并立即 replaceState 清除
  → POST /api/auth/sso/exchange   header: Token: <主服务Token>
子服务后端（sso_service）
  → _validate_verify_url：仅 HTTPS 公网主机名，解析 IP 拒绝私网/环回/保留地址
  → POST <SSO_MAIN_VERIFY_URL>（header Token，禁重定向/禁代理）
  → ret_code==200 且 ret_obj.username 非空 → 同名合并本地账号
      · 本地无此用户：随机不可用密码建号 + 挂 main_service_user 角色
      · 本地已有同名：保留既有角色，仅并集追加 main_service_user（策略 A）
      · 已禁用：401 拒绝，不自动启用
  → 签发本地 access/refresh JWT（返回结构与 /api/auth/login 一致）
子服务前端
  → setTokens()（localStorage + gsc_access_token cookie）→ 跳 next
之后所有请求走现有 JWT 链路；账号密码登录完全不变。
```

## 3. 组件与代码位置

| 组件 | 位置 |
| --- | --- |
| 换票端点（免登） | `app/routes/sso.py` → `POST /api/auth/sso/exchange`，header `Token` |
| 校验 client + 用户映射 | `app/services/sso_service.py` |
| 默认角色/权限常量 | `app/config.py`：`SSO_ROLE`、`SSO_DEFAULT_PERMISSION_CODES`、`SSO_ENABLED`、`SSO_MAIN_VERIFY_URL`、`SSO_MAIN_VERIFY_TIMEOUT` |
| 角色播种 | `app/startup.py::init_rbac`（`flask init-rbac` 手动执行；角色 is_system=True，权限并集补齐不覆盖后台手工调整） |
| 登录页入口钩子 | `static/js/template-auth.js`：`consumeSsoTokenFromHash/performSsoExchange`，端点加入 `authExemptPaths` |
| 数据层新方法 | `app/repositories/auth_repository.py`：`get_user_entity_by_username`、`get_role_id_by_code`、`append_user_role`（并集语义） |

默认权限 = 仪表盘（登录落地）+ `DEFAULT_NAVIGATION_MENU` 数据/业务模块初始路由：
`page:admin:dashboard`、`page:admin:model_summary`、`page:global_preview:single_product`、
`page:google_sheet:c3/c4/c5/c7`、`page:backtest:list`、`page:backtest_multi_product:list`。
东方财富 K 线、夏普率（performance_analysis）、回测数据分析导航项无 `page:*` 权限码，
天然对全部登录用户可见。`page:global_preview:single_product` 已补入静态 `PERMISSIONS`。

## 4. Token 传递用 fragment 而非 query

`/login#sso_token=...`：fragment 不会发送到服务端（不进访问日志）、不会进入
页面发出的子资源请求 Referer；登录页 JS 读到后立即 `history.replaceState` 清除。
若放 `?sso_token=`，落地页首帧的 CDN 静态资源请求会携带完整 URL 作为 Referer。

## 5. 安全校验清单（已实现）

- 主服务校验接口：仅 HTTPS + 公网 IP（`socket.getaddrinfo` 解析后逐 IP 校验
  `ipaddress.is_global`），禁 `allow_redirects`，禁请求库代理环境变量，
  `verify=True`（TLS 证书校验同时兜底 DNS rebinding——内网主机无法持有
  主服务域名的合法证书）。
- 上游失败映射：HTTP 401/403 或 `ret_code!=200` → 401；超时/网络/非 JSON →
  500（`ServiceError`）。任何情况不降级放行，上游正文只进日志 detail。
- 开放重定向加固：`getLoginNextUrl()` 经 `sanitizeNextUrl()`，仅接受同源
  相对路径（拒绝 `//`、控制字符）。
- SSO 建号密码为 `secrets.token_hex(32)` 随机值（不可被密码登录）。
- 用户名精确匹配（`User.username` unique）；主服务 `userid` 仅记日志，不落库。

## 6. 配置与部署

| 配置 | 默认值 | 环境变量覆盖 |
| --- | --- | --- |
| `SSO_ENABLED` | `True` | `SSO_ENABLED` |
| `SSO_MAIN_VERIFY_URL` | `https://stockapi.stplan.cn/api/SysUser/GetUserInfo` | `SSO_MAIN_VERIFY_URL` |
| `SSO_MAIN_VERIFY_TIMEOUT` | `5` 秒 | `SSO_MAIN_VERIFY_TIMEOUT` |

部署步骤（一次性）：

```bash
flask init-rbac    # 播种 main_service_user 角色与默认权限（幂等，可重复执行）
```

若未播种，换票返回 500「SSO 默认角色缺失」，日志 detail 指引执行 init-rbac。

## 7. 主服务（DY.Stock.Web）侧改造指南

目标：侧边栏按路由 code 前缀渲染特殊菜单项，点击后携带当前用户 Token 跳入
子服务。子服务已就绪，主服务只需生成正确的 URL。

### 7.1 URL 契约（唯一契约）

```
https://<子服务域名>/login?next=<URL编码的落地路径>#sso_token=<URL编码的Token>
```

- `next` 省略时默认 `/admin/`（仪表盘）。
- Token 必须放 fragment（`#` 后），不要放 `?` 查询串。

### 7.2 侧边栏生成（菜单渲染处）

```csharp
// 菜单项 ViewModel 按 code 前缀打标（例如约定 code 以 "gsc:" 开头）
if (item.Code.StartsWith("gsc:"))
{
    item.CssClass = "gsc-subservice-link";
    item.Href = item.Url;   // 外链，不走站内路由
}
```

```html
<!-- 渲染：<a class="sidebar-link gsc-subservice-link" data-subservice-url="..." href="#">任务校验平台</a> -->
```

### 7.3 点击事件（事件委托，全局绑一次）

```javascript
document.addEventListener("click", function (evt) {
    var link = evt.target.closest("a.gsc-subservice-link");
    if (!link) return;
    evt.preventDefault();

    var token = window.localStorage.getItem("token");   // ← 按主服务实际存储调整
    if (!token) { location.href = "/Login"; return; }

    var target = link.dataset.subserviceUrl;            // https://gsc.example.com/login
    var next = encodeURIComponent("/admin/");
    var sso = encodeURIComponent(token);
    window.open(target + "?next=" + next + "#sso_token=" + sso, "_blank", "noopener");
});
```

### 7.4 注意事项

- Token 若存 HttpOnly cookie（前端 JS 读不到），不能强行改非 HttpOnly：
  由主服务后端提供一个「点击时签发短时一次性 ticket」的接口替代（子服务
  校验端点改为先 consume ticket 再取用户），其余链路不变。
- 菜单若经后台权限表下发，code 前缀约定要与路由表维护流程一致，避免运营
  改 code 后 class 丢失。
- 不要在主服务前端直接调 `GetUserInfo` 预校验：校验由子服务后端完成，避免
  CORS 与双重鉴权逻辑。

## 8. 测试

`tests/integration/test_sso_exchange.py`（12 用例）：首次建号挂默认角色、
同名合并保留 admin、禁用账号 401、上游 `ret_code!=200`/超时/HTTP 502 映射、
缺 Token 头 401、重复换票幂等、`SSO_ENABLED=false`、非 HTTPS/私网校验地址
拒绝、`init_rbac` 角色播种与权限并集补齐、本地密码登录并存回归。

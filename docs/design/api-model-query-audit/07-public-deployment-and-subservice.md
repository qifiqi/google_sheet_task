# 07 — 公网部署加固与子服务化边界

> **架构前提（用户决策 2026-09-05）**：本项目后续将作为**子服务接入主服务**，路由网关、鉴权、权限、角色、登录**全部迁移到主服务**。当前内部的 RBAC（`t_param_user/role/permission`、JWT 登录、`template-auth.js`）是内部项目时期的历史产物。
>
> 因此本分册把"公网部署需要做的事"切成两栏：**移交主服务**（本项目不动）与**本项目仍需处理**（与鉴权无关的服务加固）。整改时严禁越界做权限类建设。

## 1. 移交主服务清单（登记为"已知状态"，本项目不改）

| # | 事项 | 现状（已核实） | 移交后归属 |
|---|---|---|---|
| 1.1 | **接口级授权缺失**：全部 admin 类 API 仅 `login_required`，无角色校验——任何登录用户可调 `/api/admin/users|roles|permissions`（增删用户/角色）、`/api/database/vacuum`、`/api/admin/scheduler/*`、`/admin/api/model-summary/rebuild` | `auth_api.py:156-306`、`database_api.py:14-25` 仅挂 `login_required`；`config.py:453` 注明接口级细粒度权限已移除 | 主服务网关统一鉴权 |
| 1.2 | 登录防爆破：`/api/auth/login` 无限次密码尝试（`auth_api.py:53`） | 无失败锁定、无频率限制 | 主服务登录体系 |
| 1.3 | `xpl` `/analyze`、`/v1/analyze` 未挂 `login_required` | 公网暴露计算接口 | 主服务网关路由鉴权 |
| 1.4 | RBAC 三表 + 关联表、登录/refresh/me/logout/password 接口、`template-auth.js` 前端鉴权流 | 现状可用，公网下水平越权面如 1.1 | 整体迁移/替换 |
| 1.5 | 页面 HTML 无服务端守卫（客户端鉴权架构，页面骨架匿名可见；数据全在登录后的 API 之后） | 既定设计 | 主服务网关决定页面守卫方式 |

> 1.1 在公网 + 主服务接入完成之前的**过渡窗口**内是真实的水平越权面。缓解选项（不需要本项目实现，二选一）：a) 主服务网关先上线、公网流量经网关过滤后再进本服务；b) 过渡期不公开 admin 前缀路径（nginx `deny`/网关路由白名单）。**本项目代码不做任何权限改动。**

## 2. 本项目仍需处理（与鉴权无关的公网加固）

### 2.1 P1 —— 部署形态红线

- **禁止 `app.run(host='0.0.0.0')` 直接暴露**（`run.py:22` 是开发服务器）：公网必须 nginx(TLS) → Gunicorn（`dockers/gunicorn.conf.py` 已具备）；
- nginx 侧安全响应头：`HSTS`、`X-Content-Type-Options: nosniff`、`X-Frame-Options: DENY`、`Referrer-Policy`；
- `APP_ENV=production` 部署（启动校验已强制 `AUTH_ENABLED=true`、拒绝默认 `JWT_SECRET_KEY`——`app/utils/auth.py:59-70`，**这部分无需动**）。

### 2.2 P1 —— 请求体/上传大小限制（当前完全未设，已核实）

- Flask：`app/config.py` 增 `MAX_CONTENT_LENGTH = 50MB`（import-excel 上传 Excel 的合理上限，超限 Flask 抛 413 → `errors.py` HTTPException 链自动转信封）；
- nginx：`client_max_body_size 50m;` 与上对齐；
- 此项与鉴权无关，任何部署形态都成立。

### 2.3 P2 —— 服务保护限流（`06` 分册）中与鉴权无关的部分

- xpl analyze / 重计算 / 导出端点按 user 键限流**保留**（保护的是本服务的 CPU/IO，不是权限）；
- 登录限流（`06` §3 第一行）**降级为过渡期可选项**：登录将迁移主服务，若过渡期公网暴露 login 才挂载，否则跳过。

### 2.4 已就位、无需动的（公网检查项直接打勾）

| 项 | 现状 |
|---|---|
| 错误响应不泄内部信息 | `errors.py` 兜底 500 固定文案，detail 仅入日志 |
| CSRF | JWT 存 localStorage + `Authorization: Bearer` 头，**无 cookie，天然免疫 CSRF**（⚠️ 主服务接入若改为 cookie 传递身份，需重新评估此结论） |
| 日志脱敏 | `config_manager` 对 token/secret/password 类 key 打码 |
| 配置不落库敏感明文 | 敏感项走环境变量 |

## 3. 子服务化接缝预留（只记录约束，不实现）

未来鉴权迁移时的最小改造面——现在写代码时**保持这些接缝单一**，迁移成本就低：

1. **服务端**：所有 API 的身份校验只经 `app/utils/auth.py::login_required` 一个装饰器入口——迁移时把它替换为"校验主服务签发的 token / 网关注入的身份头"即可，禁止各路由自写鉴权逻辑（现状已满足，维持）；
2. **前端**：鉴权行为全部集中在 `static/js/template-auth.js`（token 存取、fetch 包装、401 刷新、登录跳转）——迁移时替换此文件与其登录页，页面业务代码零改动（现状已满足，维持）；
3. **URL**：网关接入会在主服务域名下挂载本服务路径前缀，前端相对路径请求（`/api/...`）需要网关重写或 base 路径适配——这是接入期的部署配置问题，本项目代码无需预防性改造；
4. **不做**：不为迁移预留双认证开关、不做灰度双轨（无兼容层原则同样适用于迁移期，届时一次切换）。

## 4. 整改清单汇总（本分册范围）

| # | 优先级 | 动作 | 触发条件 |
|---|---|---|---|
| 7.1 | P1 | `MAX_CONTENT_LENGTH = 50MB`（config.py）+ nginx `client_max_body_size` | 公网部署前（内网也可做，零风险） |
| 7.2 | P1 | 公网部署形态：nginx TLS + 安全头 + Gunicorn，禁 dev server 直暴；写入部署检查单 | 公网部署前 |
| 7.3 | P2 | `06` 服务保护限流（除登录项） | 随 `05`/拆分批实施 |
| 7.4 | — | §1 移交清单**原样登记**到主服务接入需求，本项目不实现 | 主服务接入项目 |

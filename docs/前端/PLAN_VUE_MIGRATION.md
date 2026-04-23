# 前后端分离迁移计划

## 阶段一：API 层标准化

### 目标
确保所有页面所需数据都可通过 REST API 获取，统一响应格式，为 Vue 前端做好准备。

### 现状
- 大部分页面已经是客户端渲染（AJAX 调用 /api/*），Jinja2 注入的变量很少
- API 响应格式不统一：部分用 `{status: "success"}`, 部分用 `{success: true}`
- 缺少的 API：版本信息接口、枚举选项接口、前端路由元数据接口

### 任务清单

#### 1.1 统一 API 响应格式
- 创建 `app/utils/api_response.py` 统一响应工具
- 标准格式：`{code: 0, data: ..., message: ""}` 成功，`{code: 错误码, data: null, message: "错误信息"}` 失败
- 新接口使用新格式，老接口暂不改动（避免破坏现有前端）

#### 1.2 补齐缺失的 API 接口
- `GET /api/meta/versions` — 返回可用版本列表（c3, c4, c5, c31）
- `GET /api/meta/enums` — 返回前端需要的枚举值（google_sheet_table_type_options 等）
- `GET /api/meta/nav` — 返回导航菜单结构
- 移除 admin/dashboard.html 中冗余的服务端注入变量（JS 已通过 API 获取）

#### 1.3 创建 Vue 项目脚手架
- 在项目根目录创建 `frontend/` 目录
- 使用 Vue 3 + Vite + Vue Router
- 配置 Vite 代理开发环境 API 请求到 Flask 5000 端口

#### 1.4 配置 nginx
- 创建 `nginx.conf` 示例配置
- 静态文件走 nginx，`/api/*` 反代到 Flask

### 完成状态：✅ 已完成

- [x] 1.1 `app/utils/api_response.py` — 统一响应工具
- [x] 1.2 `app/routes/meta_api.py` — meta API 蓝图（versions/enums/nav）
- [x] 1.3 `frontend/` — Vue 3 + Vite + Vue Router + Axios 脚手架
- [x] 1.4 `nginx.conf` — 生产部署配置

---

## 阶段二：Vue 基础框架搭建 + Element Plus + 响应式

### 目标
搭建完整的 Vue 前端框架，基于 Element Plus 组件库，支持 PC 和移动端响应式布局。

### UI 框架选型

| 依赖 | 版本 | 用途 |
|------|------|------|
| Element Plus | ^2.x | UI 组件库（表格、表单、弹窗、菜单等） |
| @element-plus/icons-vue | ^2.x | 图标库 |
| unplugin-auto-import | latest | 自动导入 Element Plus API |
| unplugin-vue-components | latest | 自动按需导入 Element Plus 组件 |

### 响应式策略

#### 断点定义（与 Element Plus 一致）
| 断点 | 宽度 | 设备 |
|------|------|------|
| xs | <768px | 手机 |
| sm | 768-991px | 平板竖屏 |
| md | 992-1199px | 平板横屏 |
| lg | 1200-1919px | 桌面 |
| xl | ≥1920px | 大屏 |

#### 布局适配规则
- **PC 端（≥992px）**：左侧固定侧边栏（240px）+ 右侧内容区
- **平板（768-991px）**：侧边栏可折叠为图标模式（64px）
- **手机（<768px）**：侧边栏隐藏，顶部汉堡菜单触发抽屉式侧边栏；表格改为卡片列表；表单单列布局

#### 关键适配点
| 组件 | PC | 手机 |
|------|-----|------|
| 侧边栏 | 固定展开 | 抽屉式，点击遮罩关闭 |
| 数据表格 | `el-table` 完整列 | 卡片列表或隐藏次要列 |
| 表单 | 多列 `el-row` + `el-col` | 单列全宽 |
| 弹窗 | `el-dialog` 居中 | 全屏 `fullscreen` |
| 操作按钮 | 文字+图标 | 仅图标或底部固定栏 |

### 任务清单

#### 2.1 安装 Element Plus 及配置按需导入
- `npm install element-plus @element-plus/icons-vue`
- `npm install -D unplugin-auto-import unplugin-vue-components`
- 配置 `vite.config.js` 按需导入
- 创建 `src/styles/index.scss` 全局样式 + 响应式变量

#### 2.2 全局布局组件
- `AppLayout.vue` — Element Plus `el-container` + `el-aside` + `el-main`
- `AppSidebar.vue` — `el-menu` 侧边栏，从 `/api/meta/nav` 加载
- `AppHeader.vue` — 顶部栏：面包屑 + 用户信息 + 手机端汉堡按钮
- 使用 CSS media query + `el-drawer` 实现手机端侧边栏
- `useResponsive()` composable — 监听窗口宽度，暴露 `isMobile/isTablet/isDesktop`

#### 2.3 公共业务组件（基于 Element Plus 封装）
- `StatusTag.vue` — 基于 `el-tag` 的任务状态标签
- `TaskTable.vue` — 基于 `el-table` + `el-pagination` 的任务表格，手机端自动切换卡片模式
- `TaskCard.vue` — 手机端任务卡片（`el-card`）
- `SearchForm.vue` — 基于 `el-form` 的搜索栏，手机端折叠为筛选按钮
- 全局 `ElMessage` / `ElMessageBox` 直接使用，不再单独封装

#### 2.3 API 模块化
按业务拆分 API 调用文件：
- `src/api/task.js` — 任务 CRUD、取消、重启、日志、结果、SSE 事件流
- `src/api/config.js` — 系统配置、系统日志
- `src/api/template.js` — 模板 CRUD
- `src/api/googleSheet.js` — Google Sheet 管理、Token 管理、Worksheet 查询
- `src/api/scheduler.js` — 定时任务 CRUD
- `src/api/database.js` — 数据库状态、优化
- `src/api/admin.js` — 仪表盘、运行时详情
- `src/api/backtest.js` — 回测训练相关

#### 2.4 路由结构
```
/login                       → 登录页
/                           → 首页（重定向到任务列表）
/task/create?version=c3     → C3 创建页
/task/create?version=c4     → C4 创建页
/task/create?version=c5     → C5 创建页
/task/create?version=c31    → C31 批量创建页
/task/list?version=c3       → 任务列表
/task/:id                   → 任务详情
/backtest/create             → 回测训练创建
/backtest/list               → 回测训练列表
/backtest/:id                → 回测训练详情
/backtest/:id/preview        → 全局预览
/backtest/result/:id         → 结果详情
/admin                       → 仪表盘
/admin/tasks                 → 任务管理
/admin/config                → 系统配置
/admin/logs                  → 系统日志
/admin/templates             → 模板管理
/admin/results               → 结果查询
/admin/google-sheets         → Google Sheets 管理
/admin/scheduler             → 定时任务
/xpl                         → XPL 分析
```

#### 2.5 状态管理（可选）
- 如果页面间共享状态较少，用组件级 `ref/reactive` 即可
- 如果后续发现需要全局状态（如当前用户配置、轮询间隔），再引入 Pinia

#### 2.6 移除 SSE 事件流，改用轮询

SSE 原用于日志实时推送，实际价值不大，改为前端定时轮询 API。

**后端移除清单：**
- `app/routes/task_api.py` — 删除 `GET /api/tasks/<task_id>/events` 端点
- `app/services/task_manager.py` — 删除 `task_events` 字典及相关 `queue.Queue` 逻辑
- `app/services/google_sheet_service.py` — 删除向 `task_events` 推送事件的代码

**前端（老模板，迁移时自然移除）：**
- `templates/google_sheet/create.html` — EventSource 相关 JS
- `templates/google_sheet_c4/create.html` — 同上
- `templates/google_sheet_c5/create.html` — 同上
- `templates/google_sheet_c31/create.html` — 同上

**替代方案：**
- Vue 详情页使用 `setInterval` 轮询 `GET /api/tasks/<id>` + `GET /api/tasks/<id>/logs`
- 轮询间隔从系统配置读取（已有 `GET /api/config`）
- 任务完成/失败后自动停止轮询

**nginx 配置：**
- 删除 `nginx.conf` 中 SSE 专用的 `proxy_buffering off` location 块

---

## 阶段三：逐页迁移（按优先级排序）

### 目标
按页面复杂度和使用频率排序，逐个将 Jinja2 模板迁移为 Vue 页面。每迁移一个页面，老模板保留但标记废弃，直到全部完成后统一删除。

### 迁移顺序与工作量评估

> 所有页面统一使用 Element Plus 组件，每个页面必须同时实现 PC 和手机端适配。

#### 第一批：管理后台页面（复杂度低，依赖少）

| 序号 | 页面 | 老模板 | 复杂度 | Element Plus 组件 | 响应式要点 |
|------|------|--------|--------|-------------------|-----------|
| 3.1 | 仪表盘 | `admin/dashboard.html` | ⭐ | `el-statistic` + `el-card` + `el-table` | 统计卡片 `el-row :gutter` 自动换行 |
| 3.2 | 系统配置 | `admin/config.html` | ⭐ | `el-form` + `el-input` | 手机端 `label-position="top"` |
| 3.3 | 系统日志 | `admin/logs.html` | ⭐ | `el-table` + `el-tag` | 手机端隐藏次要列 |
| 3.4 | 模板管理 | `admin/templates.html` | ⭐⭐ | `el-table` + `el-dialog` + `el-form` | 弹窗手机端 `fullscreen` |
| 3.5 | 结果查询 | `admin/results.html` | ⭐⭐ | `el-table` + `el-pagination` + `el-drawer` | 详情用 `el-drawer` 替代弹窗 |
| 3.6 | Google Sheets | `admin/google_sheets.html` | ⭐⭐ | `el-tabs` + `el-table` + `el-form` | Tab 切换 Sheet/Token 管理 |
| 3.7 | 定时任务 | `admin/scheduler.html` | ⭐⭐ | `el-table` + `el-switch` + `el-dialog` | 操作列手机端改为下拉菜单 |
| 3.8 | 任务管理 | `admin/tasks.html` | ⭐⭐ | `el-table` + `el-select` + `el-pagination` | 筛选栏手机端折叠 |

#### 第二批：任务列表和详情页（中等复杂度）

| 序号 | 页面 | 老模板 | 复杂度 | Element Plus 组件 | 响应式要点 |
|------|------|--------|--------|-------------------|-----------|
| 3.9 | 任务列表 | `google_sheet/index.html` | ⭐⭐ | `el-table` / `el-card` | 手机端切换为 `TaskCard` 列表 |
| 3.10 | C3 详情 | `google_sheet/detail.html` | ⭐⭐⭐ | `el-descriptions` + `el-tabs` + `el-table` | Tab 切换日志/结果，手机端纵向排列 |
| 3.11 | C4 详情 | `google_sheet_c4/detail.html` | ⭐⭐⭐ | 同上 | 同上 |
| 3.12 | C5 详情 | `google_sheet_c5/detail.html` | ⭐⭐⭐ | 同上 | 同上 |

#### 第三批：任务创建页（复杂度最高）

| 序号 | 页面 | 老模板 | 复杂度 | Element Plus 组件 | 响应式要点 |
|------|------|--------|--------|-------------------|-----------|
| 3.13 | C3 创建 | `google_sheet/create.html` | ⭐⭐⭐⭐ | `el-steps` + `el-form` + `el-select` | 分步表单，手机端 `el-steps` 改 `simple` 模式 |
| 3.14 | C4 创建 | `google_sheet_c4/create.html` | ⭐⭐⭐⭐ | 同上 | 同上 |
| 3.15 | C5 创建 | `google_sheet_c5/create.html` | ⭐⭐⭐⭐ | 同上 | 同上 |
| 3.16 | C31 批量 | `google_sheet_c31/create.html` | ⭐⭐⭐⭐⭐ | `el-form` + `el-table`(可编辑) + `el-select` | 批量参数表格手机端改为逐条卡片编辑 |

#### 第四批：回测训练页面

| 序号 | 页面 | 老模板 | 复杂度 | Element Plus 组件 | 响应式要点 |
|------|------|--------|--------|-------------------|-----------|
| 3.17 | 回测创建 | `backtest_training/create.html` | ⭐⭐⭐ | `el-upload` + `el-autocomplete` + `el-form` | 上传区域全宽 |
| 3.18 | 回测列表 | `backtest_training/list.html` | ⭐⭐ | `el-table` / `el-card` | 同任务列表 |
| 3.19 | 回测详情 | `backtest_training/detail.html` | ⭐⭐⭐ | `el-descriptions` + `el-table` + `el-tabs` | 同任务详情 |
| 3.20 | 全局预览 | `backtest_training/global_preview.html` | ⭐⭐⭐ | `el-table` + 图表(可选 ECharts) | 手机端图表全宽，表格横向滚动 |
| 3.21 | 结果详情 | `backtest_training/result.html` | ⭐⭐ | `el-descriptions` + `el-card` | 自然适配 |

#### 第五批：工具页面（独立，优先级最低）

| 序号 | 页面 | 老模板 | 复杂度 | Element Plus 组件 | 响应式要点 |
|------|------|--------|--------|-------------------|-----------|
| 3.22 | XPL 分析 | `xpl/index.html` | ⭐⭐ | `el-upload` + `el-table` | 上传+结果全宽 |
| 3.23 | XPL v1 | `xpl/v1.html` | ⭐⭐ | `el-form` + `el-table` | 同上 |

> 3.24 / 3.25 娱乐页面（yule）已决定移除，不迁移。迁移时同步删除 `app/routes/yule.py`、`templates/yule/` 及蓝图注册。

### 每个页面的迁移步骤（标准流程）

1. 阅读老模板，梳理所有 JS 逻辑（初始化、回填、提交、轮询）
2. 确认所需 API 已存在且返回数据完整，缺失则补齐
3. 创建 Vue 页面组件，使用 Element Plus 组件实现等价功能
4. 实现响应式适配：PC 端完整布局 + 手机端适配（参照上表的响应式要点）
5. 使用浏览器 DevTools 分别在 PC（1920px）和手机（375px）下验证布局
6. 本地联调测试（Vite dev server + Flask）
7. 构建并部署到 nginx，验证生产环境
8. 老模板标记 `<!-- DEPRECATED: migrated to Vue -->` 但暂不删除

### 迁移完成后的清理

- 删除所有 `templates/` 下的 Jinja2 模板
- 删除 `google_sheet.py` 等页面渲染路由（保留 API 路由）
- 删除 `base.html` 等布局模板
- 删除 `app/routes/yule.py` + `templates/yule/`（已废弃，不迁移）
- 删除 SSE 相关代码（task_events、events 端点）
- Flask 仅保留 API 服务角色
- 更新 `CLAUDE.md` 反映新架构

---

## 阶段零（可与阶段二并行）：登录与权限系统

### 目标
为平台增加用户认证和基于角色的访问控制（RBAC），保护 API 接口和前端页面。

### 技术选型

| 方案 | 说明 | 推荐 |
|------|------|------|
| JWT (JSON Web Token) | 无状态，前后端分离友好，Token 存前端 | ✅ 推荐 |
| Session + Cookie | Flask 原生支持，但跨域需额外处理 | 不推荐 |

选择 JWT 的原因：
- 前后端分离架构下无需共享 session
- 支持多端（未来可能有移动端或其他客户端）
- Flask 端无需维护 session 存储

### 数据模型（动态 RBAC）

采用 用户-角色-权限 三表设计，角色和权限均可在管理后台动态配置。

```python
# 角色-权限 多对多关联表
role_permissions = db.Table('role_permissions',
    db.Column('role_id', db.Integer, db.ForeignKey('role.id')),
    db.Column('permission_id', db.Integer, db.ForeignKey('permission.id')),
)

# 用户-角色 多对多关联表
user_roles = db.Table('user_roles',
    db.Column('user_id', db.Integer, db.ForeignKey('user.id')),
    db.Column('role_id', db.Integer, db.ForeignKey('role.id')),
)

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_login = db.Column(db.DateTime)
    roles = db.relationship('Role', secondary=user_roles, backref='users')

class Role(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)    # 如 "管理员", "操作员"
    code = db.Column(db.String(50), unique=True, nullable=False)    # 如 "admin", "operator"
    description = db.Column(db.String(200))
    is_system = db.Column(db.Boolean, default=False)                # 系统内置角色不可删除
    permissions = db.relationship('Permission', secondary=role_permissions, backref='roles')

class Permission(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)                # 如 "创建任务"
    code = db.Column(db.String(100), unique=True, nullable=False)   # 如 "task:create"
    group = db.Column(db.String(50), nullable=False)                # 如 "task", "config", "admin"
    description = db.Column(db.String(200))
```

#### 权限编码规范

权限 code 采用 `资源:操作` 格式：

| group | code | 说明 |
|-------|------|------|
| task | `task:view` | 查看任务/日志/结果 |
| task | `task:create` | 创建任务 |
| task | `task:cancel` | 取消任务 |
| task | `task:restart` | 重启任务 |
| task | `task:delete` | 删除任务 |
| template | `template:view` | 查看模板 |
| template | `template:manage` | 创建/编辑/删除模板 |
| google_sheet | `google_sheet:view` | 查看 Google Sheet/Token |
| google_sheet | `google_sheet:manage` | 管理 Google Sheet/Token |
| config | `config:view` | 查看系统配置 |
| config | `config:manage` | 修改系统配置 |
| scheduler | `scheduler:view` | 查看定时任务 |
| scheduler | `scheduler:manage` | 管理定时任务 |
| database | `database:manage` | 数据库操作 |
| user | `user:view` | 查看用户列表 |
| user | `user:manage` | 管理用户/角色/权限 |
| backtest | `backtest:view` | 查看回测任务 |
| backtest | `backtest:create` | 创建回测任务 |

#### 初始化数据

启动时自动创建（`run.py`）：
- 所有 Permission 记录（按上表，幂等插入）
- 一个系统内置 `admin` 角色（`is_system=True`），拥有全部权限
- 一个默认 admin 用户，关联 admin 角色

#### 与固定角色方案的对比

| | 固定角色（旧方案） | 动态 RBAC（新方案） |
|---|---|---|
| 新增权限 | 改代码 + 改装饰器 | 数据库加一条记录 |
| 新增角色 | 改代码 + 改枚举 | 管理后台创建 |
| 给角色调权限 | 改代码 | 管理后台勾选 |
| 用户多角色 | 不支持 | 支持 |
| 复杂度 | 低 | 中（多三张表） |

### 后端实现

#### API 接口

```
# 认证
POST /api/auth/login          — 登录，返回 JWT access_token + refresh_token
POST /api/auth/refresh        — 刷新 access_token
POST /api/auth/logout         — 登出（可选：加入 token 黑名单）
GET  /api/auth/me             — 获取当前用户信息 + 权限列表

# 用户管理
GET    /api/admin/users         — 用户列表
POST   /api/admin/users         — 创建用户
PUT    /api/admin/users/:id     — 编辑用户（含角色分配）
DELETE /api/admin/users/:id     — 删除用户
PUT    /api/auth/password       — 修改密码

# 角色管理
GET    /api/admin/roles         — 角色列表（含关联权限）
POST   /api/admin/roles         — 创建角色
PUT    /api/admin/roles/:id     — 编辑角色（含权限分配）
DELETE /api/admin/roles/:id     — 删除角色（is_system=True 不可删）

# 权限查询
GET    /api/admin/permissions   — 全部权限列表（按 group 分组）
```

#### 认证中间件

```python
# app/utils/auth.py
def login_required(f):
    """验证 JWT，注入 g.current_user"""

def permission_required(*permission_codes):
    """检查当前用户是否拥有指定权限码"""

# 使用方式
@task_api_bp.route('/tasks', methods=['POST'])
@login_required
@permission_required('task:create')
def create_task():
    ...
```

`permission_required` 逻辑：
1. 从 `g.current_user` 获取所有角色
2. 汇总所有角色的权限 code 集合
3. 检查请求的 permission_codes 是否在集合内

#### Token 策略
- access_token 有效期：2 小时
- refresh_token 有效期：7 天
- access_token 过期后前端自动用 refresh_token 刷新
- 密码使用 `werkzeug.security.generate_password_hash` 加密

#### 依赖
- `PyJWT` — JWT 编解码
- `werkzeug.security` — 密码哈希（Flask 已内置）

### 前端实现

#### 路由守卫
```javascript
// router/index.js
router.beforeEach((to, from, next) => {
  const token = localStorage.getItem('access_token')
  if (to.meta.requiresAuth && !token) {
    next('/login')
  } else {
    next()
  }
})
```

#### Token 管理
- access_token 存 `localStorage`
- axios 拦截器自动附加 `Authorization: Bearer <token>`
- 401 响应时自动尝试 refresh，失败则跳转登录页

#### 页面
- `Login.vue` — 登录页
- `admin/Users.vue` — 用户管理页（分配角色）
- `admin/Roles.vue` — 角色管理页（勾选权限）
- 导航栏显示当前用户 + 登出按钮
- 根据用户权限列表动态隐藏无权限的菜单项和操作按钮
- 封装 `v-permission` 指令，按钮级权限控制：`<el-button v-permission="'task:create'">创建</el-button>`

### 任务清单

| 序号 | 任务 | 说明 |
|------|------|------|
| 0.1 | 创建 User/Role/Permission 模型 + 迁移 | `app/models.py` 新增三表 + 两张关联表 |
| 0.2 | 创建权限初始化脚本 | `run.py` 启动时幂等插入所有 Permission + 默认 admin 角色和用户 |
| 0.3 | 创建 `app/utils/auth.py` | JWT 编解码 + `login_required` + `permission_required` 装饰器 |
| 0.4 | 创建 `app/routes/auth_api.py` | 登录/刷新/登出/用户/角色/权限 API |
| 0.5 | 现有 API 加认证装饰器 | 逐步给 task_api、config_api 等加 `@login_required` + `@permission_required` |
| 0.6 | 前端 Login.vue | 登录页面 |
| 0.7 | 前端 axios 拦截器 | 自动附加 token + 401 刷新 |
| 0.8 | 前端路由守卫 | 未登录跳转登录页 |
| 0.9 | 前端用户管理页 | 用户 CRUD + 角色分配 |
| 0.10 | 前端角色管理页 | 角色 CRUD + 权限勾选（按 group 分组的 checkbox） |
| 0.11 | 前端 `v-permission` 指令 | 按钮级权限控制 |
| 0.12 | 前端菜单权限过滤 | `/api/auth/me` 返回权限列表，动态过滤导航菜单 |

### 注意事项
- 初期可以设置一个环境变量 `AUTH_ENABLED=true/false`，方便开发阶段关闭认证
- 老的 Jinja2 页面在迁移完成前不加认证（避免改动老代码）
- JWT secret 从 `config_manager` 获取，不硬编码

---

## 部署架构

```
用户浏览器
    │
    ▼
  nginx (80/443)
    ├── /api/*              → 反代 Flask (5000)
    ├── /static/*           → Vue 构建产物 (frontend/dist/)
    └── /*                  → Vue SPA (index.html, history mode fallback)
```

### 开发环境
- Flask: `python run.py` → 端口 5000
- Vue: `cd frontend && npm run dev` → 端口 3000（自动代理 /api 到 5000）

### 生产环境
- Flask: `python run.py` 或 gunicorn → 端口 5000（仅 API）
- Vue: `cd frontend && npm run build` → 产物在 `frontend/dist/`
- nginx: 按 `nginx.conf` 配置

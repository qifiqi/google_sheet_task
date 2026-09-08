# 权限体系清理 + tests 下生产级 Flask 权限 Demo

## 现状结论（已扫描确认）
接口级权限早已停用：`permission_required` 是空壳（81 处装饰器全部放行）、`task_authorization` 硬编码 `allowed=True`、前端 `hasPermission` 对非 `page:` 权限一律放行。实际生效的只有：登录（JWT + `login_required`，109 处数据 API）和页面路由权限（`page:*` + 导航表 + `template-auth.js` 按 URL 拦截）。本次删除全部死权限代码，保留这两层。

---

## Part 1：当前代码删除

### 1.1 定义与启动层
- `app/config.py`：`PERMISSIONS` 删除全部非 `page:` 条目（task/template/google_sheet非page/config/navigation/scheduler/database/user/backtest 约 24 条），保留全部 `page:*`。
- `app/startup.py` `init_rbac()`：新增幂等清理——删除 `permissions` 表中 code 不以 `page:` 开头的行及 `role_permissions` 关联（含 admin 角色关联），随后 `admin_role.permissions = Permission.query.all()` 自然只含 page 权限。

### 1.2 工具层
- `app/utils/auth.py`：删除 `permission_required` 函数（其余全保留）。
- `app/utils/task_authorization.py`：**整个文件删除**。其中 `normalize_task_type` 是 20+ 处非权限业务在用的纯工具函数（回测任务类型归一化），搬到新文件 `app/utils/task_types.py`，全部 import 方改路径（routes: backtest_training/backtest_multi_product/global_preview/template_api/task_api；services: backtest_training_api_service/model_summary_service）。

### 1.3 路由层（12 个文件，81 处装饰器 + decision 分支）
- 逐文件删除 `@permission_required(...)` 装饰器及 import：task_api(12) admin(7) auth_api(9) template_api(8) config_api(11) scheduler_api(9) google_sheet_api(7) backtest_training(6) backtest_multi_product(6) database_api(3) global_preview(2) stock_api(1)。
- 删除 4 个本地 `_task_permission_denied` 辅助函数（task_api:44、admin:24、backtest_multi_product:52、backtest_training_api_service:94）及 admin 的 `TASK_ACTION_LABELS`。
- 删除全部 `decision = authorize_task_type_action(...)` + `if not decision["allowed"]` 分支；`filter_task_types_by_action(...)` 调用点改为直接使用 distinct 类型列表（该过滤本就是 no-op）；`filter_task_dicts_by_action` 调用行删除。
- `app/routes/meta_api.py`：`has_nav_permission` 删除 `:view`→`:manage` 回退死逻辑，简化为直接成员判断。

### 1.4 服务层
- `app/services/task/dashboard_query.py`：`get_allowed_task_types()` 去掉过滤直接返回全部 distinct 类型（**保留方法签名**，`runtime_view.py` 调用方不动）。
- `app/services/model_summary_service.py`：1454/1668 行过滤改为直接 `SUPPORTED_TASK_TYPES`；**保留 `user` 和 `ignore_permissions` 参数签名**（export_service/export_api 调用链 + 30 处测试依赖，签名向后兼容、内部不再过滤——最小破坏取舍）。

### 1.5 前端层
- `templates/admin/users.html:8`、`roles.html:68` 删 `data-permission="user:manage"`；`navigation.html:13,228` 删 `data-permission="navigation:manage"`（本就永远显示的死配置）。`page:*` 的 data-permission 全部保留。
- `static/js/template-auth.js`：删除 `task:any` 特例和非 `page:` 放行分支，`hasPermission` 简化为纯成员判断（菜单过滤、URL 拦截、403 渲染机制不动）。

### 1.6 测试同步
- `tests/test_page_permission_sync.py`：改写 `test_interface_permission_decorator_allows_authenticated_user` 为只测 `login_required`（登录 200 / 无 token 401）。
- `tests/test/test_p0_p1_refactor.py`：`test_dashboard_overview_filters_unauthorized_task_types` 改写为断言"不过滤、全部任务类型可见"。
- 删除 6 个文件中对 `authorize_task_type_action` 的 monkeypatch：test_global_preview.py(3 处)、test_backtest_training_export_preview.py(`_allow_backtest_view` + 5 调用)、test_backtest_training_export.py(3)、test_backtest_training_result_storage.py(2)、test_backtest_multi_product.py(2，另顺手清 2 处插入 task:view 的死数据)。
- `tests/test_model_summary_service.py`、`test_fk_free_relations.py` 无需改动（签名保留）。

---

## Part 2：`tests/demos/flask_rbac_demo/`（自研精简版，用户已确认）

遵循现有 `tests/demos/google_drive_upload_demo/` 先例：独立运行、自带 requirements、pytest 不收集。

```
tests/demos/flask_rbac_demo/
├── app.py            # 直接启动：python app.py（端口 5020，SQLite 自动建库+种子数据）
├── rbac/             # ★ 可整体复制到任何 Flask 项目的权限模块
│   ├── models.py     # User/Role/Permission 多对多（含 is_system、token_version）
│   ├── service.py    # werkzeug 密码哈希、PyJWT access/refresh、token_version 强制下线、权限查询
│   ├── decorators.py # login_required / permission_required(多权限任一) / page_required(页面路由)
│   └── api.py        # /auth/login /auth/refresh /auth/me /admin/roles /admin/permissions 蓝图
├── smoke.py          # python smoke.py：test client 断言全链路（401→登录→403→授权→200→改角色→token失效→refresh）
├── templates/        # 极简登录页+按钮面板，启动即可在浏览器点出 403/200
├── requirements.txt  # Flask、Flask-SQLAlchemy、PyJWT（本 venv 已有，零新增安装）
└── README.md         # 启动方式、curl 示例、复制迁移指南（挂蓝图→建表→加装饰器 4 步）、开源组件选型对比
```

种子数据：admin/admin123 全权限；editor（task:view/create 无 delete）；viewer（只读）——登录不同账号直接看到不同 403 行为。响应 JSON 结构与主项目一致（code/data/message）。

README 附开源组件结论：Flask-Principal 已停止维护不采用；pycasbin 适合将来需要通配符/资源实例级动态策略时引入；Flask-Security-Too 适合新项目从零搭建，与本仓现有 JWT 体系迁移成本高——当前规模自研 ~300 行最合适。

---

## 验证
1. `python -c "from app import create_app; create_app()"` 冒烟 import 链。
2. 定向 pytest：test_page_permission_sync、test_p0_p1_refactor、test_global_preview、test_backtest_training_export*、test_backtest_training_result_storage、test_backtest_multi_product、test_model_summary_service。
3. `python tests/demos/flask_rbac_demo/smoke.py` 全绿。
4. 全仓 grep 确认零残留：`permission_required`、`task_authorization`、`authorize_task_type_action`、非 page 权限码。
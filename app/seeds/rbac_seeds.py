"""RBAC 权限 + 主服务 SSO 默认角色种子（自 app/config.py 原位迁出）。

消费方：app/startup.py（flask init-rbac 幂等播种）、app/services/sso_service.py（SSO 换票默认角色）、
tests/scripts/add_permission_route_path.py（route_path 回填脚本）。
"""

# RBAC 权限定义，格式：(group, code, name, route_path)
# route_path 仅供后台展示，标记该权限对应的前端路由入口
# run.py 启动时幂等插入到数据库
# 仅保留页面权限（page:*），接口级细粒度权限已移除；
# 页面权限同时由导航菜单表通过 sync_navigation_permissions 幂等同步。
PERMISSIONS = [
    ('page',         'page:admin:dashboard',    '访问仪表盘页面',         '/admin'),
    ('page',         'page:admin:tasks',        '访问任务管理页面',       '/admin/tasks'),
    ('page',         'page:admin:templates',    '访问任务模板页面',       '/admin/templates'),
    ('page',         'page:admin:results',      '访问任务结果页面',       '/admin/results'),
    ('page',         'page:admin:model_summary','访问单模型汇总页面',     '/admin/model-summary'),
    ('page',         'page:admin:scheduler',    '访问定时任务页面',       '/admin/scheduler'),
    ('page',         'page:admin:config',       '访问系统配置页面',       '/admin/config'),
    ('page',         'page:admin:navigation',   '访问路由表页面',         '/admin/navigation'),
    ('page',         'page:admin:google_sheets','访问 Google Sheet 管理页面', '/admin/google-sheets'),
    ('page',         'page:admin:logs',         '访问系统日志页面',       '/admin/logs'),
    ('page',         'page:admin:users',        '访问用户管理页面',       '/admin/users'),
    ('page',         'page:admin:roles',        '访问角色管理页面',       '/admin/roles'),
    ('page',         'page:google_sheet:c3',    '访问 Google Sheet C3 页面', '/google-sheet/?version=c3'),
    ('page',         'page:google_sheet:c4',    '访问 Google Sheet C4 页面', '/google-sheet/?version=c4'),
    ('page',         'page:google_sheet:c5',    '访问 Google Sheet C5 页面', '/google-sheet/?version=c5'),
    ('page',         'page:google_sheet:c7',    '访问 Google Sheet C7 页面', '/google-sheet/?version=c7'),
    ('page',         'page:google_sheet:c1_1',   '访问 Google Sheet C1.1 页面', '/google-sheet/?version=c1_1'),
    ('page',         'page:backtest:list',      '访问回测列表页面',       '/backtest-training/list'),
    ('page',         'page:backtest:create',    '访问回测创建页面',       '/backtest-training/create'),
    ('page',         'page:backtest_multi_product:list',   '访问多品数据回测列表页面',   '/backtest-multi-product/list'),
    ('page',         'page:backtest_multi_product:create', '访问多品数据回测创建页面',   '/backtest-multi-product/create'),
    ('page',         'page:global_preview:single_product', '访问单品全局预览页面', '/global-preview/single-product'),
]

# 主服务 SSO 默认角色（docs/design/sso-integration-2026-09/）。
# init_rbac 幂等播种角色；权限按并集补齐，不覆盖管理员后台的手工调整。
SSO_ROLE = {
    'code': 'main_service_user',
    'name': '主服务用户',
    'description': '主服务 SSO 登录默认角色：仪表盘 + 数据/业务模块初始路由',
}
# 默认权限 = 仪表盘（登录落地页）+ DEFAULT_NAVIGATION_MENU 数据/业务模块初始路由；
# 东方财富 K 线、夏普率、回测数据分析的导航项无 page:* 权限码，天然对全部登录用户可见。
SSO_DEFAULT_PERMISSION_CODES = (
    'page:admin:dashboard',
    'page:admin:model_summary',
    'page:global_preview:single_product',
    'page:google_sheet:c3',
    'page:google_sheet:c4',
    'page:google_sheet:c5',
    'page:google_sheet:c7',
    'page:google_sheet:c1_1',
    'page:backtest:list',
    'page:backtest_multi_product:list',
)

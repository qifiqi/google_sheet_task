-- Seed Jaspil navigation menu and RBAC permissions for PostgreSQL.
-- Safe to run more than once.
--
-- Usage:
--   psql "$DATABASE_URL" -f scripts/seed_navigation_rbac_postgres.sql
-- or:
--   psql -h <host> -U <user> -d <database> -f scripts/seed_navigation_rbac_postgres.sql

BEGIN;

CREATE TABLE IF NOT EXISTS navigation_menu_items (
    id SERIAL PRIMARY KEY,
    key VARCHAR(100) NOT NULL UNIQUE,
    label VARCHAR(100) NOT NULL,
    path VARCHAR(255),
    permission VARCHAR(100),
    parent_key VARCHAR(100),
    sort_order INTEGER NOT NULL DEFAULT 0,
    is_visible BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP,
    updated_at TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_navigation_menu_parent_sort
    ON navigation_menu_items (parent_key, sort_order);
CREATE INDEX IF NOT EXISTS ix_navigation_menu_items_parent_key
    ON navigation_menu_items (parent_key);
CREATE INDEX IF NOT EXISTS ix_navigation_menu_items_is_visible
    ON navigation_menu_items (is_visible);

ALTER TABLE permission
    ADD COLUMN IF NOT EXISTS route_path VARCHAR(200);

INSERT INTO permission ("group", code, name, route_path)
VALUES
    ('task', 'task:view', '查看任务/日志/结果', '/admin/tasks'),
    ('task', 'task:create', '创建任务', '/task/create'),
    ('task', 'task:cancel', '取消任务', NULL),
    ('task', 'task:restart', '重启任务', NULL),
    ('task', 'task:delete', '删除任务', NULL),
    ('template', 'template:view', '查看模板', '/admin/templates'),
    ('template', 'template:manage', '管理模板', '/admin/templates'),
    ('google_sheet', 'google_sheet:view', '查看 Google Sheet', '/admin/google-sheets'),
    ('google_sheet', 'google_sheet:manage', '管理 Google Sheet', '/admin/google-sheets'),
    ('google_sheet', 'google_sheet:c3', '访问 Google Sheet C3', '/task/list?version=c3'),
    ('google_sheet', 'google_sheet:c4', '访问 Google Sheet C4', '/task/list?version=c4'),
    ('google_sheet', 'google_sheet:c5', '访问 Google Sheet C5', '/task/list?version=c5'),
    ('config', 'config:view', '查看系统配置', '/admin/config'),
    ('config', 'config:manage', '修改系统配置', '/admin/config'),
    ('navigation', 'navigation:view', '查看路由表', '/admin/navigation'),
    ('navigation', 'navigation:manage', '管理路由表', '/admin/navigation'),
    ('scheduler', 'scheduler:view', '查看定时任务', '/admin/scheduler'),
    ('scheduler', 'scheduler:manage', '管理定时任务', '/admin/scheduler'),
    ('database', 'database:manage', '数据库操作', NULL),
    ('user', 'user:view', '查看用户列表', '/admin/users'),
    ('user', 'user:manage', '管理用户/角色/权限', '/admin/users'),
    ('backtest', 'backtest:view', '查看回测任务', '/backtest/list'),
    ('backtest', 'backtest:create', '创建回测任务', '/backtest/create'),
    ('page', 'page:admin:dashboard', '访问仪表盘页面', '/admin'),
    ('page', 'page:admin:tasks', '访问任务管理页面', '/admin/tasks'),
    ('page', 'page:admin:templates', '访问任务模板页面', '/admin/templates'),
    ('page', 'page:admin:results', '访问任务结果页面', '/admin/results'),
    ('page', 'page:admin:scheduler', '访问定时任务页面', '/admin/scheduler'),
    ('page', 'page:admin:config', '访问系统配置页面', '/admin/config'),
    ('page', 'page:admin:navigation', '访问路由表页面', '/admin/navigation'),
    ('page', 'page:admin:google_sheets', '访问 Google Sheet 管理页面', '/admin/google-sheets'),
    ('page', 'page:admin:logs', '访问系统日志页面', '/admin/logs'),
    ('page', 'page:admin:users', '访问用户管理页面', '/admin/users'),
    ('page', 'page:admin:roles', '访问角色管理页面', '/admin/roles'),
    ('page', 'page:google_sheet:c3', '访问 Google Sheet C3 页面', '/google-sheet/?version=c3'),
    ('page', 'page:google_sheet:c4', '访问 Google Sheet C4 页面', '/google-sheet/?version=c4'),
    ('page', 'page:google_sheet:c5', '访问 Google Sheet C5 页面', '/google-sheet/?version=c5'),
    ('page', 'page:backtest:list', '访问回测列表页面', '/backtest-training/list'),
    ('page', 'page:backtest:create', '访问回测创建页面', '/backtest-training/create'),
    ('page', 'page:backtest_multi_product:list', '访问多品数据回测列表页面', '/backtest-multi-product/list'),
    ('page', 'page:backtest_multi_product:create', '访问多品数据回测创建页面', '/backtest-multi-product/create')
ON CONFLICT (code) DO UPDATE SET
    "group" = EXCLUDED."group",
    name = EXCLUDED.name,
    route_path = EXCLUDED.route_path;

INSERT INTO role (name, code, description, is_system)
VALUES ('管理员', 'admin', '系统管理员，拥有全部权限', TRUE)
ON CONFLICT (code) DO UPDATE SET
    name = EXCLUDED.name,
    description = EXCLUDED.description,
    is_system = EXCLUDED.is_system;

INSERT INTO role (name, code, description, is_system)
VALUES ('开发', 'developer', '开发内置角色，用于值班与告警筛选', TRUE)
ON CONFLICT (code) DO UPDATE SET
    name = EXCLUDED.name,
    description = EXCLUDED.description,
    is_system = EXCLUDED.is_system;

INSERT INTO role_permissions (role_id, permission_id)
SELECT r.id, p.id
FROM role r
CROSS JOIN permission p
WHERE r.code = 'admin'
ON CONFLICT DO NOTHING;

INSERT INTO navigation_menu_items (
    key,
    label,
    path,
    permission,
    parent_key,
    sort_order,
    is_visible,
    created_at,
    updated_at
)
VALUES
    ('dashboard', '仪表盘', '/admin', 'page:admin:dashboard', NULL, 0, TRUE, NOW(), NOW()),
    ('task', '任务模块', NULL, NULL, NULL, 10, TRUE, NOW(), NOW()),
    ('tasks', '任务管理', '/admin/tasks', 'page:admin:tasks', 'task', 0, TRUE, NOW(), NOW()),
    ('templates', '任务模板', '/admin/templates', 'page:admin:templates', 'task', 10, TRUE, NOW(), NOW()),
    ('results', '任务结果', '/admin/results', 'page:admin:results', 'task', 20, TRUE, NOW(), NOW()),
    ('scheduler_group', '调度模块', NULL, NULL, NULL, 20, TRUE, NOW(), NOW()),
    ('scheduler', '定时任务', '/admin/scheduler', 'page:admin:scheduler', 'scheduler_group', 0, TRUE, NOW(), NOW()),
    ('system', '系统模块', NULL, NULL, NULL, 30, TRUE, NOW(), NOW()),
    ('config', '系统配置', '/admin/config', 'page:admin:config', 'system', 0, TRUE, NOW(), NOW()),
    ('sheets', 'Google Sheet 管理', '/admin/google-sheets', 'page:admin:google_sheets', 'system', 10, TRUE, NOW(), NOW()),
    ('navigation', '路由表管理', '/admin/navigation', 'page:admin:navigation', 'system', 20, TRUE, NOW(), NOW()),
    ('logs', '系统日志', '/admin/logs', 'page:admin:logs', 'system', 30, TRUE, NOW(), NOW()),
    ('users', '用户管理', '/admin/users', 'page:admin:users', 'system', 40, TRUE, NOW(), NOW()),
    ('roles', '角色管理', '/admin/roles', 'page:admin:roles', 'system', 50, TRUE, NOW(), NOW()),
    ('business', '业务模块', NULL, NULL, NULL, 40, TRUE, NOW(), NOW()),
    ('c3', 'Google Sheet C3', '/google-sheet/?version=c3', 'page:google_sheet:c3', 'business', 0, TRUE, NOW(), NOW()),
    ('c4', 'Google Sheet C4', '/google-sheet/?version=c4', 'page:google_sheet:c4', 'business', 10, TRUE, NOW(), NOW()),
    ('c5', 'Google Sheet C5', '/google-sheet/?version=c5', 'page:google_sheet:c5', 'business', 20, TRUE, NOW(), NOW()),
    ('backtest', '单品数据回测', '/backtest-training/list', 'page:backtest:list', 'business', 30, TRUE, NOW(), NOW()),
    ('backtest_multi_product', '多品数据回测', '/backtest-multi-product/list', 'page:backtest_multi_product:list', 'business', 40, TRUE, NOW(), NOW()),
    ('xpl', '夏普率计算', '/xpl', NULL, 'business', 50, TRUE, NOW(), NOW()),
    ('xpl_v1', 'V1 回测数据分析', '/xpl/v1', NULL, 'business', 60, TRUE, NOW(), NOW())
ON CONFLICT (key) DO UPDATE SET
    label = EXCLUDED.label,
    path = EXCLUDED.path,
    permission = EXCLUDED.permission,
    parent_key = EXCLUDED.parent_key,
    sort_order = EXCLUDED.sort_order,
    is_visible = EXCLUDED.is_visible,
    updated_at = NOW();

DELETE FROM system_configs WHERE key = 'nav_menu';

COMMIT;

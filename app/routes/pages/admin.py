from flask import Blueprint

from app.routes.pages import register_page_routes
from app.utils.auth import page_login_required

admin_bp = Blueprint('admin', __name__)

# (rule, template)；全部页面统一 page_login_required（ponytail 审计 D1 表驱动）
# 仪表盘页面已停用（2026-09，db-to-http 迁移）：聚合统计依赖本地 SQL，
# 远端数据访问模式下不再提供；恢复时取消注释。
PAGES = [
    # ('/', 'admin/dashboard.html'),
    ('/tasks', 'admin/tasks.html'),
    ('/config', 'admin/config.html'),
    # ('/navigation', 'admin/navigation.html'),  # 菜单管理已上收主 Web（网关对该前缀返回 404）
    ('/logs', 'admin/logs.html'),
    ('/templates', 'admin/templates.html'),
    ('/results', 'admin/results.html'),
    ('/model-summary', 'admin/model_summary.html'),
    ('/eastmoney-kline', 'admin/eastmoney_kline.html'),
    ('/google-sheets', 'admin/google_sheets.html'),
    ('/scheduler', 'admin/scheduler.html'),
    # 用户/角色管理页已随本地 RBAC 停用（单 Token 子服务模式，管理上收主 Web）。
    # ('/users', 'admin/users.html'),
    # ('/roles', 'admin/roles.html'),
]

register_page_routes(admin_bp, PAGES, guard=page_login_required)

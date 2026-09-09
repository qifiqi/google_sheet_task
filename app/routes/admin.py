from flask import Blueprint

from app.routes.page_files import register_page_routes
from app.utils.auth import page_login_required

admin_bp = Blueprint('admin', __name__)

# (rule, template)；全部页面统一 page_login_required（ponytail 审计 D1 表驱动）
PAGES = [
    ('/', 'admin/dashboard.html'),
    ('/tasks', 'admin/tasks.html'),
    ('/config', 'admin/config.html'),
    ('/navigation', 'admin/navigation.html'),
    ('/logs', 'admin/logs.html'),
    ('/templates', 'admin/templates.html'),
    ('/results', 'admin/results.html'),
    ('/model-summary', 'admin/model_summary.html'),
    ('/eastmoney-kline', 'admin/eastmoney_kline.html'),
    ('/google-sheets', 'admin/google_sheets.html'),
    ('/scheduler', 'admin/scheduler.html'),
    ('/users', 'admin/users.html'),
    ('/roles', 'admin/roles.html'),
]

register_page_routes(admin_bp, PAGES, guard=page_login_required)

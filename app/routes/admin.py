from flask import Blueprint

from app.routes.page_files import send_page
from app.utils.auth import page_login_required

admin_bp = Blueprint('admin', __name__)


@admin_bp.route('/')
@page_login_required
def dashboard():
    """管理面板首页"""
    return send_page('admin/dashboard.html')

@admin_bp.route('/tasks')
@page_login_required
def tasks():
    """任务管理页面"""
    return send_page('admin/tasks.html')

@admin_bp.route('/config')
@page_login_required
def config():
    """配置管理页面"""
    return send_page('admin/config.html')

@admin_bp.route('/navigation')
@page_login_required
def navigation():
    """路由表管理页面"""
    return send_page('admin/navigation.html')

@admin_bp.route('/logs')
@page_login_required
def logs():
    """日志管理页面"""
    return send_page('admin/logs.html')

@admin_bp.route('/templates')
@page_login_required
def templates():
    """任务模板管理页面"""
    return send_page('admin/templates.html')

@admin_bp.route('/results')
@page_login_required
def results():
    """任务结果管理页面"""
    return send_page('admin/results.html')

@admin_bp.route('/model-summary')
@page_login_required
def model_summary():
    """单模型汇总数据看板"""
    return send_page('admin/model_summary.html')


@admin_bp.route('/eastmoney-kline')
@page_login_required
def eastmoney_kline():
    return send_page('admin/eastmoney_kline.html')


@admin_bp.route('/google-sheets')
@page_login_required
def google_sheets():
    return send_page('admin/google_sheets.html')

@admin_bp.route('/scheduler')
@page_login_required
def scheduler():
    """定时任务管理页面"""
    return send_page('admin/scheduler.html')

@admin_bp.route('/users')
@page_login_required
def users():
    """用户管理页面"""
    return send_page('admin/users.html')

@admin_bp.route('/roles')
@page_login_required
def roles():
    """角色管理页面"""
    return send_page('admin/roles.html')

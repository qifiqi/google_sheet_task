from flask import Blueprint, render_template

from app.models import GoogleSheetTableType, TaskStatus, TaskType
from app.services.task import TaskDashboardQueryService
from app.utils.auth import page_login_required

admin_bp = Blueprint('admin', __name__)


@admin_bp.route('/')
@page_login_required
def dashboard():
    """管理面板首页"""
    dashboard_query = TaskDashboardQueryService()
    counts = dashboard_query.get_dashboard_counts()
    recent_tasks = dashboard_query.get_recent_tasks(10)

    return render_template('admin/dashboard.html',
                         total_tasks=counts["total"],
                         completed_tasks=counts["completed"],
                         running_tasks=counts["running"],
                         error_tasks=counts["error"],
                         recent_tasks=recent_tasks)

@admin_bp.route('/tasks')
@page_login_required
def tasks():
    """任务管理页面"""
    return render_template(
        'admin/tasks.html',
        task_status_options=TaskStatus.choices(),
        task_status_editable_options=TaskStatus.editable_choices(),
        task_type_options=TaskType.choices(),
        task_type_filter_options=TaskType.choices(include_system=True),
    )

@admin_bp.route('/config')
@page_login_required
def config():
    """配置管理页面"""
    return render_template('admin/config.html')

@admin_bp.route('/navigation')
@page_login_required
def navigation():
    """路由表管理页面"""
    return render_template('admin/navigation.html')

@admin_bp.route('/logs')
@page_login_required
def logs():
    """日志管理页面"""
    return render_template('admin/logs.html')

@admin_bp.route('/templates')
@page_login_required
def templates():
    """任务模板管理页面"""
    return render_template('admin/templates.html')

@admin_bp.route('/results')
@page_login_required
def results():
    """任务结果管理页面"""
    return render_template('admin/results.html')

@admin_bp.route('/model-summary')
@page_login_required
def model_summary():
    """单模型汇总数据看板"""
    return render_template('admin/model_summary.html')


@admin_bp.route('/eastmoney-kline')
@page_login_required
def eastmoney_kline():
    return render_template('admin/eastmoney_kline.html')


@admin_bp.route('/google-sheets')
@page_login_required
def google_sheets():
    return render_template('admin/google_sheets.html', google_sheet_table_type_options=GoogleSheetTableType.choices())

@admin_bp.route('/scheduler')
@page_login_required
def scheduler():
    """定时任务管理页面"""
    return render_template('admin/scheduler.html')

@admin_bp.route('/users')
@page_login_required
def users():
    """用户管理页面"""
    return render_template('admin/users.html')

@admin_bp.route('/roles')
@page_login_required
def roles():
    """角色管理页面"""
    return render_template('admin/roles.html')

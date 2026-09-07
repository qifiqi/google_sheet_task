from flask import Blueprint, render_template, request

from app.routes.page_files import send_page
from app.utils.auth import page_login_required
from app.utils.logger import get_logger

logger = get_logger(__name__)

google_sheet_bp = Blueprint('google_sheet', __name__)


@google_sheet_bp.route('/')
@page_login_required
def index():
    """Google Sheet参数批量校验首页（静态文档，version 仅由前端消费）"""
    return send_page('google_sheet/index.html')

@google_sheet_bp.route('/create')
@page_login_required
def create():
    """创建Google Sheet任务页面：有 version 按版本分发；仅缺 version 时落 dispatcher"""
    version = request.args.get('version')
    if not version and request.args.get('restart_task_id'):
        return send_page('google_sheet/create_dispatcher.html')
    if version == 'c31':
        return send_page('google_sheet_c31/create.html')
    # c4/c5/c七 六大页暂维持 Jinja 渲染（F5 事故后尚未重做 F3 静态化，见 04 执行清单 F5 记录）
    if version == 'c5':
        return render_template('google_sheet_c5/create.html')
    if version == 'c7':
        return render_template('google_sheet_c7/create.html')
    if version == 'c4':
        return render_template('google_sheet_c4/create.html')
    return send_page('google_sheet/create.html')

@google_sheet_bp.route('/merge-export')
@page_login_required
def merge_export():
    """C3 合并导出独立页面"""
    return send_page('google_sheet/merge_export.html')


@google_sheet_bp.route('/detail')
@page_login_required
def detail():
    """任务详情页面：有 version 按版本分发；仅缺 version 时落 dispatcher"""
    version = request.args.get('version')
    if not version and request.args.get('task_id'):
        return send_page('google_sheet/detail_dispatcher.html')

    if version == 'c5':
        return render_template('google_sheet_c5/detail.html')
    if version == 'c7':
        return render_template('google_sheet_c7/detail.html')
    if version == 'c4':
        return render_template('google_sheet_c4/detail.html')
    return send_page('google_sheet/detail.html')

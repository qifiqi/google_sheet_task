from flask import Blueprint, request

from app.routes.pages import register_page_routes, send_page
from app.utils.auth import page_login_required
from app.utils.logger import get_logger

logger = get_logger(__name__)

google_sheet_bp = Blueprint('google_sheet', __name__)


# 无参数的纯静态页走表驱动（ponytail 审计 D1）；create/detail 为版本 dispatcher，保留手写
register_page_routes(
    google_sheet_bp,
    [
        ('/', 'google_sheet/index.html'),
        ('/merge-export', 'google_sheet/merge_export.html'),
    ],
    guard=page_login_required,
)

@google_sheet_bp.route('/create')
@page_login_required
def create():
    """创建Google Sheet任务页面：有 version 按版本分发；仅缺 version 时落 dispatcher"""
    version = request.args.get('version')
    if not version and request.args.get('restart_task_id'):
        return send_page('google_sheet/create_dispatcher.html')
    if version == 'c31':
        return send_page('google_sheet_c31/create.html')
    if version == 'c5':
        return send_page('google_sheet_c5/create.html')
    if version == 'c7':
        return send_page('google_sheet_c7/create.html')
    if version == 'c4':
        return send_page('google_sheet_c4/create.html')
    return send_page('google_sheet/create.html')

@google_sheet_bp.route('/detail')
@page_login_required
def detail():
    """任务详情页面：有 version 按版本分发；仅缺 version 时落 dispatcher"""
    version = request.args.get('version')
    if not version and request.args.get('task_id'):
        return send_page('google_sheet/detail_dispatcher.html')

    if version == 'c5':
        return send_page('google_sheet_c5/detail.html')
    if version == 'c7':
        return send_page('google_sheet_c7/detail.html')
    if version == 'c4':
        return send_page('google_sheet_c4/detail.html')
    return send_page('google_sheet/detail.html')

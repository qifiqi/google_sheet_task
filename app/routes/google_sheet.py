from flask import Blueprint, render_template, request, jsonify, url_for, redirect, flash
import json
from app.services.config_manager import get_config_manager
from app.utils.logger import get_logger
from app.models import TaskTemplate

logger = get_logger(__name__)

google_sheet_bp = Blueprint('google_sheet', __name__)

@google_sheet_bp.route('/')
def index():
    """Google Sheet参数批量校验首页

    使用 query 参数 version 区分不同版本：
    - version=c4 -> C4 模板
    - version=c5 -> C5 模板
    - 其它 / 无 -> 默认模板
    """
    version = request.args.get('version')

    return render_template('google_sheet/index.html', version=version)

@google_sheet_bp.route('/create')
def create():
    """创建Google Sheet任务页面"""
    version = request.args.get('version')
    if version == 'c31':
        return render_template('google_sheet_c31/create.html', version='c31')
    if version == 'c5':
        return render_template('google_sheet_c5/create.html', version='c5')
    if version == 'c4':
        return render_template('google_sheet_c4/create.html', version='c4')
    return render_template('google_sheet/create.html', version=None)

@google_sheet_bp.route('/detail')
def detail():
    """任务详情页面"""
    version = request.args.get('version')

    if version == 'c5':
        return render_template('google_sheet_c5/detail.html', version='c5')
    if version == 'c4':
        return render_template('google_sheet_c4/detail.html', version='c4')
    return render_template('google_sheet/detail.html', version=None)

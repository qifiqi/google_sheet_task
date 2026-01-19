from flask import Blueprint, render_template, request, jsonify, url_for, redirect, flash, current_app
import json
from app.services.task_manager import task_manager
from app.services.config_manager import get_config_manager
from app.utils.logger import get_logger
from app.models import TaskTemplate

logger = get_logger(__name__)

yule_bp = Blueprint('yule', __name__)

@yule_bp.route('/')
def index():
    """Excel数据分析工具首页"""
    return render_template('yule/index.html')

@yule_bp.route('/sjxz')
def sjxz():
    """数据选择"""
    return render_template('yule/sjxz.html')

from flask import Blueprint

from app.routes.page_files import send_page
import json
from app.services.config_manager import get_config_manager
from app.utils.logger import get_logger
from app.utils.auth import page_login_required

logger = get_logger(__name__)

yule_bp = Blueprint('yule', __name__)

@yule_bp.route('/')
@page_login_required
def index():
    """Excel数据分析工具首页"""
    return send_page('yule/index.html')

@yule_bp.route('/sjxz')
@page_login_required
def sjxz():
    """数据选择"""
    return send_page('yule/sjxz.html')

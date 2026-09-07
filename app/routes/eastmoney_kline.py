from flask import Blueprint

from app.routes.page_files import send_page
from app.utils.auth import page_login_required


eastmoney_kline_bp = Blueprint("eastmoney_kline", __name__)


@eastmoney_kline_bp.route("/eastmoney-kline")
@page_login_required
def index():
    return send_page("eastmoney_kline/index.html")

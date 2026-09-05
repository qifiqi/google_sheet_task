from flask import Blueprint, render_template
from app.utils.auth import page_login_required


eastmoney_kline_bp = Blueprint("eastmoney_kline", __name__)


@eastmoney_kline_bp.route("/eastmoney-kline")
@page_login_required
def index():
    return render_template("eastmoney_kline/index.html")

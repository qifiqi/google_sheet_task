from flask import Blueprint, render_template


eastmoney_kline_bp = Blueprint("eastmoney_kline", __name__)


@eastmoney_kline_bp.route("/eastmoney-kline")
def index():
    return render_template("eastmoney_kline/index.html")

from flask import Blueprint, render_template


eastmoney_kline_bp = Blueprint("eastmoney_kline", __name__)


@eastmoney_kline_bp.route("/eastmoney-kline")
def index():
    """渲染独立的东方财富 K 线查询页面。"""
    return render_template("eastmoney_kline/index.html")

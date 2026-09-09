from flask import Blueprint

from app.routes.page_files import register_page_routes
from app.utils.auth import page_login_required


eastmoney_kline_bp = Blueprint("eastmoney_kline", __name__)

register_page_routes(
    eastmoney_kline_bp,
    [("/eastmoney-kline", "eastmoney_kline/index.html")],
    guard=page_login_required,
)

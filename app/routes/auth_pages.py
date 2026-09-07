from flask import Blueprint

from app.routes.page_files import send_page


auth_pages_bp = Blueprint("auth_pages", __name__)


@auth_pages_bp.route("/login", methods=["GET"])
def login_page():
    # next_url 由页面 JS 从 ?next= 运行时填充（03 §3 #5）
    return send_page("login.html")

from flask import Blueprint

from app.routes.pages import send_page


auth_pages_bp = Blueprint("auth_pages", __name__)


@auth_pages_bp.route("/login", methods=["GET"])
def login_page():
    # next_url 由页面 JS 从 ?next= 运行时填充（03 §3 #5）；
    # 主服务 SSO 入口亦落在本页：/login#sso_token=...（docs/design/sso-integration-2026-09/）
    return send_page("login.html")

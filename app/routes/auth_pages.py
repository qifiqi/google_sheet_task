from flask import Blueprint, render_template, request


auth_pages_bp = Blueprint("auth_pages", __name__)


@auth_pages_bp.route("/login", methods=["GET"])
def login_page():
    """渲染登录页并保留认证成功后的跳转地址。"""
    return render_template("login.html", next_url=request.args.get("next", ""))

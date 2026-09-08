"""旧版 Jinja 登录页路由（已停用，保留以便恢复）。

单 Token 子服务模式下，登录在主 Web（stock.stplan.cn）完成，本服务
不再提供独立登录页:
- Vue 前端的 ``/login`` 路由由 SPA 自行处理（Token 录入/跳转），
  不再经过本蓝图;
- 旧模板 ``templates/login.html`` 与下方路由注释保留，恢复本地登录
  能力时取消注释并重新注册蓝图即可（app/routes/__init__.py）。
"""

from flask import Blueprint  # noqa: F401  恢复时与 render_template/request 一同取消注释

auth_pages_bp = Blueprint("auth_pages", __name__)

# from flask import render_template, request
#
#
# @auth_pages_bp.route("/login", methods=["GET"])
# def login_page():
#     """渲染登录页并保留认证成功后的跳转地址。"""
#     return render_template("login.html", next_url=request.args.get("next", ""))

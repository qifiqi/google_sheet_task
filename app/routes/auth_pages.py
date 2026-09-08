"""静态模板前端登录页路由。

单 Token 子服务模式（2026-09 起）:

- 静态模板前端为实际使用的前端，登录页 ``/login`` 由本服务渲染
  （``templates/login.html``）。
- 登录请求由页面 JS 提交到 ``POST /api/auth/login``（见
  ``app/routes/auth_api.py``），后端再经 stock_sdk 调用远程
  ``POST /api/SysUser/Login`` 完成校验并颁发 Token。
- Token 失效或缺失时，网关将页面导航重定向回本页（``next`` 参数
  记录回跳地址）。
"""

from flask import Blueprint, render_template, request

auth_pages_bp = Blueprint("auth_pages", __name__)


@auth_pages_bp.route("/login", methods=["GET"])
def login_page():
    """渲染登录页并保留认证成功后的跳转地址。"""
    return render_template("login.html", next_url=request.args.get("next", ""))

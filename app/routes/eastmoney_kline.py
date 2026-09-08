"""东方财富 K 线旧版 Jinja 页面路由（整文件停用）。

单 Token 子服务模式（2026-09 起）:

- 静态模板前端已整体下线：浏览器导航无法携带 ``Token`` 请求头，
  旧页面在新鉴权下不可达；远程路由表映射（meta_api 的
  ``REMOTE_MODEL_ROUTE_MAP``）需在 Vue 端补齐对应页面后再启用。
- 恢复时取消下方注释并重新注册蓝图（见 ``app/routes/__init__.py``）。
"""

# from flask import Blueprint, render_template
#
#
# eastmoney_kline_bp = Blueprint("eastmoney_kline", __name__)
#
#
# @eastmoney_kline_bp.route("/eastmoney-kline")
# def index():
#     """渲染独立的东方财富 K 线查询页面。"""
#     return render_template("eastmoney_kline/index.html")

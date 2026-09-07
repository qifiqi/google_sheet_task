"""Standalone global preview entry for C-series backtest tasks（页面路由）。

API 端点已归位 global_preview_api.py；导出流统一在 export_service.py
（原本文件内的 ZIP 流式导出为未注册死代码，已随 2026-09 审计清理移除）。
"""

from __future__ import annotations

from flask import Blueprint

from app.routes.page_files import send_page
from app.utils.auth import page_login_required


bp = Blueprint("global_preview", __name__, url_prefix="/global-preview")


@bp.route("")
@bp.route("/single_product")
@page_login_required
def page():
    return send_page("global_preview/index.html")

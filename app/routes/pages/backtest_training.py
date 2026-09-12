"""Backtest training 页面路由（API 已归位 backtest_api.py）。

/backup 旧书签路径（legacy_bp）与正式路径服务同一组页面（ponytail 审计 D5 保留）。
"""

from flask import Blueprint

from app.routes.pages import register_page_routes
from app.utils.auth import page_login_required

bp = Blueprint("backtest_training", __name__, url_prefix="/backtest-training")
legacy_bp = Blueprint("backtest_training_legacy", __name__, url_prefix="/backtest")

PAGES = [
    ("/create", "backtest_training/create.html"),
    ("/list", "backtest_training/list.html"),
    ("/detail/<task_id>", "backtest_training/detail.html"),
    ("/global-preview/<task_id>", "backtest_training/global_preview.html"),
    ("/result/<int:result_id>", "backtest_training/result.html"),
    ("/result/<int:result_id>/export-preview", "backtest_training/result_export_preview.html"),
]

register_page_routes(bp, PAGES, guard=page_login_required)
register_page_routes(legacy_bp, PAGES, guard=page_login_required)

"""Backtest training 页面路由（API 已归位 backtest_api.py）。"""

from flask import Blueprint

from app.routes.page_files import send_page
from app.utils.auth import page_login_required

bp = Blueprint("backtest_training", __name__, url_prefix="/backtest-training")
legacy_bp = Blueprint("backtest_training_legacy", __name__, url_prefix="/backtest")
@bp.route("/create")
@page_login_required
def create_page():
    return send_page("backtest_training/create.html")


@bp.route("/list")
@page_login_required
def list_page():
    return send_page("backtest_training/list.html")


@bp.route("/detail/<task_id>")
@page_login_required
def detail_page(task_id):
    return send_page("backtest_training/detail.html")


@bp.route("/global-preview/<task_id>")
@page_login_required
def global_preview_page(task_id):
    return send_page("backtest_training/global_preview.html")


@bp.route("/result/<int:result_id>")
@page_login_required
def result_page(result_id):
    return send_page("backtest_training/result.html")


@bp.route("/result/<int:result_id>/export-preview")
@page_login_required
def result_export_preview_page(result_id):
    return send_page("backtest_training/result_export_preview.html")


legacy_bp.add_url_rule("/create", view_func=create_page)
legacy_bp.add_url_rule("/list", view_func=list_page)
legacy_bp.add_url_rule("/detail/<task_id>", view_func=detail_page)
legacy_bp.add_url_rule("/global-preview/<task_id>", view_func=global_preview_page)
legacy_bp.add_url_rule("/result/<int:result_id>", view_func=result_page)
legacy_bp.add_url_rule("/result/<int:result_id>/export-preview", view_func=result_export_preview_page)

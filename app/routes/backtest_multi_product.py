"""多产品回测页面路由（API 已归位 backtest_api.py）。"""

from flask import Blueprint, render_template

from app.services.backtest_multi_product_service import BACKTEST_MULTI_PRODUCT_TASK_TYPE
from app.services.task import task_manager

bp = Blueprint("backtest_multi_product", __name__, url_prefix="/backtest-multi-product")
legacy_bp = Blueprint("backtest_multi_product_legacy", __name__, url_prefix="/backtest-multi")


@bp.route("/create")
def create_page():
    return render_template("backtest_multi_product/create.html")


@bp.route("/list")
def list_page():
    return render_template("backtest_multi_product/list.html")


@bp.route("/detail/<task_id>")
def detail_page(task_id):
    return render_template("backtest_multi_product/detail.html", task_id=task_id)


@bp.route("/global-preview/<task_id>")
def global_preview_page(task_id):
    return render_template("backtest_multi_product/global_preview.html", task_id=task_id)


@bp.route("/result/<int:result_id>")
def result_page(result_id):
    task_id = task_manager.resolve_result_task_id(result_id, BACKTEST_MULTI_PRODUCT_TASK_TYPE)
    return render_template("backtest_multi_product/result.html", result_id=result_id, task_id=task_id)


legacy_bp.add_url_rule("/create", view_func=create_page)
legacy_bp.add_url_rule("/list", view_func=list_page)
legacy_bp.add_url_rule("/detail/<task_id>", view_func=detail_page)
legacy_bp.add_url_rule("/global-preview/<task_id>", view_func=global_preview_page)
legacy_bp.add_url_rule("/result/<int:result_id>", view_func=result_page)

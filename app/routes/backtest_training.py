"""Backtest training 页面路由（API 已归位 backtest_api.py）。"""

from flask import Blueprint, render_template

from app.repositories import task_repository, task_result_repository
from app.utils.task_types import normalize_task_type

bp = Blueprint("backtest_training", __name__, url_prefix="/backtest-training")
legacy_bp = Blueprint("backtest_training_legacy", __name__, url_prefix="/backtest")
@bp.route("/create")
def create_page():
    return render_template("backtest_training/create.html")


@bp.route("/list")
def list_page():
    return render_template("backtest_training/list.html")


@bp.route("/detail/<task_id>")
def detail_page(task_id):
    return render_template("backtest_training/detail.html", task_id=task_id)


@bp.route("/global-preview/<task_id>")
def global_preview_page(task_id):
    return render_template("backtest_training/global_preview.html", task_id=task_id)


@bp.route("/result/<int:result_id>")
def result_page(result_id):
    task_result = task_result_repository.get(result_id)
    task_id = ""
    if task_result:
        task = task_repository.get(task_result["task_id"])
        if task and normalize_task_type(task["task_type"]) == "backtest_training":
            task_id = task_result["task_id"]
    return render_template("backtest_training/result.html", result_id=result_id, task_id=task_id)


@bp.route("/result/<int:result_id>/export-preview")
def result_export_preview_page(result_id):
    return render_template(
        "backtest_training/result_export_preview.html",
        result_id=result_id,
    )


legacy_bp.add_url_rule("/create", view_func=create_page)
legacy_bp.add_url_rule("/list", view_func=list_page)
legacy_bp.add_url_rule("/detail/<task_id>", view_func=detail_page)
legacy_bp.add_url_rule("/global-preview/<task_id>", view_func=global_preview_page)
legacy_bp.add_url_rule("/result/<int:result_id>", view_func=result_page)
legacy_bp.add_url_rule("/result/<int:result_id>/export-preview", view_func=result_export_preview_page)

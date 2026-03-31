# -*- coding: utf-8 -*-
"""
Backtest training page routes.
"""

from flask import Blueprint, render_template

from app.models import TaskResult

bp = Blueprint("backtest_training", __name__, url_prefix="/backtest-training")


@bp.route("/create")
def create_page():
    return render_template("backtest_training/create.html")


@bp.route("/list")
def list_page():
    return render_template("backtest_training/list.html")


@bp.route("/detail/<task_id>")
def detail_page(task_id):
    return render_template("backtest_training/detail.html", task_id=task_id)


@bp.route("/result/<int:result_id>")
def result_page(result_id):
    task_result = TaskResult.query.get(result_id)
    task_id = task_result.task_id if task_result else ""
    return render_template("backtest_training/result.html", result_id=result_id, task_id=task_id)

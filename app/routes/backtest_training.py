# -*- coding: utf-8 -*-
"""
回测数据训练路由
"""
from flask import Blueprint, render_template, request, jsonify
from app.services.backtest_training_service import BacktestTrainingService

bp = Blueprint('backtest_training', __name__, url_prefix='/backtest-training')
service = BacktestTrainingService()


@bp.route('/create')
def create_page():
    """创建页面"""
    return render_template('backtest_training/create.html')


@bp.route('/list')
def list_page():
    """列表页面"""
    return render_template('backtest_training/list.html')


@bp.route('/detail/<int:task_id>')
def detail_page(task_id):
    """详情页面"""
    return render_template('backtest_training/detail.html', task_id=task_id)


@bp.route('/result/<int:result_id>')
def result_page(result_id):
    """结果详情页面（类似 v1.html）"""
    return render_template('backtest_training/result.html', result_id=result_id)


# API 接口
@bp.route('/api/tasks', methods=['POST'])
def create_task():
    """创建任务接口"""
    data = request.get_json()
    model_url = data.get('model_url', '')
    stock_code = data.get('stock_code', '')
    parameters = data.get('parameters', [])
    title = data.get('title', '')
    recent_years = data.get('recent_years', [])
    full_years = data.get('full_years', [])
    sheet_name = data.get('sheet_name', '')

    result = service.create_training_task(
        model_url, stock_code, parameters, title,
        recent_years, full_years, sheet_name
    )
    return jsonify(result)


@bp.route('/api/tasks', methods=['GET'])
def get_tasks():
    """获取任务列表接口"""
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)

    result = service.get_task_list(page, per_page)
    return jsonify(result)


@bp.route('/api/tasks/<int:task_id>', methods=['GET'])
def get_task_detail(task_id):
    """获取任务详情接口"""
    result = service.get_task_detail(task_id)
    return jsonify(result)


@bp.route('/api/results/<int:result_id>', methods=['GET'])
def get_result_detail(result_id):
    """获取结果详情接口"""
    result = service.get_result_detail(result_id)
    return jsonify(result)

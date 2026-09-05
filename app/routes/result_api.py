"""任务结果 API（自 template_api 归位，URL 不变）。

数据访问经 task_manager 门面（任务结果查询/删除服务）；
行为与迁移前逐一对齐：
- 列表保持精简投影与 task_id 过滤语义；
- 详情/删除目标不存在 → NotFoundError → 全局处理器 404 信封。
"""
from flask import Blueprint, request

from app.services.task import task_manager
from app.exceptions import NotFoundError
from app.utils.api_response import success
from app.utils.auth import login_required

result_api_bp = Blueprint('result_api', __name__)


@result_api_bp.route('/tasks/<task_id>/results', methods=['GET'])
@login_required
def get_task_results(task_id):
    """获取任务结果（自 task_api 归位，URL 不变）"""
    task_manager.get_required_task(task_id)

    page = request.args.get('page', type=int)
    per_page = request.args.get('per_page', type=int)

    if page is not None and per_page is not None:
        data = task_manager.get_task_results(task_id, page=page, per_page=per_page)
        return success(data={
            "results": data["items"],
            "total": data["total"],
            "pages": data["pages"],
            "current_page": data["current_page"],
            "per_page": data["per_page"],
            "total_success": data.get("total_success"),
            "total_failed": data.get("total_failed"),
        })

    results = task_manager.get_task_results(task_id)
    return success(data={"results": results})


@result_api_bp.route('/results', methods=['GET'])
@login_required
def get_results():
    """获取任务结果列表"""
    page = max(request.args.get('page', 1, type=int) or 1, 1)
    per_page = min(request.args.get('per_page', 20, type=int) or 20, 100)
    task_id = request.args.get('task_id', None)

    data = task_manager.get_results_paginated(page, per_page, task_id=task_id)
    return success(data=data)


@result_api_bp.route('/results/<int:result_id>', methods=['GET'])
@login_required
def get_result(result_id):
    """获取任务结果详情"""
    record = task_manager.get_result_detail(result_id)
    if record is None:
        raise NotFoundError("结果不存在")
    return success(data=record)


@result_api_bp.route('/results/<int:result_id>', methods=['DELETE'])
@login_required
def delete_result(result_id):
    """删除任务结果"""
    deleted = task_manager.delete_result(result_id)
    if not deleted:
        raise NotFoundError("结果不存在")
    return success(message="结果已删除")

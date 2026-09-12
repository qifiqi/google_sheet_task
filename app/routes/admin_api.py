"""管理后台 API（自 admin.py 页面蓝图归位，URL 不变）。

- dashboard/overview 与 model-summary 查询为服务层契约 payload，保持透传；
- rebuild 端点挂保护性限流（api-model-query-audit/06 §3，rate_limit_rebuild）。
"""

from flask import Blueprint, current_app, g, jsonify, request

from app.services.model_summary_service import model_summary_service
from app.services.task import TaskRuntimeViewService, task_manager
from app.extensions import limiter, rate_limit_config
from app.schemas.admin import RebuildSchema
from app.utils.request_parsing import parse_body
from app.utils.api_response import success
from app.utils.auth import admin_required, login_required
from app.utils.logger import get_logger

admin_api_bp = Blueprint('admin_api', __name__, url_prefix='/admin')
logger = get_logger(__name__)
runtime_view_service = TaskRuntimeViewService(task_manager)

@admin_api_bp.route('/api/dashboard/overview')
@login_required
def dashboard_overview():
    """管理后台仪表盘总览数据

    响应契约由 runtime_view 服务定义（task/runtime_view.py），本路由保持透传。
    """
    return success(
        data=runtime_view_service.build_dashboard_overview(
            getattr(g, "current_user", None),
        )
    )

@admin_api_bp.route('/api/model-summary')
@login_required
def model_summary_api():
    """单模型汇总数据查询（服务层契约 payload 整体移入 data，键名不变）。"""
    payload = model_summary_service.query(getattr(g, "current_user", None), request.args.to_dict())
    return success(data=payload)

@admin_api_bp.route('/api/model-summary/rebuild', methods=['POST'])
@admin_required
@limiter.limit(
    lambda: f"{rate_limit_config('rate_limit_rebuild', 2) or 2}/minute",
    key_func=lambda: f"user:{getattr(getattr(g, 'current_user', None), 'id', 'anon')}",
)
def rebuild_model_summary_api():
    """重建单模型汇总索引。"""
    data = parse_body(RebuildSchema)
    logger.info("请求重建模型汇总索引: params=%s", data.model_dump())
    job = model_summary_service.start_rebuild_job(
        current_app._get_current_object(),
        task_type=data.task_type,
        task_id=data.task_id,
        batch_size=data.batch_size,
        reset=data.reset,
        created_by_user_id=getattr(getattr(g, "current_user", None), "id", None),
    )
    return success(data={'job': job})

@admin_api_bp.route('/api/model-summary/rebuild/status')
@login_required
def model_summary_rebuild_status_api():
    """查询单模型汇总索引后台重建状态。"""
    job_id = request.args.get('job_id')
    job = model_summary_service.get_rebuild_job(job_id) if job_id else model_summary_service.latest_rebuild_job()
    return success(data={'job': job})

@admin_api_bp.route('/api/tasks/<task_id>/runtime-detail')
@login_required
def task_runtime_detail(task_id):
    """管理后台任务运行细节"""
    return success(data={
        'task': runtime_view_service.get_runtime_detail(task_id),
    })

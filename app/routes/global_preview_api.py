"""全局预览 API（自 global_preview.py 归位，URL 不变）。"""

from flask import Blueprint, request

from app.exceptions import BadRequestError
from app.services.backtest_training_api_service import (
    _build_global_preview_group_payload,
    _build_global_preview_initial_payload,
)
from app.services.task import task_manager
from app.utils.api_response import success
from app.utils.auth import login_required
from app.utils.task_types import normalize_task_type


gp_api_bp = Blueprint("global_preview_api", __name__, url_prefix="/global-preview")


def _preview_status(task):
    task_type = normalize_task_type(task.get("task_type"))
    if task_type in {
        "backtest_training",
        "google_sheet",
        "google_sheet_c4",
        "google_sheet_c5",
        "google_sheet_c7",
    }:
        return {"supported": True, "message": "C 系列单品回测全局预览已就绪"}
    if task_type == "backtest_multi_product":
        return {"supported": False, "message": "多品回测入口已预留，内容将在后续适配"}
    return {"supported": False, "message": "当前任务类型暂不支持全局预览"}


@gp_api_bp.route("/api/tasks/<task_id>", methods=["GET"])
@login_required
def get_preview(task_id):
    task = task_manager.get_required_task(task_id)

    status = _preview_status(task)
    data = {
        "task": {
            "id": task["id"],
            "name": task["name"],
            "task_type": task["task_type"],
            "task_status": task["status"],
        },
        **status,
    }
    if status["supported"]:
        initial = _build_global_preview_initial_payload(task_id)
        data["initial"] = initial
        # 保留 preview 字段，避免已有调用方在前端升级期间失效。
        data["preview"] = initial["preview"]
    return success(data=data)


@gp_api_bp.route("/api/tasks/<task_id>/preview-group", methods=["POST"])
@login_required
def get_preview_group(task_id):
    task = task_manager.get_required_task(task_id)
    if not _preview_status(task)["supported"]:
        raise BadRequestError("当前任务暂不支持全局预览")

    # result_ids 来自初始化接口；服务层仍会附加 task_id 条件，防止跨任务读取。
    result_ids = (request.get_json(silent=True) or {}).get("result_ids") or []
    if not isinstance(result_ids, list) or not result_ids:
        raise BadRequestError("请选择需要加载的结果分组")
    payload = _build_global_preview_group_payload(task_id, result_ids)
    return success(data={"preview": payload})

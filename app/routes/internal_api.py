"""内部进程命令端点（钉钉微服务 → Web 任务执行者）。

只允许带 ``X-Internal-Secret`` 的兄弟进程调用；未配置密钥时端点 404。
Web 进程是唯一任务执行者，钉钉进程不再直接持有 TaskManager。
"""
import hmac

from flask import Blueprint, current_app, request

from app.exceptions import ForbiddenError, NotFoundError, ValidationError
from app.services.task import task_manager
from app.utils.api_response import success


internal_api_bp = Blueprint("internal_api", __name__)


@internal_api_bp.route("/task-command", methods=["POST"])
def task_command():
    secret = str(current_app.config.get("INTERNAL_COMMAND_SECRET") or "")
    if not secret:
        raise NotFoundError("内部命令端点未启用")
    provided = str(request.headers.get("X-Internal-Secret") or "")
    if not hmac.compare_digest(provided, secret):
        raise ForbiddenError("内部命令鉴权失败")

    payload = request.get_json(silent=True) or {}
    action = str(payload.get("action") or "").strip().lower()
    task_id = str(payload.get("task_id") or "").strip()
    if not task_id:
        raise ValidationError("task_id 不能为空")

    if action == "restart":
        result = task_manager.restart_task(
            task_id,
            resume_from_checkpoint=bool(payload.get("resume_from_checkpoint", True)),
        )
        return success(data=result)
    if action == "cancel":
        cancelled = task_manager.cancel_task(task_id)
        return success(data={"cancelled": bool(cancelled)})
    raise ValidationError(f"不支持的内部命令: {action}")

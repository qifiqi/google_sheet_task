from __future__ import annotations

from typing import Any

from app.models import Task


class TaskStatusService:
    """集中处理任务状态判断与流转前置校验。"""

    TERMINAL_STATUSES = {"completed", "cancelled", "error"}
    RESTARTABLE_STATUSES = {"pending", "completed", "error", "cancelled"}

    def can_cancel(self, task: Task | None) -> bool:
        """判断任务当前是否允许取消。"""
        return bool(task and task.status not in self.TERMINAL_STATUSES)

    def validate_restart(self, task: Task | None, status_check: dict[str, Any]) -> dict[str, Any]:
        """校验任务是否允许重启，并返回统一结果。"""
        if not task:
            return {"status": "error", "message": "任务不存在"}

        if task.status == "running" and not status_check.get("can_restart", False):
            return {"status": "error", "message": "任务正在运行中，无法重启"}

        if task.status != "running" and task.status not in self.RESTARTABLE_STATUSES:
            return {"status": "error", "message": f"任务状态 '{task.status}' 不允许重启"}

        return {
            "status": "success",
            "restart_reason": self.resolve_restart_reason(
                task_status=task.status,
                fallback_reason=status_check.get("restart_reason"),
            ),
        }

    def build_restart_plan(self, task: Task, resume_from_checkpoint: bool) -> dict[str, Any]:
        """生成重启前需要的状态重置计划。"""
        if resume_from_checkpoint:
            restart_step = task.current_step
            return {
                "restart_step": restart_step,
                "start_time": task.start_time,
                "reset_current_step": False,
                "clear_history_results": False,
                "log_message": f"从断点重启任务，从第 {restart_step} 步继续",
            }

        return {
            "restart_step": 0,
            "start_time": None,
            "reset_current_step": True,
            "clear_history_results": True,
            "log_message": "重新开始任务，从第 1 步开始（已清空历史结果）",
        }

    def validate_config_update(self, task: Task | None) -> dict[str, Any]:
        """校验任务当前是否允许修改配置。"""
        if not task:
            return {"status": "error", "message": "任务不存在"}

        if task.status == "running":
            return {"status": "error", "message": "正在运行的任务无法直接修改配置，请先停止任务"}

        return {"status": "success"}

    def resolve_restart_reason(self, task_status: str, fallback_reason: str | None = None) -> str:
        """根据任务状态生成重启原因说明。"""
        if fallback_reason:
            return fallback_reason

        reason_map = {
            "pending": "用户手动重启待执行任务",
            "completed": "用户手动重启已完成任务",
            "error": "用户手动重启错误任务",
            "cancelled": "用户手动重启已取消任务",
        }
        return reason_map.get(task_status, "用户手动重启")


task_status_service = TaskStatusService()

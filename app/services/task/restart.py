"""任务取消、删除与重启逻辑。"""

from __future__ import annotations

from datetime import datetime

from flask import current_app

from app.extensions import db
from app.models import Task, TaskLog, TaskResult, TaskResultReturn
from app.utils.database import safe_update, transaction_required
from app.utils.logger import get_logger

logger = get_logger(__name__)


class TaskRestartMixin:
    """封装运行态任务的停止、删除与重启操作。"""

    def get_start_error(self, task_id: str) -> str:
        return self.start_errors.get(task_id, "任务启动失败")

    @transaction_required
    def cancel_task(self, task_id: str) -> bool:
        """取消任务。"""
        task = db.session.get(Task, task_id)
        if not task:
            return False

        if task.status in ["completed", "cancelled", "error"]:
            return False

        was_pending = task.status == "pending"
        stop_event = self.task_stop_events.get(task_id)
        if stop_event:
            stop_event.set()

        safe_update(task, commit=False, status="cancelled", end_time=datetime.now())

        if was_pending:
            self.release_task_token_occupancy(task_id)
            self.release_google_sheet_occupancy(task_id)

        self.add_task_log(task_id, "info", "任务已取消")
        logger.info("取消任务: %s", task_id)
        return True

    def restart_task(
        self,
        task_id: str,
        resume_from_checkpoint: bool = True,
    ) -> dict[str, str | int]:
        """重启任务。"""
        try:
            task = db.session.get(Task, task_id)
            if not task:
                return {"status": "error", "message": "任务不存在"}

            original_status = task.status
            current_step = task.current_step
            original_start_time = task.start_time
            status_check = self.check_local_task_status(task_id)
            if original_status == "running":
                if not status_check.get("can_restart", False):
                    return {"status": "error", "message": "任务正在运行中，无法重启"}
            elif original_status not in ["pending", "completed", "error", "cancelled"]:
                return {
                    "status": "error",
                    "message": f"任务状态 '{original_status}' 不允许重启",
                }

            if task_id in self.running_tasks:
                try:
                    thread = self.running_tasks.get(task_id)
                    self.cancel_task(task_id)
                    if thread and thread.is_alive():
                        thread.join(timeout=3.0)
                    logger.info("已停止原有任务线程: %s", task_id)
                except Exception as exc:
                    logger.warning("停止原有任务线程失败: %s", exc)

            alive_thread = self.running_tasks.get(task_id)
            if alive_thread and alive_thread.is_alive():
                return {
                    "status": "error",
                    "message": "task is still stopping, please retry shortly",
                }

            self.task_stop_events.pop(task_id, None)
            start_time = None
            if resume_from_checkpoint:
                restart_step = current_step
                self.add_task_log(
                    task_id,
                    "info",
                    f"从断点重启任务，从第 {restart_step} 步继续",
                )
                start_time = original_start_time
            else:
                restart_step = 0
                task.current_step = 0
                self.release_task_token_occupancy(task_id)
                self.release_google_sheet_occupancy(task_id)
                TaskResult.query.filter_by(task_id=task_id).delete()
                TaskResultReturn.query.filter_by(task_id=task_id).delete()
                db.session.commit()
                self.add_task_log(
                    task_id,
                    "info",
                    "重新开始任务，从第 1 步开始（已清空历史结果）",
                )

            task = db.session.get(Task, task_id)
            if not task:
                return {"status": "error", "message": "任务不存在"}
            if task.task_type in ("backtest_training", "backtest_multi_product"):
                config_data = self._get_task_config_dict(task)
                spreadsheet_ids = self._extract_backtest_spreadsheet_ids(config_data)
                running_backtest = self._find_running_backtest_task_for_spreadsheets(
                    spreadsheet_ids,
                    exclude_task_id=task_id,
                )
                if running_backtest:
                    message = (
                        "同一个 Google Sheet 已有回测任务正在运行，"
                        f"当前任务保持待执行: {running_backtest.id}"
                    )
                    self.start_errors[task_id] = message
                    return {
                        "status": "error",
                        "message": f"任务重启失败: {message}",
                        "start_error": message,
                        "task_id": task_id,
                    }
            task.status = "pending"
            task.error_message = None
            task.start_time = start_time
            task.end_time = None
            db.session.commit()

            success = self.start_task(task_id)
            if not success:
                start_error = self.get_start_error(task_id)
                return {
                    "status": "error",
                    "message": f"任务重启失败: {start_error}",
                    "start_error": start_error,
                    "task_id": task_id,
                }

            restart_reason = status_check.get("restart_reason")
            if not restart_reason:
                manual_reason_map = {
                    "pending": "用户手动重启待执行任务",
                    "completed": "用户手动重启已完成任务",
                    "error": "用户手动重启错误任务",
                    "cancelled": "用户手动重启已取消任务",
                }
                restart_reason = manual_reason_map.get(original_status, "用户手动重启")

            self.add_task_log(task_id, "info", f"任务重启成功，原因: {restart_reason}")
            return {
                "status": "success",
                "message": "任务重启成功",
                "restart_from_step": restart_step,
                "restart_reason": restart_reason,
            }
        except Exception as exc:
            logger.error("重启任务失败: %s, 错误: %s", task_id, exc)
            return {"status": "error", "message": f"任务重启失败: {exc}"}

    def delete_task(self, task_id: str) -> bool:
        """删除任务及相关数据。"""
        try:
            with current_app.app_context():
                task = db.session.get(Task, task_id)
                if not task:
                    logger.warning("任务不存在: %s", task_id)
                    return False

                if task.status == "running":
                    task.status = "cancelled"
                    task.end_time = datetime.now()
                    self.release_task_token_occupancy(task_id)
                self.release_google_sheet_occupancy(task_id)

                TaskResult.query.filter_by(task_id=task_id).delete()
                TaskLog.query.filter_by(task_id=task_id).delete()
                db.session.delete(task)
                db.session.commit()

                self.running_tasks.pop(task_id, None)
                stop_event = self.task_stop_events.pop(task_id, None)
                if stop_event:
                    stop_event.set()

                logger.info("任务删除成功: %s", task_id)
                return True
        except Exception as exc:
            logger.error("删除任务失败: %s, 错误: %s", task_id, exc)
            db.session.rollback()
            return False

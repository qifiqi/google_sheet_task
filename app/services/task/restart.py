"""任务取消、删除与重启逻辑。"""

from __future__ import annotations

from datetime import datetime

from flask import current_app

from app.exceptions import ConflictError, NotFoundError
from app.models import TaskStatus

from app.services.task.data_cleanup import clear_task_execution_data
from app.repositories import task_repository
from app.services.task.runtime_state import get_runtime_state_store
from app.utils.database import transaction_required
from app.utils.logger import get_logger

logger = get_logger(__name__)


class TaskRestartMixin:
    """封装运行态任务的停止、删除与重启操作。"""

    def get_start_error(self, task_id: str) -> str:
        return self.start_errors.get(task_id, "任务启动失败")

    @transaction_required
    def cancel_task(self, task_id: str) -> bool:
        """取消任务。"""
        task = task_repository.get_entity(task_id)
        if not task:
            return False

        if task.status in ["completed", "cancelled", "error"]:
            return False

        was_pending = task.status == TaskStatus.PENDING.value
        stop_event = self.task_stop_events.get(task_id)
        if stop_event:
            stop_event.set()

        # 方案 B：运行中任务的取消标志写 Redis 运行态（执行链热路径读这里）。
        try:
            get_runtime_state_store().request_cancel(task_id)
        except Exception as exc:
            logger.warning("写入任务取消标志失败: %s", exc)

        task_repository.update_fields(
            task_id,
            commit=False,
            status=TaskStatus.CANCELLED.value,
            end_time=datetime.now(),
        )

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
        """重启任务；成功返回重启信息 dict，失败抛领域异常（NotFoundError/ConflictError）。"""
        try:
            task = task_repository.get_entity(task_id)
            if not task:
                raise NotFoundError("任务不存在")

            original_status = task.status
            original_start_time = task.start_time
            status_check = self.check_local_task_status(task_id)
            if original_status == "running":
                if not status_check.get("can_restart", False):
                    raise ConflictError("任务正在运行中，无法重启")
            elif original_status not in ["pending", "completed", "error", "cancelled"]:
                raise ConflictError(f"任务状态 '{original_status}' 不允许重启")

            # 持锁取运行态快照，避免与 start_task/watchdog 的注册清理并发竞争。
            with self._runtime_state_lock:
                existing_handle = self.running_tasks.get(task_id)
            if existing_handle is not None:
                try:
                    self.cancel_task(task_id)
                    if existing_handle.is_alive():
                        existing_handle.join(timeout=3.0)
                    logger.info("已停止原有任务线程: %s", task_id)
                except Exception as exc:
                    logger.warning("停止原有任务线程失败: %s", exc)

            with self._runtime_state_lock:
                alive_thread = self.running_tasks.get(task_id)
                still_alive = bool(alive_thread and alive_thread.is_alive())
                if not still_alive:
                    self.task_stop_events.pop(task_id, None)
            if still_alive:
                raise ConflictError("任务仍在停止中，请稍后重试")

            # 方案 B：先对账可能残留的 Redis 运行态（崩溃遗留进度/日志回灌数据库），
            # 再取断点步号，避免读到上一进程未回灌的旧值。无运行态时为 no-op。
            try:
                get_runtime_state_store().sync_snapshot(task_id)
            except Exception as exc:
                logger.warning("重启前回灌任务运行态失败: %s", exc)
            task = task_repository.get_entity(task_id)
            if not task:
                raise NotFoundError("任务不存在")
            current_step = task.current_step
            original_start_time = task.start_time

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
                self.release_task_token_occupancy(task_id)
                self.release_google_sheet_occupancy(task_id)
                task_repository.update_fields(task_id, current_step=0, commit=False)
                clear_task_execution_data(task_id)
                task_repository.commit()
                self.add_task_log(
                    task_id,
                    "info",
                    "重新开始任务，从第 1 步开始（已清空历史结果）",
                )

            task = task_repository.get_entity(task_id)
            if not task:
                raise NotFoundError("任务不存在")
            task_repository.update_fields(
                task_id,
                status=TaskStatus.PENDING.value,
                error_message=None,
                start_time=start_time,
                end_time=None,
            )

            # 统一入口：Sheet 执行锁被占 → queued（保持 pending 排队等接力）；
            # 其他启动失败 → ConflictError 由上层标记。
            result = self.start_task(task_id)
            if result.queued:
                return {
                    "message": result.message,
                    "start_error": result.message,
                    "task_id": task_id,
                    "queued": True,
                    "restart_from_step": restart_step,
                }
            if not result.started:
                raise ConflictError(f"任务重启失败: {result.message}")

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
            logger.info("任务重启成功: task_id=%s from_step=%s", task_id, restart_step)
            return {
                "message": "任务重启成功",
                "restart_from_step": restart_step,
                "restart_reason": restart_reason,
            }
        except Exception as exc:
            logger.error("重启任务失败: %s, 错误: %s", task_id, exc)
            raise

    def delete_task(self, task_id: str) -> bool:
        """删除任务及相关数据。"""
        try:
            with current_app.app_context():
                task = task_repository.get_entity(task_id)
                if not task:
                    logger.warning("任务不存在: %s", task_id)
                    return False

                if task.status == TaskStatus.RUNNING.value:
                    task_repository.update_fields(
                        task_id,
                        commit=False,
                        status=TaskStatus.CANCELLED.value,
                        end_time=datetime.now(),
                    )
                    self.release_task_token_occupancy(task_id)
                self.release_google_sheet_occupancy(task_id)

                clear_task_execution_data(task_id, include_logs=True)
                task_repository.delete(task_id)
                get_runtime_state_store().drop(task_id)

                self.running_tasks.pop(task_id, None)
                stop_event = self.task_stop_events.pop(task_id, None)
                if stop_event:
                    stop_event.set()

                logger.info("任务删除成功: %s", task_id)
                return True
        except Exception as exc:
            logger.error("删除任务失败: %s, 错误: %s", task_id, exc)
            task_repository.rollback()
            return False

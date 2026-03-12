from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Dict

from flask import current_app
from sqlalchemy import text

from app.models import Task, TaskLog, db
from app.services.config_manager import get_config_manager
from app.services.google_sheet_client import GoogleSheet
from app.utils.database import safe_db_operation
from app.utils.logger import get_logger

logger = get_logger(__name__)


class BaseGoogleSheetService:
    """Google Sheet 任务执行链路的公共基类。"""

    service_label = "Google Sheet"
    advisory_lock_tag = ""
    use_advisory_lock = False

    def __init__(self, config: Dict[str, Any], task_id: str, event_queue=None, app=None):
        self.config = config
        self.task_id = task_id
        self.event_queue = event_queue
        self.app = app
        self.task = None
        self.google_sheet = None
        self.google_sheets: list[GoogleSheet] = []
        # 保持每个任务一条独立日志链路，便于定位执行问题。
        self.task_logger = get_logger(f"{self.__class__.__module__}.{task_id}")

    def error_dd(self, error_msg: str) -> None:
        """发送任务失败通知。"""
        message = self.app.notifier.error_google_task_templates(
            f"{self.task_id} -- {self.task.name}",
            error_msg,
            f"{current_app.config.get('BASE_URL')}/google-sheet/detail?task_id={self.task_id}",
        )
        self.app.notifier.send_message(message)

    def task_ok_to_dd(self, result: str) -> None:
        """发送任务成功通知。"""
        message = self.app.notifier.google_task_ok_templates(
            f"{self.task_id} -- {self.task.name}",
            result,
            f"{current_app.config.get('BASE_URL')}/google-sheet/detail?task_id={self.task_id}",
        )
        self.app.notifier.send_message(message)

    def execute_task(self):
        """执行任务公共外壳，具体批处理逻辑由子类实现。"""
        try:
            context_app = self.app or current_app
            with context_app.app_context():
                lock_acquired = self._acquire_task_lock()
                try:
                    task = Task.query.get(self.task_id)
                    self.task = task
                    if not task:
                        self._log_error(f"任务 {self.task_id} 不存在")
                        return "error"

                    if task.status == "cancelled":
                        self._log_info(f"任务 {self.task_id} 已被取消，停止执行")
                        return "cancelled"

                    config_data = self._load_task_config(task)
                    if config_data is None:
                        return "error"

                    self._log_info(f"开始执行{self.service_label}任务")
                    self._init_google_sheet(config_data)

                    parameters = config_data.get("parameters", [])
                    if not parameters:
                        self._log_error("没有参数配置")
                        return "error"

                    if task.status == "cancelled":
                        self._log_info(f"任务 {self.task_id} 已被取消，停止执行")
                        return "cancelled"

                    execution_summary = self._run_task(task, task.name, parameters, config_data)
                    return self._resolve_execution_result(execution_summary)
                finally:
                    self._release_task_lock(lock_acquired)
        except Exception as exc:
            try:
                task = Task.query.get(self.task_id)
                if task and task.status == "cancelled":
                    self._log_info(f"任务已被取消: {str(exc)}")
                    return "cancelled"
            except Exception:
                pass

            error_msg = f"执行{self.service_label}任务失败: {self.task_id}, 错误: {str(exc)}"
            self._log_error(error_msg)
            self.error_dd(error_msg)
            return "error"

    def _load_task_config(self, task: Task) -> Dict[str, Any] | None:
        """解析并合并系统配置。"""
        if isinstance(task.config, str):
            try:
                config_data = json.loads(task.config)
            except json.JSONDecodeError as exc:
                self._log_error(f"配置解析失败: {str(exc)}")
                return None
        else:
            config_data = task.config or {}

        config_manager = get_config_manager()
        return {**config_manager.get_google_sheet_config(), **config_data}

    def _resolve_execution_result(self, execution_summary: Dict[str, Any]) -> str:
        """根据子类返回的执行摘要统一决定最终状态。"""
        success_count = execution_summary.get("success_count", 0)
        failed_count = execution_summary.get("failed_count", 0)
        task_status = execution_summary.get("task_status", "completed")
        final_status = execution_summary.get("final_status")

        if task_status == "cancelled":
            self._log_info(f"任务已取消，成功执行: {success_count}, 失败: {failed_count}")
            return "cancelled"

        if task_status == "error":
            error_details = f"任务执行出错！成功: {success_count}, 失败: {failed_count}"
            if self.task and getattr(self.task, "error", None):
                error_details += f", 错误信息: {str(self.task.error)}"
            self.error_dd(error_details)
            return "error"

        if final_status is not None:
            if final_status == "completed":
                self.task_ok_to_dd(f"任务成功完成！成功执行: {success_count}, 失败: {failed_count}")
            else:
                self.error_dd(f"任务执行失败！成功: {success_count}, 失败: {failed_count}")
            return final_status

        if success_count == 0 and failed_count == 0:
            self._log_error("任务执行失败")
            self.error_dd("任务执行失败！没有成功或失败的参数组合")
            return "error"

        completion_msg = f"任务执行完成！成功: {success_count}, 失败: {failed_count}"
        self.task_ok_to_dd(completion_msg)
        self._log_info(completion_msg)
        return "completed"

    def _acquire_task_lock(self) -> bool:
        """按需获取数据库级任务锁。"""
        if not self.use_advisory_lock:
            return False

        try:
            lock_acquired = db.session.execute(
                text("SELECT pg_try_advisory_lock(:k)"),
                {"k": int(self.task_id)},
            ).scalar()
            if not lock_acquired:
                self._log_warning(
                    f"任务 {self.task_id} 已在运行（获取锁失败），拒绝并发执行 {self.advisory_lock_tag}".strip()
                )
            return bool(lock_acquired)
        except Exception:
            # 非 Postgres 或锁不可用时忽略，由上层状态更新兜底。
            return False

    def _release_task_lock(self, lock_acquired: bool) -> None:
        """在执行结束后释放数据库级任务锁。"""
        if not self.use_advisory_lock or not lock_acquired:
            return

        try:
            db.session.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": int(self.task_id)})
        except Exception:
            pass

    def _log(self, level: str, message: str, log_type: str = "general", **kwargs):
        """统一日志入口，负责系统日志、数据库日志和前端推送。"""
        try:
            formatted_message = self._format_log_message(message, log_type, **kwargs)
            prefixed_message = f"[Task-{self.task_id[:8]}] {formatted_message}"

            if level == "error":
                self.task_logger.error(prefixed_message)
            elif level == "warning":
                self.task_logger.warning(prefixed_message)
            else:
                self.task_logger.info(prefixed_message)

            self._save_to_database(level, formatted_message)
            self._push_to_frontend(level, formatted_message)
        except Exception:
            pass

    def _format_log_message(self, message: str, log_type: str, **kwargs) -> str:
        """格式化日志消息。"""
        if log_type == "step":
            return f"[Step {kwargs.get('step', 0)}/{kwargs.get('total', 0)}] {message}"
        if log_type == "progress":
            return f"[Progress {kwargs.get('percentage', 0):.1f}%] {message}"
        if log_type == "api":
            action = kwargs.get("action", "")
            details = kwargs.get("details", "")
            base_msg = f"[API] {action}"
            return f"{base_msg} - {details}" if details else base_msg
        if log_type == "api_error":
            return f"[API_ERROR] {kwargs.get('action', '')} - {kwargs.get('error', '')}"
        return message

    def _save_to_database(self, level: str, message: str) -> None:
        """保存日志到数据库。"""
        def save_log_operation():
            log = TaskLog(task_id=self.task_id, level=level, message=message)
            db.session.add(log)
            db.session.commit()

        try:
            if self.app:
                with self.app.app_context():
                    safe_db_operation(save_log_operation)
            else:
                with current_app.app_context():
                    safe_db_operation(save_log_operation)
        except Exception:
            pass

    def _push_to_frontend(self, level: str, message: str) -> None:
        """通过 SSE 推送日志到前端。"""
        try:
            if self.event_queue:
                self.event_queue.put(
                    {
                        "type": "log_update",
                        "data": {
                            "level": level,
                            "message": message,
                            "timestamp": datetime.now().isoformat(),
                        },
                    }
                )
        except Exception:
            pass

    def _log_info(self, message: str, log_type: str = "general", **kwargs):
        """记录 info 级别日志。"""
        self._log("info", message, log_type, **kwargs)

    def _log_warning(self, message: str, log_type: str = "general", **kwargs):
        """记录 warning 级别日志。"""
        self._log("warning", message, log_type, **kwargs)

    def _log_error(self, message: str, log_type: str = "general", **kwargs):
        """记录 error 级别日志。"""
        self._log("error", message, log_type, **kwargs)

    def _log_step(self, step: int, total: int, message: str):
        """记录步骤日志。"""
        self._log("info", message, "step", step=step, total=total)

    def _log_progress(self, percentage: float, message: str):
        """记录进度日志。"""
        self._log("info", message, "progress", percentage=percentage)

    def _log_api(self, action: str, details: str = ""):
        """记录外部接口调用日志。"""
        self._log("info", "", "api", action=action, details=details)

    def _log_api_error(self, action: str, error: str):
        """记录外部接口错误日志。"""
        self._log("error", "", "api_error", action=action, error=error)

    @staticmethod
    def get_worksheets(
        spreadsheet_id: str,
        token_file: str = "data/token.json",
        proxy_url: str = None,
    ) -> Dict[str, Any]:
        """获取指定电子表格下的全部工作表名称。"""
        try:
            with GoogleSheet(spreadsheet_id, None, token_file, proxy_url) as google_sheet:
                worksheets = google_sheet.get_all_worksheets()
                if not worksheets:
                    return {"title": "", "worksheets": []}
                title = google_sheet.sheet.title if google_sheet.sheet else ""
                return {"title": title, "worksheets": worksheets}
        except Exception as exc:
            logger.error(f"获取工作表列表失败: {str(exc)}")
            return {"title": "", "worksheets": []}

    def _init_google_sheet(self, config_data: Dict[str, Any]) -> None:
        """初始化 Google Sheet 连接，具体由子类实现。"""
        raise NotImplementedError

    def _run_task(
        self,
        task: Task,
        name: str,
        parameters,
        config_data: Dict[str, Any],
    ) -> Dict[str, Any]:
        """执行具体批处理逻辑，具体由子类实现。"""
        raise NotImplementedError

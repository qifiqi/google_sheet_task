"""任务运行时编排与执行。"""

from __future__ import annotations

import json
import threading
from datetime import datetime, timedelta
from typing import Any

from flask import current_app

from app.extensions import db
from app.models import Task
from app.services.backtest_training_service import BacktestTrainingService
from app.services.config_manager import get_config_manager
from app.services.google_sheet_service import GoogleSheetService
from app.services.google_sheet_service_C4 import GoogleSheetService as GoogleSheetServiceC4
from app.services.google_sheet_service_C5 import GoogleSheetService as GoogleSheetServiceC5
from app.services.google_sheet_token_service import get_google_sheet_token_service
from app.utils.logger import get_logger, get_task_logger
from app.utils.task_error_utils import build_task_error_message, unwrap_exception

logger = get_logger(__name__)


class TaskRuntimeMixin:
    """任务线程调度与执行收尾逻辑。"""

    # 运行态字段由 TaskManager.__init__ 注入；这里声明给静态类型检查器使用。
    backtest_sheet_start_lock: Any

    def _extract_backtest_spreadsheet_id(self, config: dict[str, Any] | None) -> str:
        """Extract the Google Sheet spreadsheet_id used by a backtest task."""
        if not isinstance(config, dict):
            return ""

        sheet_config = config.get("sheet")
        if isinstance(sheet_config, dict):
            spreadsheet_id = str(sheet_config.get("spreadsheet_id") or "").strip()
            if spreadsheet_id:
                return spreadsheet_id

        return str(config.get("spreadsheet_id") or "").strip()

    def _get_task_config_dict(self, task: Task | None) -> dict[str, Any]:
        if not task:
            return {}
        if isinstance(task.config, dict):
            return task.config
        try:
            return json.loads(task.config) if task.config else {}
        except (TypeError, json.JSONDecodeError):
            return {}

    def _find_running_backtest_task_for_spreadsheet(
        self,
        spreadsheet_id: str,
        *,
        exclude_task_id: str | None = None,
    ) -> Task | None:
        """Find a running backtest task using the same spreadsheet_id."""
        if not spreadsheet_id:
            return None

        since = datetime.now() - timedelta(days=1)
        running_tasks = (
            Task.query.populate_existing()
            .filter(
                Task.task_type == "backtest_training",
                Task.status == "running",
                Task.created_at >= since,
            )
            .all()
        )
        for task in running_tasks:
            if exclude_task_id and task.id == exclude_task_id:
                continue
            config = self._get_task_config_dict(task)
            if self._extract_backtest_spreadsheet_id(config) == spreadsheet_id:
                return task
        return None

    def _start_next_pending_backtest_task(self, finished_task_id: str, app) -> None:
        """Start the oldest pending backtest task that uses the finished task's sheet."""
        finished_task = db.session.get(Task, finished_task_id)
        finished_config = self._get_task_config_dict(finished_task)
        spreadsheet_id = self._extract_backtest_spreadsheet_id(finished_config)
        if not spreadsheet_id:
            return

        if self._find_running_backtest_task_for_spreadsheet(
            spreadsheet_id,
            exclude_task_id=finished_task_id,
        ):
            return

        pending_tasks = Task.query.filter(
            Task.task_type == "backtest_training",
            Task.status == "pending",
            Task.id != finished_task_id,
        ).order_by(Task.created_at.asc(), Task.id.asc()).all()
        for pending_task in pending_tasks:
            pending_config = self._get_task_config_dict(pending_task)
            if self._extract_backtest_spreadsheet_id(pending_config) != spreadsheet_id:
                continue

            logger.info(
                "回测任务 %s 结束，启动同 sheet 的下一个待执行任务: %s",
                finished_task_id,
                pending_task.id,
            )
            self.add_task_log(
                pending_task.id,
                "info",
                f"同一 Sheet 上一个回测任务 {finished_task_id} 已结束，开始自动执行",
                app,
            )
            self.start_task(pending_task.id)
            return

    def _release_backtest_sheet_run_reservation(
        self,
        spreadsheet_id: str | None,
        task_id: str,
    ) -> None:
        return

    def _get_config(self, key: str, default: Any = None) -> Any:
        """动态获取配置，确保运行期修改能实时生效。"""
        config_manager = get_config_manager()
        return config_manager.get_config(key, default)

    def _record_task_exception(self, task_id: str, exc: Exception, app):
        error_message = build_task_error_message(exc)
        with app.app_context():
            task = db.session.get(Task, task_id)
            if task:
                task.status = "error"
                task.error_message = error_message
                task.end_time = datetime.now()
                db.session.commit()
        return error_message

    def _get_task_fresh(self, task_id: str):
        """重新读取任务状态，避免会话缓存影响最终收尾判断。"""
        try:
            db.session.expire_all()
        except Exception:
            pass
        return Task.query.populate_existing().filter(Task.id == task_id).first()

    def _is_stop_requested(self, task_id: str) -> bool:
        stop_event = self.task_stop_events.get(task_id)
        return bool(stop_event and stop_event.is_set())

    def _cleanup_runtime_state(self, task_id: str, task_logger=None) -> None:
        thread = self.running_tasks.pop(task_id, None)
        if thread and task_logger:
            task_logger.info("清理任务线程资源")

        stop_event = self.task_stop_events.pop(task_id, None)
        if stop_event and task_logger:
            task_logger.info("stop event cleaned")
            task_logger.info("清理任务事件队列")

    def _finalize_task_execution(
        self,
        task_id: str,
        app,
        task_logger,
        task_result: str,
    ) -> None:
        """统一收尾任务状态。

        取消信号优先于执行返回值，避免线程尾部把已取消任务覆盖成 completed。
        """
        task = self._get_task_fresh(task_id)
        if not task:
            task_logger.warning("任务不存在，无法收尾: %s", task_id)
            return

        if task.status == "cancelled" or self._is_stop_requested(task_id):
            task.status = "cancelled"
            task.end_time = datetime.now()
            db.session.commit()
            task_logger.info("任务执行完成，状态: cancelled（任务被取消）")
            self.add_task_log(
                task_id,
                "info",
                "任务执行完成，状态: cancelled（任务被取消）",
                app,
            )
            return

        if task_result == "cancelled":
            task.status = "cancelled"
            task.end_time = datetime.now()
            db.session.commit()
            task_logger.info("任务执行完成，状态: cancelled（执行过程中被取消）")
            self.add_task_log(
                task_id,
                "info",
                "任务执行完成，状态: cancelled（执行过程中被取消）",
                app,
            )
            return

        if task_result == "completed":
            task.status = "completed"
            task.end_time = datetime.now()
            db.session.commit()
            task_logger.info("任务执行完成，状态: completed")
            self.add_task_log(task_id, "info", "任务执行完成，状态: completed", app)
            return

        task.status = "error"
        task.end_time = datetime.now()
        db.session.commit()
        task_logger.info("任务执行完成，状态: error")
        self.add_task_log(task_id, "info", "任务执行完成，状态: error", app)

    def start_task(self, task_id: str) -> bool:
        """启动任务线程。"""
        self.start_errors.pop(task_id, None)
        acquired_token_id = None
        reserved_backtest_spreadsheet_id = None

        thread = self.running_tasks.get(task_id)
        if thread and thread.is_alive():
            error_msg = "任务已在启动或运行中，拒绝重复启动"
            self.start_errors[task_id] = error_msg
            logger.warning("重复启动任务被拒绝: %s", task_id)
            return False

        task_logger = get_task_logger(task_id, f"{__name__}.start")
        self.running_tasks.pop(task_id, None)

        task = db.session.get(Task, task_id)
        if not task:
            error_msg = "任务不存在"
            self.start_errors[task_id] = error_msg
            if acquired_token_id:
                get_google_sheet_token_service().release_usage(acquired_token_id)
                self.task_token_occupancy.pop(task_id, None)
            task_logger.error(error_msg)
            logger.error("任务不存在: %s", task_id)
            return False

        if task.status != "pending":
            error_msg = f"任务状态不是pending，当前状态: {task.status}"
            self.start_errors[task_id] = error_msg
            task_logger.warning(error_msg)
            logger.warning("任务状态不是pending，无法启动: %s", task_id)
            return False

        config_data = self._get_task_config_dict(task)
        if task.task_type == "backtest_training":
            with self.backtest_sheet_start_lock:
                spreadsheet_id = self._extract_backtest_spreadsheet_id(config_data)
                running_backtest = self._find_running_backtest_task_for_spreadsheet(
                    spreadsheet_id,
                    exclude_task_id=task_id,
                )
                if running_backtest:
                    error_msg = (
                        "同一个 Google Sheet 已有回测任务正在运行，"
                        f"当前任务保持待执行: {running_backtest.id}"
                    )
                    self.start_errors[task_id] = error_msg
                    task_logger.info(error_msg)
                    self.add_task_log(task_id, "info", error_msg)
                    return False

        max_concurrent = int(self._get_config("max_concurrent_tasks", 5))
        if len(self.running_tasks) >= max_concurrent:
            error_msg = (
                f"任务队列已满，无法启动任务 (当前运行: {len(self.running_tasks)}, "
                f"最大并发数: {max_concurrent})"
            )
            self.start_errors[task_id] = error_msg
            task_logger.warning(error_msg)
            logger.warning("任务队列已满，无法启动任务: %s (最大并发数: %s)", task_id, max_concurrent)
            return False

        backtest_marked_running = False
        try:
            if task.task_type == "backtest_training":
                with self.backtest_sheet_start_lock:
                    spreadsheet_id = self._extract_backtest_spreadsheet_id(config_data)
                    running_backtest = self._find_running_backtest_task_for_spreadsheet(
                        spreadsheet_id,
                        exclude_task_id=task_id,
                    )
                    if running_backtest:
                        error_msg = (
                            "同一个 Google Sheet 已有回测任务正在运行，"
                            f"当前任务保持待执行: {running_backtest.id}"
                        )
                        self.start_errors[task_id] = error_msg
                        task_logger.info(error_msg)
                        self.add_task_log(task_id, "info", error_msg)
                        return False

                    self.ensure_google_sheet_occupancy(task_id, config_data)
                    rows = (
                        Task.query.filter(Task.id == task_id, Task.status == "pending")
                        .update(
                            {"status": "running", "start_time": datetime.now()},
                            synchronize_session=False,
                        )
                    )
                    db.session.commit()
                    if rows == 0:
                        error_msg = "任务状态已变化，无法启动"
                        self.start_errors[task_id] = error_msg
                        task_logger.warning(error_msg)
                        self.release_google_sheet_occupancy(task_id)
                        return False
                    backtest_marked_running = True
                    reserved_backtest_spreadsheet_id = spreadsheet_id
            else:
                self.ensure_google_sheet_occupancy(task_id, config_data)

            token_id = config_data.get("token_id")
            if token_id:
                token_service = get_google_sheet_token_service()
                token_service.validate_task_start(config_data)
                token_service.increment_usage(token_id)
                acquired_token_id = int(token_id)
                self.task_token_occupancy[task_id] = acquired_token_id
        except Exception as exc:
            error_msg = str(exc)
            self.start_errors[task_id] = error_msg
            self.release_google_sheet_occupancy(task_id)
            self._release_backtest_sheet_run_reservation(
                reserved_backtest_spreadsheet_id,
                task_id,
            )
            if backtest_marked_running:
                Task.query.filter(Task.id == task_id, Task.status == "running").update(
                    {"status": "pending", "start_time": None},
                    synchronize_session=False,
                )
                db.session.commit()
            task_logger.warning("Token校验失败，无法启动任务: %s", error_msg)
            logger.warning("Token校验失败，任务无法启动: %s, %s", task_id, error_msg)
            return False

        task_logger.info("开始启动任务 - 名称: %s, 类型: %s", task.name, task.task_type)
        self.task_stop_events[task_id] = threading.Event()
        app = current_app._get_current_object()

        if task.task_type == "google_sheet":
            new_thread = threading.Thread(
                target=self._execute_google_sheet_task,
                args=(task_id, app),
                name=task_id,
            )
            task_logger.info("创建Google Sheet任务执行线程")
        elif task.task_type == "google_sheet_C4":
            new_thread = threading.Thread(
                target=self._execute_google_sheet_c4_task,
                args=(task_id, app),
                name=task_id,
            )
            task_logger.info("创建Google Sheet C4 任务执行线程")
        elif task.task_type == "google_sheet_C5":
            new_thread = threading.Thread(
                target=self._execute_google_sheet_c5_task,
                args=(task_id, app),
                name=task_id,
            )
            task_logger.info("创建Google Sheet C5 任务执行线程")
        elif task.task_type == "backtest_training":
            new_thread = threading.Thread(
                target=self._execute_backtest_training_task,
                args=(task_id, app),
                name=task_id,
            )
            task_logger.info("创建回测数据训练任务执行线程")
        else:
            error_msg = f"不支持的任务类型: {task.task_type}"
            self.start_errors[task_id] = error_msg
            self.task_stop_events.pop(task_id, None)
            self.release_task_token_occupancy(task_id)
            self.release_google_sheet_occupancy(task_id)
            task_logger.error(error_msg)
            logger.error("不支持的任务类型: %s", task.task_type)
            return False

        self.running_tasks[task_id] = new_thread
        try:
            new_thread.start()
        except Exception as exc:
            self.running_tasks.pop(task_id, None)
            self.task_stop_events.pop(task_id, None)
            self.release_task_token_occupancy(task_id)
            self.release_google_sheet_occupancy(task_id)
            self._release_backtest_sheet_run_reservation(
                reserved_backtest_spreadsheet_id,
                task_id,
            )
            if task.task_type == "backtest_training":
                Task.query.filter(Task.id == task_id, Task.status == "running").update(
                    {"status": "pending", "start_time": None},
                    synchronize_session=False,
                )
                db.session.commit()
            error_msg = f"任务线程启动失败: {exc}"
            self.start_errors[task_id] = error_msg
            task_logger.error(error_msg)
            logger.error("任务线程启动失败: %s, err=%s", task_id, exc)
            return False

        task_logger.info("任务执行线程启动成功")
        logger.info("启动任务: %s", task_id)
        return True

    def _mark_task_running(self, task_id: str, task_logger, app, start_message: str) -> Task | None:
        """将任务置为运行中。

        Google Sheet 普通任务保留旧行为；其它任务使用原子更新防止并发重复启动。
        """
        task = db.session.get(Task, task_id)
        if not task:
            task_logger.error("任务不存在")
            return None

        if task.task_type == "google_sheet":
            task.status = "running"
            task.start_time = datetime.now()
            db.session.commit()
        else:
            if task.status == "running":
                if not task.start_time:
                    task.start_time = datetime.now()
                    db.session.commit()
            else:
                rows = (
                    Task.query.filter(Task.id == task_id, Task.status != "running")
                    .update(
                        {"status": "running", "start_time": datetime.now()},
                        synchronize_session=False,
                    )
                )
                db.session.commit()
                if rows == 0:
                    duplicate_message = self._build_duplicate_start_message(task.task_type)
                    task_logger.warning(duplicate_message)
                    self.add_task_log(task_id, "warn", duplicate_message, app)
                    return None
                task = db.session.get(Task, task_id)

        self.add_task_log(task_id, "info", start_message, app)
        return task

    def _build_duplicate_start_message(self, task_type: str) -> str:
        duplicate_map = {
            "google_sheet_C4": "任务已在运行，拒绝并发启动 (C4)",
            "google_sheet_C5": "任务已在运行，拒绝并发启动 (C5)",
        }
        return duplicate_map.get(task_type, "任务已在运行，拒绝并发启动")

    def _execute_service_task(
        self,
        task_id: str,
        app,
        *,
        logger_name: str,
        start_message: str,
        service_class,
        business_message: str,
        failure_label: str,
    ) -> None:
        """统一执行后台任务服务。"""
        task_logger = get_task_logger(task_id, logger_name)
        try:
            with app.app_context():
                task = db.session.get(Task, task_id)
                if not task:
                    task_logger.error("任务不存在")
                    return

                task_logger.info("%s: %s", start_message, task.name)
                task = self._mark_task_running(task_id, task_logger, app, start_message)
                if not task:
                    return

                service = service_class(
                    task.config,
                    task_id,
                    app,
                    self.task_stop_events.get(task_id),
                )
                task_logger.info(business_message)
                task_result = service.execute_task()
                self._finalize_task_execution(task_id, app, task_logger, task_result)
        except Exception as exc:
            root = unwrap_exception(exc) or exc
            task_logger.exception("%s: %s", failure_label, root)
            try:
                self._record_task_exception(task_id, exc, app)
            except Exception as update_error:
                task_logger.error("更新任务状态失败: %s", update_error)
            self.add_task_log(
                task_id,
                "error",
                f"任务执行失败: {build_task_error_message(exc)}",
                app,
            )
        finally:
            with app.app_context():
                finished_task = db.session.get(Task, task_id)
                finished_config = self._get_task_config_dict(finished_task)
                finished_spreadsheet_id = self._extract_backtest_spreadsheet_id(
                    finished_config
                )
                self.release_task_token_occupancy(task_id)
                self.release_google_sheet_occupancy(task_id)
                if service_class is BacktestTrainingService:
                    if finished_spreadsheet_id:
                        self._release_backtest_sheet_run_reservation(
                            finished_spreadsheet_id,
                            task_id,
                        )
                    with self.backtest_sheet_start_lock:
                        self._start_next_pending_backtest_task(task_id, app)
            self._cleanup_runtime_state(task_id, task_logger=task_logger)
            task_logger.info("任务执行器退出")

    def _execute_google_sheet_task(self, task_id: str, app) -> None:
        self._execute_service_task(
            task_id,
            app,
            logger_name=f"{__name__}.{task_id}",
            start_message="开始执行Google Sheet任务",
            service_class=GoogleSheetService,
            business_message="开始执行任务业务逻辑",
            failure_label="执行任务失败",
        )

    def _execute_google_sheet_c4_task(self, task_id: str, app) -> None:
        self._execute_service_task(
            task_id,
            app,
            logger_name=f"{__name__}.C4.{task_id}",
            start_message="开始执行Google Sheet C4 任务",
            service_class=GoogleSheetServiceC4,
            business_message="开始执行 C4 任务业务逻辑",
            failure_label="执行 C4 任务失败",
        )

    def _execute_google_sheet_c5_task(self, task_id: str, app) -> None:
        self._execute_service_task(
            task_id,
            app,
            logger_name=f"{__name__}.C5.{task_id}",
            start_message="开始执行Google Sheet C5 任务",
            service_class=GoogleSheetServiceC5,
            business_message="开始执行 C5 任务业务逻辑",
            failure_label="执行 C5 任务失败",
        )

    def _execute_backtest_training_task(self, task_id: str, app) -> None:
        self._execute_service_task(
            task_id,
            app,
            logger_name=f"{__name__}.backtest.{task_id}",
            start_message="开始执行回测数据训练任务",
            service_class=BacktestTrainingService,
            business_message="开始执行回测训练任务业务逻辑",
            failure_label="执行回测训练任务失败",
        )

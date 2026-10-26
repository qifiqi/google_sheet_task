"""任务运行时编排与执行。"""

from __future__ import annotations

from app.utils.json_utils import loads, JSONDecodeError
import threading
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from flask import current_app

from app.repositories import task_repository
from app.services.sheet_execution_lock_service import get_sheet_execution_lock_service
from app.services.task.registry import (
    GLOBAL_MAX_DEFAULT,
    GLOBAL_MAX_KEY,
    build_runner,
    get_task_type_spec,
)
from app.models import Task, TaskStatus, TaskType
from app.services.backtest_multi_product_service import BacktestMultiProductService
from app.services.backtest_training_service import BacktestTrainingService
from app.services.config_manager import get_config_manager
from app.services.google_sheet_tasks.c3 import C3Service
from app.services.google_sheet_tasks.c4 import C4Service
from app.services.google_sheet_tasks.c5 import C5Service
from app.services.google_sheet_tasks.c7 import C7Service
from app.services.google_sheet_tasks.c1_1 import C1_1Service
from app.services.google_sheet_token_service import get_google_sheet_token_service
from app.services.task.error_handling import format_task_error_message, record_task_exception
from app.utils.logger import get_logger, get_task_logger
from app.utils.task_error_utils import SHEET_QUEUED_PREFIX, unwrap_exception
from app.utils.task_types import is_c_series_task_type
from app.services.task.occupancy import C_SERIES_TABLE_TYPES

logger = get_logger(__name__)

sheet_execution_lock_service = get_sheet_execution_lock_service()


@dataclass(frozen=True)
class TaskStartResult:
    """start_task 结构化结果（统一入口语义，替代 bool + start_errors 文本匹配）。

    - started: 已提交执行线程；
    - queued:  目标 Sheet 执行锁被其他任务持有，任务保持 pending 排队，
      由持有者收尾后的接力启动接管（不算失败）；
    - rejected: 前置校验/配额/线程提交失败，任务保持 pending，message 给出原因。
    """

    status: str  # "started" | "queued" | "rejected"
    message: str = ""

    @property
    def started(self) -> bool:
        return self.status == "started"

    @property
    def queued(self) -> bool:
        return self.status == "queued"


class TaskRuntimeMixin:
    """任务线程调度与执行收尾逻辑。"""

    # 运行态字段由 TaskManager.__init__ 注入；这里声明给静态类型检查器使用。
    sheet_start_lock: Any

    def _extract_task_spreadsheet_ids(self, config: dict[str, Any] | None) -> list[str]:
        """提取任务配置引用的全部 spreadsheet_id（全引用形态统一，锁键口径）。"""
        if not isinstance(config, dict):
            return []

        ids: set[str] = set()
        for ref in self._iter_sheet_references(config):
            if not isinstance(ref, dict):
                continue
            spreadsheet_id = str(ref.get("spreadsheet_id") or "").strip()
            if spreadsheet_id:
                ids.add(spreadsheet_id)
        return sorted(ids)

    def _extract_sheets_to_lock(
        self,
        task_type: str,
        config: dict[str, Any] | None,
    ) -> list[str]:
        """Extract spreadsheet IDs that still need real execution locks."""
        if task_type != "backtest_multi_product" or not isinstance(config, dict):
            return self._extract_task_spreadsheet_ids(config)

        products = config.get("products")
        if not isinstance(products, list):
            return self._extract_task_spreadsheet_ids(config)

        spreadsheet_ids = []
        for product in products:
            if not isinstance(product, dict):
                continue
            if product.get("is_fixed") and BacktestMultiProductService.fixed_product_cache_exists(config, product):
                continue
            sheet = product.get("sheet") if isinstance(product.get("sheet"), dict) else {}
            spreadsheet_id = str(
                sheet.get("spreadsheet_id") or product.get("spreadsheet_id") or ""
            ).strip()
            if spreadsheet_id:
                spreadsheet_ids.append(spreadsheet_id)
        return sorted(set(spreadsheet_ids))

    def _config_for_spreadsheet_locks(
        self,
        config: dict[str, Any],
        spreadsheet_ids: list[str],
    ) -> dict[str, Any]:
        if not isinstance(config, dict) or not spreadsheet_ids:
            return {}
        allowed = set(spreadsheet_ids)
        filtered = dict(config)
        products = config.get("products")
        if isinstance(products, list):
            filtered_products = []
            for product in products:
                if not isinstance(product, dict):
                    continue
                sheet = product.get("sheet") if isinstance(product.get("sheet"), dict) else {}
                spreadsheet_id = str(sheet.get("spreadsheet_id") or product.get("spreadsheet_id") or "").strip()
                if spreadsheet_id in allowed:
                    filtered_products.append(product)
            filtered["products"] = filtered_products
        return filtered

    def _get_task_config_dict(self, task: Task | None) -> dict[str, Any]:
        if not task:
            return {}
        if isinstance(task.config, dict):
            return task.config
        try:
            return loads(task.config) if task.config else {}
        except (TypeError, JSONDecodeError):
            return {}

    def release_sheet_execution_locks(self, task_id: str) -> int:
        """Release every sheet execution lock held by this task.

        Public entry point for collaborators (watchdog / cleanup) that need to
        free sheet locks without reaching into private helpers. No-op for tasks
        that hold no lock.
        """
        return sheet_execution_lock_service.release_for_task(task_id)

    def _start_next_pending_task(
        self,
        finished_task_id: str,
        finished_spreadsheet_ids: list[str],
        app,
    ) -> None:
        """Start the oldest pending task waiting on any of the released sheets."""
        if not finished_spreadsheet_ids:
            return

        pending_tasks = task_repository.list_pending_entities(
            exclude_task_id=finished_task_id
        )
        for pending_task in pending_tasks:
            pending_config = self._get_task_config_dict(pending_task)
            pending_spreadsheet_ids = self._extract_sheets_to_lock(
                pending_task.task_type, pending_config
            )
            if not set(finished_spreadsheet_ids).intersection(pending_spreadsheet_ids):
                continue

            pending_task_id = pending_task.id
            transition_message = (
                f"任务 {finished_task_id} 结束并释放 Sheet 占用，接力启动同 sheet 的"
                f"下一个待执行任务: {pending_task_id}"
            )
            logger.info(transition_message)
            self.add_task_log(finished_task_id, "info", transition_message, app)
            self.add_task_log(
                pending_task_id,
                "info",
                transition_message,
                app,
            )
            result = self.start_task(pending_task_id)
            if not result.started:
                logger.warning(
                    "接力启动未成功（任务保持排队待执行）: pending_task_id=%s, "
                    "status=%s, message=%s",
                    pending_task_id,
                    result.status,
                    result.message,
                )
                self.add_task_log(
                    pending_task_id,
                    "warning",
                    f"接力启动未成功，任务保持待执行: {result.message}",
                    app,
                )
            return

    def _get_config(self, key: str, default: Any = None) -> Any:
        """动态获取配置，确保运行期修改能实时生效。"""
        config_manager = get_config_manager()
        return config_manager.get_config(key, default)

    def _record_task_exception(self, task_id: str, exc: Exception, app):
        record = record_task_exception(task_id, exc, "task_runtime", app)
        return format_task_error_message(record)

    def _get_task_fresh(self, task_id: str):
        """重新读取任务状态，避免会话缓存影响最终收尾判断。"""
        return task_repository.get_entity_fresh(task_id)

    def _is_stop_requested(self, task_id: str) -> bool:
        stop_event = self.task_stop_events.get(task_id)
        return bool(stop_event and stop_event.is_set())

    def _get_type_concurrency_limit(self, spec):
        """分类型并发上限；未配置单独上限返回 None。"""
        if not spec.max_concurrency_key:
            return None
        try:
            return int(
                self._get_config(spec.max_concurrency_key, spec.max_concurrency_default)
            )
        except (TypeError, ValueError):
            return spec.max_concurrency_default

    def _cleanup_runtime_state(self, task_id: str, task_logger=None) -> None:
        """清理任务运行态（worker 收尾路径）。

        持运行态锁完成多 dict 清理；_active_worker_ids 仅在仍指向本线程时清理，
        防止被替换的老一代线程误删新一代线程登记的 worker id。
        """
        current_thread_id = threading.get_ident()
        with self._runtime_state_lock:
            thread = self.running_tasks.pop(task_id, None)
            stop_event = self.task_stop_events.pop(task_id, None)
            self.task_execution_types.pop(task_id, None)
            if self._active_worker_ids.get(task_id) == current_thread_id:
                self._active_worker_ids.pop(task_id, None)

        if thread and task_logger:
            task_logger.info("清理任务线程资源")

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

        if task.status == TaskStatus.CANCELLED.value or self._is_stop_requested(task_id):
            task_repository.update_fields(task_id, status=TaskStatus.CANCELLED.value, end_time=datetime.now())
            task_logger.info("任务执行完成，状态: cancelled（任务被取消）")
            self.add_task_log(
                task_id,
                "info",
                "任务执行完成，状态: cancelled（任务被取消）",
                app,
            )
            return

        if task_result == "cancelled":
            task_repository.update_fields(task_id, status=TaskStatus.CANCELLED.value, end_time=datetime.now())
            task_logger.info("任务执行完成，状态: cancelled（执行过程中被取消）")
            self.add_task_log(
                task_id,
                "info",
                "任务执行完成，状态: cancelled（执行过程中被取消）",
                app,
            )
            return

        if task_result == "completed":
            task_repository.update_fields(task_id, status=TaskStatus.COMPLETED.value, end_time=datetime.now())
            task_logger.info("任务执行完成，状态: completed")
            self.add_task_log(task_id, "info", "任务执行完成，状态: completed", app)
            return

        task_repository.update_fields(task_id, status=TaskStatus.ERROR.value, end_time=datetime.now())
        task_logger.info("任务执行完成，状态: error")
        self.add_task_log(task_id, "info", "任务执行完成，状态: error", app)

    def _rollback_start_reservation(
        self,
        task_id: str,
        reserved_sheet_ids: list[str],
        marked_running: bool,
    ) -> None:
        """回滚 start_task 前置阶段已占用的全部资源。

        任务线程提交（submit_task_execution）之前的任何失败路径都必须调用本方法，
        否则 sheet 执行锁 / Google Sheet 占用镜像 / token 计数会残留，任务会卡在
        running 状态并阻塞同一 sheet 的排队任务。
        """
        self.release_task_token_occupancy(task_id)
        self.release_google_sheet_occupancy(task_id)
        sheet_execution_lock_service.release_sheets(reserved_sheet_ids, task_id)
        if marked_running:
            task_repository.revert_running_to_pending(task_id)

    def _queue_task_for_sheet_busy(
        self,
        task_id: str,
        task_logger,
        holder_task_id: str | None,
    ) -> TaskStartResult:
        """Sheet 执行锁被占：任务保持 pending 排队，等持有者收尾后的接力启动。

        error_message 写入 [SHEET_QUEUED] 标记：既是页面可见的排队说明，
        也是启动期补跑扫描识别排队任务的依据（与崩溃中断任务区分）。
        """
        message = (
            "同一 Google Sheet 正在被其他任务执行，当前任务保持待执行排队: "
            f"{holder_task_id or 'unknown'}"
        )
        self.start_errors[task_id] = message
        task_logger.info(message)
        self.add_task_log(task_id, "info", message)
        task_repository.update_fields(
            task_id,
            error_message=f"{SHEET_QUEUED_PREFIX} {message}",
        )
        logger.info("任务排队等待 Sheet 执行锁: task_id=%s, holder=%s", task_id, holder_task_id)
        return TaskStartResult(status="queued", message=message)

    def start_task(self, task_id: str) -> TaskStartResult:
        """启动任务线程（统一入口）。

        Sheet 执行锁被占 → queued（保持 pending 排队，不算失败）；
        前置校验/配额/提交失败 → rejected（保持 pending，message 说明原因）；
        成功 → started。
        """
        self.start_errors.pop(task_id, None)
        acquired_token_id = None
        reserved_sheet_ids: list[str] = []
        marked_running = False

        def _rejected(message: str) -> TaskStartResult:
            self.start_errors[task_id] = message
            return TaskStartResult(status="rejected", message=message)

        with self._runtime_state_lock:
            thread = self.running_tasks.get(task_id)
            if thread and thread.is_alive():
                error_msg = "任务已在启动或运行中，拒绝重复启动"
                logger.warning("重复启动任务被拒绝: %s", task_id)
                return _rejected(error_msg)

            task_logger = get_task_logger(task_id, f"{__name__}.start")
            self.running_tasks.pop(task_id, None)

        task = task_repository.get_entity(task_id)
        if not task:
            error_msg = "任务不存在"
            if acquired_token_id:
                get_google_sheet_token_service().release_usage(acquired_token_id)
                self.task_token_occupancy.pop(task_id, None)
            task_logger.error(error_msg)
            logger.error("任务不存在: %s", task_id)
            return _rejected(error_msg)

        if task.status != TaskStatus.PENDING.value:
            error_msg = f"任务状态不是pending，当前状态: {task.status}"
            task_logger.warning(error_msg)
            logger.warning("任务状态不是pending，无法启动: %s", task_id)
            return _rejected(error_msg)

        config_data = self._get_task_config_dict(task)
        c_series_task = is_c_series_task_type(task.task_type)

        try:
            # 统一 Sheet 执行锁是互斥唯一权威（键 spreadsheet_id，类型无关）。
            # 被占不报错——保持 pending 排队，由持有者收尾的接力启动或启动期补跑接管。
            sheets_to_lock = self._extract_sheets_to_lock(task.task_type, config_data)
            # 回滚集合按"准备加锁"的全量口径预置：acquire_for_task 中途抛异常时，
            # except 路径才能释放已获取的锁（release_sheets 按持有者过滤，未持有为 no-op）。
            reserved_sheet_ids = sheets_to_lock
            with self.sheet_start_lock:
                holder_task_id = sheet_execution_lock_service.find_conflict(
                    sheets_to_lock, exclude_task_id=task_id
                )
                if holder_task_id:
                    return self._queue_task_for_sheet_busy(
                        task_id, task_logger, holder_task_id
                    )

                lock_acquired, holder_task_id, acquired_ids = (
                    sheet_execution_lock_service.acquire_for_task(
                        task_id, task.task_type, sheets_to_lock
                    )
                )
                if not lock_acquired:
                    return self._queue_task_for_sheet_busy(
                        task_id, task_logger, holder_task_id
                    )
                reserved_sheet_ids = acquired_ids

                # 占用镜像仅作展示，登记失败不拦截启动。
                self.ensure_google_sheet_occupancy(
                    task_id,
                    self._config_for_spreadsheet_locks(config_data, sheets_to_lock),
                    allowed_table_types=(
                        C_SERIES_TABLE_TYPES if c_series_task else None
                    ),
                )
                if c_series_task:
                    # C 系合法性复核（模型注册/启用）；占用互斥不在其职责内。
                    self.validate_c_series_sheet_models(config_data)

                rows = task_repository.mark_running_if_pending(
                    task_id,
                    start_time=datetime.now(),
                    commit=False,
                )
                if rows == 0:
                    # 任务已被并发方（取消/看门狗）改走：只提交已发生的变更，
                    # 不清 error_message——避免覆盖并发方刚写入的取消/错误原因。
                    task_repository.commit()
                    error_msg = "任务状态已变化，无法启动"
                    task_logger.warning(error_msg)
                    self._rollback_start_reservation(
                        task_id, reserved_sheet_ids, marked_running
                    )
                    return _rejected(error_msg)
                # 启动成功即清排队标记，避免运行中残留 "[SHEET_QUEUED]" 误导展示。
                task_repository.update_fields(task_id, error_message=None, commit=False)
                task_repository.commit()
                marked_running = True

            token_id = config_data.get("token_id")
            if token_id:
                token_service = get_google_sheet_token_service()
                token_service.validate_task_start(config_data)
                # 排除自身：mark_running 已提交，活扫描不排除会把本任务计入再 +1（双计）
                token_service.increment_usage(token_id, exclude_task_id=task_id)
                acquired_token_id = int(token_id)
                self.task_token_occupancy[task_id] = acquired_token_id
        except Exception as exc:
            error_msg = str(exc)
            self._rollback_start_reservation(task_id, reserved_sheet_ids, marked_running)
            task_logger.warning("任务启动前置校验失败，无法启动任务: %s", error_msg)
            logger.warning("任务启动前置校验失败: %s, %s", task_id, error_msg)
            return _rejected(error_msg)

        task_logger.info("开始启动任务 - 名称: %s, 类型: %s", task.name, task.task_type)

        task_type = task.task_type.lower()

        # 分发走任务类型注册表；未注册类型拒绝启动并写 error_message 供前端展示。
        spec = get_task_type_spec(task_type)
        if spec is None:
            error_msg = f"不支持的任务类型: {task_type}"
            self._rollback_start_reservation(task_id, reserved_sheet_ids, marked_running)
            task_repository.update_fields(task_id, error_message=error_msg)
            self.add_task_log(task_id, "error", f"任务启动被拒绝: {error_msg}")
            task_logger.error(error_msg)
            logger.error("不支持的任务类型: %s", task_type)
            return _rejected(error_msg)

        # 启动前配额检查（全局 + 分类型）：超限不排队不报错，回滚本次预占并保持任务
        # 待执行等待下次调度/手动启动（保住看门狗 pending 不检查/running 无日志告警语义）。
        max_workers = int(self._get_config(GLOBAL_MAX_KEY, GLOBAL_MAX_DEFAULT) or GLOBAL_MAX_DEFAULT)
        if self.count_running_executions() >= max_workers:
            error_msg = f"并发已满（{self.count_running_executions()}/{max_workers}），任务保持待执行"
            self._rollback_start_reservation(task_id, reserved_sheet_ids, marked_running)
            self.add_task_log(task_id, "warning", f"任务启动被拒绝: {error_msg}")
            task_logger.warning(error_msg)
            return _rejected(error_msg)

        type_limit = self._get_type_concurrency_limit(spec)
        if type_limit is not None:
            with self._runtime_state_lock:
                execution_types_snapshot = list(self.task_execution_types.items())
                running_snapshot = dict(self.running_tasks)
            type_running = sum(
                1
                for running_id, running_type in execution_types_snapshot
                if running_type == task_type
                and running_snapshot.get(running_id)
                and running_snapshot[running_id].is_alive()
            )
            if type_running >= type_limit:
                error_msg = (
                    f"{spec.display_name} 并发已满（{type_running}/{type_limit}），任务保持待执行"
                )
                self._rollback_start_reservation(task_id, reserved_sheet_ids, marked_running)
                self.add_task_log(task_id, "warning", f"任务启动被拒绝: {error_msg}")
                task_logger.warning(error_msg)
                return _rejected(error_msg)

        self.task_stop_events[task_id] = threading.Event()
        app = current_app._get_current_object()

        try:
            runner = build_runner(self, spec)
        except LookupError as exc:
            error_msg = str(exc)
            self.task_stop_events.pop(task_id, None)
            self._rollback_start_reservation(task_id, reserved_sheet_ids, marked_running)
            self.add_task_log(task_id, "error", f"任务启动被拒绝: {error_msg}")
            task_logger.error(error_msg)
            return _rejected(error_msg)

        task_logger.info(f"创建{spec.display_name}任务执行线程")
        self.task_execution_types[task_id] = task_type

        try:
            self.submit_task_execution(task_id, app, runner)
        except Exception as exc:
            # submit_task_execution 可能已在入队前注册运行态句柄后失败，
            # 无论失败发生在哪一步都需撤回注册。
            self.running_tasks.pop(task_id, None)
            self.task_stop_events.pop(task_id, None)
            self._rollback_start_reservation(task_id, reserved_sheet_ids, marked_running)
            error_msg = f"任务线程启动失败: {exc}"
            task_logger.error(error_msg)
            logger.error("任务线程启动失败: %s, err=%s", task_id, exc)
            return _rejected(error_msg)

        task_logger.info("任务执行线程启动成功")
        logger.info("启动任务: %s", task_id)
        return TaskStartResult(status="started")

    def _mark_task_running(self, task_id: str, task_logger, app, start_message: str) -> Task | None:
        """将任务置为运行中。

        Google Sheet 普通任务保留旧行为；其它任务使用原子更新防止并发重复启动。
        """
        task = task_repository.get_entity(task_id)
        if not task:
            task_logger.error("任务不存在")
            return None

        if task.task_type == TaskType.GOOGLE_SHEET.value:
            task_repository.update_fields(task_id, status=TaskStatus.RUNNING.value, start_time=datetime.now())
        else:
            if task.status == TaskStatus.RUNNING.value:
                if not task.start_time:
                    task_repository.update_fields(task_id, start_time=datetime.now())
            else:
                rows = task_repository.mark_running_if_not_running(
                    task_id,
                    start_time=datetime.now(),
                )
                if rows == 0:
                    duplicate_message = self._build_duplicate_start_message(task.task_type)
                    task_logger.warning(duplicate_message)
                    self.add_task_log(task_id, "warn", duplicate_message, app)
                    return None
                task = task_repository.get_entity(task_id)

        self.add_task_log(task_id, "info", start_message, app)
        return task

    def _build_duplicate_start_message(self, task_type: str) -> str:
        duplicate_map = {
            "google_sheet_C4": "任务已在运行，拒绝并发启动 (C4)",
            "google_sheet_C5": "任务已在运行，拒绝并发启动 (C5)",
            "google_sheet_C7": "任务已在运行，拒绝并发启动 (C7)",
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

        def _is_active_generation() -> bool:
            # Why: watchdog 强制重启会把本线程踢出 running_tasks 并起新线程接管。
            # 老线程若在网络 IO 解开后醒来，不应再覆盖任务状态或释放新一代占用。
            handle = self.running_tasks.get(task_id)
            if handle is None or handle.future.done():
                return False
            worker_id = self._active_worker_ids.get(task_id)
            return worker_id is None or worker_id == threading.get_ident()

        try:
            with app.app_context():
                task = task_repository.get_entity(task_id)
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
                if not _is_active_generation():
                    task_logger.warning(
                        "本线程已被 watchdog 强制重启替换，跳过状态收尾"
                    )
                else:
                    self._finalize_task_execution(task_id, app, task_logger, task_result)
        except Exception as exc:
            root = unwrap_exception(exc) or exc
            task_logger.exception("%s: %s", failure_label, root)
            if _is_active_generation():
                try:
                    self._record_task_exception(task_id, exc, app)
                except Exception as update_error:
                    task_logger.error("更新任务状态失败: %s", update_error)
            else:
                task_logger.warning(
                    "本线程已被 watchdog 强制重启替换，跳过异常态写入"
                )
        finally:
            if not _is_active_generation():
                task_logger.warning(
                    "本线程已被替换，跳过 finally 清理以保护新一代任务"
                )
                task_logger.info("任务执行器退出")
                return

            finished_spreadsheet_ids: list[str] = []
            with app.app_context():
                # 接力集合取本任务实际持有的锁行（与释放同源），不从 config 重算：
                # multi_product 固定产品缓存执行中落库会让重算漏掉已锁 Sheet，
                # 导致等该 Sheet 的排队任务无人接力。
                finished_spreadsheet_ids = (
                    sheet_execution_lock_service.list_held_spreadsheet_ids(task_id)
                )
                self.release_task_token_occupancy(task_id)
                self.release_google_sheet_occupancy(task_id)
                # 统一释放 Sheet 执行锁（仅持锁者可释放，由仓储保证）。
                sheet_execution_lock_service.release_for_task(task_id)
                # 所有任务类型统一接力：释放的 sheet 上有排队任务就启动最早的一个。
            self._cleanup_runtime_state(task_id, task_logger=task_logger)
            with app.app_context():
                with self.sheet_start_lock:
                    self._start_next_pending_task(
                        task_id, finished_spreadsheet_ids, app
                    )
            task_logger.info("任务执行器退出")

    def _execute_google_sheet_task(self, task_id: str, app) -> None:
        self._execute_service_task(
            task_id,
            app,
            logger_name=f"{__name__}.{task_id}",
            start_message="开始执行Google Sheet任务",
            service_class=C3Service,
            business_message="开始执行任务业务逻辑",
            failure_label="执行任务失败",
        )

    def _execute_google_sheet_c4_task(self, task_id: str, app) -> None:
        self._execute_service_task(
            task_id,
            app,
            logger_name=f"{__name__}.C4.{task_id}",
            start_message="开始执行Google Sheet C4 任务",
            service_class=C4Service,
            business_message="开始执行 C4 任务业务逻辑",
            failure_label="执行 C4 任务失败",
        )

    def _execute_google_sheet_c5_task(self, task_id: str, app) -> None:
        self._execute_service_task(
            task_id,
            app,
            logger_name=f"{__name__}.C5.{task_id}",
            start_message="开始执行Google Sheet C5 任务",
            service_class=C5Service,
            business_message="开始执行 C5 任务业务逻辑",
            failure_label="执行 C5 任务失败",
        )

    def _execute_google_sheet_c7_task(self, task_id: str, app) -> None:
        self._execute_service_task(
            task_id,
            app,
            logger_name=f"{__name__}.C7.{task_id}",
            start_message="开始执行Google Sheet C7 任务",
            service_class=C7Service,
            business_message="开始执行 C7 任务业务逻辑",
            failure_label="执行 C7 任务失败",
        )

    def _execute_google_sheet_c1_1_task(self, task_id: str, app) -> None:
        self._execute_service_task(
            task_id,
            app,
            logger_name=f"{__name__}.C1.1.{task_id}",
            start_message="开始执行Google Sheet C1.1 任务",
            service_class=C1_1Service,
            business_message="开始执行 C1.1 任务业务逻辑",
            failure_label="执行 C1.1 任务失败",
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

    def _execute_backtest_multi_product_task(self, task_id: str, app) -> None:
        self._execute_service_task(
            task_id,
            app,
            logger_name=f"{__name__}.backtest_multi_product.{task_id}",
            start_message="开始执行多品数据回测任务",
            service_class=BacktestMultiProductService,
            business_message="开始执行多品数据回测任务业务逻辑",
            failure_label="执行多品数据回测任务失败",
        )

"""任务运行态视图拼装服务。"""

from __future__ import annotations

from app.utils.json_utils import loads
from datetime import datetime
from typing import Any

from app.exceptions import NotFoundError
from app.repositories import task_log_repository, task_repository, task_result_repository

from app.models import Task
from app.utils.return_series import parse_return_series_fields

from app.services.task.dashboard_query import TaskDashboardQueryService
from app.services.task.runtime_state import get_runtime_state_store, read_task_logs


def _safe_json_loads(raw_value, default=None):
    if default is None:
        default = {}
    if not raw_value:
        return default
    if isinstance(raw_value, (dict, list)):
        return raw_value
    try:
        return loads(raw_value)
    except Exception:
        return default


def _as_dict(value):
    return value if isinstance(value, dict) else {}


def _extract_parameter_label(parameters_payload, step_index: int):
    if isinstance(parameters_payload, dict):
        return (
            parameters_payload.get("stock_code")
            or parameters_payload.get("stock_no")
            or parameters_payload.get("code")
            or parameters_payload.get("symbol")
            or f"step-{step_index + 1}"
        )

    if isinstance(parameters_payload, list):
        for item in parameters_payload:
            if isinstance(item, dict):
                label = (
                    item.get("stock_code")
                    or item.get("stock_no")
                    or item.get("code")
                    or item.get("symbol")
                )
                if label:
                    return label
            elif item not in (None, ""):
                return str(item)

    if parameters_payload not in (None, "", {}):
        return str(parameters_payload)

    return f"step-{step_index + 1}"


class TaskRuntimeViewService:
    """管理后台任务运行态视图拼装服务。"""

    def __init__(self, task_manager):
        self._task_manager = task_manager
        self._dashboard_query_service = TaskDashboardQueryService()

    def build_config_summary(self, task: Task) -> dict[str, Any]:
        config = _safe_json_loads(task.config, {})
        parameters = config.get("parameters") if isinstance(config, dict) else None
        parameter_groups = len(parameters) if isinstance(parameters, list) else 0
        parameter_sizes = []
        parameter_preview = []
        if isinstance(parameters, list):
            for idx, param_group in enumerate(parameters[:4], start=1):
                if isinstance(param_group, list):
                    parameter_sizes.append(len(param_group))
                    parameter_preview.append(
                        {
                            "group": idx,
                            "size": len(param_group),
                            "sample": param_group[:3],
                        }
                    )
                else:
                    parameter_preview.append(
                        {
                            "group": idx,
                            "size": 1,
                            "sample": [param_group],
                        }
                    )

        # 统一 sheets[] 形态：管理页摘要消费首个 Sheet 引用
        sheets = config.get("sheets") if isinstance(config, dict) and isinstance(config.get("sheets"), list) else []
        first_sheet = sheets[0] if sheets and isinstance(sheets[0], dict) else {}
        return {
            "sheet_name": first_sheet.get("sheet_name"),
            "spreadsheet_id": first_sheet.get("spreadsheet_id"),
            "token_id": config.get("token_id") if isinstance(config, dict) else None,
            "parameter_groups": parameter_groups,
            "parameter_sizes": parameter_sizes,
            "parameter_preview": parameter_preview,
            "config_keys": (
                sorted(list(config.keys()))[:12] if isinstance(config, dict) else []
            ),
        }

    def build_stop_confirmation(self, task_id: str) -> dict[str, Any]:
        status_check = self._task_manager.check_local_task_status(task_id)
        thread = self._task_manager.running_tasks.get(task_id)
        stop_event = self._task_manager.task_stop_events.get(task_id)
        task = task_repository.get_entity(task_id)

        thread_alive = bool(thread and thread.is_alive())
        stop_requested = bool(stop_event and stop_event.is_set())
        db_status = task.status if task else status_check.get("db_status")
        stop_confirmed = (db_status != "running") and (not thread_alive)

        return {
            "task_id": task_id,
            "db_status": db_status,
            "thread_alive": thread_alive,
            "memory_running": status_check.get("memory_running", thread_alive),
            "stop_requested": stop_requested,
            "stop_confirmed": stop_confirmed,
            "current_step": task.current_step if task else None,
            "total_steps": task.total_steps if task else None,
            "checked_at": datetime.now().isoformat(),
            "status_check": status_check,
        }

    def build_result_summary(self, task_id: str) -> dict[str, Any]:
        results = task_result_repository.list_entities_by_task_ordered(task_id)
        total = len(results)
        success_count = sum(1 for item in results if item.success)
        failed_count = total - success_count

        metric_points = []
        for result in results[-30:]:
            result_payload = _as_dict(_safe_json_loads(result.result, {}))
            parameters_payload = _safe_json_loads(result.parameters, {})
            annualized = (
                result_payload.get("I16")
                or result_payload.get("annualized_rate")
                or result_payload.get("annualized")
            )
            max_drawdown = result_payload.get("I17") or result_payload.get("maxdd")
            return_rate = result_payload.get("I15") or result_payload.get("return_rate")
            metric_points.append(
                {
                    "step": result.step_index + 1,
                    "success": bool(result.success),
                    "annualized_rate": annualized,
                    "max_drawdown": max_drawdown,
                    "return_rate": return_rate,
                    "parameter_label": _extract_parameter_label(
                        parameters_payload,
                        result.step_index,
                    ),
                }
            )

        return_chart = []
        series_result = next((item for item in reversed(results) if item.return_series_id), None)
        series_row = (
            task_result_repository.get_return_entity(series_result.return_series_id)
            if series_result and series_result.return_series_id
            else None
        )
        if series_row:
            return_chart = [
                {"date": item["date"], "index_return": item.get("index_return"),
                 "strategy_return": item.get("start_return")}
                for item in parse_return_series_fields(series_row)
            ][-120:]
        if not return_chart:
            returns = task_result_repository.list_return_entities_by_task(task_id)
            return_chart = [
                {
                    "date": item.stock_date,
                    "index_return": item.index_return,
                    "strategy_return": item.start_return,
                }
                for item in returns[-120:]
                if item.stock_date is not None
            ]

        return {
            "total_results": total,
            "success_count": success_count,
            "failed_count": failed_count,
            "success_rate": round((success_count / total) * 100, 2) if total else 0,
            "latest_metric_points": metric_points,
            "return_chart": return_chart,
        }

    def get_runtime_detail(self, task_id: str) -> dict[str, Any]:
        """admin runtime-detail 端点：任务不存在抛 NotFoundError，存在返回运行态细节。"""
        task = task_repository.get_entity(task_id)
        if not task:
            raise NotFoundError("任务不存在")
        return self.serialize_task_runtime(task)

    def serialize_task_runtime(self, task: Task) -> dict[str, Any]:
        config_summary = self.build_config_summary(task)
        stop_confirmation = self.build_stop_confirmation(task.id)
        result_summary = self.build_result_summary(task.id)
        # 方案 B：运行中任务的日志在 Redis 运行态，读取时优先运行态。
        recent_logs = read_task_logs(task.id, limit=20)

        duration_seconds = None
        if task.start_time:
            end_at = task.end_time or datetime.now()
            duration_seconds = max(
                0,
                int((end_at - task.start_time).total_seconds()),
            )

        data = task.to_dict()
        # 进度百分比由 data 字段计算（不依赖本地模型方法，HTTP RemoteRecord 同样可用）。
        _current = int(data.get("current_step") or 0)
        _total = int(data.get("total_steps") or 0)
        progress_percentage = round(_current / _total * 100, 2) if _total else 0
        # 方案 B：运行态存在时叠加 Redis 进度（进度百分比随之以运行态为准）。
        try:
            runtime_state = get_runtime_state_store().get_state(task.id)
        except Exception:
            runtime_state = None
        if runtime_state:
            for field in ("current_step", "total_steps"):
                if runtime_state.get(field) is not None:
                    data[field] = runtime_state[field]
            if runtime_state.get("total_steps"):
                progress_percentage = round(
                    (runtime_state.get("current_step") or 0)
                    / runtime_state["total_steps"]
                    * 100,
                    2,
                )
        data.update(
            {
                "progress_percentage": progress_percentage,
                "duration_seconds": duration_seconds,
                "config_summary": config_summary,
                "stop_confirmation": stop_confirmation,
                "result_summary": result_summary,
                "recent_logs": recent_logs,
            }
        )
        return data

    def build_dashboard_overview(self, user) -> dict[str, Any]:
        now = datetime.now()
        # 当前为全量类型（无权限过滤）；缺口登记见 07-public-deployment-and-subservice §1。
        allowed_task_types = self._dashboard_query_service.list_all_task_types()

        if not allowed_task_types:
            return self._dashboard_query_service.build_empty_overview(now)

        status_distribution = self._dashboard_query_service.get_status_distribution(
            allowed_task_types
        )
        task_type_distribution = (
            self._dashboard_query_service.get_task_type_distribution(
                allowed_task_types
            )
        )
        summary = self._dashboard_query_service.get_summary(allowed_task_types)
        daily_trend = self._dashboard_query_service.get_daily_trend(
            allowed_task_types,
            now=now,
        )
        recent_task_models = self._dashboard_query_service.get_recent_task_models(
            allowed_task_types,
            limit=10,
        )
        running_task_models = self._dashboard_query_service.get_active_task_models(
            allowed_task_types,
            limit=6,
        )

        recent_tasks = [self.serialize_task_runtime(task) for task in recent_task_models]
        active_tasks = [
            self.serialize_task_runtime(task) for task in running_task_models
        ]

        return {
            "success": True,
            "summary": summary,
            "status_distribution": status_distribution,
            "task_type_distribution": task_type_distribution,
            "daily_trend": daily_trend,
            "recent_tasks": recent_tasks,
            "active_tasks": active_tasks,
            "checked_at": now.isoformat(),
        }

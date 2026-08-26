"""任务创建与配置更新逻辑。"""

from __future__ import annotations

import json
import operator
import time
import uuid
from datetime import datetime, timedelta
from functools import reduce
from itertools import product
from typing import Any, Optional

from app.models import GoogleSheetTokenTaskType, TaskStatus
from app.repositories.task_repository import TaskRepository
from app.services.google_sheet_token_service import (
    RANDOM_TOKEN_VALUE,
    get_google_sheet_token_service,
)
from app.services.backtest_parameter_utils import normalize_backtest_training_config
from app.services.stock_metadata_service import lookup_stock_metadata, save_stock_metadata
from app.services.kline_service import KlineService
from app.utils.database import transaction_required
from app.utils.logger import get_logger, get_task_logger
from app.utils.market import infer_market_type, normalize_market_type, normalize_stock_code

logger = get_logger(__name__)
_task_repository = TaskRepository()

KLINE_SOURCE_AUTO = "auto"
KLINE_SOURCE_CUSTOM = "custom"
VALID_KLINE_SOURCES = {KLINE_SOURCE_AUTO, KLINE_SOURCE_CUSTOM}


def _is_empty_custom_kline_option(value: Any) -> bool:
    """判断自定义 K 线模式中可忽略的空配置项。"""
    return value in (None, "") or value == [] or value == ()


def _normalize_c_series_kline_source_config(config: dict[str, Any]) -> dict[str, Any]:
    """规范化 C 系列任务的自动与自定义 K 线配置。"""
    normalized = dict(config)
    kline_source = str(normalized.get("kline_source") or KLINE_SOURCE_AUTO).strip().lower()
    if kline_source not in VALID_KLINE_SOURCES:
        raise ValueError("kline_source 仅支持 auto 或 custom")

    normalized["kline_source"] = kline_source
    if kline_source != KLINE_SOURCE_CUSTOM:
        return normalized

    if normalized.get("count_mode") not in (None, "", "total"):
        raise ValueError("自定义K线模式不支持 N+1 或其它统计方式")
    if not _is_empty_custom_kline_option(normalized.get("market_type")) and normalized.get("market_type") != "custom":
        raise ValueError("自定义K线模式不支持选择 A股/美股市场")
    if not _is_empty_custom_kline_option(normalized.get("price_mode")):
        raise ValueError("自定义K线模式不支持选择价格类型")
    if not _is_empty_custom_kline_option(normalized.get("kline_adjustment")):
        raise ValueError("自定义K线模式不支持选择K线复权")
    if not _is_empty_custom_kline_option(normalized.get("date_range_mode")):
        raise ValueError("自定义K线模式不支持整年/近年选项")
    if not _is_empty_custom_kline_option(normalized.get("exclude_recent_years")):
        raise ValueError("自定义K线模式不支持近年排除选项")
    if not _is_empty_custom_kline_option(normalized.get("start_date")) or not _is_empty_custom_kline_option(normalized.get("end_date")):
        raise ValueError("自定义K线模式不支持开始日期/结束日期")

    normalized["count_mode"] = "total"
    normalized["market_type"] = "custom"
    normalized["price_mode"] = None
    normalized["kline_adjustment"] = None
    normalized["date_range_mode"] = []
    normalized["exclude_recent_years"] = []
    normalized["start_date"] = None
    normalized["end_date"] = None
    return normalized


def _normalize_c7_random_price_config(config: dict[str, Any]) -> dict[str, Any]:
    """规范化 C7 随机价格模式相关的任务配置字段。"""
    normalized = dict(config)
    price_mode = normalized.get("price_mode") or "vwap_price"
    if price_mode != "random_price":
        normalized.pop("random_price_range", None)
        normalized.pop("random_group_count", None)
        return normalized

    versions = {
        str(sheet.get("c7_model_version") or "c7_0_2").strip().lower()
        for sheet in normalized.get("sheets") or []
    }
    if "c7_0_3" in versions:
        raise ValueError("随机价格仅支持 C7.0.2")
    random_range = str(normalized.get("random_price_range") or "high_low").strip().lower()
    if random_range not in {"high_low", "open_close"}:
        raise ValueError("随机价格范围仅支持最高最低或开盘收盘")
    try:
        raw_group_count = normalized.get("random_group_count")
        group_count = 1 if raw_group_count in (None, "") else int(raw_group_count)
    except (TypeError, ValueError) as exc:
        raise ValueError("随机组数必须是正整数") from exc
    if isinstance(raw_group_count, bool) or (
        isinstance(raw_group_count, float) and not raw_group_count.is_integer()
    ) or group_count < 1:
        raise ValueError("随机组数必须是正整数")
    normalized["random_price_range"] = random_range
    normalized["random_group_count"] = group_count
    return normalized


def _stock_metadata_items_from_config(config: Any) -> list[dict[str, Any]]:
    """从任务配置提取可用于补全股票名称的元数据项。"""
    if not isinstance(config, dict):
        return []

    items: list[dict[str, Any]] = []
    stock_item = {
        "stock_code": config.get("stock_code"),
        "stock_name": config.get("stock_name"),
        "market_type": config.get("market_type"),
        "exchange_market": config.get("exchange_market") or config.get("market"),
        "security_type_name": config.get("security_type_name"),
        "source": config.get("stock_source") or "task_config",
    }
    if stock_item["stock_code"] and stock_item["stock_name"]:
        items.append(stock_item)

    for key in ("stocks", "stock_items", "selected_stocks"):
        values = config.get(key)
        if not isinstance(values, list):
            continue
        for value in values:
            if isinstance(value, dict):
                items.append({
                    "stock_code": value.get("stock_code") or value.get("code"),
                    "stock_name": value.get("stock_name") or value.get("name"),
                    "market_type": value.get("market_type") or value.get("marketType") or config.get("market_type"),
                    "exchange_market": value.get("exchange_market") or value.get("market"),
                    "security_type_name": value.get("security_type_name") or value.get("securityTypeName"),
                    "source": value.get("source") or "task_config",
                    "raw": value,
                })
    return items


def _hydrate_stock_name_from_metadata(config: dict[str, Any]) -> dict[str, Any]:
    """依据内嵌股票元数据补全任务配置中的股票名称。"""
    if config.get("stock_name") or not config.get("stock_code"):
        return config
    metadata = lookup_stock_metadata(config.get("stock_code"), config.get("market_type"))
    stock_name = str(metadata.get("stock_name") or "").strip()
    if not stock_name:
        return config
    hydrated = dict(config)
    hydrated["stock_name"] = stock_name
    if metadata.get("exchange_market") and not hydrated.get("exchange_market"):
        hydrated["exchange_market"] = metadata.get("exchange_market")
    if metadata.get("security_type_name") and not hydrated.get("security_type_name"):
        hydrated["security_type_name"] = metadata.get("security_type_name")
    return hydrated


class TaskCreationMixin:
    """封装任务创建、批量拆分与配置更新。"""

    def _normalize_task_config_for_type(self, task_type: str, config):
        """根据任务类型统一规范化参数、股票和 K 线配置。"""
        if not isinstance(config, dict):
            return config
        normalized = dict(config)
        market_type = normalize_market_type(normalized.get("market_type"))
        if market_type:
            normalized["market_type"] = market_type
        if normalized.get("stock_code"):
            normalized["stock_code"] = normalize_stock_code(
                normalized["stock_code"],
                market_type or infer_market_type(normalized["stock_code"]),
                normalized.get("exchange_market"),
            )
        if task_type.lower() in ("google_sheet", "google_sheet_c4", "google_sheet_c5","google_sheet_c7"):
            normalized["token_task_type"] = GoogleSheetTokenTaskType.GOOGLE_SHEET.value
            normalized["kline_data_source"] = KlineService.normalize_data_source(
                normalized.get("kline_data_source", normalized.get("data_source"))
            )
            if task_type.lower() in ("google_sheet_c5", "google_sheet_c7"):
                normalized = _normalize_c_series_kline_source_config(normalized)
            if task_type.lower() == "google_sheet_c7":
                normalized = _normalize_c7_random_price_config(normalized)
        elif task_type in ("backtest_training", "backtest_multi_product"):
            normalized["token_task_type"] = (
                GoogleSheetTokenTaskType.BACKTEST_TRAINING.value
            )
            normalized.pop("token_file", None)
            normalized["price_mode"] = (
                normalized.get("price_mode")
                if normalized.get("price_mode") in ("kp_price", "sp_price", "vwap_price")
                else "vwap_price"
            )
            normalized["kline_data_source"] = KlineService.normalize_data_source(
                normalized.get("kline_data_source", normalized.get("data_source"))
            )

        if task_type.lower() in ("google_sheet_c4", "google_sheet_c5","google_sheet_c7"):
            normalized.pop("spreadsheet_id", None)
            normalized.pop("sheet_name", None)

        if task_type == "backtest_multi_product":
            from app.services.backtest_multi_product_service import (
                normalize_multi_product_config,
            )

            normalized = normalize_multi_product_config(normalized)
        elif task_type == "backtest_training":
            normalized = normalize_backtest_training_config(normalized)

        if task_type in ("backtest_training", "backtest_multi_product") and not normalized.get("token_id"):
            token_id = (
                self._get_config("backtest_training_token_id")
                or self._get_config("backtest_token_id")
                or self._get_config("google_sheet_backtest_token_id")
            )
            if token_id not in (None, "", 0, "0"):
                normalized["token_type"] = normalized.get("token_type", "file")
                normalized["token_id"] = token_id
        return normalized

    @transaction_required
    def create_task(
        self,
        name: str,
        description: str,
        task_type: str,
        config: dict[str, Any],
        created_by_user_id: Optional[int] = None,
    ) -> str:
        """创建新任务。"""
        task_id = str(uuid.uuid4())
        config = self._normalize_task_config_for_type(task_type, config)

        if isinstance(config, dict):
            config = _hydrate_stock_name_from_metadata(config)
            config = get_google_sheet_token_service().prepare_task_config(config)
            if task_type == "backtest_training":
                self.validate_backtest_training_sheet(config)
            self.validate_google_sheet_available_for_task(
                config,
                task_id,
                allow_in_use=(task_type in ("backtest_training", "backtest_multi_product")),
            )
            for stock_item in _stock_metadata_items_from_config(config):
                save_stock_metadata(stock_item)

        config_str = json.dumps(config) if isinstance(config, dict) else str(config)
        # 任务主记录和股票元数据均通过远程 CRUD 创建。
        _task_repository.save({
            "id": task_id,
            "name": name,
            "description": description,
            "task_type": task_type,
            "config": config_str,
            "status": "pending",
            "created_by_user_id": created_by_user_id,
        })

        if isinstance(config, dict) and task_type not in ("backtest_training", "backtest_multi_product"):
            self.ensure_google_sheet_occupancy(task_id, config)

        task_logger = get_task_logger(task_id, f"{__name__}.create")
        task_logger.info(
            "创建任务成功 - 名称: %s, 类型: %s, 配置项数量: %s",
            name,
            task_type,
            len(config) if isinstance(config, dict) else "N/A",
        )
        logger.info("创建任务: %s - %s", task_id, name)
        return task_id

    def create_and_start_task(
        self,
        name: str,
        description: str,
        task_type: str,
        config: dict[str, Any],
        created_by_user_id: Optional[int] = None,
    ):
        """创建并启动任务。"""
        task_id = self.create_task(
            name,
            description,
            task_type,
            config,
            created_by_user_id=created_by_user_id,
        )
        if self.start_task(task_id):
            return {
                "status": "success",
                "task_id": task_id,
                "message": "任务创建并启动成功",
            }, 200
        start_error = self.get_start_error(task_id)
        if task_type in ("backtest_training", "backtest_multi_product") and "已有回测任务正在运行" in start_error:
            return {
                "status": "success",
                "task_id": task_id,
                "message": start_error,
                "queued": True,
            }, 200
        self.release_google_sheet_occupancy(task_id)
        return {
            "status": "error",
            "task_id": task_id,
            "message": start_error,
        }, 400

    def batch_create_and_start_task(
        self,
        data: dict[str, Any],
        created_by_user_id: Optional[int] = None,
    ):
        """将 C31 批量请求拆分为多个 C3 子任务。"""
        if not isinstance(data, dict):
            raise ValueError("批量任务请求体必须是 JSON 对象")

        config = data.get("config") or {}
        if not isinstance(config, dict):
            raise ValueError("缺少有效的 config 配置")

        base_name = str(config.get("base_task_name") or data.get("name") or "").strip()
        if not base_name:
            raise ValueError("缺少 base_task_name")

        description = str(
            data.get("description") or config.get("task_description") or ""
        ).strip()
        child_task_type = "google_sheet"

        sheets = config.get("sheets") or []
        stock_codes = config.get("stock_codes") or []
        stocks = config.get("stocks") or []
        stock_metadata_by_code = {}
        if isinstance(stocks, list):
            for item in stocks:
                if not isinstance(item, dict):
                    continue
                code = str(item.get("stock_code") or item.get("code") or "").strip().upper()
                if not code:
                    continue
                stock_metadata_by_code[code] = item
            if stock_metadata_by_code and not stock_codes:
                stock_codes = [item.get("stock_code") or item.get("code") for item in stocks if isinstance(item, dict)]
        parameter_groups = config.get("parameters") or []
        if not isinstance(sheets, list) or not sheets:
            raise ValueError("至少需要一组 sheets 配置")
        if not isinstance(stock_codes, list) or not stock_codes:
            raise ValueError("至少需要一个 stock_codes")
        if not isinstance(parameter_groups, list) or not parameter_groups:
            raise ValueError("至少需要一组 parameters")

        normalized_groups = self._normalize_c31_parameter_groups(parameter_groups)
        parameter_combinations = list(product(*normalized_groups))
        if not parameter_combinations:
            raise ValueError("未生成任何参数组合")

        sheet_count = len(
            [
                sheet
                for sheet in sheets
                if isinstance(sheet, dict)
                and str(sheet.get("spreadsheet_id") or "").strip()
            ]
        )
        combination_count = len(parameter_combinations)
        if not self._is_count_compatible(combination_count, sheet_count):
            raise ValueError(
                f"参数组合数({combination_count})与Sheet数({sheet_count})必须相等，或其中一方是另一方的整数倍"
            )

        sheet_dict: dict[str, list[dict[str, Any]]] = {}
        for sheet in sheets:
            sheet_title = str(sheet.get("title") or "").strip()
            if not sheet_title.endswith("]"):
                raise ValueError("格式必须以“任意前缀-数字y-数字]”结尾，例如：策略A-1y-3]")

            segments = sheet_title.strip().strip("]").split("-")
            year_n = segments[-2]
            sort_n = int(segments[-1])
            sheet["sort_n"] = sort_n
            sheet["year_n"] = year_n
            sheet_dict.setdefault(year_n, []).append(sheet)

        for year_n, grouped_sheets in sheet_dict.items():
            if len(grouped_sheets) != combination_count:
                raise ValueError(
                    f"{year_n} 所含有的表格数，无法对齐参数数量，{combination_count},检查是否是参数设置过多还是表格创建过少"
                )

        created_task_ids = []
        started_task_ids = []
        failed_to_start = []
        child_summaries = []

        shared_config = {
            key: value
            for key, value in config.items()
            if key
            not in {
                "base_task_name",
                "task_description",
                "stock_codes",
                "parameters",
                "parameter_dimensions",
                "sheets",
            }
        }

        if "token_id" not in shared_config or not shared_config.get("token_id"):
            shared_config["token_type"] = "file"
            shared_config["token_id"] = RANDOM_TOKEN_VALUE

        for stock_code in stock_codes:
            stock_code = str(stock_code).strip()
            if not stock_code:
                continue
            stock_metadata = stock_metadata_by_code.get(stock_code.upper()) or {}
            stock_market_type = normalize_market_type(
                stock_metadata.get("market_type")
                or stock_metadata.get("marketType")
                or shared_config.get("market_type")
            ) or infer_market_type(stock_code)
            stock_code = normalize_stock_code(
                stock_code,
                stock_market_type,
                stock_metadata.get("exchange_market") or stock_metadata.get("market"),
            )
            stock_name = str(
                stock_metadata.get("stock_name") or stock_metadata.get("name") or ""
            ).strip()
            if stock_metadata:
                save_stock_metadata({
                    **stock_metadata,
                    "stock_code": stock_code,
                    "stock_name": stock_name,
                    "market_type": stock_market_type,
                    "source": stock_metadata.get("source") or "task_config",
                })

            for index, parameter_combo in enumerate(parameter_combinations):
                matched_sheets = [sheet_dict[key][index] for key in sheet_dict.keys()]
                for sheet in matched_sheets:
                    if not isinstance(sheet, dict):
                        continue

                    spreadsheet_id = str(sheet.get("spreadsheet_id") or "").strip()
                    sheet_name = str(sheet.get("sheet_name") or "").strip()
                    sheet_title = str(sheet.get("title") or "").strip()
                    sort_n = sheet.get("sort_n")
                    year_n = str(sheet.get("year_n") or "").strip()
                    if not spreadsheet_id:
                        continue

                    child_parameters = self._materialize_c31_parameter_combo(
                        parameter_combo
                    )
                    task_name = f"{base_name}-{year_n}-{sort_n}"
                    end_date = shared_config.get("end_date")
                    if not end_date:
                        end_dt = datetime.now() - timedelta(days=1)
                        end_date = end_dt.strftime("%Y-%m-%d")

                    child_config = dict(shared_config)
                    child_config.update(
                        {
                            "spreadsheet_id": spreadsheet_id,
                            "sheet_name": sheet_name,
                            "title": sheet_title or None,
                            "stock_code": stock_code,
                            "stock_name": stock_name,
                            "market_type": stock_market_type,
                            "kline_adjustment": shared_config.get("kline_adjustment", "forward"),
                            "end_date": end_date,
                            "year_n": year_n,
                            "parameters": child_parameters,
                        }
                    )

                    combo_count = reduce(
                        operator.mul,
                        [len(parameter_row) for parameter_row in child_parameters],
                        1,
                    )
                    child_description = description or f"批量执行 {combo_count} 个参数组合"
                    try:
                        task_id = self.create_task(
                            task_name,
                            child_description,
                            child_task_type,
                            child_config,
                            created_by_user_id=created_by_user_id,
                        )
                    except Exception:
                        # 远端没有跨任务事务：创建中断时补偿删除已经成功创建的子任务。
                        for created_task_id in reversed(created_task_ids):
                            try:
                                self.delete_task(created_task_id)
                            except Exception as cleanup_exc:
                                logger.error("C31 补偿删除子任务失败: task_id=%s err=%s", created_task_id, cleanup_exc)
                        raise
                    created_task_ids.append(task_id)

                    started = self.start_task(task_id)
                    if started:
                        started_task_ids.append(task_id)
                    else:
                        failed_to_start.append(
                            {
                                "task_id": task_id,
                                "task_name": task_name,
                                "error": self.get_start_error(task_id),
                            }
                        )

                    child_summaries.append(
                        {
                            "task_id": task_id,
                            "task_name": task_name,
                            "spreadsheet_id": spreadsheet_id,
                            "sheet_name": sheet_name,
                            "stock_code": stock_code,
                            "parameters": child_parameters,
                            "started": started,
                        }
                    )
                    time.sleep(0.5)

        if not created_task_ids:
            raise ValueError("没有生成任何子任务，请检查 sheets / stock_codes / parameters 配置")

        status = "success" if started_task_ids else "error"
        message = (
            f"C31 已拆分创建 {len(created_task_ids)} 个 C3 任务，"
            f"成功启动 {len(started_task_ids)} 个，未启动 {len(failed_to_start)} 个"
        )
        http_status = 200 if started_task_ids else 400
        return {
            "status": status,
            "message": message,
            "task_id": (
                started_task_ids[0] if started_task_ids else created_task_ids[0]
            ),
            "task_ids": created_task_ids,
            "started_task_ids": started_task_ids,
            "failed_to_start": failed_to_start,
            "total_created": len(created_task_ids),
            "total_started": len(started_task_ids),
            "children": child_summaries,
        }, http_status

    def _materialize_c31_parameter_combo(self, parameter_combo):
        """将单次组合整理成单个 C3 任务所需的二维数组。"""
        rows = []
        for item in parameter_combo:
            if not isinstance(item, list) or not item:
                raise ValueError("参数组合项必须是非空一维数组")
            rows.append(item)
        return rows

    def _normalize_c31_parameter_groups(self, parameter_groups):
        """将 C31 批量参数转换为可拆分子任务的二维分组。"""
        normalized_groups = []
        for index, group in enumerate(parameter_groups, start=1):
            if not isinstance(group, list) or not group:
                raise ValueError(f"参数组 {index} 必须是非空数组")

            if all(isinstance(group_item, list) for group_item in group):
                candidate_group = []
                for group_item in group:
                    if not isinstance(group_item, list) or not group_item:
                        raise ValueError(
                            f"参数组 {index} 的二维子项必须是非空一维数组"
                        )
                    candidate_group.append(group_item)
                normalized_groups.append(candidate_group)
            else:
                normalized_groups.append([group])
        return normalized_groups

    def _is_count_compatible(self, left_count: int, right_count: int) -> bool:
        """判断两个参数组长度是否满足 C31 批量拆分规则。"""
        if left_count <= 0 or right_count <= 0:
            return False
        return (
            left_count == right_count
            or left_count % right_count == 0
            or right_count % left_count == 0
        )

    @transaction_required
    def update_task_config(
        self,
        task_id: str,
        new_config: dict[str, Any],
        update_name: str = None,
        update_description: str = None,
        update_status: str = None,
    ) -> dict[str, Any]:
        """更新任务配置。"""
        try:
            task = _task_repository.get(task_id)
            if not task:
                return {"status": "error", "message": "任务不存在"}

            if task.get("status") == "running":
                return {
                    "status": "error",
                    "message": "正在运行的任务无法直接修改，请先停止任务",
                }

            if not isinstance(new_config, dict):
                return {"status": "error", "message": "配置格式不正确"}

            allowed_statuses = {
                option["value"] for option in TaskStatus.editable_choices()
            }
            next_status = (update_status or "").strip()
            if next_status:
                if next_status == TaskStatus.RUNNING.value:
                    return {"status": "error", "message": "不能手动将任务状态改为运行中，请使用重启任务"}
                if next_status not in allowed_statuses:
                    return {"status": "error", "message": f"不支持的任务状态: {next_status}"}

            task_type = task.get("task_type")
            new_config = self._normalize_task_config_for_type(task_type, new_config)
            if task_type == "backtest_training":
                self.validate_backtest_training_sheet(new_config)
            old_config = task.get("config") or {}
            old_google_sheet_id = (
                old_config.get("google_sheet_id") if isinstance(old_config, dict) else None
            )
            new_google_sheet_id = new_config.get("google_sheet_id")

            if old_google_sheet_id != new_google_sheet_id:
                if old_google_sheet_id:
                    self.release_google_sheet_occupancy(task_id)
                if new_google_sheet_id:
                    self.ensure_google_sheet_occupancy(task_id, new_config)

            updated = dict(task)
            updated["config"] = new_config
            if update_name:
                updated["name"] = update_name
            if update_description is not None:
                updated["description"] = update_description
            old_status = task.get("status")
            if next_status and next_status != old_status:
                updated["status"] = next_status
                if next_status == TaskStatus.PENDING.value:
                    updated.update(start_time=None, end_time=None, error_message=None)
                elif next_status in {TaskStatus.COMPLETED.value, TaskStatus.CANCELLED.value}:
                    updated["end_time"] = updated.get("end_time") or datetime.now()
                    if next_status == TaskStatus.COMPLETED.value:
                        updated["error_message"] = None
            task = _task_repository.save(updated)

            task_logger = get_task_logger(task_id, f"{__name__}.update_config")
            if next_status and next_status != old_status:
                status_message = f"任务状态已由 {old_status} 修改为 {next_status}"
                task_logger.info(status_message)
                self.add_task_log(task_id, "warning", status_message)
            task_logger.info("任务配置已更新")
            self.add_task_log(task_id, "info", "任务配置已更新")
            logger.info("任务配置更新成功: %s", task_id)
            return {
                "status": "success",
                "message": "任务更新成功",
                "task": task,
            }
        except Exception as exc:
            # 远端任务更新失败不依赖本地事务回滚；保留异常供调用方处理。
            logger.error("更新任务配置失败: %s, 错误: %s", task_id, exc)
            return {"status": "error", "message": f"更新任务配置失败: {exc}"}

    def create_restart_task(self, original_task_id: str) -> str:
        """基于原任务创建新的重启任务。"""
        try:
            original_task = _task_repository.get(original_task_id)
            if not original_task:
                raise ValueError("原任务不存在")

            new_task_id = str(uuid.uuid4())
            original_config = (
                original_task.get("config") or {}
            )
            original_config = self._normalize_task_config_for_type(
                original_task.get("task_type"),
                original_config,
            )

            _task_repository.save({
                "id": new_task_id,
                "name": f"{original_task.get('name')} (重启)",
                "description": f"{original_task.get('description') or ''}基于任务 {original_task_id} 重启",
                "task_type": original_task.get("task_type"),
                "config": original_config,
                "status": "pending",
                "created_by_user_id": original_task.get("created_by_user_id"),
            })

            if isinstance(original_config, dict) and original_task.get("task_type") not in ("backtest_training", "backtest_multi_product"):
                self.ensure_google_sheet_occupancy(new_task_id, original_config)

            logger.info("创建重启任务: %s (基于 %s)", new_task_id, original_task_id)
            return new_task_id
        except Exception as exc:
            logger.error("创建重启任务失败: %s", exc)
            raise

"""任务资源占用管理。"""

from __future__ import annotations

from typing import Any

from app.models import GoogleSheetTableType
from app.exceptions import ValidationError
from app.repositories import google_sheet_repository, task_repository
from app.services.google_sheet_registry_service import (
    get_google_sheet_registry_service,
)
from app.services.google_sheet_token_service import get_google_sheet_token_service
from app.utils.logger import get_logger

logger = get_logger(__name__)

C_SERIES_TABLE_TYPES = frozenset(
    {
        GoogleSheetTableType.C3.value,
        GoogleSheetTableType.C4.value,
        GoogleSheetTableType.C5.value,
        GoogleSheetTableType.C7.value,
        GoogleSheetTableType.C1_1.value,
    }
)


class TaskOccupancyMixin:
    """统一管理 token 与 Google Sheet 占用。"""

    def _iter_sheet_references(self, config):
        """遍历配置中的全部 Sheet 引用（顶层 / sheets[] / products[]）。"""
        if not isinstance(config, dict):
            return
        yield config

        sheets = config.get("sheets")
        if isinstance(sheets, list):
            for item in sheets:
                if isinstance(item, dict):
                    yield item

        products = config.get("products")
        if isinstance(products, list):
            for product in products:
                if not isinstance(product, dict):
                    continue
                yield product
                yield product.get("sheet")

    def _collect_sheet_registry_rows(self, sheet_config) -> list[dict[str, Any]]:
        """按引用收集注册表记录：显式 id + 同一 spreadsheet 的全部类型记录。"""
        if not isinstance(sheet_config, dict):
            return []

        rows: dict[int, dict[str, Any]] = {}
        sheet_id = sheet_config.get("google_sheet_id")
        if sheet_id:
            try:
                row = google_sheet_repository.get(int(sheet_id))
            except (TypeError, ValueError):
                row = None
            if row:
                rows[row["id"]] = row

        spreadsheet_id = str(sheet_config.get("spreadsheet_id") or "").strip()
        if spreadsheet_id:
            for row in google_sheet_repository.list_by_spreadsheet_id(spreadsheet_id):
                rows[row["id"]] = row
        return list(rows.values())

    def _collect_google_sheet_ids(
        self,
        config: dict[str, Any] | None,
        allowed_table_types: frozenset[str] | None = None,
    ) -> list[int]:
        """从任务配置中收集 registry 内的 Google Sheet ID。

        allowed_table_types 为 None 时保持原语义（显式 id 优先，否则第一条）；
        指定时按类型筛选所有匹配记录（C 系占用只落 C 系模型）。
        """
        if not isinstance(config, dict):
            return []

        sheet_ids: list[int] = []
        seen_refs: set[tuple[str, str]] = set()

        for sheet_config in self._iter_sheet_references(config):
            ref_key = (
                str(sheet_config.get("google_sheet_id") or ""),
                str(sheet_config.get("spreadsheet_id") or ""),
            )
            if ref_key == ("", "") or ref_key in seen_refs:
                continue
            seen_refs.add(ref_key)

            if allowed_table_types is None:
                sheet_id = sheet_config.get("google_sheet_id")
                if sheet_id:
                    sheet_ids.append(int(sheet_id))
                    continue
                spreadsheet_id = sheet_config.get("spreadsheet_id")
                if spreadsheet_id:
                    matched_sheet = google_sheet_repository.get_by_spreadsheet_id(spreadsheet_id)
                    if matched_sheet:
                        sheet_ids.append(int(matched_sheet["id"]))
                continue

            for row in self._collect_sheet_registry_rows(sheet_config):
                if row["table_type"] in allowed_table_types:
                    sheet_ids.append(int(row["id"]))

        return sorted(set(sheet_ids))

    def validate_c_series_sheet_models(
        self,
        config: dict[str, Any] | None,
        task_id: str | None = None,
    ) -> None:
        """C 系任务必须使用 C 系模型，且同一 spreadsheet 的任一条记录不得被其他任务占用。"""
        seen_refs: set[tuple[str, str]] = set()

        for sheet_config in self._iter_sheet_references(config):
            ref_key = (
                str(sheet_config.get("google_sheet_id") or ""),
                str(sheet_config.get("spreadsheet_id") or ""),
            )
            if ref_key == ("", "") or ref_key in seen_refs:
                continue
            seen_refs.add(ref_key)

            rows = self._collect_sheet_registry_rows(sheet_config)
            c_series_rows = [
                row for row in rows if row["table_type"] in C_SERIES_TABLE_TYPES
            ]
            if not c_series_rows:
                raise ValidationError(
                    "所选 Google Sheet 不是 C 系模型（未注册或仅注册为回测模型）"
                )
            if not any(row["is_active"] for row in c_series_rows):
                raise ValidationError("所选 Google Sheet 未启用")
            if any(
                row["is_in_use"]
                and (task_id is None or row.get("current_task_id") != task_id)
                for row in rows
            ):
                raise ValidationError("所选 Google Sheet 正在被其他任务使用，无法启动")

    def release_task_token_occupancy(self, task_id: str) -> None:
        """释放任务对应的 token 运行占用。"""
        token_id = self.task_token_occupancy.pop(task_id, None)
        if not token_id:
            return

        try:
            get_google_sheet_token_service().release_usage(token_id)
        except Exception as exc:
            logger.warning(
                "释放 token 占用失败: task_id=%s, token_id=%s, err=%s",
                task_id,
                token_id,
                exc,
            )

    def ensure_google_sheet_occupancy(
        self,
        task_id: str,
        config: dict[str, Any] | None,
        allowed_table_types: frozenset[str] | None = None,
    ) -> None:
        """根据任务配置建立 Google Sheet 占用。"""
        for sheet_id in self._collect_google_sheet_ids(
            config, allowed_table_types=allowed_table_types
        ):
            get_google_sheet_registry_service().acquire_for_task(sheet_id, task_id)

    def validate_google_sheet_available_for_task(
        self,
        config: dict[str, Any] | None,
        task_id: str | None = None,
        allow_in_use: bool = False,
    ) -> None:
        """在创建或启动任务前校验 Google Sheet 是否可占用。"""
        for sheet_id in self._collect_google_sheet_ids(config):
            sheet = google_sheet_repository.get(sheet_id)
            if not sheet:
                raise ValidationError("所选 Google Sheet 不存在")
            if not sheet["is_active"]:
                raise ValidationError("所选 Google Sheet 未启用")
            if (
                not allow_in_use
                and
                sheet["is_in_use"]
                and sheet["current_task_id"]
                and sheet["current_task_id"] != task_id
            ):
                raise ValidationError("该 Google Sheet 已被其他任务使用")

    def validate_backtest_training_sheet(self, config: dict[str, Any] | None) -> None:
        """Verify that a single-product backtest uses its dedicated sheet type."""
        sheets = config.get("sheets") if isinstance(config, dict) else None
        sheet_config = sheets[0] if isinstance(sheets, list) and sheets and isinstance(sheets[0], dict) else None
        if not isinstance(sheet_config, dict):
            raise ValidationError("单品回测缺少 Google Sheet 配置")

        google_sheet_id = sheet_config.get("google_sheet_id")
        spreadsheet_id = str(sheet_config.get("spreadsheet_id") or "").strip()
        if not google_sheet_id:
            if not spreadsheet_id:
                raise ValidationError("单品回测缺少 Google Sheet ID")
            return

        try:
            sheet = google_sheet_repository.get(int(google_sheet_id))
        except (TypeError, ValueError):
            sheet = None

        if not sheet:
            raise ValidationError("所选单品回测 Sheet 不存在")
        if not sheet["is_active"]:
            raise ValidationError("所选单品回测 Sheet 未启用")
        if sheet["table_type"] != GoogleSheetTableType.BACKTEST_TRAINING.value:
            raise ValidationError("所选 Sheet 不是单品回测模板")
        if not spreadsheet_id or sheet["spreadsheet_id"] != spreadsheet_id:
            raise ValidationError("所选单品回测 Sheet 信息不一致")

    def release_google_sheet_occupancy(self, task_id: str) -> None:
        """释放任务关联的 Google Sheet 占用。"""
        try:
            released = get_google_sheet_registry_service().release_for_task(task_id)
            if released:
                return

            task = task_repository.get(task_id)
            if not task:
                return

            config_data = task.get("config") or {}
            if isinstance(config_data, dict) and config_data.get("google_sheet_id"):
                logger.warning(
                    "Google Sheet 占用释放跳过: task_id=%s, google_sheet_id=%s",
                    task_id,
                    config_data.get("google_sheet_id"),
                )
        except Exception as exc:
            logger.warning("释放 Google Sheet 占用失败: task_id=%s, err=%s", task_id, exc)

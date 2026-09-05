"""任务资源占用管理。"""

from __future__ import annotations

from typing import Any

from app.models import GoogleSheetTableType
from app.repositories import google_sheet_repository, task_repository
from app.services.google_sheet_registry_service import (
    get_google_sheet_registry_service,
)
from app.services.google_sheet_token_service import get_google_sheet_token_service
from app.utils.logger import get_logger

logger = get_logger(__name__)


class TaskOccupancyMixin:
    """统一管理 token 与 Google Sheet 占用。"""

    def _collect_google_sheet_ids(
        self,
        config: dict[str, Any] | None,
    ) -> list[int]:
        """从任务配置中收集 registry 内的 Google Sheet ID。"""
        if not isinstance(config, dict):
            return []

        sheet_ids: list[int] = []

        def add_sheet_reference(sheet_config: dict[str, Any] | None) -> None:
            if not isinstance(sheet_config, dict):
                return

            sheet_id = sheet_config.get("google_sheet_id")
            if sheet_id:
                sheet_ids.append(int(sheet_id))
                return

            spreadsheet_id = sheet_config.get("spreadsheet_id")
            if spreadsheet_id:
                matched_sheet = google_sheet_repository.get_by_spreadsheet_id(spreadsheet_id)
                if matched_sheet:
                    sheet_ids.append(int(matched_sheet["id"]))

        add_sheet_reference(config)
        add_sheet_reference(config.get("sheet"))

        sheets = config.get("sheets")
        if isinstance(sheets, list):
            for item in sheets:
                add_sheet_reference(item)

        products = config.get("products")
        if isinstance(products, list):
            for product in products:
                if not isinstance(product, dict):
                    continue
                add_sheet_reference(product)
                add_sheet_reference(product.get("sheet"))

        return sorted(set(sheet_ids))

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
    ) -> None:
        """根据任务配置建立 Google Sheet 占用。"""
        for sheet_id in self._collect_google_sheet_ids(config):
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
                raise ValueError("所选 Google Sheet 不存在")
            if not sheet["is_active"]:
                raise ValueError("所选 Google Sheet 未启用")
            if (
                not allow_in_use
                and
                sheet["is_in_use"]
                and sheet["current_task_id"]
                and sheet["current_task_id"] != task_id
            ):
                raise ValueError("该 Google Sheet 已被其他任务使用")

    def validate_backtest_training_sheet(self, config: dict[str, Any] | None) -> None:
        """Verify that a single-product backtest uses its dedicated sheet type."""
        sheet_config = config.get("sheet") if isinstance(config, dict) else None
        if not isinstance(sheet_config, dict):
            raise ValueError("单品回测缺少 Google Sheet 配置")

        google_sheet_id = sheet_config.get("google_sheet_id")
        spreadsheet_id = str(sheet_config.get("spreadsheet_id") or "").strip()
        if not google_sheet_id:
            if not spreadsheet_id:
                raise ValueError("单品回测缺少 Google Sheet ID")
            return

        try:
            sheet = google_sheet_repository.get(int(google_sheet_id))
        except (TypeError, ValueError):
            sheet = None

        if not sheet:
            raise ValueError("所选单品回测 Sheet 不存在")
        if not sheet["is_active"]:
            raise ValueError("所选单品回测 Sheet 未启用")
        if sheet["table_type"] != GoogleSheetTableType.BACKTEST_TRAINING.value:
            raise ValueError("所选 Sheet 不是单品回测模板")
        if not spreadsheet_id or sheet["spreadsheet_id"] != spreadsheet_id:
            raise ValueError("所选单品回测 Sheet 信息不一致")

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

    # 兼容旧私有命名。
    def _release_task_token_occupancy(self, task_id: str) -> None:
        self.release_task_token_occupancy(task_id)

    def _ensure_google_sheet_occupancy(
        self,
        task_id: str,
        config: dict[str, Any] | None,
    ) -> None:
        self.ensure_google_sheet_occupancy(task_id, config)

    def _release_google_sheet_occupancy(self, task_id: str) -> None:
        self.release_google_sheet_occupancy(task_id)

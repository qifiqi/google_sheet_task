"""任务资源占用管理。"""

from __future__ import annotations

import json
from typing import Any

from app.extensions import db
from app.models import GoogleSheet, Task
from app.services.google_sheet_registry_service import (
    get_google_sheet_registry_service,
)
from app.services.google_sheet_token_service import get_google_sheet_token_service
from app.utils.logger import get_logger

logger = get_logger(__name__)


class TaskOccupancyMixin:
    """统一管理 token 与 Google Sheet 占用。"""

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
        if not isinstance(config, dict):
            return

        sheet_ids: list[int] = []
        direct_sheet_id = config.get("google_sheet_id")
        if direct_sheet_id:
            sheet_ids.append(int(direct_sheet_id))

        spreadsheet_id = config.get("spreadsheet_id")
        if spreadsheet_id:
            matched_sheet = GoogleSheet.query.filter_by(
                spreadsheet_id=str(spreadsheet_id)
            ).first()
            if matched_sheet:
                sheet_ids.append(int(matched_sheet.id))

        sheets = config.get("sheets")
        if isinstance(sheets, list):
            for item in sheets:
                if not isinstance(item, dict):
                    continue
                item_sheet_id = item.get("google_sheet_id")
                if item_sheet_id:
                    sheet_ids.append(int(item_sheet_id))
                    continue
                item_spreadsheet_id = item.get("spreadsheet_id")
                if item_spreadsheet_id:
                    matched_sheet = GoogleSheet.query.filter_by(
                        spreadsheet_id=str(item_spreadsheet_id)
                    ).first()
                    if matched_sheet:
                        sheet_ids.append(int(matched_sheet.id))

        for sheet_id in sorted(set(sheet_ids)):
            get_google_sheet_registry_service().acquire_for_task(sheet_id, task_id)

    def release_google_sheet_occupancy(self, task_id: str) -> None:
        """释放任务关联的 Google Sheet 占用。"""
        try:
            released = get_google_sheet_registry_service().release_for_task(task_id)
            if released:
                return

            task = db.session.get(Task, task_id)
            if not task:
                return

            config_data = (
                json.loads(task.config)
                if isinstance(task.config, str)
                else (task.config or {})
            )
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

"""任务资源占用管理。"""

from __future__ import annotations

from typing import Any

from app.domain_constants import GoogleSheetTableType
from app.repositories.google_sheet_repository import GoogleSheetRepository
from app.services.google_sheet_token_service import get_google_sheet_token_service
from app.utils.logger import get_logger

logger = get_logger(__name__)
_google_sheet_repository = GoogleSheetRepository()


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
            """从单个 Sheet 配置提取已注册的数值主键。"""
            if not isinstance(sheet_config, dict):
                return

            sheet_id = sheet_config.get("google_sheet_id")
            if sheet_id:
                sheet_ids.append(int(sheet_id))
                return

            # TODO: spreadsheet_id 反查需要远端 Query；仅接受配置中的已知 registry ID。

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
        """保留兼容入口；Sheet 注册表字段不再作为运行占用事实来源。"""
        # 回测互斥由 BacktestSheetRunLock 负责；非回测目前允许并行。
        return None

    def validate_google_sheet_available_for_task(
        self,
        config: dict[str, Any] | None,
        task_id: str | None = None,
        allow_in_use: bool = False,
    ) -> None:
        """在创建或启动任务前校验 Google Sheet 是否可占用。"""
        for sheet_id in self._collect_google_sheet_ids(config):
            sheet = _google_sheet_repository.get(sheet_id)
            if not sheet:
                raise ValueError("所选 Google Sheet 不存在")
            if not sheet.get("is_active"):
                raise ValueError("所选 Google Sheet 未启用")
            # is_in_use/current_task_id 是派生展示字段，不能用于互斥判定。

    def validate_backtest_training_sheet(self, config: dict[str, Any] | None) -> None:
        """校验单品回测使用已启用且类型匹配的专用 Sheet。"""
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
            sheet = _google_sheet_repository.get(int(google_sheet_id))
        except (TypeError, ValueError):
            sheet = None

        if not sheet:
            raise ValueError("所选单品回测 Sheet 不存在")
        if not sheet.get("is_active"):
            raise ValueError("所选单品回测 Sheet 未启用")
        if sheet.get("table_type") != GoogleSheetTableType.BACKTEST_TRAINING.value:
            raise ValueError("所选 Sheet 不是单品回测模板")
        if not spreadsheet_id or sheet.get("spreadsheet_id") != spreadsheet_id:
            raise ValueError("所选单品回测 Sheet 信息不一致")

    def release_google_sheet_occupancy(self, task_id: str) -> None:
        """保留兼容入口；实际互斥锁由回测锁在任务收尾阶段释放。"""
        return None

    # 兼容旧私有命名。
    def _release_task_token_occupancy(self, task_id: str) -> None:
        """兼容旧私有入口，转发到统一 Token 占用释放方法。"""
        self.release_task_token_occupancy(task_id)

    def _ensure_google_sheet_occupancy(
        self,
        task_id: str,
        config: dict[str, Any] | None,
    ) -> None:
        """兼容旧私有入口，转发到当前 Sheet 占用检查方法。"""
        self.ensure_google_sheet_occupancy(task_id, config)

    def _release_google_sheet_occupancy(self, task_id: str) -> None:
        """兼容旧私有入口，转发到当前 Sheet 占用释放方法。"""
        self.release_google_sheet_occupancy(task_id)

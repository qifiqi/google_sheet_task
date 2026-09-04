from __future__ import annotations

from typing import Optional

from app.models import GoogleSheetTableType, google_sheet_registry_scope
from app.repositories import google_sheet_repository


def _find_duplicate_sheet(spreadsheet_id: str, table_type: str, exclude_id: int | None = None):
    return google_sheet_repository.find_duplicate(
        spreadsheet_id,
        google_sheet_registry_scope(table_type),
        exclude_id=exclude_id,
    )


class GoogleSheetRegistryService:
    def list_sheets(self, include_inactive: bool = False, only_available: bool = False, task_id: str | None = None,
                    table_type: str | None = None):
        normalized_table_type = GoogleSheetTableType.normalize(table_type)
        return google_sheet_repository.list_filtered(
            include_inactive=include_inactive,
            only_available=only_available,
            task_id=task_id,
            table_type=normalized_table_type,
        )

    def get_sheet(self, sheet_id: int) -> Optional[dict]:
        return google_sheet_repository.get(int(sheet_id))

    def create_sheet(self, spreadsheet_id: str, name: str | None = None, remark: str | None = None,
                     is_active: bool = True, table_type: str | None = None):
        spreadsheet_id = (spreadsheet_id or '').strip()
        if not spreadsheet_id:
            raise ValueError("spreadsheet_id 不能为空")

        normalized_table_type = GoogleSheetTableType.normalize(table_type, GoogleSheetTableType.C3.value)
        if not normalized_table_type:
            raise ValueError("table_type 无效")

        existing = _find_duplicate_sheet(spreadsheet_id, normalized_table_type)
        if existing:
            raise ValueError("该 spreadsheet_id 已存在于同类表类型中")

        return google_sheet_repository.create({
            'spreadsheet_id': spreadsheet_id,
            'name': (name or spreadsheet_id).strip(),
            'table_type': normalized_table_type,
            'remark': (remark or '').strip() or None,
            'is_active': bool(is_active),
        })

    def update_sheet(self, sheet_id: int, **payload):
        sheet = google_sheet_repository.get(int(sheet_id))
        if not sheet:
            raise ValueError("Google Sheet 不存在")

        spreadsheet_id = sheet["spreadsheet_id"]
        if 'spreadsheet_id' in payload:
            spreadsheet_id = (payload.get('spreadsheet_id') or '').strip()
            if not spreadsheet_id:
                raise ValueError("spreadsheet_id 不能为空")

        table_type = sheet["table_type"]
        if 'table_type' in payload:
            table_type = GoogleSheetTableType.normalize(payload.get('table_type'))
            if not table_type:
                raise ValueError("table_type 无效")

        existing = _find_duplicate_sheet(spreadsheet_id, table_type, exclude_id=sheet["id"])
        if existing:
            raise ValueError("该 spreadsheet_id 已存在于同类表类型中")

        fields = {
            "spreadsheet_id": spreadsheet_id,
            "table_type": table_type,
        }
        if 'name' in payload:
            fields["name"] = (payload.get('name') or '').strip() or spreadsheet_id
        if 'remark' in payload:
            fields["remark"] = (payload.get('remark') or '').strip() or None
        if 'is_active' in payload:
            fields["is_active"] = bool(payload.get('is_active'))

        return google_sheet_repository.update(int(sheet_id), fields)

    def delete_sheet(self, sheet_id: int):
        sheet = google_sheet_repository.get(int(sheet_id))
        if not sheet:
            raise ValueError("Google Sheet 不存在")
        if sheet["is_in_use"]:
            raise ValueError("该 Google Sheet 正在被任务使用，无法删除")

        google_sheet_repository.delete(int(sheet_id))

    def acquire_for_task(self, sheet_id: int, task_id: str):
        sheet = google_sheet_repository.get_entity(int(sheet_id))
        if not sheet:
            raise ValueError("所选 Google Sheet 不存在")
        if not sheet.is_active:
            raise ValueError("所选 Google Sheet 未启用")
        if sheet.current_task_id == task_id and sheet.is_in_use:
            return sheet.to_dict()
        if sheet.is_in_use and sheet.current_task_id and sheet.current_task_id != task_id:
            raise ValueError("该 Google Sheet 已被其他任务使用")

        occupied = google_sheet_repository.occupy(int(sheet_id), task_id)
        if occupied is None:
            raise ValueError("Google Sheet 占用失败，请重试")
        return occupied

    def release_for_task(self, task_id: str):
        if not task_id:
            return False
        return google_sheet_repository.release_by_task(task_id) > 0


google_sheet_registry_service = GoogleSheetRegistryService()


def get_google_sheet_registry_service() -> GoogleSheetRegistryService:
    return google_sheet_registry_service

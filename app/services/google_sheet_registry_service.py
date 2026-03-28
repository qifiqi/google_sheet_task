from __future__ import annotations

from typing import Optional

from sqlalchemy import or_

from app.extensions import db
from app.models import GoogleSheet, GoogleSheetTableType


class GoogleSheetRegistryService:
    def list_sheets(self, include_inactive: bool = False, only_available: bool = False, task_id: str | None = None,
                    table_type: str | None = None):
        query = GoogleSheet.query
        normalized_table_type = GoogleSheetTableType.normalize(table_type)
        if normalized_table_type:
            query = query.filter_by(table_type=normalized_table_type)
        if not include_inactive:
            query = query.filter_by(is_active=True)
        if only_available:
            query = query.filter(
                or_(
                    GoogleSheet.is_in_use.is_(False),
                    GoogleSheet.current_task_id == task_id if task_id else False,
                )
            )
        return [sheet.to_dict() for sheet in query.order_by(GoogleSheet.name.asc(), GoogleSheet.id.asc()).all()]

    def get_sheet(self, sheet_id: int) -> Optional[dict]:
        sheet = GoogleSheet.query.get(int(sheet_id))
        return sheet.to_dict() if sheet else None

    def create_sheet(self, spreadsheet_id: str, name: str | None = None, remark: str | None = None,
                     is_active: bool = True, table_type: str | None = None):
        spreadsheet_id = (spreadsheet_id or '').strip()
        if not spreadsheet_id:
            raise ValueError("spreadsheet_id 不能为空")

        normalized_table_type = GoogleSheetTableType.normalize(table_type, GoogleSheetTableType.C3.value)
        if not normalized_table_type:
            raise ValueError("table_type 无效")

        existing = GoogleSheet.query.filter_by(spreadsheet_id=spreadsheet_id).first()
        if existing:
            raise ValueError("该 spreadsheet_id 已存在")

        sheet = GoogleSheet(
            spreadsheet_id=spreadsheet_id,
            name=(name or spreadsheet_id).strip(),
            table_type=normalized_table_type,
            remark=(remark or '').strip() or None,
            is_active=bool(is_active),
        )
        db.session.add(sheet)
        db.session.commit()
        return sheet.to_dict()

    def update_sheet(self, sheet_id: int, **payload):
        sheet = GoogleSheet.query.get(int(sheet_id))
        if not sheet:
            raise ValueError("Google Sheet 不存在")

        if 'spreadsheet_id' in payload:
            spreadsheet_id = (payload.get('spreadsheet_id') or '').strip()
            if not spreadsheet_id:
                raise ValueError("spreadsheet_id 不能为空")
            existing = GoogleSheet.query.filter(
                GoogleSheet.spreadsheet_id == spreadsheet_id,
                GoogleSheet.id != sheet.id
            ).first()
            if existing:
                raise ValueError("该 spreadsheet_id 已存在")
            sheet.spreadsheet_id = spreadsheet_id

        if 'name' in payload:
            sheet.name = (payload.get('name') or '').strip() or sheet.spreadsheet_id
        if 'table_type' in payload:
            normalized_table_type = GoogleSheetTableType.normalize(payload.get('table_type'))
            if not normalized_table_type:
                raise ValueError("table_type 无效")
            sheet.table_type = normalized_table_type
        if 'remark' in payload:
            sheet.remark = (payload.get('remark') or '').strip() or None
        if 'is_active' in payload:
            sheet.is_active = bool(payload.get('is_active'))

        db.session.commit()
        return sheet.to_dict()

    def delete_sheet(self, sheet_id: int):
        sheet = GoogleSheet.query.get(int(sheet_id))
        if not sheet:
            raise ValueError("Google Sheet 不存在")
        if sheet.is_in_use:
            raise ValueError("该 Google Sheet 正在被任务使用，无法删除")

        db.session.delete(sheet)
        db.session.commit()

    def acquire_for_task(self, sheet_id: int, task_id: str):
        sheet = GoogleSheet.query.get(int(sheet_id))
        if not sheet:
            raise ValueError("所选 Google Sheet 不存在")
        if not sheet.is_active:
            raise ValueError("所选 Google Sheet 未启用")
        if sheet.current_task_id == task_id:
            if not sheet.is_in_use:
                sheet.is_in_use = True
                db.session.commit()
            return sheet.to_dict()
        if sheet.is_in_use and sheet.current_task_id and sheet.current_task_id != task_id:
            raise ValueError("该 Google Sheet 已被其他任务使用")

        sheet.is_in_use = True
        sheet.current_task_id = task_id
        db.session.commit()
        db.session.refresh(sheet)
        if not sheet.is_in_use or sheet.current_task_id != task_id:
            raise ValueError("Google Sheet 占用失败，请重试")
        return sheet.to_dict()

    def release_for_task(self, task_id: str):
        if not task_id:
            return False
        updated = GoogleSheet.query.filter_by(current_task_id=task_id).update(
            {
                'is_in_use': False,
                'current_task_id': None,
            },
            synchronize_session=False
        )
        db.session.commit()
        return updated > 0


google_sheet_registry_service = GoogleSheetRegistryService()


def get_google_sheet_registry_service() -> GoogleSheetRegistryService:
    return google_sheet_registry_service

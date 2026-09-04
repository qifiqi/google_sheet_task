"""GoogleSheet 仓储（契约见 docs/design/data-layer-refactor/02 §2.8）。

registry scope 过滤与占用查询方法按 google_sheet_registry_service、
task/occupancy.py 调用点定形后补入（B2/B3）。
"""
from app.extensions import db
from app.exceptions import NotFoundError
from app.models import GoogleSheet
from app.repositories.base import BaseRepository


class GoogleSheetRepository(BaseRepository):
    model = GoogleSheet

    # ---- 读 ----

    def list_all(self, table_type=None, scope=None):
        query = GoogleSheet.query
        if table_type:
            query = query.filter_by(table_type=table_type)
        if scope:
            query = query.filter_by(registry_scope=scope)
        return [
            row.to_dict()
            for row in query.order_by(GoogleSheet.id.asc()).all()
        ]

    def list_filtered(self, include_inactive=False, only_available=False, task_id=None, table_type=None):
        """管理端/选择器列表（google_sheet_registry_service.list_sheets 语义）。"""
        from sqlalchemy import or_

        query = GoogleSheet.query
        if table_type:
            query = query.filter_by(table_type=table_type)
        if not include_inactive:
            query = query.filter_by(is_active=True)
        if only_available:
            query = query.filter(
                or_(
                    GoogleSheet.is_in_use.is_(False),
                    GoogleSheet.current_task_id == task_id if task_id else False,
                )
            )
        return [
            row.to_dict()
            for row in query.order_by(GoogleSheet.name.asc(), GoogleSheet.id.asc()).all()
        ]

    def find_duplicate(self, spreadsheet_id, scope_value, exclude_id=None):
        """同 scope 下 spreadsheet_id 查重；返回 dict 或 None。"""
        query = GoogleSheet.query.filter_by(
            spreadsheet_id=spreadsheet_id,
            registry_scope=scope_value,
        )
        if exclude_id is not None:
            query = query.filter(GoogleSheet.id != exclude_id)
        row = query.first()
        return row.to_dict() if row else None

    def occupy(self, sheet_id, task_id, commit=True):
        """任务占用 Sheet：同任务幂等；成功返回占用后的 dict，占用校验失败返回 None。

        对齐原 acquire 语义：提交后 refresh 复核，防止过期状态。
        """
        sheet = db.session.get(GoogleSheet, sheet_id)
        if sheet is None:
            return None
        if sheet.current_task_id == task_id:
            if not sheet.is_in_use:
                sheet.is_in_use = True
                if commit:
                    self._commit()
            return sheet.to_dict()
        sheet.is_in_use = True
        sheet.current_task_id = task_id
        if commit:
            self._commit()
        db.session.refresh(sheet)
        if not sheet.is_in_use or sheet.current_task_id != task_id:
            return None
        return sheet.to_dict()

    def release_by_task(self, task_id, commit=True):
        """按任务释放其占用的全部 Sheet；返回受影响行数。"""
        updated = GoogleSheet.query.filter_by(current_task_id=task_id).update(
            {
                "is_in_use": False,
                "current_task_id": None,
            },
            synchronize_session=False,
        )
        if commit:
            self._commit()
        return updated

    def get(self, sheet_id):
        row = db.session.get(GoogleSheet, sheet_id)
        return row.to_dict() if row else None

    def get_required(self, sheet_id):
        data = self.get(sheet_id)
        if data is None:
            raise NotFoundError(f"Google Sheet 配置不存在: {sheet_id}")
        return data

    # ---- 写 ----

    def create(self, fields, commit=True):
        row = GoogleSheet(**fields)
        db.session.add(row)
        if commit:
            self._commit()
        return row.to_dict()

    def update(self, sheet_id, fields, commit=True):
        row = db.session.get(GoogleSheet, sheet_id)
        if row is None:
            return None
        for key, value in fields.items():
            setattr(row, key, value)
        if commit:
            self._commit()
        return row.to_dict()

    def delete(self, sheet_id, commit=True):
        row = db.session.get(GoogleSheet, sheet_id)
        if row is None:
            return False
        db.session.delete(row)
        if commit:
            self._commit()
        return True

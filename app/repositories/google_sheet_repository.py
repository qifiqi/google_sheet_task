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

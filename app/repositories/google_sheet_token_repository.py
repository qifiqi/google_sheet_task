"""GoogleSheetToken 仓储（契约见 docs/design/data-layer-refactor/02 §2.9）。

可用性筛选、状态流转方法按 google_sheet_token_service 调用点定形后补入（B2）。
"""
from app.extensions import db
from app.exceptions import NotFoundError
from app.models import GoogleSheetToken
from app.repositories.base import BaseRepository


class GoogleSheetTokenRepository(BaseRepository):
    model = GoogleSheetToken

    # ---- 读 ----

    def list_all(self, include_context=True):
        return [
            row.to_dict(include_context=include_context)
            for row in GoogleSheetToken.query.order_by(GoogleSheetToken.id.asc()).all()
        ]

    def get(self, token_id):
        row = db.session.get(GoogleSheetToken, token_id)
        return row.to_dict() if row else None

    def get_required(self, token_id):
        data = self.get(token_id)
        if data is None:
            raise NotFoundError(f"Token 不存在: {token_id}")
        return data

    # ---- 写 ----

    def create(self, fields, commit=True):
        row = GoogleSheetToken(**fields)
        db.session.add(row)
        if commit:
            self._commit()
        return row.to_dict()

    def update(self, token_id, fields, commit=True):
        row = db.session.get(GoogleSheetToken, token_id)
        if row is None:
            return None
        for key, value in fields.items():
            setattr(row, key, value)
        if commit:
            self._commit()
        return row.to_dict()

    def delete(self, token_id, commit=True):
        row = db.session.get(GoogleSheetToken, token_id)
        if row is None:
            return False
        db.session.delete(row)
        if commit:
            self._commit()
        return True

    def bulk_import(self, rows, commit=True):
        """批量导入 token；返回写入行数。"""
        for fields in rows or []:
            db.session.add(GoogleSheetToken(**fields))
        if commit:
            self._commit()
        return len(rows or [])

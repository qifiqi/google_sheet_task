"""Google Sheet / Token 池域请求 Schema。"""

from pydantic import field_validator

from app.schemas.common import APIModel


class TokenImportSchema(APIModel):
    token_context: str | None = None
    token_file: str | None = None
    name: str | None = None
    task_type: str | None = None
    max_usage_count: int | None = None

    @field_validator("max_usage_count", mode="before")
    @classmethod
    def _empty_to_none(cls, value):
        """对齐原路由语义：空串视为未指定。"""
        if value == "":
            return None
        return value


class WorksheetsQuerySchema(APIModel):
    """POST /api/google-sheet/worksheets。"""

    spreadsheet_id: str = ""
    proxy_url: str | None = None


class SheetCreateSchema(APIModel):
    """POST /api/google-sheets。"""

    spreadsheet_id: str = ""
    name: str | None = None
    table_type: str | None = None
    remark: str | None = None
    is_active: bool = True


class SheetUpdateSchema(APIModel):
    """PUT /api/google-sheets/<id>；仅声明的键会被透传服务层。"""

    spreadsheet_id: str | None = None
    name: str | None = None
    remark: str | None = None
    table_type: str | None = None
    is_active: bool | None = None


class TokenUpdateSchema(APIModel):
    """PUT /api/google-sheet-tokens/<id>。"""

    name: str | None = None
    token_context: str | None = None
    is_active: bool | None = None
    task_type: str | None = None
    max_usage_count: int | None = None

    @field_validator("max_usage_count", mode="before")
    @classmethod
    def _empty_to_none(cls, value):
        if value == "":
            return None
        return value

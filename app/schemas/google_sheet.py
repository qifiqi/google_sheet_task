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

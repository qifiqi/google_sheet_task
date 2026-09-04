"""任务模板域请求 Schema。"""

from typing import Any, Union

from pydantic import Field

from app.schemas.common import APIModel


class TemplateCreateSchema(APIModel):
    name: str = Field(min_length=1)
    description: str = ""
    config: Union[dict[str, Any], str]


class TemplateUpdateSchema(APIModel):
    name: str = Field(min_length=1)
    description: str | None = None
    config: Union[dict[str, Any], str]

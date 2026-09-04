"""回测域请求 Schema。"""

from typing import Any

from pydantic import BaseModel

from app.schemas.common import APIModel


class CalculateRatiosSchema(APIModel):
    ratios: list[Any]


class ImportExcelSchema(BaseModel):
    """multipart 文件上传不在 JSON body 校验域；
    文件存在性由路由检查（保留现状）。"""

    model_config = None

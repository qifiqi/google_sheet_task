"""通用 Schema：APIModel 基类 + 分页查询模型。"""

from pydantic import BaseModel, ConfigDict, Field


class APIModel(BaseModel):
    """全库默认：忽略未声明字段 + 字符串自动去首尾空白。"""

    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)


class PageQuery(APIModel):
    """列表端点分页参数（对齐各 list_* 的 clamp 语义：page>=1、1<=per_page<=100）。"""

    page: int = Field(default=1, ge=1)
    per_page: int = Field(default=20, ge=1, le=100)


class NonEmptyStr(str):
    """语义标记类型（文档用）；实际非空约束以 Field(min_length=1) 声明。"""

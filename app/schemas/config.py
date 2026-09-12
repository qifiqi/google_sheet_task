"""配置域请求 Schema。"""

from typing import Any

from pydantic import RootModel, model_validator


class ConfigBatchSchema(RootModel[dict[str, Any]]):
    """/api/config POST：任意 key/value 配置字典。"""


class SystemConfigUpdateSchema(RootModel[dict[str, Any]]):
    """/api/system-configs/<key> PUT：value 与 description 至少其一。

    语义对齐原路由的键存在性检查（value 可显式传 null 清空，
    故不能用字段默认值区分"缺失"与"显式 null"）。
    """

    @model_validator(mode="before")
    @classmethod
    def _require_one_of(cls, data):
        if not isinstance(data, dict) or ("value" not in data and "description" not in data):
            raise ValueError("缺少需要更新的字段")
        return data

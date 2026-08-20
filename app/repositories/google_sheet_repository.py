"""Google Sheet 注册表记录的远程 CRUD 访问。"""

from collections.abc import Mapping
from typing import Any

from app.repositories.base import SdkCrudRepository, normalize_bool_fields


class GoogleSheetRepository(SdkCrudRepository):
    """统一处理 Sheet 启用、占用状态的布尔字段。"""
    group_name = "param_google_sheet"

    def normalize_record(self, record: Mapping[str, Any]) -> dict[str, Any]:
        """将远端 Sheet 状态字段标准化为 Python 布尔值。"""
        return normalize_bool_fields(record, "is_active", "is_in_use")

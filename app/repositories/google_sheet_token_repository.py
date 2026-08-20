"""Google Sheet Token 记录的远程 CRUD 访问。"""

from collections.abc import Mapping
from typing import Any

from app.repositories.base import SdkCrudRepository, normalize_bool_fields


class GoogleSheetTokenRepository(SdkCrudRepository):
    """处理 Token 的公共字段，并默认隐藏敏感凭据内容。"""
    group_name = "param_google_sheet_tokens"

    def normalize_record(self, record: Mapping[str, Any]) -> dict[str, Any]:
        """将远端 Token 的启用标记标准化为布尔值。"""
        return normalize_bool_fields(record, "is_active")

    def public_record(self, record: Mapping[str, Any], *, include_context: bool = False) -> dict[str, Any]:
        """生成可用于接口响应的 Token 字典，默认移除 ``token_context``。"""
        result = self.normalize_record(record)
        if not include_context:
            result.pop("token_context", None)
        return result

    def list_public(self, *, include_context: bool = False) -> list[dict[str, Any]]:
        """读取全部 Token 并按公共响应规则脱敏。"""
        return [
            self.public_record(record, include_context=include_context)
            for record in self.list_all()
        ]

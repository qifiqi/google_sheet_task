"""导航菜单域请求 Schema。

创建/更新的字段校验由 navigation_service._validate_menu_payload 负责，
body 边界仅约束为 JSON 对象（与既有服务层校验语义对齐）。
"""

from typing import Any

from pydantic import RootModel


class NavigationMenuPayloadSchema(RootModel[dict[str, Any]]):
    """POST/PUT /api/navigation-menu-items 请求体。"""

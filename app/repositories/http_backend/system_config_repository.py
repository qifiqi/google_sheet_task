"""SystemConfig HTTP 仓储（本地对应 app/repositories/system_config_repository.py）。

远端 param_system_configs 分页查询无 key 过滤（RequsetPageDto），配置表行数小，
统一走全量拉取 + 本地匹配；config_manager 自带缓存，读放大可接受。
"""
from __future__ import annotations

from typing import Any

from app.repositories.http_backend.base import HttpRepositoryBase
from app.repositories.sdk_client import SdkNotFoundError


class SystemConfigHttpRepository(HttpRepositoryBase):
    """system_configs 表远程访问；id 为数值主键。"""

    group_name = "param_system_configs"

    # ---- 读 ----

    def _find_row(self, key: str) -> dict[str, Any] | None:
        for row in self.list_all():
            if row.get("key") == key:
                return row
        return None

    def get_row(self, key):
        """返回 {key, value, description, ...}；value 保持原样字符串。不存在返回 None。"""
        return self._find_row(key)

    def list_rows(self):
        """按 key asc 返回全部配置行（config_api 管理端）。"""
        rows = self.list_all(order_field="key", order_type="asc")
        rows.sort(key=lambda item: str(item.get("key") or ""))
        return rows

    # ---- 写 ----

    def update(self, key, fields, commit=True):
        """按 key 更新指定列；key 不存在返回 None。"""
        row = self._find_row(key)
        if row is None:
            return None
        row.update(fields)
        return self.save(row)

    def upsert(self, key, value, description=None, commit=True):
        """写入或更新一行；不负责缓存刷新（调用方负责走 set_config/update_configs 或刷新缓存）。"""
        row = self._find_row(key)
        if row is None:
            payload = {"key": key, "value": value}
            if description is not None:
                payload["description"] = description
        else:
            payload = dict(row)
            payload["value"] = value
            if description is not None:
                payload["description"] = description
        return self.save(payload)

    def delete(self, key, commit=True):
        row = self._find_row(key)
        if row is None:
            return False
        try:
            super().delete(row["id"])
        except SdkNotFoundError:
            return False
        return True

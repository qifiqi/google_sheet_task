"""``/api/SysRole`` —— 系统角色接口。

每个方法对应远程的一个具体端点，docstring 内含等价 curl 调用示例；
请求统一经 ``app/remote_api/client.py`` 的 ``StockApiClient`` 发出
（Token 请求头、统一信封解包、异常翻译、布尔 0/1 编码都在那里完成）。
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from app.remote_api.base import ControllerApi


class SysRoleApi(ControllerApi):
    """系统角色接口（远程控制器 ``/api/SysRole``）。"""

    def delete(self, payload: Mapping[str, Any] | None = None) -> Any:
        """
        按主键删除角色

            curl -X 'POST' \
              'http://stockapi.stplan.cn/api/SysRole/Delete' \
              -H 'accept: application/json' \
              -H 'Content-Type: application/json' \
              -d '{"id": 1}'
        """
        return self._make_request('POST', '/api/SysRole/Delete', payload)

    def get_by_id(self, payload: Mapping[str, Any] | None = None) -> Any:
        """
        按主键查询角色详情

            curl -X 'POST' \
              'http://stockapi.stplan.cn/api/SysRole/GetById' \
              -H 'accept: application/json' \
              -H 'Content-Type: application/json' \
              -d '{"id": 1}'
        """
        return self._make_request('POST', '/api/SysRole/GetById', payload)

    def get_data_by_page_list(self, payload: Mapping[str, Any] | None = None) -> tuple[Any, int | None]:
        """
        分页查询角色（支持 role_name 过滤）

            curl -X 'POST' \
              'http://stockapi.stplan.cn/api/SysRole/GetDataByPageList' \
              -H 'accept: application/json' \
              -H 'Content-Type: application/json' \
              -d '{"page_index": 1, "page_size": 20}'

        返回 ``(ret_obj, ret_count)``：ret_count 为匹配总记录数，远端未返回时为 None。
        """
        return self._make_request_with_count('POST', '/api/SysRole/GetDataByPageList', payload)

    def get_role_list_for_select(self, payload: Mapping[str, Any] | None = None) -> Any:
        """
        查询角色下拉选项列表

            curl -X 'POST' \
              'http://stockapi.stplan.cn/api/SysRole/GetRoleListForSelect' \
              -H 'accept: application/json' \
              -H 'Content-Type: application/json' \
              -d '{}'
        """
        return self._make_request('POST', '/api/SysRole/GetRoleListForSelect', payload)

    def is_role(self, payload: Mapping[str, Any] | None = None) -> Any:
        """
        校验模型（菜单）名称是否已分配角色

            curl -X 'POST' \
              'http://stockapi.stplan.cn/api/SysRole/IsRole' \
              -H 'accept: application/json' \
              -H 'Content-Type: application/json' \
              -d '{"model_name": "..."}'
        """
        return self._make_request('POST', '/api/SysRole/IsRole', payload)

    def modify_or_add(self, payload: Mapping[str, Any] | None = None) -> Any:
        """
        新增/更新角色

            curl -X 'POST' \
              'http://stockapi.stplan.cn/api/SysRole/ModifyOrAdd' \
              -H 'accept: application/json' \
              -H 'Content-Type: application/json' \
              -d '{"role_name": "...", "model_ids": "1,2,3"}'
        """
        return self._make_request('POST', '/api/SysRole/ModifyOrAdd', payload)

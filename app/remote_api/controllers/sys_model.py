"""``/api/SysModel`` —— 系统模型（导航/模型表）接口。

每个方法对应远程的一个具体端点，docstring 内含等价 curl 调用示例；
请求统一经 ``app/remote_api/client.py`` 的 ``StockApiClient`` 发出
（Token 请求头、统一信封解包、异常翻译、布尔 0/1 编码都在那里完成）。
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from app.remote_api.base import ControllerApi


class SysModelApi(ControllerApi):
    """系统模型（导航/模型表）接口（远程控制器 ``/api/SysModel``）。"""

    def delete(self, payload: Mapping[str, Any] | None = None) -> Any:
        """
        按主键删除系统模型

            curl -X 'POST' \
              'http://stockapi.stplan.cn/api/SysModel/Delete' \
              -H 'accept: application/json' \
              -H 'Content-Type: application/json' \
              -d '{"id": 1}'
        """
        return self._make_request('POST', '/api/SysModel/Delete', payload)

    def get_by_id(self, payload: Mapping[str, Any] | None = None) -> Any:
        """
        按主键查询系统模型详情

            curl -X 'POST' \
              'http://stockapi.stplan.cn/api/SysModel/GetById' \
              -H 'accept: application/json' \
              -H 'Content-Type: application/json' \
              -d '{"id": 1}'
        """
        return self._make_request('POST', '/api/SysModel/GetById', payload)

    def get_data_by_page_list(self, payload: Mapping[str, Any] | None = None) -> tuple[Any, int | None]:
        """
        分页查询系统模型（支持 model_name/parent_model_name 过滤）

            curl -X 'POST' \
              'http://stockapi.stplan.cn/api/SysModel/GetDataByPageList' \
              -H 'accept: application/json' \
              -H 'Content-Type: application/json' \
              -d '{"page_index": 1, "page_size": 20}'

        返回 ``(ret_obj, ret_count)``：ret_count 为匹配总记录数，远端未返回时为 None。
        """
        return self._make_request_with_count('POST', '/api/SysModel/GetDataByPageList', payload)

    def get_top_model_list(self, payload: Mapping[str, Any] | None = None) -> Any:
        """
        查询顶层模型列表

            curl -X 'POST' \
              'http://stockapi.stplan.cn/api/SysModel/GetTopModelList' \
              -H 'accept: application/json' \
              -H 'Content-Type: application/json' \
              -d '{}'
        """
        return self._make_request('POST', '/api/SysModel/GetTopModelList', payload)

    def modify_or_add(self, payload: Mapping[str, Any] | None = None) -> Any:
        """
        新增/更新系统模型

            curl -X 'POST' \
              'http://stockapi.stplan.cn/api/SysModel/ModifyOrAdd' \
              -H 'accept: application/json' \
              -H 'Content-Type: application/json' \
              -d '{"model_name": "...", "model_code": "...", "order_num": 1}'
        """
        return self._make_request('POST', '/api/SysModel/ModifyOrAdd', payload)

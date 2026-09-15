"""``/api/ParamScheduledTasks`` —— 计划任务表接口。

每个方法对应远程的一个具体端点，docstring 内含等价 curl 调用示例；
请求统一经 ``app/remote_api/client.py`` 的 ``StockApiClient`` 发出
（Token 请求头、统一信封解包、异常翻译、布尔 0/1 编码都在那里完成）。
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from app.remote_api.base import ControllerApi


class ParamScheduledTasksApi(ControllerApi):
    """计划任务表接口（远程控制器 ``/api/ParamScheduledTasks``）。"""

    def delete(self, payload: Mapping[str, Any] | None = None) -> Any:
        """
        按主键删除计划任务

            curl -X 'POST' \
              'http://stockapi.stplan.cn/api/ParamScheduledTasks/Delete' \
              -H 'accept: application/json' \
              -H 'Content-Type: application/json' \
              -d '{"id": 1}'
        """
        return self._make_request('POST', '/api/ParamScheduledTasks/Delete', payload)

    def get_data_by_page_list(self, payload: Mapping[str, Any] | None = None) -> tuple[Any, int | None]:
        """
        分页查询计划任务

            curl -X 'POST' \
              'http://stockapi.stplan.cn/api/ParamScheduledTasks/GetDataByPageList' \
              -H 'accept: application/json' \
              -H 'Content-Type: application/json' \
              -d '{"page_index": 1, "page_size": 20}'

        返回 ``(ret_obj, ret_count)``：ret_count 为匹配总记录数，远端未返回时为 None。
        """
        return self._make_request_with_count('POST', '/api/ParamScheduledTasks/GetDataByPageList', payload)

    def get_info_by_id(self, payload: Mapping[str, Any] | None = None) -> Any:
        """
        按主键查询计划任务详情

            curl -X 'POST' \
              'http://stockapi.stplan.cn/api/ParamScheduledTasks/GetInfoById' \
              -H 'accept: application/json' \
              -H 'Content-Type: application/json' \
              -d '{"id": 1}'
        """
        return self._make_request('POST', '/api/ParamScheduledTasks/GetInfoById', payload)

    def modify_or_add(self, payload: Mapping[str, Any] | None = None) -> Any:
        """
        新增/更新计划任务

            curl -X 'POST' \
              'http://stockapi.stplan.cn/api/ParamScheduledTasks/ModifyOrAdd' \
              -H 'accept: application/json' \
              -H 'Content-Type: application/json' \
              -d '{"id": 1, "name": "..."}'
        """
        return self._make_request('POST', '/api/ParamScheduledTasks/ModifyOrAdd', payload)

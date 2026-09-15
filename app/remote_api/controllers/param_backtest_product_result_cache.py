"""``/api/ParamBacktestProductResultCache`` —— 回测产品结果缓存表接口。

每个方法对应远程的一个具体端点，docstring 内含等价 curl 调用示例；
请求统一经 ``app/remote_api/client.py`` 的 ``StockApiClient`` 发出
（Token 请求头、统一信封解包、异常翻译、布尔 0/1 编码都在那里完成）。
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from app.remote_api.base import ControllerApi


class ParamBacktestProductResultCacheApi(ControllerApi):
    """回测产品结果缓存表接口（远程控制器 ``/api/ParamBacktestProductResultCache``）。"""

    def delete(self, payload: Mapping[str, Any] | None = None) -> Any:
        """
        按主键删除缓存记录

            curl -X 'POST' \
              'http://stockapi.stplan.cn/api/ParamBacktestProductResultCache/Delete' \
              -H 'accept: application/json' \
              -H 'Content-Type: application/json' \
              -d '{"id": 1}'
        """
        return self._make_request('POST', '/api/ParamBacktestProductResultCache/Delete', payload)

    def get_data_by_page_list(self, payload: Mapping[str, Any] | None = None) -> tuple[Any, int | None]:
        """
        分页查询缓存记录（远端无业务过滤字段，全量分页）

            curl -X 'POST' \
              'http://stockapi.stplan.cn/api/ParamBacktestProductResultCache/GetDataByPageList' \
              -H 'accept: application/json' \
              -H 'Content-Type: application/json' \
              -d '{"page_index": 1, "page_size": 20}'

        返回 ``(ret_obj, ret_count)``：ret_count 为匹配总记录数，远端未返回时为 None。
        """
        return self._make_request_with_count('POST', '/api/ParamBacktestProductResultCache/GetDataByPageList', payload)

    def get_info_by_id(self, payload: Mapping[str, Any] | None = None) -> Any:
        """
        按主键查询缓存详情

            curl -X 'POST' \
              'http://stockapi.stplan.cn/api/ParamBacktestProductResultCache/GetInfoById' \
              -H 'accept: application/json' \
              -H 'Content-Type: application/json' \
              -d '{"id": 1}'
        """
        return self._make_request('POST', '/api/ParamBacktestProductResultCache/GetInfoById', payload)

    def modify_or_add(self, payload: Mapping[str, Any] | None = None) -> Any:
        """
        新增/更新缓存记录（存在 id 则更新，否则新增）

            curl -X 'POST' \
              'http://stockapi.stplan.cn/api/ParamBacktestProductResultCache/ModifyOrAdd' \
              -H 'accept: application/json' \
              -H 'Content-Type: application/json' \
              -d '{"batch_id": "...", "cache_key": "...", "payload": "..."}'
        """
        return self._make_request('POST', '/api/ParamBacktestProductResultCache/ModifyOrAdd', payload)

"""``/api/StockDataUs`` —— 美股K线数据接口。

每个方法对应远程的一个具体端点，docstring 内含等价 curl 调用示例；
请求统一经 ``app/remote_api/client.py`` 的 ``StockApiClient`` 发出
（Token 请求头、统一信封解包、异常翻译、布尔 0/1 编码都在那里完成）。
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from app.remote_api.base import ControllerApi


class StockDataUsApi(ControllerApi):
    """美股K线数据接口（远程控制器 ``/api/StockDataUs``）。"""

    def delete(self, payload: Mapping[str, Any] | None = None) -> Any:
        """
        按主键删除美股K线记录

            curl -X 'POST' \
              'http://stockapi.stplan.cn/api/StockDataUs/Delete' \
              -H 'accept: application/json' \
              -H 'Content-Type: application/json' \
              -d '{"id": 1}'
        """
        return self._make_request('POST', '/api/StockDataUs/Delete', payload)

    def get_by_id(self, payload: Mapping[str, Any] | None = None) -> Any:
        """
        按主键查询美股K线记录

            curl -X 'POST' \
              'http://stockapi.stplan.cn/api/StockDataUs/GetById' \
              -H 'accept: application/json' \
              -H 'Content-Type: application/json' \
              -d '{"id": 1}'
        """
        return self._make_request('POST', '/api/StockDataUs/GetById', payload)

    def get_data_all_list(self, payload: Mapping[str, Any] | None = None) -> Any:
        """
        按条件查询美股K线全量数据（无分页）

            curl -X 'POST' \
              'http://stockapi.stplan.cn/api/StockDataUs/GetDataAllList' \
              -H 'accept: application/json' \
              -H 'Content-Type: application/json' \
              -d '{"begin_date": "2024-01-01", "stock_code": "AAPL"}'
        """
        return self._make_request('POST', '/api/StockDataUs/GetDataAllList', payload)

    def get_data_by_page_list(self, payload: Mapping[str, Any] | None = None) -> tuple[Any, int | None]:
        """
        分页查询美股K线数据

            curl -X 'POST' \
              'http://stockapi.stplan.cn/api/StockDataUs/GetDataByPageList' \
              -H 'accept: application/json' \
              -H 'Content-Type: application/json' \
              -d '{"stock_code": "AAPL", "page_index": 1, "page_size": 200}'

        返回 ``(ret_obj, ret_count)``：ret_count 为匹配总记录数，远端未返回时为 None。
        """
        return self._make_request_with_count('POST', '/api/StockDataUs/GetDataByPageList', payload)

    def get_list_his_page(self, payload: Mapping[str, Any] | None = None) -> tuple[Any, int | None]:
        """
        按日期分页查询美股历史K线

            curl -X 'POST' \
              'http://stockapi.stplan.cn/api/StockDataUs/GetListHisPage' \
              -H 'accept: application/json' \
              -H 'Content-Type: application/json' \
              -d '{"stock_date": "2024-01-01", "page_index": 1, "page_size": 200}'

        返回 ``(ret_obj, ret_count)``：ret_count 为匹配总记录数，远端未返回时为 None。
        """
        return self._make_request_with_count('POST', '/api/StockDataUs/GetListHisPage', payload)

    def get_list_page(self, payload: Mapping[str, Any] | None = None) -> tuple[Any, int | None]:
        """
        分页查询美股K线

            curl -X 'POST' \
              'http://stockapi.stplan.cn/api/StockDataUs/GetListPage' \
              -H 'accept: application/json' \
              -H 'Content-Type: application/json' \
              -d '{"stock_code": "AAPL", "page_index": 1, "page_size": 200}'

        返回 ``(ret_obj, ret_count)``：ret_count 为匹配总记录数，远端未返回时为 None。
        """
        return self._make_request_with_count('POST', '/api/StockDataUs/GetListPage', payload)

    def modify_or_add(self, payload: Mapping[str, Any] | None = None) -> Any:
        """
        写入/更新一行美股K线

            curl -X 'POST' \
              'http://stockapi.stplan.cn/api/StockDataUs/ModifyOrAdd' \
              -H 'accept: application/json' \
              -H 'Content-Type: application/json' \
              -d '{"stock_code": "AAPL", "stock_date": "2024-01-01", "stock_open": 180.0, "stock_close": 182.5}'
        """
        return self._make_request('POST', '/api/StockDataUs/ModifyOrAdd', payload)

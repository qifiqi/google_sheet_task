"""``/api/StockData`` —— A股K线数据接口。

每个方法对应远程的一个具体端点，docstring 内含等价 curl 调用示例；
请求统一经 ``app/remote_api/client.py`` 的 ``StockApiClient`` 发出
（Token 请求头、统一信封解包、异常翻译、布尔 0/1 编码都在那里完成）。
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from app.remote_api.base import ControllerApi


class StockDataApi(ControllerApi):
    """A股K线数据接口（远程控制器 ``/api/StockData``）。"""

    def delete(self, payload: Mapping[str, Any] | None = None) -> Any:
        """
        按主键删除K线记录

            curl -X 'POST' \
              'http://stockapi.stplan.cn/api/StockData/Delete' \
              -H 'accept: application/json' \
              -H 'Content-Type: application/json' \
              -d '{"id": 1}'
        """
        return self._make_request('POST', '/api/StockData/Delete', payload)

    def get_by_id(self, payload: Mapping[str, Any] | None = None) -> Any:
        """
        按主键查询K线记录

            curl -X 'POST' \
              'http://stockapi.stplan.cn/api/StockData/GetById' \
              -H 'accept: application/json' \
              -H 'Content-Type: application/json' \
              -d '{"id": 1}'
        """
        return self._make_request('POST', '/api/StockData/GetById', payload)

    def get_data_all_list(self, payload: Mapping[str, Any] | None = None) -> Any:
        """
        按条件查询K线全量数据（无分页）

            curl -X 'POST' \
              'http://stockapi.stplan.cn/api/StockData/GetDataAllList' \
              -H 'accept: application/json' \
              -H 'Content-Type: application/json' \
              -d '{"begin_date": "2024-01-01", "stock_code": "600000.SH"}'
        """
        return self._make_request('POST', '/api/StockData/GetDataAllList', payload)

    def get_data_by_page_list(self, payload: Mapping[str, Any] | None = None) -> tuple[Any, int | None]:
        """
        分页查询K线数据（支持 stock_code/行业/日期区间等过滤）

            curl -X 'POST' \
              'http://stockapi.stplan.cn/api/StockData/GetDataByPageList' \
              -H 'accept: application/json' \
              -H 'Content-Type: application/json' \
              -d '{"stock_code": "600000.SH", "begin_date": "2024-01-01", "page_index": 1, "page_size": 200}'

        返回 ``(ret_obj, ret_count)``：ret_count 为匹配总记录数，远端未返回时为 None。
        """
        return self._make_request_with_count('POST', '/api/StockData/GetDataByPageList', payload)

    def get_list_his_page(self, payload: Mapping[str, Any] | None = None) -> tuple[Any, int | None]:
        """
        按日期分页查询历史K线

            curl -X 'POST' \
              'http://stockapi.stplan.cn/api/StockData/GetListHisPage' \
              -H 'accept: application/json' \
              -H 'Content-Type: application/json' \
              -d '{"stock_date": "2024-01-01", "page_index": 1, "page_size": 200}'

        返回 ``(ret_obj, ret_count)``：ret_count 为匹配总记录数，远端未返回时为 None。
        """
        return self._make_request_with_count('POST', '/api/StockData/GetListHisPage', payload)

    def get_list_page(self, payload: Mapping[str, Any] | None = None) -> tuple[Any, int | None]:
        """
        分页查询K线（支持系数/概念/等级过滤）

            curl -X 'POST' \
              'http://stockapi.stplan.cn/api/StockData/GetListPage' \
              -H 'accept: application/json' \
              -H 'Content-Type: application/json' \
              -d '{"stock_code": "600000.SH", "page_index": 1, "page_size": 200}'

        返回 ``(ret_obj, ret_count)``：ret_count 为匹配总记录数，远端未返回时为 None。
        """
        return self._make_request_with_count('POST', '/api/StockData/GetListPage', payload)

    def get_list_volume(self, payload: Mapping[str, Any] | None = None) -> Any:
        """
        按成交量条件查询K线（多条件动态拼接）

            curl -X 'POST' \
              'http://stockapi.stplan.cn/api/StockData/GetListVolume' \
              -H 'accept: application/json' \
              -H 'Content-Type: application/json' \
              -d '{"stock_code": "600000.SH", "coefficient": 1.0}'
        """
        return self._make_request('POST', '/api/StockData/GetListVolume', payload)

    def get_stock_list_by_code(self, payload: Mapping[str, Any] | None = None) -> Any:
        """
        按代码与日期区间查询K线

            curl -X 'POST' \
              'http://stockapi.stplan.cn/api/StockData/GetStockListByCode' \
              -H 'accept: application/json' \
              -H 'Content-Type: application/json' \
              -d '{"stock_code": "600000.SH", "begin_date": "2024-01-01", "end_time": "2024-01-31"}'
        """
        return self._make_request('POST', '/api/StockData/GetStockListByCode', payload)

    def get_stock_list_by_code_or_date(self, payload: Mapping[str, Any] | None = None) -> Any:
        """
        按代码或日期查询K线

            curl -X 'POST' \
              'http://stockapi.stplan.cn/api/StockData/GetStockListByCodeOrDate' \
              -H 'accept: application/json' \
              -H 'Content-Type: application/json' \
              -d '{"stock_code": "600000.SH", "begin_date": "2024-01-01", "end_time": "2024-01-31"}'
        """
        return self._make_request('POST', '/api/StockData/GetStockListByCodeOrDate', payload)

    def modify_or_add(self, payload: Mapping[str, Any] | None = None) -> Any:
        """
        写入/更新一行K线（wire 字段 stock_open/stock_max/...）

            curl -X 'POST' \
              'http://stockapi.stplan.cn/api/StockData/ModifyOrAdd' \
              -H 'accept: application/json' \
              -H 'Content-Type: application/json' \
              -d '{"stock_code": "600000.SH", "stock_date": "2024-01-01", "stock_open": 10.0, "stock_max": 11.0, "stock_min": 9.8, "stock_close": 10.5}'
        """
        return self._make_request('POST', '/api/StockData/ModifyOrAdd', payload)

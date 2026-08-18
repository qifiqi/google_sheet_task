"""Generated endpoint wrappers for one Swagger controller."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..http_client import ApiGroup
from ..models import GetDataByPageListForWindowsRequestDto, GetStockXtOrderListRequestDto, IdRequestDto, t_stock_xt_order
from ..response import ResponseDto
from ._metadata import endpoint

class StockxtorderApi(ApiGroup):
    @endpoint('POST', '/api/StockXtOrder/Delete')
    def delete(
        self,
        request: IdRequestDto | Mapping[str, Any],
    ) -> ResponseDto[Any]:
        return self._call('POST', '/api/StockXtOrder/Delete', json_body=request)

    @endpoint('POST', '/api/StockXtOrder/GetDataByPageList')
    def get_data_by_page_list(
        self,
        request: GetStockXtOrderListRequestDto | Mapping[str, Any],
    ) -> ResponseDto[Any]:
        return self._call('POST', '/api/StockXtOrder/GetDataByPageList', json_body=request)

    @endpoint('POST', '/api/StockXtOrder/GetDataByPageListForWindows')
    def get_data_by_page_list_for_windows(
        self,
        request: GetDataByPageListForWindowsRequestDto | Mapping[str, Any],
    ) -> ResponseDto[Any]:
        return self._call('POST', '/api/StockXtOrder/GetDataByPageListForWindows', json_body=request)

    @endpoint('POST', '/api/StockXtOrder/GetInfoById')
    def get_info_by_id(
        self,
        request: IdRequestDto | Mapping[str, Any],
    ) -> ResponseDto[Any]:
        return self._call('POST', '/api/StockXtOrder/GetInfoById', json_body=request)

    @endpoint('POST', '/api/StockXtOrder/ModifyOrAdd')
    def modify_or_add(
        self,
        request: t_stock_xt_order | Mapping[str, Any],
    ) -> ResponseDto[Any]:
        return self._call('POST', '/api/StockXtOrder/ModifyOrAdd', json_body=request)

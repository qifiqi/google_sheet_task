"""Generated endpoint wrappers for one Swagger controller."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..http_client import ApiGroup
from ..models import GetStockXtTradeListForWindowsRequestDto, GetStockXtTradeListRequestDto, IdRequestDto, t_stock_xt_trade
from ..response import ResponseDto
from ._metadata import endpoint

class StockxttradeApi(ApiGroup):
    @endpoint('POST', '/api/StockXtTrade/Delete')
    def delete(
        self,
        request: IdRequestDto | Mapping[str, Any],
    ) -> ResponseDto[Any]:
        return self._call('POST', '/api/StockXtTrade/Delete', json_body=request)

    @endpoint('POST', '/api/StockXtTrade/GetDataByPageList')
    def get_data_by_page_list(
        self,
        request: GetStockXtTradeListRequestDto | Mapping[str, Any],
    ) -> ResponseDto[Any]:
        return self._call('POST', '/api/StockXtTrade/GetDataByPageList', json_body=request)

    @endpoint('POST', '/api/StockXtTrade/GetDataByPageListForWindows')
    def get_data_by_page_list_for_windows(
        self,
        request: GetStockXtTradeListForWindowsRequestDto | Mapping[str, Any],
    ) -> ResponseDto[Any]:
        return self._call('POST', '/api/StockXtTrade/GetDataByPageListForWindows', json_body=request)

    @endpoint('POST', '/api/StockXtTrade/GetInfoById')
    def get_info_by_id(
        self,
        request: IdRequestDto | Mapping[str, Any],
    ) -> ResponseDto[Any]:
        return self._call('POST', '/api/StockXtTrade/GetInfoById', json_body=request)

    @endpoint('POST', '/api/StockXtTrade/ModifyOrAdd')
    def modify_or_add(
        self,
        request: t_stock_xt_trade | Mapping[str, Any],
    ) -> ResponseDto[Any]:
        return self._call('POST', '/api/StockXtTrade/ModifyOrAdd', json_body=request)

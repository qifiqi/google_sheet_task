"""Generated endpoint wrappers for one Swagger controller."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..http_client import ApiGroup
from ..models import GetStockXtPositionListForWindowsRequestDto, GetStockXtPositionListRequestDto, IdRequestDto, t_stock_xt_position
from ..response import ResponseDto
from ._metadata import endpoint

class StockxtpositionApi(ApiGroup):
    @endpoint('POST', '/api/StockXtPosition/Delete')
    def delete(
        self,
        request: IdRequestDto | Mapping[str, Any],
    ) -> ResponseDto[Any]:
        return self._call('POST', '/api/StockXtPosition/Delete', json_body=request)

    @endpoint('POST', '/api/StockXtPosition/GetDataByPageList')
    def get_data_by_page_list(
        self,
        request: GetStockXtPositionListRequestDto | Mapping[str, Any],
    ) -> ResponseDto[Any]:
        return self._call('POST', '/api/StockXtPosition/GetDataByPageList', json_body=request)

    @endpoint('POST', '/api/StockXtPosition/GetDataByPageListForWindows')
    def get_data_by_page_list_for_windows(
        self,
        request: GetStockXtPositionListForWindowsRequestDto | Mapping[str, Any],
    ) -> ResponseDto[Any]:
        return self._call('POST', '/api/StockXtPosition/GetDataByPageListForWindows', json_body=request)

    @endpoint('POST', '/api/StockXtPosition/GetInfoById')
    def get_info_by_id(
        self,
        request: IdRequestDto | Mapping[str, Any],
    ) -> ResponseDto[Any]:
        return self._call('POST', '/api/StockXtPosition/GetInfoById', json_body=request)

    @endpoint('POST', '/api/StockXtPosition/ModifyOrAdd')
    def modify_or_add(
        self,
        request: t_stock_xt_position | Mapping[str, Any],
    ) -> ResponseDto[Any]:
        return self._call('POST', '/api/StockXtPosition/ModifyOrAdd', json_body=request)

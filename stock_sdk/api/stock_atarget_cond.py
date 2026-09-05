"""Generated endpoint wrappers for one Swagger controller."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..http_client import ApiGroup
from ..models import GetStockATargetCondListRequestDto, GetStockATargetCondSearchRequestDto, IdRequestDto, t_stock_a_target_cond
from ..response import ResponseDto
from ._metadata import endpoint

class StockatargetcondApi(ApiGroup):
    @endpoint('POST', '/api/StockATargetCond/Delete')
    def delete(
        self,
        request: IdRequestDto | Mapping[str, Any],
    ) -> ResponseDto[Any]:
        return self._call('POST', '/api/StockATargetCond/Delete', json_body=request)

    @endpoint('POST', '/api/StockATargetCond/GetDataByPageList')
    def get_data_by_page_list(
        self,
        request: GetStockATargetCondListRequestDto | Mapping[str, Any],
    ) -> ResponseDto[Any]:
        return self._call('POST', '/api/StockATargetCond/GetDataByPageList', json_body=request)

    @endpoint('POST', '/api/StockATargetCond/GetDataBySearch')
    def get_data_by_search(
        self,
        request: GetStockATargetCondSearchRequestDto | Mapping[str, Any],
    ) -> ResponseDto[Any]:
        return self._call('POST', '/api/StockATargetCond/GetDataBySearch', json_body=request)

    @endpoint('POST', '/api/StockATargetCond/GetInfoById')
    def get_info_by_id(
        self,
        request: IdRequestDto | Mapping[str, Any],
    ) -> ResponseDto[Any]:
        return self._call('POST', '/api/StockATargetCond/GetInfoById', json_body=request)

    @endpoint('POST', '/api/StockATargetCond/ModifyOrAdd')
    def modify_or_add(
        self,
        request: t_stock_a_target_cond | Mapping[str, Any],
    ) -> ResponseDto[Any]:
        return self._call('POST', '/api/StockATargetCond/ModifyOrAdd', json_body=request)

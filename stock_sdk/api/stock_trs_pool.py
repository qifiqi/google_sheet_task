"""Generated endpoint wrappers for one Swagger controller."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..http_client import ApiGroup
from ..models import GetStockTrsPoolListRequestDto, IdRequestDto, t_stock_trs_pool
from ..response import ResponseDto
from ._metadata import endpoint

class StocktrspoolApi(ApiGroup):
    @endpoint('POST', '/api/StockTrsPool/Delete')
    def delete(
        self,
        request: IdRequestDto | Mapping[str, Any],
    ) -> ResponseDto[Any]:
        return self._call('POST', '/api/StockTrsPool/Delete', json_body=request)

    @endpoint('POST', '/api/StockTrsPool/GetDataByPageList')
    def get_data_by_page_list(
        self,
        request: GetStockTrsPoolListRequestDto | Mapping[str, Any],
    ) -> ResponseDto[Any]:
        return self._call('POST', '/api/StockTrsPool/GetDataByPageList', json_body=request)

    @endpoint('POST', '/api/StockTrsPool/GetInfoById')
    def get_info_by_id(
        self,
        request: IdRequestDto | Mapping[str, Any],
    ) -> ResponseDto[Any]:
        return self._call('POST', '/api/StockTrsPool/GetInfoById', json_body=request)

    @endpoint('POST', '/api/StockTrsPool/ModifyOrAdd')
    def modify_or_add(
        self,
        request: t_stock_trs_pool | Mapping[str, Any],
    ) -> ResponseDto[Any]:
        return self._call('POST', '/api/StockTrsPool/ModifyOrAdd', json_body=request)

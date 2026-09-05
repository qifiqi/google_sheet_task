"""Generated endpoint wrappers for one Swagger controller."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..http_client import ApiGroup
from ..models import GetStockATargetListRequestDto, IdRequestDto, t_stock_a_target
from ..response import ResponseDto
from ._metadata import endpoint

class StockatargetApi(ApiGroup):
    @endpoint('POST', '/api/StockATarget/Delete')
    def delete(
        self,
        request: IdRequestDto | Mapping[str, Any],
    ) -> ResponseDto[Any]:
        return self._call('POST', '/api/StockATarget/Delete', json_body=request)

    @endpoint('POST', '/api/StockATarget/GetDataByPageList')
    def get_data_by_page_list(
        self,
        request: GetStockATargetListRequestDto | Mapping[str, Any],
    ) -> ResponseDto[Any]:
        return self._call('POST', '/api/StockATarget/GetDataByPageList', json_body=request)

    @endpoint('POST', '/api/StockATarget/GetInfoById')
    def get_info_by_id(
        self,
        request: IdRequestDto | Mapping[str, Any],
    ) -> ResponseDto[Any]:
        return self._call('POST', '/api/StockATarget/GetInfoById', json_body=request)

    @endpoint('POST', '/api/StockATarget/ModifyOrAdd')
    def modify_or_add(
        self,
        request: t_stock_a_target | Mapping[str, Any],
    ) -> ResponseDto[Any]:
        return self._call('POST', '/api/StockATarget/ModifyOrAdd', json_body=request)

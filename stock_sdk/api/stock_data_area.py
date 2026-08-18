"""Generated endpoint wrappers for one Swagger controller."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..http_client import ApiGroup
from ..models import GetAreaListRequestDto, IdRequestDto, t_stock_data_area
from ..response import ResponseDto
from ._metadata import endpoint

class StockdataareaApi(ApiGroup):
    @endpoint('POST', '/api/StockDataArea/Delete')
    def delete(
        self,
        request: IdRequestDto | Mapping[str, Any],
    ) -> ResponseDto[Any]:
        return self._call('POST', '/api/StockDataArea/Delete', json_body=request)

    @endpoint('POST', '/api/StockDataArea/GetById')
    def get_by_id(
        self,
        request: IdRequestDto | Mapping[str, Any],
    ) -> ResponseDto[Any]:
        return self._call('POST', '/api/StockDataArea/GetById', json_body=request)

    @endpoint('POST', '/api/StockDataArea/GetDataByPageList')
    def get_data_by_page_list(
        self,
        request: GetAreaListRequestDto | Mapping[str, Any],
    ) -> ResponseDto[Any]:
        return self._call('POST', '/api/StockDataArea/GetDataByPageList', json_body=request)

    @endpoint('POST', '/api/StockDataArea/ModifyOrAdd')
    def modify_or_add(
        self,
        request: t_stock_data_area | Mapping[str, Any],
    ) -> ResponseDto[Any]:
        return self._call('POST', '/api/StockDataArea/ModifyOrAdd', json_body=request)

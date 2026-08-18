"""Generated endpoint wrappers for one Swagger controller."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..http_client import ApiGroup
from ..models import GetDataIndexListRequestDto, IdRequestDto, t_stock_data_index
from ..response import ResponseDto
from ._metadata import endpoint

class StockdataindexApi(ApiGroup):
    @endpoint('POST', '/api/StockDataIndex/Delete')
    def delete(
        self,
        request: IdRequestDto | Mapping[str, Any],
    ) -> ResponseDto[Any]:
        return self._call('POST', '/api/StockDataIndex/Delete', json_body=request)

    @endpoint('POST', '/api/StockDataIndex/GetById')
    def get_by_id(
        self,
        request: IdRequestDto | Mapping[str, Any],
    ) -> ResponseDto[Any]:
        return self._call('POST', '/api/StockDataIndex/GetById', json_body=request)

    @endpoint('POST', '/api/StockDataIndex/GetDataByPageList')
    def get_data_by_page_list(
        self,
        request: GetDataIndexListRequestDto | Mapping[str, Any],
    ) -> ResponseDto[Any]:
        return self._call('POST', '/api/StockDataIndex/GetDataByPageList', json_body=request)

    @endpoint('POST', '/api/StockDataIndex/ModifyOrAdd')
    def modify_or_add(
        self,
        request: t_stock_data_index | Mapping[str, Any],
    ) -> ResponseDto[Any]:
        return self._call('POST', '/api/StockDataIndex/ModifyOrAdd', json_body=request)

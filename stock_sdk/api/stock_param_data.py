"""Generated endpoint wrappers for one Swagger controller."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..http_client import ApiGroup
from ..models import GetStockParamDataListRequestDto, IdRequestDto, t_stock_param_data
from ..response import ResponseDto
from ._metadata import endpoint

class StockparamdataApi(ApiGroup):
    @endpoint('POST', '/api/StockParamData/Delete')
    def delete(
        self,
        request: IdRequestDto | Mapping[str, Any],
    ) -> ResponseDto[Any]:
        return self._call('POST', '/api/StockParamData/Delete', json_body=request)

    @endpoint('POST', '/api/StockParamData/GetDataByPageList')
    def get_data_by_page_list(
        self,
        request: GetStockParamDataListRequestDto | Mapping[str, Any],
    ) -> ResponseDto[Any]:
        return self._call('POST', '/api/StockParamData/GetDataByPageList', json_body=request)

    @endpoint('POST', '/api/StockParamData/GetInfoById')
    def get_info_by_id(
        self,
        request: IdRequestDto | Mapping[str, Any],
    ) -> ResponseDto[Any]:
        return self._call('POST', '/api/StockParamData/GetInfoById', json_body=request)

    @endpoint('POST', '/api/StockParamData/ModifyOrAdd')
    def modify_or_add(
        self,
        request: t_stock_param_data | Mapping[str, Any],
    ) -> ResponseDto[Any]:
        return self._call('POST', '/api/StockParamData/ModifyOrAdd', json_body=request)

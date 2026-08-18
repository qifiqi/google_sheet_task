"""Generated endpoint wrappers for one Swagger controller."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..http_client import ApiGroup
from ..models import GetStockParamTuningListRequestDto, IdRequestDto, t_stock_param_tuning
from ..response import ResponseDto
from ._metadata import endpoint

class StockparamtuningApi(ApiGroup):
    @endpoint('POST', '/api/StockParamTuning/Delete')
    def delete(
        self,
        request: IdRequestDto | Mapping[str, Any],
    ) -> ResponseDto[Any]:
        return self._call('POST', '/api/StockParamTuning/Delete', json_body=request)

    @endpoint('POST', '/api/StockParamTuning/GetDataByPageList')
    def get_data_by_page_list(
        self,
        request: GetStockParamTuningListRequestDto | Mapping[str, Any],
    ) -> ResponseDto[Any]:
        return self._call('POST', '/api/StockParamTuning/GetDataByPageList', json_body=request)

    @endpoint('POST', '/api/StockParamTuning/GetInfoById')
    def get_info_by_id(
        self,
        request: IdRequestDto | Mapping[str, Any],
    ) -> ResponseDto[Any]:
        return self._call('POST', '/api/StockParamTuning/GetInfoById', json_body=request)

    @endpoint('POST', '/api/StockParamTuning/ModifyOrAdd')
    def modify_or_add(
        self,
        request: t_stock_param_tuning | Mapping[str, Any],
    ) -> ResponseDto[Any]:
        return self._call('POST', '/api/StockParamTuning/ModifyOrAdd', json_body=request)

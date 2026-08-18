"""Generated endpoint wrappers for one Swagger controller."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..http_client import ApiGroup
from ..models import DeleteStockParamResultRequestDto, GetSingleStockTemplateRequestDto, GetStockParamResultListRequestDto, t_stock_param_result
from ..response import ResponseDto
from ._metadata import endpoint

class StockparamresultApi(ApiGroup):
    @endpoint('POST', '/api/StockParamResult/AddOrModify')
    def add_or_modify(
        self,
        request: t_stock_param_result | Mapping[str, Any],
    ) -> ResponseDto[Any]:
        return self._call('POST', '/api/StockParamResult/AddOrModify', json_body=request)

    @endpoint('POST', '/api/StockParamResult/Delete')
    def delete(
        self,
        request: DeleteStockParamResultRequestDto | Mapping[str, Any],
    ) -> ResponseDto[Any]:
        return self._call('POST', '/api/StockParamResult/Delete', json_body=request)

    @endpoint('POST', '/api/StockParamResult/GetDataByPageList')
    def get_data_by_page_list(
        self,
        request: GetStockParamResultListRequestDto | Mapping[str, Any],
    ) -> ResponseDto[Any]:
        return self._call('POST', '/api/StockParamResult/GetDataByPageList', json_body=request)

    @endpoint('POST', '/api/StockParamResult/GetSingleStockTemplateParam')
    def get_single_stock_template_param(
        self,
        request: GetSingleStockTemplateRequestDto | Mapping[str, Any],
    ) -> ResponseDto[Any]:
        return self._call('POST', '/api/StockParamResult/GetSingleStockTemplateParam', json_body=request)

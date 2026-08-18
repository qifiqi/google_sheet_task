"""Generated endpoint wrappers for one Swagger controller."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..http_client import ApiGroup
from ..models import GetStockParamTemplateListRequestDto, IdRequestDto, t_stock_param_template
from ..response import ResponseDto
from ._metadata import endpoint

class StockparamtemplateApi(ApiGroup):
    @endpoint('POST', '/api/StockParamTemplate/Delete')
    def delete(
        self,
        request: IdRequestDto | Mapping[str, Any],
    ) -> ResponseDto[Any]:
        return self._call('POST', '/api/StockParamTemplate/Delete', json_body=request)

    @endpoint('POST', '/api/StockParamTemplate/GetDataByPageList')
    def get_data_by_page_list(
        self,
        request: GetStockParamTemplateListRequestDto | Mapping[str, Any],
    ) -> ResponseDto[Any]:
        return self._call('POST', '/api/StockParamTemplate/GetDataByPageList', json_body=request)

    @endpoint('POST', '/api/StockParamTemplate/GetInfoById')
    def get_info_by_id(
        self,
        request: IdRequestDto | Mapping[str, Any],
    ) -> ResponseDto[Any]:
        return self._call('POST', '/api/StockParamTemplate/GetInfoById', json_body=request)

    @endpoint('POST', '/api/StockParamTemplate/GetListForSelect')
    def get_list_for_select(self) -> ResponseDto[Any]:
        return self._call('POST', '/api/StockParamTemplate/GetListForSelect')

    @endpoint('POST', '/api/StockParamTemplate/ModifyOrAdd')
    def modify_or_add(
        self,
        request: t_stock_param_template | Mapping[str, Any],
    ) -> ResponseDto[Any]:
        return self._call('POST', '/api/StockParamTemplate/ModifyOrAdd', json_body=request)

"""Generated endpoint wrappers for one Swagger controller."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..http_client import ApiGroup
from ..models import GetDataConceptListRequestDto, IdRequestDto, t_stock_data_concept
from ..response import ResponseDto
from ._metadata import endpoint

class StockdataconceptApi(ApiGroup):
    @endpoint('POST', '/api/StockDataConcept/Delete')
    def delete(
        self,
        request: IdRequestDto | Mapping[str, Any],
    ) -> ResponseDto[Any]:
        return self._call('POST', '/api/StockDataConcept/Delete', json_body=request)

    @endpoint('POST', '/api/StockDataConcept/GetById')
    def get_by_id(
        self,
        request: IdRequestDto | Mapping[str, Any],
    ) -> ResponseDto[Any]:
        return self._call('POST', '/api/StockDataConcept/GetById', json_body=request)

    @endpoint('POST', '/api/StockDataConcept/GetDataByPageList')
    def get_data_by_page_list(
        self,
        request: GetDataConceptListRequestDto | Mapping[str, Any],
    ) -> ResponseDto[Any]:
        return self._call('POST', '/api/StockDataConcept/GetDataByPageList', json_body=request)

    @endpoint('POST', '/api/StockDataConcept/ModifyOrAdd')
    def modify_or_add(
        self,
        request: t_stock_data_concept | Mapping[str, Any],
    ) -> ResponseDto[Any]:
        return self._call('POST', '/api/StockDataConcept/ModifyOrAdd', json_body=request)

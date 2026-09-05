"""Generated endpoint wrappers for one Swagger controller."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..http_client import ApiGroup
from ..models import GetStockFinancialDataRequestDto, IdRequestDto, t_stock_financial_data
from ..response import ResponseDto
from ._metadata import endpoint

class StockfinancialdataApi(ApiGroup):
    @endpoint('POST', '/api/StockFinancialData/Delete')
    def delete(
        self,
        request: IdRequestDto | Mapping[str, Any],
    ) -> ResponseDto[Any]:
        return self._call('POST', '/api/StockFinancialData/Delete', json_body=request)

    @endpoint('POST', '/api/StockFinancialData/GetById')
    def get_by_id(
        self,
        request: IdRequestDto | Mapping[str, Any],
    ) -> ResponseDto[Any]:
        return self._call('POST', '/api/StockFinancialData/GetById', json_body=request)

    @endpoint('POST', '/api/StockFinancialData/GetDataByPageList')
    def get_data_by_page_list(
        self,
        request: GetStockFinancialDataRequestDto | Mapping[str, Any],
    ) -> ResponseDto[Any]:
        return self._call('POST', '/api/StockFinancialData/GetDataByPageList', json_body=request)

    @endpoint('POST', '/api/StockFinancialData/ModifyOrAdd')
    def modify_or_add(
        self,
        request: t_stock_financial_data | Mapping[str, Any],
    ) -> ResponseDto[Any]:
        return self._call('POST', '/api/StockFinancialData/ModifyOrAdd', json_body=request)

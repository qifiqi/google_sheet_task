"""Generated endpoint wrappers for one Swagger controller."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..http_client import ApiGroup
from ..models import GetStockXtCreditDetailListRequestDto, IdRequestDto, t_stock_xt_credit_detail
from ..response import ResponseDto
from ._metadata import endpoint

class StockxtcreditdetailApi(ApiGroup):
    @endpoint('POST', '/api/StockXtCreditDetail/Delete')
    def delete(
        self,
        request: IdRequestDto | Mapping[str, Any],
    ) -> ResponseDto[Any]:
        return self._call('POST', '/api/StockXtCreditDetail/Delete', json_body=request)

    @endpoint('POST', '/api/StockXtCreditDetail/GetDataByPageList')
    def get_data_by_page_list(
        self,
        request: GetStockXtCreditDetailListRequestDto | Mapping[str, Any],
    ) -> ResponseDto[Any]:
        return self._call('POST', '/api/StockXtCreditDetail/GetDataByPageList', json_body=request)

    @endpoint('POST', '/api/StockXtCreditDetail/GetInfoById')
    def get_info_by_id(
        self,
        request: IdRequestDto | Mapping[str, Any],
    ) -> ResponseDto[Any]:
        return self._call('POST', '/api/StockXtCreditDetail/GetInfoById', json_body=request)

    @endpoint('POST', '/api/StockXtCreditDetail/ModifyOrAdd')
    def modify_or_add(
        self,
        request: t_stock_xt_credit_detail | Mapping[str, Any],
    ) -> ResponseDto[Any]:
        return self._call('POST', '/api/StockXtCreditDetail/ModifyOrAdd', json_body=request)

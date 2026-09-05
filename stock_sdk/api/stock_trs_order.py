"""Generated endpoint wrappers for one Swagger controller."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..http_client import ApiGroup
from ..models import GetStockTrsOrderListRequestDto, GetStockTrsOrderStatusRequestDto, IdRequestDto, t_stock_trs_order
from ..response import ResponseDto
from ._metadata import endpoint

class StocktrsorderApi(ApiGroup):
    @endpoint('POST', '/api/StockTrsOrder/CancelOrderId')
    def cancel_order_id(
        self,
        request: IdRequestDto | Mapping[str, Any],
    ) -> ResponseDto[Any]:
        return self._call('POST', '/api/StockTrsOrder/CancelOrderId', json_body=request)

    @endpoint('POST', '/api/StockTrsOrder/Delete')
    def delete(
        self,
        request: IdRequestDto | Mapping[str, Any],
    ) -> ResponseDto[Any]:
        return self._call('POST', '/api/StockTrsOrder/Delete', json_body=request)

    @endpoint('POST', '/api/StockTrsOrder/GetDataByPageList')
    def get_data_by_page_list(
        self,
        request: GetStockTrsOrderListRequestDto | Mapping[str, Any],
    ) -> ResponseDto[Any]:
        return self._call('POST', '/api/StockTrsOrder/GetDataByPageList', json_body=request)

    @endpoint('POST', '/api/StockTrsOrder/GetInfoById')
    def get_info_by_id(
        self,
        request: IdRequestDto | Mapping[str, Any],
    ) -> ResponseDto[Any]:
        return self._call('POST', '/api/StockTrsOrder/GetInfoById', json_body=request)

    @endpoint('POST', '/api/StockTrsOrder/ModifyOrAdd')
    def modify_or_add(
        self,
        request: t_stock_trs_order | Mapping[str, Any],
    ) -> ResponseDto[Any]:
        return self._call('POST', '/api/StockTrsOrder/ModifyOrAdd', json_body=request)

    @endpoint('POST', '/api/StockTrsOrder/ModifyStatusById')
    def modify_status_by_id(
        self,
        request: GetStockTrsOrderStatusRequestDto | Mapping[str, Any],
    ) -> ResponseDto[Any]:
        return self._call('POST', '/api/StockTrsOrder/ModifyStatusById', json_body=request)

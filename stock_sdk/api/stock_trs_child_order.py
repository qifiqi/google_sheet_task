"""Generated endpoint wrappers for one Swagger controller."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..http_client import ApiGroup
from ..models import GetStockTrsChildOrderListRequestDto, IdRequestDto, t_stock_trs_child_orders
from ..response import ResponseDto
from ._metadata import endpoint

class StocktrschildorderApi(ApiGroup):
    @endpoint('POST', '/api/StockTrsChildOrder/Delete')
    def delete(
        self,
        request: IdRequestDto | Mapping[str, Any],
    ) -> ResponseDto[Any]:
        return self._call('POST', '/api/StockTrsChildOrder/Delete', json_body=request)

    @endpoint('POST', '/api/StockTrsChildOrder/GetDataByPageList')
    def get_data_by_page_list(
        self,
        request: GetStockTrsChildOrderListRequestDto | Mapping[str, Any],
    ) -> ResponseDto[Any]:
        return self._call('POST', '/api/StockTrsChildOrder/GetDataByPageList', json_body=request)

    @endpoint('POST', '/api/StockTrsChildOrder/GetDataBySummaryList')
    def get_data_by_summary_list(
        self,
        request: GetStockTrsChildOrderListRequestDto | Mapping[str, Any],
    ) -> ResponseDto[Any]:
        return self._call('POST', '/api/StockTrsChildOrder/GetDataBySummaryList', json_body=request)

    @endpoint('POST', '/api/StockTrsChildOrder/GetInfoById')
    def get_info_by_id(
        self,
        request: IdRequestDto | Mapping[str, Any],
    ) -> ResponseDto[Any]:
        return self._call('POST', '/api/StockTrsChildOrder/GetInfoById', json_body=request)

    @endpoint('POST', '/api/StockTrsChildOrder/ModifyOrAdd')
    def modify_or_add(
        self,
        request: t_stock_trs_child_orders | Mapping[str, Any],
    ) -> ResponseDto[Any]:
        return self._call('POST', '/api/StockTrsChildOrder/ModifyOrAdd', json_body=request)

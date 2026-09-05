"""Generated endpoint wrappers for one Swagger controller."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..http_client import ApiGroup
from ..models import GetStockXtDataTradingListRequestDto, IdRequestDto, t_stock_xt_data_trading
from ..response import ResponseDto
from ._metadata import endpoint

class StockxtdatatradingApi(ApiGroup):
    @endpoint('POST', '/api/StockXtDataTrading/Add')
    def add(
        self,
        request: t_stock_xt_data_trading | Mapping[str, Any],
    ) -> ResponseDto[Any]:
        return self._call('POST', '/api/StockXtDataTrading/Add', json_body=request)

    @endpoint('POST', '/api/StockXtDataTrading/Delete')
    def delete(
        self,
        request: IdRequestDto | Mapping[str, Any],
    ) -> ResponseDto[Any]:
        return self._call('POST', '/api/StockXtDataTrading/Delete', json_body=request)

    @endpoint('POST', '/api/StockXtDataTrading/GetDataByPageList')
    def get_data_by_page_list(
        self,
        request: GetStockXtDataTradingListRequestDto | Mapping[str, Any],
    ) -> ResponseDto[Any]:
        return self._call('POST', '/api/StockXtDataTrading/GetDataByPageList', json_body=request)

    @endpoint('POST', '/api/StockXtDataTrading/GetInfoById')
    def get_info_by_id(
        self,
        request: IdRequestDto | Mapping[str, Any],
    ) -> ResponseDto[Any]:
        return self._call('POST', '/api/StockXtDataTrading/GetInfoById', json_body=request)

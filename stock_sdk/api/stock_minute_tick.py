"""Generated endpoint wrappers for one Swagger controller."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..http_client import ApiGroup
from ..models import GetStockMinuteTickListRequestDto, LongIdRequestDto, t_stock_minute_tick
from ..response import ResponseDto
from ._metadata import endpoint

class StockminutetickApi(ApiGroup):
    @endpoint('POST', '/api/StockMinuteTick/Delete')
    def delete(
        self,
        request: LongIdRequestDto | Mapping[str, Any],
    ) -> ResponseDto[Any]:
        return self._call('POST', '/api/StockMinuteTick/Delete', json_body=request)

    @endpoint('POST', '/api/StockMinuteTick/GetDataByPageList')
    def get_data_by_page_list(
        self,
        request: GetStockMinuteTickListRequestDto | Mapping[str, Any],
    ) -> ResponseDto[Any]:
        return self._call('POST', '/api/StockMinuteTick/GetDataByPageList', json_body=request)

    @endpoint('POST', '/api/StockMinuteTick/GetInfoById')
    def get_info_by_id(
        self,
        request: LongIdRequestDto | Mapping[str, Any],
    ) -> ResponseDto[Any]:
        return self._call('POST', '/api/StockMinuteTick/GetInfoById', json_body=request)

    @endpoint('POST', '/api/StockMinuteTick/ModifyOrAdd')
    def modify_or_add(
        self,
        request: t_stock_minute_tick | Mapping[str, Any],
    ) -> ResponseDto[Any]:
        return self._call('POST', '/api/StockMinuteTick/ModifyOrAdd', json_body=request)

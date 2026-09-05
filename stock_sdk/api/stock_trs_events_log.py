"""Generated endpoint wrappers for one Swagger controller."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..http_client import ApiGroup
from ..models import GetStockTrsEventsLogListRequestDto, IdRequestDto, t_stock_trs_events_log
from ..response import ResponseDto
from ._metadata import endpoint

class StocktrseventslogApi(ApiGroup):
    @endpoint('POST', '/api/StockTrsEventsLog/GetDataByPageList')
    def get_data_by_page_list(
        self,
        request: GetStockTrsEventsLogListRequestDto | Mapping[str, Any],
    ) -> ResponseDto[Any]:
        return self._call('POST', '/api/StockTrsEventsLog/GetDataByPageList', json_body=request)

    @endpoint('POST', '/api/StockTrsEventsLog/GetInfoById')
    def get_info_by_id(
        self,
        request: IdRequestDto | Mapping[str, Any],
    ) -> ResponseDto[Any]:
        return self._call('POST', '/api/StockTrsEventsLog/GetInfoById', json_body=request)

    @endpoint('POST', '/api/StockTrsEventsLog/ModifyOrAdd')
    def modify_or_add(
        self,
        request: t_stock_trs_events_log | Mapping[str, Any],
    ) -> ResponseDto[Any]:
        return self._call('POST', '/api/StockTrsEventsLog/ModifyOrAdd', json_body=request)

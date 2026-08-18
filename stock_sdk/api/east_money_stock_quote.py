"""Generated endpoint wrappers for one Swagger controller."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..http_client import ApiGroup
from ..models import GetEastMoneyStockQuoteRequestDto, GetEastMoneyStockTrendsRequestDto
from ..response import ResponseDto
from ._metadata import endpoint

class EastmoneystockquoteApi(ApiGroup):
    @endpoint('POST', '/api/EastMoneyStockQuote/GetStockQuote')
    def get_stock_quote(
        self,
        request: GetEastMoneyStockQuoteRequestDto | Mapping[str, Any],
    ) -> ResponseDto[Any]:
        return self._call('POST', '/api/EastMoneyStockQuote/GetStockQuote', json_body=request)

    @endpoint('POST', '/api/EastMoneyStockQuote/GetStockTrends')
    def get_stock_trends(
        self,
        request: GetEastMoneyStockTrendsRequestDto | Mapping[str, Any],
    ) -> ResponseDto[Any]:
        return self._call('POST', '/api/EastMoneyStockQuote/GetStockTrends', json_body=request)

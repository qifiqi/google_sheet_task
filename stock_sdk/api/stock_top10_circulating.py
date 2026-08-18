"""Generated endpoint wrappers for one Swagger controller."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..http_client import ApiGroup
from ..models import GetStockTop10CirculatingListRequestDto, IdRequestDto, t_stock_top10_circulating
from ..response import ResponseDto
from ._metadata import endpoint

class Stocktop10circulatingApi(ApiGroup):
    @endpoint('POST', '/api/StockTop10Circulating/AddOrModify')
    def add_or_modify(
        self,
        request: t_stock_top10_circulating | Mapping[str, Any],
    ) -> ResponseDto[Any]:
        return self._call('POST', '/api/StockTop10Circulating/AddOrModify', json_body=request)

    @endpoint('POST', '/api/StockTop10Circulating/Delete')
    def delete(
        self,
        request: IdRequestDto | Mapping[str, Any],
    ) -> ResponseDto[Any]:
        return self._call('POST', '/api/StockTop10Circulating/Delete', json_body=request)

    @endpoint('POST', '/api/StockTop10Circulating/GetDataByPageList')
    def get_data_by_page_list(
        self,
        request: GetStockTop10CirculatingListRequestDto | Mapping[str, Any],
    ) -> ResponseDto[Any]:
        return self._call('POST', '/api/StockTop10Circulating/GetDataByPageList', json_body=request)

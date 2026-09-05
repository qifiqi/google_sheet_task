"""Generated endpoint wrappers for one Swagger controller."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..http_client import ApiGroup
from ..models import GetStockTrsPositionSnapshottRequestDto, IdRequestDto, t_stock_trs_position_snapshot
from ..response import ResponseDto
from ._metadata import endpoint

class StocktrspositionsnapshotApi(ApiGroup):
    @endpoint('POST', '/api/StockTrsPositionSnapshot/Delete')
    def delete(
        self,
        request: IdRequestDto | Mapping[str, Any],
    ) -> ResponseDto[Any]:
        return self._call('POST', '/api/StockTrsPositionSnapshot/Delete', json_body=request)

    @endpoint('POST', '/api/StockTrsPositionSnapshot/GetDataByPageList')
    def get_data_by_page_list(
        self,
        request: GetStockTrsPositionSnapshottRequestDto | Mapping[str, Any],
    ) -> ResponseDto[Any]:
        return self._call('POST', '/api/StockTrsPositionSnapshot/GetDataByPageList', json_body=request)

    @endpoint('POST', '/api/StockTrsPositionSnapshot/GetInfoById')
    def get_info_by_id(
        self,
        request: IdRequestDto | Mapping[str, Any],
    ) -> ResponseDto[Any]:
        return self._call('POST', '/api/StockTrsPositionSnapshot/GetInfoById', json_body=request)

    @endpoint('POST', '/api/StockTrsPositionSnapshot/ModifyOrAdd')
    def modify_or_add(
        self,
        request: t_stock_trs_position_snapshot | Mapping[str, Any],
    ) -> ResponseDto[Any]:
        return self._call('POST', '/api/StockTrsPositionSnapshot/ModifyOrAdd', json_body=request)

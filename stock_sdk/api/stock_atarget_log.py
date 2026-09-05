"""Generated endpoint wrappers for one Swagger controller."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..http_client import ApiGroup
from ..models import GetStockATargetLogListRequestDto, IdRequestDto, t_stock_a_target_log
from ..response import ResponseDto
from ._metadata import endpoint

class StockatargetlogApi(ApiGroup):
    @endpoint('POST', '/api/StockATargetLog/Delete')
    def delete(
        self,
        request: IdRequestDto | Mapping[str, Any],
    ) -> ResponseDto[Any]:
        return self._call('POST', '/api/StockATargetLog/Delete', json_body=request)

    @endpoint('POST', '/api/StockATargetLog/GetDataByPageList')
    def get_data_by_page_list(
        self,
        request: GetStockATargetLogListRequestDto | Mapping[str, Any],
    ) -> ResponseDto[Any]:
        return self._call('POST', '/api/StockATargetLog/GetDataByPageList', json_body=request)

    @endpoint('POST', '/api/StockATargetLog/GetInfoById')
    def get_info_by_id(
        self,
        request: IdRequestDto | Mapping[str, Any],
    ) -> ResponseDto[Any]:
        return self._call('POST', '/api/StockATargetLog/GetInfoById', json_body=request)

    @endpoint('POST', '/api/StockATargetLog/ModifyOrAdd')
    def modify_or_add(
        self,
        request: t_stock_a_target_log | Mapping[str, Any],
    ) -> ResponseDto[Any]:
        return self._call('POST', '/api/StockATargetLog/ModifyOrAdd', json_body=request)

"""Generated endpoint wrappers for one Swagger controller."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..http_client import ApiGroup
from ..models import GetStockTrsDealRecordsListRequestDto, IdRequestDto, t_stock_trs_deal_records
from ..response import ResponseDto
from ._metadata import endpoint

class StocktrsdealrecordsApi(ApiGroup):
    @endpoint('POST', '/api/StockTrsDealRecords/Delete')
    def delete(
        self,
        request: IdRequestDto | Mapping[str, Any],
    ) -> ResponseDto[Any]:
        return self._call('POST', '/api/StockTrsDealRecords/Delete', json_body=request)

    @endpoint('POST', '/api/StockTrsDealRecords/GetDataByPageList')
    def get_data_by_page_list(
        self,
        request: GetStockTrsDealRecordsListRequestDto | Mapping[str, Any],
    ) -> ResponseDto[Any]:
        return self._call('POST', '/api/StockTrsDealRecords/GetDataByPageList', json_body=request)

    @endpoint('POST', '/api/StockTrsDealRecords/GetInfoById')
    def get_info_by_id(
        self,
        request: IdRequestDto | Mapping[str, Any],
    ) -> ResponseDto[Any]:
        return self._call('POST', '/api/StockTrsDealRecords/GetInfoById', json_body=request)

    @endpoint('POST', '/api/StockTrsDealRecords/ModifyOrAdd')
    def modify_or_add(
        self,
        request: t_stock_trs_deal_records | Mapping[str, Any],
    ) -> ResponseDto[Any]:
        return self._call('POST', '/api/StockTrsDealRecords/ModifyOrAdd', json_body=request)

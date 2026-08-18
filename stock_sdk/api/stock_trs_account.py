"""Generated endpoint wrappers for one Swagger controller."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..http_client import ApiGroup
from ..models import IdRequestDto, t_stock_trs_account
from ..response import ResponseDto
from ._metadata import endpoint

class StocktrsaccountApi(ApiGroup):
    @endpoint('POST', '/api/StockTrsAccount/GetDataByPageList')
    def get_data_by_page_list(self) -> ResponseDto[Any]:
        return self._call('POST', '/api/StockTrsAccount/GetDataByPageList')

    @endpoint('POST', '/api/StockTrsAccount/GetInfoById')
    def get_info_by_id(
        self,
        request: IdRequestDto | Mapping[str, Any],
    ) -> ResponseDto[Any]:
        return self._call('POST', '/api/StockTrsAccount/GetInfoById', json_body=request)

    @endpoint('POST', '/api/StockTrsAccount/ModifyOrAdd')
    def modify_or_add(
        self,
        request: t_stock_trs_account | Mapping[str, Any],
    ) -> ResponseDto[Any]:
        return self._call('POST', '/api/StockTrsAccount/ModifyOrAdd', json_body=request)

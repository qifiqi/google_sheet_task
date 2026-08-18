"""Generated endpoint wrappers for one Swagger controller."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..http_client import ApiGroup
from ..models import GetDataStateListRequestDto, GetStockXtDataListRequestDto, IdRequestDto, UpdateStateRequestDto, UpdateUserRequestDto, t_stock_xt_data
from ..response import ResponseDto
from ._metadata import endpoint

class StockxtdataApi(ApiGroup):
    @endpoint('POST', '/api/StockXtData/Add')
    def add(
        self,
        request: t_stock_xt_data | Mapping[str, Any],
    ) -> ResponseDto[Any]:
        return self._call('POST', '/api/StockXtData/Add', json_body=request)

    @endpoint('POST', '/api/StockXtData/Delete')
    def delete(
        self,
        request: IdRequestDto | Mapping[str, Any],
    ) -> ResponseDto[Any]:
        return self._call('POST', '/api/StockXtData/Delete', json_body=request)

    @endpoint('POST', '/api/StockXtData/GetDataByPageList')
    def get_data_by_page_list(
        self,
        request: GetStockXtDataListRequestDto | Mapping[str, Any],
    ) -> ResponseDto[Any]:
        return self._call('POST', '/api/StockXtData/GetDataByPageList', json_body=request)

    @endpoint('POST', '/api/StockXtData/GetDataStateList')
    def get_data_state_list(
        self,
        request: GetDataStateListRequestDto | Mapping[str, Any],
    ) -> ResponseDto[Any]:
        return self._call('POST', '/api/StockXtData/GetDataStateList', json_body=request)

    @endpoint('POST', '/api/StockXtData/GetInfoById')
    def get_info_by_id(
        self,
        request: IdRequestDto | Mapping[str, Any],
    ) -> ResponseDto[Any]:
        return self._call('POST', '/api/StockXtData/GetInfoById', json_body=request)

    @endpoint('POST', '/api/StockXtData/UpdateState')
    def update_state(
        self,
        request: UpdateStateRequestDto | Mapping[str, Any],
    ) -> ResponseDto[Any]:
        return self._call('POST', '/api/StockXtData/UpdateState', json_body=request)

    @endpoint('POST', '/api/StockXtData/UpdateUser')
    def update_user(
        self,
        request: UpdateUserRequestDto | Mapping[str, Any],
    ) -> ResponseDto[Any]:
        return self._call('POST', '/api/StockXtData/UpdateUser', json_body=request)
